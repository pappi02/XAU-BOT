"""Phase 6 tests: an order path that is safe when the network is not.

The failure these guard against is the expensive one: a retry that opens a
second position because the first one's outcome was unknown.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import fake_config, fake_mt5, fake_risk_manager, make_executor

from execution.trade_executor import (
    BrokerQueryFailed,
    RETRYABLE_RETCODES,
    TradeExecutor,
)


def result(retcode, volume=0.1, price=2000.50, order=1, comment=""):
    return MagicMock(retcode=retcode, volume=volume, price=price,
                     order=order, comment=comment)


class TestNoMockFallback(unittest.TestCase):
    """6.3 (M-05): a fake broker must not be reachable from production."""

    def test_missing_broker_raises(self):
        with self.assertRaises(ValueError) as ctx:
            TradeExecutor(None, fake_config(), fake_risk_manager())
        self.assertIn("mt5_module", str(ctx.exception))

    def test_missing_config_raises(self):
        with self.assertRaises(ValueError):
            TradeExecutor(fake_mt5(), None, fake_risk_manager())

    def test_missing_risk_manager_raises(self):
        with self.assertRaises(ValueError):
            TradeExecutor(fake_mt5(), fake_config(), None)

    def test_all_missing_raises_naming_all_three(self):
        with self.assertRaises(ValueError) as ctx:
            TradeExecutor(None, None, None)
        message = str(ctx.exception)
        for name in ("mt5_module", "config", "risk_manager"):
            self.assertIn(name, message)

    def test_the_old_no_arg_construction_is_gone(self):
        # It used to build a broker whose order_send always returned DONE.
        with self.assertRaises(TypeError):
            TradeExecutor()


class TestPositionQueryIsUnambiguous(unittest.TestCase):
    """6.4 (H-04): 'no positions' and 'I could not ask' are different answers."""

    def setUp(self):
        self.ex = make_executor()

    def test_empty_list_when_genuinely_flat(self):
        self.ex.mt5.positions_get.return_value = ()
        self.ex.mt5.terminal_info.return_value = MagicMock(connected=True)
        self.assertEqual(self.ex.get_open_positions("XAUUSDm"), [])

    def test_none_while_connected_is_genuinely_flat(self):
        self.ex.mt5.positions_get.return_value = None
        self.ex.mt5.terminal_info.return_value = MagicMock(connected=True)
        self.assertEqual(self.ex.get_open_positions("XAUUSDm"), [])

    def test_none_while_disconnected_raises(self):
        # THE BUG: this used to return [] -- the bot concluded it held nothing
        # and would happily open another position on top of the ones it could
        # not see.
        self.ex.mt5.positions_get.return_value = None
        self.ex.mt5.terminal_info.return_value = MagicMock(connected=False)
        with self.assertRaises(BrokerQueryFailed):
            self.ex.get_open_positions("XAUUSDm")

    def test_terminal_info_none_means_disconnected(self):
        self.ex.mt5.positions_get.return_value = None
        self.ex.mt5.terminal_info.return_value = None
        with self.assertRaises(BrokerQueryFailed):
            self.ex.get_open_positions("XAUUSDm")

    def test_exception_raises_rather_than_reporting_flat(self):
        self.ex.mt5.positions_get.side_effect = RuntimeError("pipe closed")
        with self.assertRaises(BrokerQueryFailed):
            self.ex.get_open_positions("XAUUSDm")

    def test_or_none_variant_returns_none_for_read_only_callers(self):
        self.ex.mt5.positions_get.side_effect = RuntimeError("pipe closed")
        self.assertIsNone(self.ex.get_open_positions_or_none("XAUUSDm"))

    def test_entry_is_blocked_when_position_state_is_unknown(self):
        self.ex.mt5.positions_get.side_effect = RuntimeError("pipe closed")
        with self.assertRaises(Exception):
            self.ex.enter_trade("XAUUSDm", "BUY", 2000.0, 1990.0, 2020.0)


class TestIdempotentRetries(unittest.TestCase):
    """6.1 (H-02): never resend an order whose outcome is unknown."""

    def setUp(self):
        self.ex = make_executor()
        self.ex.mt5.positions_get.return_value = []
        self.ex.mt5.history_orders_get.return_value = []

    def _place(self):
        return self.ex._place_market_order("XAUUSDm", True, 0.1, 1990.0, 2020.0)

    def test_success_first_time_sends_once(self):
        self.ex.mt5.order_send.return_value = result(10009)
        self._place()
        self.assertEqual(self.ex.mt5.order_send.call_count, 1)

    def test_requote_is_retried(self):
        self.ex.mt5.order_send.side_effect = [result(10004), result(10009)]
        self._place()
        self.assertEqual(self.ex.mt5.order_send.call_count, 2)

    def test_hard_rejection_is_not_retried(self):
        # 10019 = NO_MONEY. Resending cannot help and wastes the window.
        self.ex.mt5.order_send.return_value = result(10019)
        with self.assertRaises(RuntimeError):
            self._place()
        self.assertEqual(self.ex.mt5.order_send.call_count, 1)

    def test_invalid_stops_is_not_retried(self):
        self.ex.mt5.order_send.return_value = result(10016)
        with self.assertRaises(RuntimeError):
            self._place()
        self.assertEqual(self.ex.mt5.order_send.call_count, 1)

    def test_none_result_is_never_retried(self):
        # THE H-02 CORE. A None result means the outcome is UNKNOWN. The old
        # loop resent regardless -- the one case where resending can double
        # your position size.
        self.ex.mt5.order_send.return_value = None
        with self.assertRaises(RuntimeError):
            self._place()
        self.assertEqual(self.ex.mt5.order_send.call_count, 1)

    def test_none_result_reconciles_by_token_instead_of_resending(self):
        sent = {}

        def capture(req):
            sent["comment"] = req["comment"]
            return None

        self.ex.mt5.order_send.side_effect = capture
        # The order actually landed; it shows up as an open position.
        def positions(symbol=None):
            if "comment" in sent:
                return [MagicMock(ticket=77, comment=sent["comment"])]
            return []
        self.ex.mt5.positions_get.side_effect = positions

        found = self._place()
        self.assertEqual(found.ticket, 77)
        self.assertEqual(self.ex.mt5.order_send.call_count, 1)

    def test_retry_aborts_if_the_first_attempt_already_executed(self):
        sent = {}

        def capture(req):
            sent["comment"] = req["comment"]
            return result(10004)            # requote: retryable

        self.ex.mt5.order_send.side_effect = capture

        calls = {"n": 0}

        def positions(symbol=None):
            calls["n"] += 1
            # First call (pre-retry check) finds the filled position.
            if calls["n"] > 0 and "comment" in sent:
                return [MagicMock(ticket=99, comment=sent["comment"])]
            return []

        self.ex.mt5.positions_get.side_effect = positions
        found = self._place()
        self.assertEqual(found.ticket, 99)
        self.assertEqual(self.ex.mt5.order_send.call_count, 1,
                         "resent an order that had already executed")

    def test_each_attempt_carries_a_unique_token(self):
        tokens = []
        self.ex.mt5.order_send.side_effect = lambda r: (
            tokens.append(r["comment"]) or result(10009))
        self._place()
        self._place()
        self.assertEqual(len(set(tokens)), 2)
        for token in tokens:
            self.assertTrue(token.startswith("XAU-"))
            self.assertLessEqual(len(token), 31, "MT5 truncates past 31 chars")

    def test_price_is_refreshed_before_a_retry(self):
        prices = []
        self.ex.mt5.order_send.side_effect = lambda r: (
            prices.append(r["price"]) or
            (result(10004) if len(prices) == 1 else result(10009)))
        ticks = [MagicMock(bid=2000.40, ask=2000.50),
                 MagicMock(bid=2010.40, ask=2010.50)]
        self.ex.mt5.symbol_info_tick.side_effect = lambda s: ticks[
            min(len(prices), len(ticks) - 1)]
        self._place()
        self.assertEqual(len(prices), 2)
        self.assertNotEqual(prices[0], prices[1],
                            "retry reused a stale price")

    def test_retryable_set_excludes_unknown_and_hard_failures(self):
        self.assertIn(10004, RETRYABLE_RETCODES)     # requote
        self.assertIn(10021, RETRYABLE_RETCODES)     # price off
        for code in (10006, 10016, 10018, 10019, 10027, 10030):
            self.assertNotIn(code, RETRYABLE_RETCODES)


class TestPartialFills(unittest.TestCase):
    """6.2: result.volume was never compared to the requested volume."""

    def setUp(self):
        self.ex = make_executor()
        self.ex.mt5.positions_get.return_value = []

    def test_partial_fill_is_detected_and_reported(self):
        self.ex.mt5.order_send.return_value = result(10009, volume=0.04)
        with self.assertLogs("xau_bot", level="WARNING") as logs:
            self.ex._place_market_order("XAUUSDm", True, 0.1, 1990.0, 2020.0)
        self.assertTrue(any("PARTIAL FILL" in line for line in logs.output))

    def test_full_fill_is_not_reported_as_partial(self):
        self.ex.mt5.order_send.return_value = result(10009, volume=0.1)
        with self.assertLogs("xau_bot", level="INFO") as logs:
            self.ex._place_market_order("XAUUSDm", True, 0.1, 1990.0, 2020.0)
        self.assertFalse(any("PARTIAL FILL" in line for line in logs.output))

    def test_slippage_is_measured(self):
        self.ex.mt5.order_send.return_value = result(10009, price=2001.00)
        quality = self.ex._log_fill_quality(
            result(10009, volume=0.1, price=2001.00),
            {"volume": 0.1}, 2000.50)
        self.assertAlmostEqual(quality["slippage"], 0.50)

    def test_unknown_fill_fields_do_not_crash(self):
        quality = self.ex._log_fill_quality(
            MagicMock(volume="?", price=None), {"volume": 0.1}, 2000.50)
        self.assertIsNone(quality["filled_volume"])
        self.assertIsNone(quality["fill_price"])


if __name__ == "__main__":
    unittest.main()


class TestReconnection(unittest.TestCase):
    """6.4: no reconnection logic existed at all."""

    def setUp(self):
        import data.connect_mt5 as mod
        self.mod = mod
        self._real = mod.mt5
        mod.mt5 = MagicMock()
        mod.mt5.ACCOUNT_TRADE_MODE_DEMO = 0
        self.slept = []

    def tearDown(self):
        self.mod.mt5 = self._real

    def _sleep(self, seconds):
        self.slept.append(seconds)

    def test_already_connected_returns_immediately(self):
        self.mod.mt5.terminal_info.return_value = MagicMock(connected=True)
        self.assertTrue(self.mod.reconnect_with_backoff(1, "p", "s",
                                                        sleep=self._sleep))
        self.assertEqual(self.slept, [])

    def test_backoff_doubles_between_attempts(self):
        self.mod.mt5.terminal_info.return_value = MagicMock(connected=False)
        self.mod.mt5.initialize.return_value = False
        self.mod.reconnect_with_backoff(1, "p", "s", max_attempts=4,
                                        base_delay=2.0, sleep=self._sleep)
        self.assertEqual(self.slept, [2.0, 4.0, 8.0])

    def test_backoff_is_capped(self):
        self.mod.mt5.terminal_info.return_value = MagicMock(connected=False)
        self.mod.mt5.initialize.return_value = False
        self.mod.reconnect_with_backoff(1, "p", "s", max_attempts=8,
                                        base_delay=2.0, max_delay=10.0,
                                        sleep=self._sleep)
        self.assertTrue(all(d <= 10.0 for d in self.slept))

    def test_exhausted_attempts_report_failure(self):
        self.mod.mt5.terminal_info.return_value = MagicMock(connected=False)
        self.mod.mt5.initialize.return_value = False
        self.assertFalse(self.mod.reconnect_with_backoff(
            1, "p", "s", max_attempts=3, sleep=self._sleep))

    def test_credential_errors_are_not_retried(self):
        # Retrying a bad credential cannot help, and risks connecting to the
        # wrong account.
        self.mod.mt5.terminal_info.return_value = MagicMock(connected=False)
        with self.assertRaises(self.mod.AccountIdentityError):
            self.mod.reconnect_with_backoff(None, None, None, sleep=self._sleep)
        self.assertEqual(self.slept, [])

    def test_is_connected_handles_a_dead_terminal(self):
        self.mod.mt5.terminal_info.return_value = None
        self.assertFalse(self.mod.is_connected())
        self.mod.mt5.terminal_info.side_effect = RuntimeError("gone")
        self.assertFalse(self.mod.is_connected())

    def test_loop_checks_the_connection_before_trading(self):
        import ast, inspect, textwrap
        import main
        tree = ast.parse(textwrap.dedent(inspect.getsource(main.main_loop)))
        called = {n.func.id for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("is_connected", called)
        self.assertIn("reconnect_with_backoff", called)

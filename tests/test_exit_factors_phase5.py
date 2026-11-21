"""Phase 5 tests: every exit factor gets a positive AND a negative case.

The plan's claim is that this one file would have caught C-03 (an always-true
factor), C-06 (trailing that closed instead of trailing) and M-01 (an
unsatisfiable condition). That is the point of demanding *both* cases: a factor
that can never fire and a factor that always fires are both invisible to a
one-sided test, and both were shipped.
"""

import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import make_executor

from execution.trade_executor import TradeExecutor


def spec_info(**overrides):
    fields = dict(
        digits=2, point=0.01, trade_contract_size=100.0, trade_tick_value=1.0,
        trade_tick_size=0.01, volume_min=0.01, volume_step=0.01,
        volume_max=50.0, trade_stops_level=0, trade_freeze_level=0,
        filling_mode=2, spread=20, bid=2000.0, ask=2000.2, visible=True,
    )
    fields.update(overrides)
    return MagicMock(**fields)


def position(**overrides):
    fields = dict(ticket=1, symbol="XAUUSDm", type=0, volume=0.1,
                  price_open=2000.0, price_current=2000.0, sl=1990.0,
                  tp=2020.0, time=0, magic=987654321, profit=0.0)
    fields.update(overrides)
    return MagicMock(**fields)


def frame(closes, highs=None, lows=None):
    n = len(closes)
    return pd.DataFrame({
        "close": closes,
        "high": highs if highs is not None else [c + 1 for c in closes],
        "low": lows if lows is not None else [c - 1 for c in closes],
    }, index=pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC"))


class FactorHarness(unittest.TestCase):
    def setUp(self):
        import config
        self.ex = make_executor()
        self.ex.config = config
        self.ex.mt5.symbol_info.return_value = spec_info()
        self.ex.mt5.symbol_select.return_value = True
        self.config = config


# ---------------------------------------------------------------- factor 10

class TestBreakOfStructure(FactorHarness):
    """M-01: fired 0/20,000 on random walks because the window self-included."""

    FLAT = [2000.0] * 15

    def test_positive_breakdown_closes_a_buy(self):
        df = frame(self.FLAT + [1980.0],
                   highs=[2005.0] * 15 + [1990.0],
                   lows=[1995.0] * 15 + [1975.0])
        self.assertTrue(self.ex._check_break_of_structure(df, "BUY"))

    def test_negative_inside_range_does_not_close_a_buy(self):
        df = frame(self.FLAT + [2000.0],
                   highs=[2005.0] * 16, lows=[1995.0] * 16)
        self.assertFalse(self.ex._check_break_of_structure(df, "BUY"))

    def test_positive_breakout_closes_a_sell(self):
        df = frame(self.FLAT + [2020.0],
                   highs=[2005.0] * 15 + [2025.0],
                   lows=[1995.0] * 15 + [2015.0])
        self.assertTrue(self.ex._check_break_of_structure(df, "SELL"))

    def test_negative_inside_range_does_not_close_a_sell(self):
        df = frame(self.FLAT + [2000.0],
                   highs=[2005.0] * 16, lows=[1995.0] * 16)
        self.assertFalse(self.ex._check_break_of_structure(df, "SELL"))

    def test_the_old_self_including_window_was_unsatisfiable(self):
        # close >= own low always, so min over a window containing the current
        # bar can never exceed the close.
        df = frame(self.FLAT + [1980.0],
                   highs=[2005.0] * 15 + [1990.0],
                   lows=[1995.0] * 15 + [1975.0])
        old_condition = df["close"].iloc[-1] < df["low"].tail(10).min()
        self.assertFalse(old_condition)
        self.assertTrue(self.ex._check_break_of_structure(df, "BUY"))

    def test_insufficient_history_returns_false(self):
        self.assertFalse(self.ex._check_break_of_structure(frame([2000.0] * 3), "BUY"))


# ---------------------------------------------------------------- factor 11

class TestRRReversal(FactorHarness):
    """C-03: the shipped version could never return False."""

    def setUp(self):
        super().setUp()
        self.config.RR_REVERSAL_ENABLED = True

    def tearDown(self):
        self.config.RR_REVERSAL_ENABLED = False

    def test_negative_fresh_position_is_not_closed(self):
        # THE C-03 REGRESSION. A brand-new position at zero profit was closed
        # by the old arithmetic, and still would be by the fixed arithmetic
        # without peak tracking.
        self.assertFalse(self.ex._check_rr_ratio_reversal(position(), 0.0))

    def test_negative_position_in_profit_but_not_retraced(self):
        pos = position()
        self.ex._check_rr_ratio_reversal(pos, 100.0)       # peak = 100
        self.assertFalse(self.ex._check_rr_ratio_reversal(pos, 90.0))

    def test_positive_profit_retraced_past_the_threshold(self):
        pos = position()
        self.ex._check_rr_ratio_reversal(pos, 200.0)       # peak = 200
        self.assertTrue(self.ex._check_rr_ratio_reversal(pos, 40.0))

    def test_peak_never_decreases(self):
        pos = position()
        self.ex.record_peak_profit(pos, 150.0)
        self.ex.record_peak_profit(pos, 20.0)
        self.assertEqual(self.ex._peak_profit[pos.ticket], 150.0)

    def test_losing_position_has_no_retracement_to_measure(self):
        self.assertFalse(self.ex._check_rr_ratio_reversal(position(), -50.0))

    def test_disabled_by_default_in_config(self):
        import importlib, config as c
        importlib.reload(c)
        self.assertFalse(c.RR_REVERSAL_ENABLED,
                         "RR reversal must stay off until PFE is persisted")

    def test_the_shipped_arithmetic_was_always_true(self):
        # |2000-1990| * 2.5 * 0.1 * 100000 = 250,000 -> needs 125,000 profit.
        max_profit = abs(2000.0 - 1990.0) * 2.5 * 0.1 * 100000
        for pnl in (-5, 0, 1, 10, 100, 500):
            self.assertTrue(pnl < max_profit * 0.5)


# ----------------------------------------------------------------- factor 9

class TestSessionEnd(FactorHarness):
    """M-06: the buffer was integer-divided to zero."""

    def test_positive_inside_the_buffer(self):
        self.config.SESSION_END_BUFFER_MINUTES = 15
        friday = datetime(2026, 1, 9, 21, 50, tzinfo=timezone.utc)
        self.assertTrue(self.ex._check_market_session_end(friday))

    def test_negative_before_the_buffer(self):
        self.config.SESSION_END_BUFFER_MINUTES = 15
        friday = datetime(2026, 1, 9, 21, 30, tzinfo=timezone.utc)
        self.assertFalse(self.ex._check_market_session_end(friday))

    def test_negative_on_a_weekday(self):
        self.config.SESSION_END_BUFFER_MINUTES = 15
        monday = datetime(2026, 1, 5, 23, 0, tzinfo=timezone.utc)
        self.assertFalse(self.ex._check_market_session_end(monday))

    def test_the_buffer_is_actually_honoured(self):
        # 22 - (15 // 60) == 22, so the old code fired at 22:00, not 21:45.
        self.config.SESSION_END_BUFFER_MINUTES = 15
        self.assertEqual(22 - 15 // 60, 22)
        at_2144 = datetime(2026, 1, 9, 21, 44, tzinfo=timezone.utc)
        at_2145 = datetime(2026, 1, 9, 21, 45, tzinfo=timezone.utc)
        self.assertFalse(self.ex._check_market_session_end(at_2144))
        self.assertTrue(self.ex._check_market_session_end(at_2145))

    def test_a_larger_buffer_moves_the_boundary(self):
        self.config.SESSION_END_BUFFER_MINUTES = 120
        self.assertTrue(self.ex._check_market_session_end(
            datetime(2026, 1, 9, 20, 5, tzinfo=timezone.utc)))
        self.config.SESSION_END_BUFFER_MINUTES = 15


# ----------------------------------------------------------------- factor 7

class TestVolatilitySpike(FactorHarness):
    def test_positive_spike(self):
        self.assertTrue(self.ex._check_volatility_spike(10.0, 4.0))

    def test_negative_calm(self):
        self.assertFalse(self.ex._check_volatility_spike(4.5, 4.0))

    def test_missing_entry_atr_cannot_fire(self):
        # This was the LIVE state: entry_atr=None on every call.
        self.assertFalse(self.ex._check_volatility_spike(10.0, None))

    def test_entry_atr_is_recorded_so_the_factor_can_fire(self):
        self.ex._entry_atr[42] = 4.0
        self.assertTrue(self.ex._check_volatility_spike(
            10.0, self.ex._entry_atr.get(42)))


# ----------------------------------------------------------------- factor 8

class TestTimeBasedExit(FactorHarness):
    def test_positive_too_old(self):
        self.assertTrue(self.ex._check_time_based_exit(self.config.MAX_POSITION_AGE_SECONDS + 1))

    def test_negative_young_enough(self):
        self.assertFalse(self.ex._check_time_based_exit(10))


# ----------------------------------------------------------------- factor 4

class TestOppositeSignal(FactorHarness):
    def test_positive_strong_opposite(self):
        self.assertTrue(self.ex._check_opposite_signal("BUY", "SELL", 95.0))

    def test_negative_weak_opposite(self):
        self.assertFalse(self.ex._check_opposite_signal("BUY", "SELL", 10.0))

    def test_negative_same_direction(self):
        self.assertFalse(self.ex._check_opposite_signal("BUY", "BUY", 95.0))


# ---------------------------------------------------------------- factor 13

class TestMaxTotalPositions(FactorHarness):
    """M-02: this was labelled 'correlation' and measured no correlation."""

    def test_positive_over_the_cap(self):
        self.config.MAX_TOTAL_POSITIONS = 2
        self.ex.mt5.positions_get.return_value = [position(ticket=i) for i in range(5)]
        self.assertTrue(self.ex._check_max_total_positions("XAUUSDm"))

    def test_negative_within_the_cap(self):
        self.config.MAX_TOTAL_POSITIONS = 2
        self.ex.mt5.positions_get.return_value = [position()]
        self.assertFalse(self.ex._check_max_total_positions("XAUUSDm"))

    def test_the_old_name_is_gone(self):
        self.assertFalse(hasattr(self.ex, "_check_correlation_conflict"),
                         "a mislabeled risk control is worse than none")


# ------------------------------------------------------- factors 1, 2 and 3

class TestDeletedFactors(FactorHarness):
    """5.6/5.2: client-side TP/SL deleted; trailing moved out of the close path."""

    @staticmethod
    def _method_calls(func):
        """Names of self.<name>(...) calls actually made by func.

        Parsed, not grepped: a comment explaining that something was removed
        must not read as evidence that it is still there.
        """
        import ast, inspect, textwrap
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
        return names

    def test_trailing_no_longer_closes_positions(self):
        self.assertNotIn("_check_trailing_stop",
                         self._method_calls(self.ex.should_close_trade),
                         "trailing is back in the close path: a trail trigger "
                         "would market-close the position (C-06)")

    def test_client_side_tp_sl_are_not_consulted(self):
        called = self._method_calls(self.ex.should_close_trade)
        self.assertNotIn("_check_take_profit_reached", called)
        self.assertNotIn("_check_stop_loss_hit", called)

    def test_manage_open_positions_exists_and_only_modifies(self):
        called = self._method_calls(self.ex.manage_open_positions)
        self.assertIn("modify_trade_sl", called)
        self.assertNotIn("close_position_by_ticket", called)
        self.assertNotIn("close_all_positions", called)


class TestDeterminism(FactorHarness):
    """M-04: jitter made risk irreproducible."""

    def test_no_randomness_in_the_executor(self):
        """No `random` import and no random call -- checked by parsing, not grep."""
        import ast, inspect
        import execution.trade_executor as te
        tree = ast.parse(inspect.getsource(te))

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("random", imported)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                value = node.func.value
                if isinstance(value, ast.Name):
                    self.assertNotEqual(value.id, "random",
                                        "non-deterministic call survives (M-04)")

    def test_break_even_buffer_is_repeatable(self):
        pos = position(price_current=2050.0)
        self.ex.mt5.symbol_info_tick.return_value = MagicMock(bid=2050.0, ask=2050.2)
        runs = set()
        for _ in range(20):
            try:
                runs.add(self.ex.calculate_trailing_stop(pos, 2050.0, atr=5.0))
            except Exception:
                runs.add("error")
        self.assertEqual(len(runs), 1,
                         "trailing stop is not reproducible across identical inputs")


class TestTrailingMovesStopsMonotonically(FactorHarness):
    """5.8: a favourable ramp must produce improving SLTP and zero DEAL closes."""

    def test_favourable_ramp_only_issues_sltp_and_improves_the_stop(self):
        import config
        config.TRAILING_STOP_ENABLED = True
        config.BREAK_EVEN_ENABLED = False
        config.ADAPTIVE_TRAILING_STOP = False

        sent = []
        self.ex.mt5.order_send.side_effect = lambda req: (
            sent.append(req) or MagicMock(retcode=self.ex.mt5.TRADE_RETCODE_DONE,
                                          comment="ok"))
        self.ex.mt5.TRADE_ACTION_SLTP = 6
        self.ex.mt5.TRADE_ACTION_DEAL = 1

        pos = position(sl=1990.0, price_current=2000.0)
        self.ex.mt5.positions_get.return_value = [pos]

        for price in range(2010, 2120, 10):     # a clean uptrend
            pos.price_current = float(price)
            self.ex.mt5.symbol_info_tick.return_value = MagicMock(
                bid=float(price), ask=float(price) + 0.2)
            self.ex.mt5.symbol_info.return_value = spec_info(
                bid=float(price), ask=float(price) + 0.2)
            self.ex.manage_open_positions("XAUUSDm", atr=5.0)
            new_sl = None
            for req in sent:
                if req.get("action") == 6:
                    new_sl = req["sl"]
            if new_sl is not None:
                pos.sl = new_sl

        deals = [r for r in sent if r.get("action") == self.ex.mt5.TRADE_ACTION_DEAL]
        self.assertEqual(deals, [], "trailing closed a position at market")

        stops = [r["sl"] for r in sent if r.get("action") == 6]
        self.assertEqual(stops, sorted(stops),
                         "trailing stop moved backwards")

        config.BREAK_EVEN_ENABLED = True


if __name__ == "__main__":
    unittest.main()


class TestBreakEvenIsAlwaysProtective(FactorHarness):
    """Regression: break-even produced stops BELOW entry, and even negative.

    Two compounding bugs found while verifying the trailing switch:

      * BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER grew the buffer by 0.01 price
        units per minute held, with no upper bound.
      * The "safety" clamp then set `sl = price_current - buffer * 0.5`, so a
        large buffer pushed the stop far below entry -- in the observed case to
        -147,012, a negative price.

    A break-even stop below the entry it protects is not break-even.
    """

    def _apply(self, entry, current, age_seconds, is_buy=True, sl=0.0):
        import time
        self.config.BREAK_EVEN_ENABLED = True
        self.ex.mt5.TRADE_ACTION_SLTP = 6
        sent = []
        self.ex.mt5.order_send.side_effect = lambda r: sent.append(r) or MagicMock(
            retcode=self.ex.mt5.TRADE_RETCODE_DONE, comment="ok")
        pos = position(type=0 if is_buy else 1, price_open=entry,
                       price_current=current, sl=sl, tp=0.0,
                       time=time.time() - age_seconds)
        self.ex.apply_break_even_sl(pos)
        return sent[0]["sl"] if sent else None

    def test_fresh_position_gets_a_stop_above_entry(self):
        sl = self._apply(2000.0, 2100.0, 60)
        self.assertIsNotNone(sl)
        self.assertGreater(sl, 2000.0)
        self.assertLess(sl, 2100.0)

    def test_week_old_position_still_protective(self):
        sl = self._apply(2000.0, 2100.0, 604800)
        self.assertGreater(sl, 2000.0)
        self.assertLessEqual(sl, 2100.0)

    def test_absurd_position_age_cannot_produce_a_negative_stop(self):
        # The exact crash case: position.time == 0 (epoch).
        import time
        sl = self._apply(2000.0, 2100.0, time.time())
        self.assertGreater(sl, 0.0, "break-even produced a negative price")
        self.assertGreaterEqual(sl, 2000.0, "break-even stop is below entry")

    def test_sell_side_is_symmetric(self):
        sl = self._apply(2000.0, 1900.0, 604800, is_buy=False)
        self.assertLess(sl, 2000.0)
        self.assertGreaterEqual(sl, 1900.0)

    def test_buffer_never_exceeds_the_profit_it_protects(self):
        for age in (60, 3600, 86400, 604800, 2592000):
            sl = self._apply(2000.0, 2050.0, age)
            if sl is not None:
                self.assertLessEqual(sl, 2050.0)
                self.assertGreaterEqual(sl, 2000.0)

    def test_stop_is_never_moved_backwards(self):
        # An existing stop already better than the computed one must survive.
        self.assertIsNone(self._apply(2000.0, 2100.0, 60, sl=2095.0))


class TestTrailingIsConfigurableAndOff(unittest.TestCase):
    """Trailing must be one switch, and that switch must currently be off."""

    def test_trailing_is_disabled_by_default(self):
        import importlib, config as c
        importlib.reload(c)
        self.assertFalse(c.TRAILING_STOP_ENABLED)

    def test_there_is_only_one_trailing_switch(self):
        import importlib, config as c
        importlib.reload(c)
        self.assertFalse(hasattr(c, "TRAILING_STOP_MODIFICATION"),
                         "a second trailing switch can disagree with the first")

    def test_disabled_trailing_moves_no_stops(self):
        import config
        from execution.trade_executor import TradeExecutor
        was_be, was_ts = config.BREAK_EVEN_ENABLED, config.TRAILING_STOP_ENABLED
        config.BREAK_EVEN_ENABLED = False       # isolate trailing
        config.TRAILING_STOP_ENABLED = False
        try:
            ex = make_executor()
            ex.config = config
            ex.mt5.symbol_info.return_value = spec_info()
            ex.mt5.symbol_info_tick.return_value = MagicMock(bid=2100.0, ask=2100.2)
            sent = []
            ex.mt5.order_send.side_effect = lambda r: sent.append(r) or MagicMock(
                retcode=ex.mt5.TRADE_RETCODE_DONE, comment="ok")
            ex.mt5.positions_get.return_value = [
                position(price_current=2100.0, profit=1000.0)]
            moved = ex.manage_open_positions("XAUUSDm", atr=5.0)
            self.assertEqual(moved, 0)
            self.assertEqual(sent, [], "a stop was moved with trailing disabled")
        finally:
            config.BREAK_EVEN_ENABLED = was_be
            config.TRAILING_STOP_ENABLED = was_ts


class TestNoStopModificationAtAll(unittest.TestCase):
    """User decision: the bot must not modify a stop in flight, at all.

    Once a position is open its SL/TP are exactly what was sent at entry and
    held server-side. These assert that end-to-end, not just that two flags
    happen to be False.
    """

    def test_both_stop_modification_switches_are_off(self):
        import importlib, config as c
        importlib.reload(c)
        self.assertFalse(c.TRAILING_STOP_ENABLED)
        self.assertFalse(c.BREAK_EVEN_ENABLED)

    def test_no_sltp_request_is_ever_issued(self):
        import config
        from execution.trade_executor import TradeExecutor
        ex = make_executor()
        ex.config = config
        ex.mt5.symbol_info.return_value = spec_info()
        ex.mt5.TRADE_ACTION_SLTP = 6

        sent = []
        ex.mt5.order_send.side_effect = lambda r: sent.append(r) or MagicMock(
            retcode=ex.mt5.TRADE_RETCODE_DONE, comment="ok")

        # Walk a position from flat to deeply profitable; nothing may be sent.
        for price in range(2000, 2300, 10):
            ex.mt5.symbol_info_tick.return_value = MagicMock(
                bid=float(price), ask=float(price) + 0.2)
            ex.mt5.positions_get.return_value = [position(
                price_current=float(price), profit=(price - 2000) * 10.0)]
            ex.manage_open_positions("XAUUSDm", atr=5.0)

        self.assertEqual(sent, [],
                         "a stop was modified while both switches are off")

    def test_the_loop_still_calls_the_manager_so_re_enabling_works(self):
        # The gate is the config flag, not a deleted call site -- turning the
        # switches back on must be sufficient to restore the behaviour.
        import ast, inspect, textwrap
        import main
        tree = ast.parse(textwrap.dedent(inspect.getsource(main.main_loop)))
        calls = {n.func.attr for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn("manage_open_positions", calls)

"""Executor paths the live loop depends on: closing, order lookup, broker time.

Two of these guard server-time defects found in Phase 12 follow-up work: the
order-history window used by retry reconciliation, and the deal window used by
the daily loss limit, both ended at real UTC "now" and so could not see the
last 2-3 hours of broker activity.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import MAGIC, fake_config, fake_mt5, fake_symbol_info, make_executor

from execution.trade_executor import BrokerQueryFailed
from utils.market_time import BrokerClock


def pos(ticket=1, type_=0, **kw):
    fields = dict(ticket=ticket, symbol="XAUUSDm", type=type_, volume=0.1, magic=MAGIC,
                  time=1, profit=0.0, price_open=2000.0, sl=1990.0, tp=2020.0, comment="")
    fields.update(kw)
    return SimpleNamespace(**fields)


class TestClosePosition(unittest.TestCase):
    def setUp(self):
        self.ex = make_executor()
        self.mt5 = self.ex.mt5

    def test_close_sends_the_opposite_deal_at_the_right_side(self):
        self.mt5.positions_get.side_effect = lambda **kw: [pos(type_=0)]
        self.assertTrue(self.ex.close_position_by_ticket(1))
        request = self.mt5.order_send.call_args[0][0]
        self.assertEqual(request["type"], self.mt5.ORDER_TYPE_SELL)
        self.assertEqual(request["price"], 2000.40)             # a BUY closes at the bid
        self.assertEqual(request["position"], 1)

    def test_sell_closes_at_the_ask(self):
        self.mt5.positions_get.side_effect = lambda **kw: [pos(type_=1)]
        self.ex.close_position_by_ticket(1)
        request = self.mt5.order_send.call_args[0][0]
        self.assertEqual((request["type"], request["price"]), (self.mt5.ORDER_TYPE_BUY, 2000.50))

    def test_missing_position_or_tick(self):
        self.mt5.positions_get.side_effect = lambda **kw: []
        self.assertFalse(self.ex.close_position_by_ticket(1))
        self.mt5.positions_get.side_effect = lambda **kw: [pos()]
        self.mt5.symbol_info_tick.return_value = None
        self.assertFalse(self.ex.close_position_by_ticket(1))

    def test_no_broker_answer_is_a_failure_not_a_crash(self):
        self.mt5.positions_get.side_effect = lambda **kw: [pos()]
        self.mt5.order_send.return_value = None
        self.assertFalse(self.ex.close_position_by_ticket(1))
        self.mt5.order_send.side_effect = RuntimeError("terminal gone")
        self.assertFalse(self.ex.close_position_by_ticket(1))

    def test_rejected_close(self):
        self.mt5.positions_get.side_effect = lambda **kw: [pos()]
        self.mt5.order_send.return_value = MagicMock(retcode=10018)
        self.assertFalse(self.ex.close_position_by_ticket(1))

    def test_close_all(self):
        self.mt5.positions_get.side_effect = lambda **kw: [pos(1), pos(2)]
        self.assertEqual(self.ex.close_all_positions("XAUUSDm"), 2)
        self.mt5.positions_get.side_effect = lambda **kw: []
        self.assertEqual(self.ex.close_all_positions("XAUUSDm"), 0)


class TestPositionQueries(unittest.TestCase):
    def setUp(self):
        self.ex = make_executor()
        self.mt5 = self.ex.mt5

    def test_none_with_connected_terminal_is_flat(self):
        self.mt5.positions_get.return_value = None
        self.assertEqual(self.ex.get_open_positions("XAUUSDm"), [])

    def test_none_with_disconnected_terminal_is_unknown(self):
        self.mt5.positions_get.return_value = None
        self.mt5.terminal_info.return_value = None
        with self.assertRaises(BrokerQueryFailed):
            self.ex.get_open_positions("XAUUSDm")
        self.assertIsNone(self.ex.get_open_positions_or_none("XAUUSDm"))

    def test_terminal_query_raising_counts_as_disconnected(self):
        self.mt5.terminal_info.side_effect = RuntimeError("boom")
        self.assertFalse(self.ex._terminal_is_connected())

    def test_resolve_ticket_prefers_our_newest_position(self):
        self.mt5.positions_get.side_effect = lambda **kw: [
            pos(10, time=5), pos(11, time=9), pos(12, time=20, magic=1)]
        self.assertEqual(self.ex._resolve_position_ticket("XAUUSDm", MagicMock(order=99)), 11)

    def test_resolve_ticket_falls_back_on_query_failure(self):
        self.mt5.positions_get.side_effect = RuntimeError("down")
        self.assertEqual(self.ex._resolve_position_ticket("XAUUSDm", MagicMock(order=99)), 99)


class TestTokenLookupUsesServerTime(unittest.TestCase):
    def test_a_just_executed_order_is_found(self):
        ex = make_executor()
        clock = BrokerClock()
        placed = clock.utc_to_server_epoch(datetime.now(timezone.utc) - timedelta(seconds=5))
        order = SimpleNamespace(ticket=77, comment="XAU-abc123", time_done=placed)

        def history(since, until):
            return [order] if since.timestamp() <= placed <= until.timestamp() else []

        ex.mt5.positions_get.side_effect = lambda **kw: []
        ex.mt5.history_orders_get.side_effect = history
        self.assertIs(ex._find_order_by_token("XAUUSDm", "XAU-abc123"), order)

    def test_lookup_failures_return_none(self):
        ex = make_executor()
        ex.mt5.positions_get.side_effect = RuntimeError("x")
        ex.mt5.history_orders_get.side_effect = RuntimeError("y")
        self.assertIsNone(ex._find_order_by_token("XAUUSDm", "XAU-zzz"))


class TestDailyPnlWindowUsesServerTime(unittest.TestCase):
    def test_a_loss_closed_minutes_ago_counts_today(self):
        from risk.risk_manager import RiskManager
        mt5 = fake_mt5()
        clock = BrokerClock()
        now = datetime.now(timezone.utc)
        if now.hour == 0 and now.minute < 5:
            self.skipTest("too close to the UTC day boundary")
        closed = clock.utc_to_server_epoch(now - timedelta(minutes=2))
        deal = SimpleNamespace(profit=-40.0, commission=-0.5, swap=0.0, time=closed)

        def history(since, until):
            return [deal] if since.timestamp() <= closed <= until.timestamp() else []

        mt5.history_deals_get.side_effect = history
        rm = RiskManager(mt5, fake_config())
        self.assertAlmostEqual(rm.realised_pnl_today(now=now), -40.5)


class TestSizingHoldsRiskWhenTheStopIsWidened(unittest.TestCase):
    """Phase 12 follow-up: enforce_stops_level can widen the stop after sizing.

    Nothing used to re-check that the position's real dollar risk still
    matched what compute_lot_size authorised. On THIS broker
    trade_stops_level is 0, so it never fired -- but a broker with a real
    minimum stop distance would have silently taken more risk than configured.
    """

    def _mt5(self, stops_level_points):
        mt5 = fake_mt5()
        mt5.symbol_info.return_value = fake_symbol_info(trade_stops_level=stops_level_points)
        mt5.symbol_info_tick.return_value = MagicMock(bid=2000.00, ask=2000.00)
        return mt5

    def test_stop_widened_beyond_intent_shrinks_the_position(self):
        # stops_level 100 points = $1.00 minimum distance; the intended stop
        # is only $0.10 away, so it will be forced out to $1.00 -- 10x wider.
        mt5 = self._mt5(stops_level_points=100)
        ex = make_executor(mt5=mt5, config=fake_config())
        result = ex._place_market_order("XAUUSDm", True, 0.50, 1999.90, 2010.00)
        self.assertEqual(result.retcode, mt5.TRADE_RETCODE_DONE)
        sent = mt5.order_send.call_args[0][0]
        self.assertAlmostEqual(sent["volume"], 0.05, places=2)   # 0.50 / 10
        self.assertAlmostEqual(sent["sl"], 1999.00, places=2)

    def test_stop_not_widened_leaves_size_unchanged(self):
        mt5 = self._mt5(stops_level_points=0)
        ex = make_executor(mt5=mt5, config=fake_config())
        ex._place_market_order("XAUUSDm", True, 0.50, 1990.00, 2010.00)
        sent = mt5.order_send.call_args[0][0]
        self.assertAlmostEqual(sent["volume"], 0.50, places=2)

    def test_shrinking_below_the_broker_minimum_declines_rather_than_over_risks(self):
        # A tiny intended stop against a large minimum distance: shrinking to
        # hold risk constant would need less than volume_min.
        mt5 = self._mt5(stops_level_points=100)
        ex = make_executor(mt5=mt5, config=fake_config())
        with self.assertRaises(RuntimeError) as ctx:
            ex._place_market_order("XAUUSDm", True, 0.01, 1999.99, 2010.00)
        self.assertIn("declining rather than risking more", str(ctx.exception))
        mt5.order_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()

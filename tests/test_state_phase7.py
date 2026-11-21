"""Phase 7 tests: survive a restart without losing risk constraints or records.

The two scenarios the plan names:

  * open -> scale twice -> kill the process -> restart -> the third scale-up is
    REFUSED (it used to be granted, because the counter rebuilt as zero);
  * a server-side stop closure appears in the statistics with the broker's own
    realised figure (it used to be invisible).
"""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import fake_config, fake_mt5, fake_risk_manager, make_executor

from execution.position_state import PositionStateStore


def deal(ticket, profit=0.0, commission=0.0, swap=0.0, entry=1,
         position_id=None, symbol="XAUUSDm", volume=0.1, price=2000.0,
         when=None, comment=""):
    """A broker deal. entry=1 is DEAL_ENTRY_OUT -- a closing deal.

    Each deal closes its own position unless ``position_id`` says otherwise,
    as on a real account.
    """
    when = when or datetime.now(timezone.utc)
    position_id = ticket if position_id is None else position_id
    return MagicMock(ticket=ticket, position_id=position_id, order=ticket,
                     symbol=symbol, type=0, entry=entry, volume=volume,
                     price=price, profit=profit, commission=commission,
                     swap=swap, time=when.timestamp(), comment=comment)


class StoreHarness(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "trades.db")
        self.store = PositionStateStore(self.db)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestStateSurvivesRestart(StoreHarness):
    """7.3 (H-04): per-position state must not reset on restart.

    Scaling -- the original H-04 case -- was deleted (it had no live caller),
    so a restart can no longer refill an exposure allowance. The state that
    remains, ATR at entry and peak profit, must still survive.
    """

    def test_entry_atr_and_peak_persist(self):
        self.store.save_position(1, "XAUUSDm", entry_atr=3.5)
        self.store.record_peak(1, 42.0)
        reborn = PositionStateStore(self.db)
        stored = reborn.get_position(1)
        self.assertEqual(stored["entry_atr"], 3.5)
        self.assertEqual(stored["peak_favourable_excursion"], 42.0)

    def test_restarted_executor_restores_entry_atr(self):
        config = fake_config(TRADE_DB_PATH=self.db)
        position = MagicMock(ticket=1, symbol="XAUUSDm", type=0, volume=0.1,
                             price_open=2000.0, price_current=2010.0,
                             sl=1990.0, tp=0.0, time=0, magic=987654321,
                             profit=10.0, comment="XAU-abc")
        self.store.save_position(1, "XAUUSDm", entry_atr=3.5)
        reborn = make_executor(fake_mt5(positions_get=MagicMock(
            return_value=[position])), config, fake_risk_manager())
        self.assertEqual(reborn._entry_atr[1], 3.5)

    def test_there_is_no_scaling_path_to_refill(self):
        from execution.trade_executor import TradeExecutor
        for name in ("may_scale", "scale_up_position", "evaluate_position_scaling",
                     "close_position_partial", "place_order"):
            self.assertFalse(hasattr(TradeExecutor, name), name)

    def test_adopted_positions_are_never_scaled(self):
        # A position the broker holds but we have no record of: its scaling
        # history is unknown, so assuming zero is exactly the bug.
        report = self.store.reconcile([42], "XAUUSDm")
        self.assertEqual(report["adopted"], [42])
        self.assertTrue(self.store.get_position(42)["manage_only"])

    def test_reconcile_cleans_up_closed_positions(self):
        # Positions closed server-side used to leak their state rows forever.
        self.store.save_position(1, "XAUUSDm")
        self.store.save_position(2, "XAUUSDm")
        report = self.store.reconcile([1], "XAUUSDm")
        self.assertEqual(report["closed"], [2])
        self.assertIsNone(self.store.get_position(2))

    def test_matched_positions_keep_their_history(self):
        self.store.save_position(1, "XAUUSDm", original_volume=0.1,
                                 total_volume=0.2, scaling_count=2)
        self.store.reconcile([1], "XAUUSDm")
        self.assertEqual(self.store.get_position(1)["scaling_count"], 2)
        self.assertFalse(self.store.get_position(1)["manage_only"])


class TestPeakFavourableExcursionPersists(StoreHarness):
    """5.1 depended on this: PFE resetting to zero would close a winner."""

    def test_peak_survives_a_restart(self):
        self.store.save_position(1, "XAUUSDm")
        self.store.record_peak(1, 250.0)
        self.store.record_peak(1, 100.0)        # must not lower it
        reborn = PositionStateStore(self.db)
        self.assertEqual(reborn.get_position(1)["peak_favourable_excursion"],
                         250.0)

    def test_entry_atr_survives_a_restart(self):
        self.store.save_position(1, "XAUUSDm", entry_atr=4.25)
        reborn = PositionStateStore(self.db)
        self.assertAlmostEqual(reborn.get_position(1)["entry_atr"], 4.25)


class TestBrokerSourcedRecords(StoreHarness):
    """7.2 (H-07): survivorship bias in the recorded results."""

    def test_server_side_stop_out_is_recorded(self):
        # THE H-07 CORE. A stop-out is closed by the broker, so the bot's own
        # close-handler never ran and the trade was never recorded at all.
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [
            deal(1, profit=-45.0, comment="sl 1990.00"),
        ]
        self.assertEqual(self.store.sync_deals(mt5), 1)
        stats = self.store.compute_statistics()
        self.assertEqual(stats["total_trades"], 1)
        self.assertAlmostEqual(stats["total_pnl"], -45.0)

    def test_omitting_stop_outs_biases_the_win_rate_upward(self):
        # Two winners the bot closed itself, three stop-outs it never saw.
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [
            deal(1, profit=30.0), deal(2, profit=25.0),
            deal(3, profit=-40.0), deal(4, profit=-35.0), deal(5, profit=-50.0),
        ]
        self.store.sync_deals(mt5)
        stats = self.store.compute_statistics()

        self.assertEqual(stats["total_trades"], 5)
        self.assertAlmostEqual(stats["win_rate"], 40.0)
        self.assertLess(stats["total_pnl"], 0)
        # What the audited code would have reported: only the two self-closes.
        self.assertAlmostEqual(2 / 2 * 100, 100.0)

    def test_costs_are_included_in_realised_pnl(self):
        # Recording `profit` alone overstates every trade by its costs, which
        # on a scalping strategy is most of the edge.
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [
            deal(1, profit=10.0, commission=-3.0, swap=-1.5),
        ]
        self.store.sync_deals(mt5)
        stats = self.store.compute_statistics()
        self.assertAlmostEqual(stats["total_pnl"], 5.5)
        self.assertAlmostEqual(stats["total_costs"], -4.5)

    def test_deals_are_not_double_counted_on_re_poll(self):
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [deal(1, profit=10.0)]
        self.assertEqual(self.store.sync_deals(mt5), 1)
        self.assertEqual(self.store.sync_deals(mt5), 0)
        self.assertEqual(self.store.compute_statistics()["total_trades"], 1)

    def test_open_and_close_deals_make_one_trade_with_both_costs(self):
        mt5 = fake_mt5()
        opened = datetime.now(timezone.utc) - timedelta(minutes=40)
        mt5.history_deals_get.return_value = [
            deal(1, commission=-0.35, entry=0, position_id=9, when=opened),
            deal(2, profit=12.0, commission=-0.35, entry=1, position_id=9),
        ]
        self.store.sync_deals(mt5)
        trades = self.store.closed_trades()
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["net_pnl"], 11.3)
        self.assertEqual(trades[0]["direction"], "BUY")
        self.assertAlmostEqual(trades[0]["holding_seconds"], 2400, delta=5)

    def test_buy_deal_type_zero_is_kept(self):
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [deal(1, entry=0, position_id=3)]
        self.store.sync_deals(mt5)
        with self.store._connect() as conn:
            row = conn.execute("SELECT deal_type, entry_type FROM broker_deals").fetchone()
        self.assertEqual((row["deal_type"], row["entry_type"]), (0, 0))

    def test_opening_deals_are_not_trades(self):
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [
            deal(1, profit=0.0, entry=0, position_id=7),   # DEAL_ENTRY_IN
            deal(2, profit=12.0, entry=1, position_id=7),  # DEAL_ENTRY_OUT
        ]
        self.store.sync_deals(mt5)
        self.assertEqual(self.store.compute_statistics()["total_trades"], 1)

    def test_records_survive_a_restart(self):
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [deal(1, profit=10.0)]
        self.store.sync_deals(mt5)
        reborn = PositionStateStore(self.db)
        self.assertEqual(reborn.compute_statistics()["total_trades"], 1)

    def test_empty_history_is_not_an_error(self):
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = []
        self.assertEqual(self.store.sync_deals(mt5), 0)
        self.assertEqual(self.store.compute_statistics()["total_trades"], 0)

    def test_broker_failure_does_not_crash_the_loop(self):
        mt5 = fake_mt5()
        mt5.history_deals_get.side_effect = RuntimeError("disconnected")
        self.assertEqual(self.store.sync_deals(mt5), 0)

    def test_statistics_declare_their_source(self):
        # So nobody mistakes these for the old locally-reconstructed numbers.
        self.assertEqual(self.store.compute_statistics()["source"],
                         "broker_deals")

    def test_equity_reconciliation_reports(self):
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [deal(1, profit=10.0)]
        self.store.sync_deals(mt5)
        report = self.store.reconcile_equity(mt5)
        self.assertTrue(report["reconciled"])
        self.assertEqual(report["trades"], 1)


class TestExecutorIntegration(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.config = fake_config(TRADE_DB_PATH=os.path.join(self.dir, "t.db"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_forget_position_clears_the_durable_row(self):
        ex = make_executor(fake_mt5(), self.config, fake_risk_manager())
        ex.state.save_position(7, "XAUUSDm")
        ex.forget_position(7)
        self.assertIsNone(ex.state.get_position(7))

    def test_loop_syncs_broker_deals(self):
        import ast, inspect, textwrap
        import main
        tree = ast.parse(textwrap.dedent(inspect.getsource(main.main_loop)))
        called = {n.func.attr for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn("sync_broker_deals", called)




class TestDashboardShowsBrokerTruth(unittest.TestCase):
    """The display must not keep showing the biased numbers after 7.2.

    Fixing the recording without fixing the reporting leaves the dangerous
    behaviour exactly where a human can see it and believe it.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "trades.db")
        from trade_logger import TradeLogger
        self.logger = TradeLogger(self.db)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_statistics_come_from_broker_deals(self):
        store = PositionStateStore(self.db)
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [
            deal(1, profit=30.0), deal(2, profit=-40.0), deal(3, profit=-35.0),
        ]
        store.sync_deals(mt5)

        stats = self.logger.compute_statistics()
        self.assertEqual(stats["source"], "broker_deals")
        self.assertEqual(stats["total_trades"], 3)
        self.assertAlmostEqual(stats["win_rate"], 100.0 / 3, places=4)
        self.assertAlmostEqual(stats["total_pnl"], -45.0)

    def test_total_pnl_matches_the_broker(self):
        store = PositionStateStore(self.db)
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [
            deal(1, profit=10.0, commission=-2.0, swap=-1.0),
        ]
        store.sync_deals(mt5)
        self.assertAlmostEqual(self.logger.get_total_pnl(), 7.0)

    def test_legacy_fallback_declares_that_it_is_biased(self):
        # Historical rows are not hidden, but they are labelled.
        import sqlite3
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO trades (timestamp, symbol, side, entry_price, "
                "volume, pnl, status) VALUES (?,?,?,?,?,?,?)",
                ("2026-01-01", "XAUUSDm", "BUY", 2000.0, 0.1, 50.0, "CLOSED"))
        stats = self.logger.compute_statistics()
        self.assertIn("BIASED", stats["source"])
        self.assertEqual(stats["total_trades"], 1)


class TestLossStreakHalt(unittest.TestCase):
    """Phase 12.5 / audit scenario 19: ten losers in a row changed nothing,
    because get_recent_performance() returned the literal "neutral"."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "trades.db")
        self.store = PositionStateStore(self.db)
        self.base = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _deals(self, pnls):
        mt5 = fake_mt5()
        mt5.history_deals_get.return_value = [
            deal(i + 1, profit=p, when=self.base + timedelta(minutes=5 * i))
            for i, p in enumerate(pnls)]
        self.store.sync_deals(mt5, since=self.base - timedelta(days=1),
                              until=self.base + timedelta(days=1))

    def test_counts_losses_since_the_last_winner(self):
        self._deals([30.0, -10.0, -12.0, -8.0])
        self.assertEqual(self.store.consecutive_losses(), 3)

    def test_a_winner_resets_the_streak(self):
        self._deals([-10.0, -12.0, 25.0])
        self.assertEqual(self.store.consecutive_losses(), 0)

    def test_no_history_is_no_streak(self):
        self.assertEqual(self.store.consecutive_losses(), 0)

    def test_acknowledgement_clears_the_streak(self):
        self._deals([-1.0] * 6)
        self.assertEqual(self.store.consecutive_losses(), 6)
        self.store.acknowledge_loss_streak()
        self.assertEqual(self.store.consecutive_losses(), 0)

    def test_a_streak_blocks_new_entries(self):
        config = fake_config(TRADE_DB_PATH=self.db, MAX_CONSECUTIVE_LOSSES=5)
        ex = make_executor(fake_mt5(), config, fake_risk_manager())
        self._deals([-5.0] * 5)
        with self.assertRaises(RuntimeError) as ctx:
            ex.enter_trade("XAUUSDm", "BUY", 2000.0, 1990.0, 2020.0)
        self.assertIn("Loss-streak halt", str(ctx.exception))

    def test_below_the_limit_does_not_block(self):
        config = fake_config(TRADE_DB_PATH=self.db, MAX_CONSECUTIVE_LOSSES=5)
        ex = make_executor(fake_mt5(), config, fake_risk_manager())
        self._deals([-5.0] * 4)
        try:
            ex.enter_trade("XAUUSDm", "BUY", 2000.0, 1990.0, 2020.0)
        except RuntimeError as exc:
            self.assertNotIn("Loss-streak", str(exc))


if __name__ == "__main__":
    unittest.main()

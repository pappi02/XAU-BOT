"""Phase 11 forward-test report and Phase 13 live-rollout guardrails."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution import rollout

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def rollout_config(**overrides):
    fields = dict(MAX_OPEN_TRADES=1, MAX_CONCURRENT_POSITIONS=1, MAX_LOTS_PER_ORDER=0.01,
                  LIVE_MAX_LOTS_PER_ORDER=0.01, MAX_DAILY_LOSS_FRACTION=0.02,
                  LIVE_MAX_DAILY_LOSS_FRACTION=0.02)
    fields.update(overrides)
    return SimpleNamespace(**fields)


def passing_gates():
    return {"gate_c": {"passed": True, "verdict": "ALL 7 STEPS PASSED"},
            "gate_d": {"automatic_checks_passed": True, "signed_off_by": "operator"},
            "daily_review": {"last_reviewed": (NOW - timedelta(hours=2)).isoformat()}}


class TestLiveRollout(unittest.TestCase):
    def test_everything_in_place_is_allowed(self):
        self.assertEqual(rollout.live_rollout_problems(rollout_config(), passing_gates(), NOW), [])

    def test_no_evidence_blocks_everything(self):
        problems = rollout.live_rollout_problems(rollout_config(), {}, NOW)
        text = " ".join(problems)
        for needle in ("Gate C", "Gate D", "sign-off", "review"):
            self.assertIn(needle, text)

    def test_current_project_state_is_blocked(self):
        # Gate C failed on 2026-09-13; nothing may trade live.
        import config
        self.assertTrue(rollout.live_rollout_problems(config))

    def test_size_and_loss_limits(self):
        problems = rollout.live_rollout_problems(
            rollout_config(MAX_LOTS_PER_ORDER=0.5, MAX_DAILY_LOSS_FRACTION=0.05,
                           MAX_OPEN_TRADES=2), passing_gates(), NOW)
        self.assertEqual(len(problems), 3)

    def test_review_expires(self):
        gates = passing_gates()
        gates["daily_review"]["last_reviewed"] = (NOW - timedelta(hours=40)).isoformat()
        self.assertIn("overdue", " ".join(
            rollout.live_rollout_problems(rollout_config(), gates, NOW)))

    def test_record_review_and_gate(self):
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, "gates.json")
            rollout.record_daily_review("tester", NOW, path)
            rollout.record_gate("gate_c", {"passed": False}, path)
            gates = rollout.load_gates(path)
            self.assertFalse(rollout.review_overdue(gates, NOW))
            self.assertEqual(gates["gate_c"], {"passed": False})
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_live_login_is_refused_without_the_gates(self):
        import data.connect_mt5 as cm
        fake = MagicMock()
        fake.ACCOUNT_TRADE_MODE_DEMO = 0
        fake.account_info.return_value = SimpleNamespace(trade_mode=2, login=1, server="Live")
        with patch.object(cm, "mt5", fake), patch.dict(os.environ, {"ALLOW_LIVE": "true"}):
            with self.assertRaises(cm.AccountIdentityError) as ctx:
                cm.assert_account_identity()
        self.assertIn("micro-rollout", str(ctx.exception))
        fake.shutdown.assert_called_once()

    def test_demo_login_is_unaffected(self):
        import data.connect_mt5 as cm
        fake = MagicMock()
        fake.ACCOUNT_TRADE_MODE_DEMO = 0
        fake.account_info.return_value = SimpleNamespace(trade_mode=0, login=1, server="Demo")
        with patch.object(cm, "mt5", fake):
            self.assertEqual(cm.assert_account_identity().login, 1)


class TestForwardTestReport(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.db")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _seed(self):
        from execution.position_state import PositionStateStore
        from utils.market_time import BrokerClock
        clock = BrokerClock()
        store = PositionStateStore(self.db, clock=clock)
        start = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        for i, pnl in enumerate([12.0, -6.0, -6.0, 18.0]):
            opened = start + timedelta(days=i)
            closed = opened + timedelta(minutes=45)
            common = dict(symbol="XAUUSD", volume=0.01, price=4000.0, swap=0.0, comment="")
            store.record_deal(SimpleNamespace(ticket=100 + 2 * i, position_id=i + 1, order=1,
                                              type=0, entry=0, profit=0.0, commission=-0.035,
                                              time=clock.utc_to_server_epoch(opened), **common))
            store.record_deal(SimpleNamespace(ticket=101 + 2 * i, position_id=i + 1, order=2,
                                              type=1, entry=1, profit=pnl, commission=-0.035,
                                              time=clock.utc_to_server_epoch(closed), **common))
        return store

    def test_forward_records_and_report(self):
        from backtest.report import performance_report
        from scripts.forward_test_report import forward_records
        store = self._seed()
        records = forward_records(store, datetime(2026, 9, 1, tzinfo=timezone.utc),
                                  datetime(2026, 10, 1, tzinfo=timezone.utc))
        report = performance_report(records, 1000.0)
        self.assertEqual(report["total_trades"], 4)
        self.assertEqual((report["total_wins"], report["total_losses"]), (2, 2))
        self.assertAlmostEqual(report["net_profit"], 17.72)
        self.assertEqual(report["average_holding_minutes"], 45.0)
        self.assertEqual(report["maximum_loss"]["net_pnl"], -6.07)
        self.assertEqual(report["by_direction"]["BUY"]["trades"], 4)

    def test_comparison_flags_tolerance(self):
        from scripts.forward_test_report import compare
        backtest = {"period": {"first_entry": "2025-01-01T00:00:00+00:00",
                               "last_exit": "2025-01-29T00:00:00+00:00"},
                    "total_trades": 40, "average_holding_minutes": 45.0,
                    "total_lots": 0.4, "costs": {"commission": 2.8, "swap": 0.0},
                    "win_rate_pct": 32.0, "expectancy_per_trade": 0.1}
        forward = dict(backtest, total_trades=12, win_rate_pct=30.0)
        rows = {name: ok for name, _, _, ok in compare(forward, 28.0, backtest)}
        self.assertFalse(rows["trades_per_week"])
        self.assertTrue(rows["average_holding_minutes"])
        self.assertTrue(rows["win_rate_pct"])

    def test_script_runs_offline_and_writes_reports(self):
        import scripts.forward_test_report as ftr
        self._seed()
        reports = os.path.join(self.dir, "reports")
        with patch.object(ftr, "REPORT_DIR", reports):
            code = ftr.main(["--db", self.db, "--since", "2026-09-01", "--until",
                             "2026-10-01", "--backtest", os.path.join(self.dir, "none.json")])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(reports, "forward-test-2026-09-01_2026-10-01.txt")))
        with open(os.path.join(reports, "gates.json"), encoding="utf-8") as fh:
            self.assertFalse(json.load(fh)["gate_d"]["automatic_checks_passed"])


if __name__ == "__main__":
    unittest.main()

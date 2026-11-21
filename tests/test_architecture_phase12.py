"""Phase 12 tests: architecture and cleanup.

12.1  one MT5 client; the dashboard and API read persisted state only
12.3  no live market state read from static config
12.4  every config key typed, ranged and unit-declared; fail fast
12.5  covered in test_state_phase7.TestLossStreakHalt
"""

import ast
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fakes import fake_config, fake_mt5, fake_risk_manager, make_executor

import execution.control as control
import execution.position_state as position_state
import logger_config


def _read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


class IsolatedState(unittest.TestCase):
    """Point every persisted-state path at a throwaway directory."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.logs = os.path.join(self.dir, "logs")
        os.makedirs(self.logs)
        self._saved = (control.DEFAULT_HEALTH_FILE, control.DEFAULT_CANDLE_CACHE,
                       control.DEFAULT_KILL_FILE, position_state.DEFAULT_DB,
                       logger_config.DEFAULT_LOG_DIR)
        control.DEFAULT_HEALTH_FILE = os.path.join(self.logs, "health.json")
        control.DEFAULT_CANDLE_CACHE = os.path.join(self.logs, "candles.csv")
        control.DEFAULT_KILL_FILE = os.path.join(self.dir, "STOP")
        position_state.DEFAULT_DB = os.path.join(self.dir, "trades.db")
        logger_config.DEFAULT_LOG_DIR = self.logs
        import dashboard_data
        self._saved_cache = dashboard_data.DEFAULT_CANDLE_CACHE
        dashboard_data.DEFAULT_CANDLE_CACHE = control.DEFAULT_CANDLE_CACHE

    def tearDown(self):
        (control.DEFAULT_HEALTH_FILE, control.DEFAULT_CANDLE_CACHE,
         control.DEFAULT_KILL_FILE, position_state.DEFAULT_DB,
         logger_config.DEFAULT_LOG_DIR) = self._saved
        import dashboard_data
        dashboard_data.DEFAULT_CANDLE_CACHE = self._saved_cache
        shutil.rmtree(self.dir, ignore_errors=True)


# ====================================================================== 12.1

class TestOneMT5Client(unittest.TestCase):
    """M-09: the dashboard, API and trading loop shared one MT5 connection."""

    MT5_FREE_MODULES = ["dashboard_data", "run_bot", "tabs.live_trading_tab",
                        "tabs.performance_tab", "tabs.trade_history_tab",
                        "tabs.charts_tab", "tabs.signals_tab",
                        "tabs.sl_management_tab", "tabs.news_tab"]

    def test_read_side_never_loads_metatrader5(self):
        # A fresh interpreter: modules imported by other tests cannot mask a
        # transitive MT5 import here.
        code = ("import sys; sys.path.insert(0, %r)\n"
                "import importlib\n"
                "for m in %r: importlib.import_module(m)\n"
                "print('MT5' if 'MetaTrader5' in sys.modules else 'CLEAN')"
                % (ROOT, self.MT5_FREE_MODULES))
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "CLEAN",
                         "a read-side module loads MetaTrader5: %s"
                         % result.stderr[-500:])

    def test_dashboard_source_does_not_reference_mt5(self):
        for rel in ["dashboard.py", "dashboard_data.py", "run_bot.py"] + [
                "tabs/%s.py" % m.split(".")[1]
                for m in self.MT5_FREE_MODULES if m.startswith("tabs.")]:
            tree = ast.parse(_read(rel))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names]
                    module = getattr(node, "module", None) or ""
                    self.assertNotIn("MetaTrader5", names + [module],
                                     "%s imports MetaTrader5" % rel)
                    self.assertNotIn("data.fetch_candles", [module],
                                     "%s imports get_candles, which calls "
                                     "mt5.initialize()" % rel)

    def test_dashboard_is_not_launched_through_a_shell(self):
        tree = ast.parse(_read("run_bot.py"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell":
                        self.fail("run_bot.py passes shell=... to a subprocess")

    def test_the_wrong_symbol_signals_route_is_gone(self):
        import run_bot
        rules = {r.rule for r in run_bot.app.url_map.iter_rules()}
        self.assertNotIn("/signals", rules)

    def test_no_trading_widgets_remain_in_the_dashboard(self):
        source = _read("dashboard.py") + "".join(
            _read("tabs/%s.py" % t) for t in (
                "live_trading_tab", "sl_management_tab", "performance_tab",
                "trade_history_tab", "charts_tab", "signals_tab"))
        tree = ast.parse(source)
        called = {n.func.attr for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        for forbidden in ("enter_trade", "close_all_positions",
                          "close_position_by_ticket", "partial_close_position",
                          "apply_break_even_sl", "_send_order", "order_send"):
            self.assertNotIn(forbidden, called,
                             "dashboard still offers a trading action: %s" % forbidden)


class TestReadAPI(IsolatedState):
    """run_bot.py serves persisted state and never connects."""

    def setUp(self):
        super().setUp()
        import run_bot
        self.client = run_bot.app.test_client()

    def test_status_before_the_bot_has_run(self):
        data = self.client.get("/status").get_json()
        self.assertFalse(data["connected"])
        self.assertTrue(data["stale"])

    def test_status_reflects_a_fresh_snapshot(self):
        control.HealthReport().update(
            connected=True, account={"login": 1, "balance": 1000.0,
                                     "equity": 990.0, "free_margin": 900.0,
                                     "margin_level": 5000.0})
        data = self.client.get("/status").get_json()
        self.assertTrue(data["connected"])
        self.assertEqual(data["balance"], 1000.0)
        self.assertFalse(data["stale"])

    def test_a_stale_snapshot_is_not_reported_as_connected(self):
        report = control.HealthReport()
        report.update(connected=True, account={"balance": 1.0})
        stored = report.read()
        stored["last_loop_time"] = (datetime.now(timezone.utc)
                                    - timedelta(hours=3)).isoformat()
        with open(control.DEFAULT_HEALTH_FILE, "w", encoding="utf-8") as fh:
            json.dump(stored, fh)
        data = self.client.get("/status").get_json()
        self.assertFalse(data["connected"],
                         "hours-old state presented as a live connection")
        self.assertTrue(data["stale"])

    def test_market_data_without_a_snapshot_is_503_not_a_guess(self):
        self.assertEqual(self.client.get("/market_data").status_code, 503)

    def test_positions_come_from_the_snapshot(self):
        control.HealthReport().update(positions=[{"ticket": 7, "type": 0}])
        self.assertEqual(self.client.get("/positions").get_json()[0]["ticket"], 7)

    def test_no_route_contacts_the_broker(self):
        import MetaTrader5 as mt5

        def forbid(*a, **k):
            raise AssertionError("the read API contacted MT5")

        with patch.object(mt5, "initialize", forbid), \
                patch.object(mt5, "account_info", forbid), \
                patch.object(mt5, "positions_get", forbid):
            for route in ("/status", "/positions", "/market_data",
                          "/statistics", "/decisions"):
                self.client.get(route)


class TestSnapshotPublishing(IsolatedState):
    def test_broker_snapshot_is_json_safe(self):
        mt5 = fake_mt5()
        position = MagicMock(ticket=1, symbol="XAUUSD", type=0, volume=0.01,
                             price_open=2000.0, price_current=2001.0, sl=1990.0,
                             tp=2020.0, profit=1.0, swap=0.0, time=0,
                             magic=987654321, comment="XAU-x")
        snap = control.broker_snapshot(mt5, "XAUUSD", [position])
        json.dumps(snap)       # must not raise
        self.assertEqual(snap["positions"][0]["ticket"], 1)
        self.assertAlmostEqual(snap["tick"]["spread_points"], 10.0)

    def test_snapshot_failure_never_raises(self):
        mt5 = MagicMock()
        mt5.account_info.side_effect = RuntimeError("gone")
        mt5.symbol_info_tick.side_effect = RuntimeError("gone")
        snap = control.broker_snapshot(mt5, "XAUUSD", [])
        self.assertIsNone(snap["account"])

    def test_candle_cache_round_trips(self):
        import pandas as pd
        import dashboard_data
        index = pd.date_range("2026-01-05", periods=600, freq="5min", tz="UTC")
        frame = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5,
                              "close": 1.5, "tick_volume": 1}, index=index)
        self.assertTrue(control.publish_candles(frame))
        loaded = dashboard_data.candles()
        self.assertEqual(len(loaded), 500)

    def test_loop_publishes_both(self):
        source = _read("main.py")
        self.assertIn("broker_snapshot(", source)
        self.assertIn("publish_candles(", source)


class TestRealKillSwitch(IsolatedState):
    """The old button set a session variable the bot never read."""

    def test_dashboard_engages_the_file_the_loop_checks(self):
        import dashboard_data
        self.assertTrue(dashboard_data.engage_kill_switch("test"))
        self.assertTrue(os.path.exists(control.DEFAULT_KILL_FILE))
        self.assertTrue(control.KillSwitch().is_engaged())

    def test_release(self):
        import dashboard_data
        dashboard_data.engage_kill_switch("test")
        self.assertTrue(dashboard_data.release_kill_switch())
        self.assertFalse(control.KillSwitch().is_engaged())

    def test_dashboard_no_longer_has_a_session_state_kill_switch(self):
        self.assertNotIn("session_state.kill_switch", _read("dashboard.py"))


class TestDatabaseConnectionsClose(IsolatedState):
    """`with sqlite3.connect()` commits but does not close."""

    def test_the_database_file_is_deletable_after_use(self):
        store = position_state.PositionStateStore()
        store.save_position(1, "XAUUSD")
        store.compute_statistics()
        store.consecutive_losses()
        os.remove(position_state.DEFAULT_DB)   # raises on Windows if held open
        for suffix in ("-wal", "-shm"):
            path = position_state.DEFAULT_DB + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_no_bare_sqlite_connect_context_managers_remain(self):
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames
                           if d not in ("env", ".git", "__pycache__", "tests")]
            for fn in filenames:
                if not fn.endswith(".py") or fn == "db.py":
                    continue
                path = os.path.join(dirpath, fn)
                tree = ast.parse(io.open(path, encoding="utf-8",
                                         errors="replace").read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.With):
                        for item in node.items:
                            call = item.context_expr
                            if (isinstance(call, ast.Call)
                                    and isinstance(call.func, ast.Attribute)
                                    and call.func.attr == "connect"
                                    and isinstance(call.func.value, ast.Name)
                                    and call.func.value.id == "sqlite3"):
                                self.fail("%s:%d uses `with sqlite3.connect()`, "
                                          "which never closes -- use utils.db"
                                          % (fn, node.lineno))

    def test_a_failed_write_rolls_back(self):
        from utils import db
        path = position_state.DEFAULT_DB
        with db.connect(path) as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
        with self.assertRaises(RuntimeError):
            with db.connect(path) as conn:
                conn.execute("INSERT INTO t VALUES (1)")
                raise RuntimeError("boom")
        with db.connect(path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 0)


# ====================================================================== 12.3

class TestNoMarketStateFromConfig(unittest.TestCase):
    def test_static_market_state_keys_are_gone(self):
        import importlib, config
        importlib.reload(config)
        for key in ("CURRENT_ATR", "CURRENT_TREND_STRENGTH",
                    "CURRENT_VOLATILITY", "CURRENT_NEWS_SENTIMENT"):
            self.assertFalse(hasattr(config, key), key)

    def test_no_code_reads_them(self):
        for rel in ("execution/trade_executor.py", "risk/risk_manager.py",
                    "main.py"):
            tree = ast.parse(_read(rel))
            strings = {n.value for n in ast.walk(tree)
                       if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            for key in ("CURRENT_ATR", "CURRENT_TREND_STRENGTH",
                        "CURRENT_NEWS_SENTIMENT"):
                self.assertNotIn(key, attrs, "%s reads config.%s" % (rel, key))
                self.assertNotIn(key, strings, "%s getattr()s %s" % (rel, key))

    def test_trailing_without_a_live_atr_does_not_trail(self):
        import config as real_config
        cfg = fake_config(TRAIL_START_PRICE=1.0)
        ex = make_executor(fake_mt5(), cfg, fake_risk_manager())
        position = MagicMock(ticket=1, type=0, price_open=2000.0, sl=1990.0,
                             symbol="XAUUSD", last_trail_update=None)
        self.assertFalse(ex._check_trailing_stop(position, 2100.0, atr=None))


# ====================================================================== 12.4

class TestConfigSchema(unittest.TestCase):
    def setUp(self):
        import importlib, config
        self.config = importlib.reload(config)

    def test_every_key_has_a_schema_entry(self):
        from utils.config_validation import SCHEMA, config_keys
        missing = [k for k in config_keys(self.config) if k not in SCHEMA]
        self.assertEqual(missing, [],
                         "config keys without a declared type/range/unit")

    def test_every_schema_entry_declares_a_unit(self):
        from utils.config_validation import SCHEMA
        for key, (_t, _lo, _hi, unit, _secret) in SCHEMA.items():
            self.assertTrue(unit and unit.strip(), key)

    def test_the_real_config_is_valid(self):
        from utils.config_validation import validate
        self.assertEqual(validate(self.config), [])

    def _broken(self, **overrides):
        cfg = SimpleNamespace(**{k: getattr(self.config, k)
                                 for k in dir(self.config) if k.isupper()})
        for k, v in overrides.items():
            setattr(cfg, k, v)
        return cfg

    def test_out_of_range_risk_is_rejected(self):
        from utils.config_validation import validate
        problems = validate(self._broken(RISK_PER_TRADE_FRACTION=0.5))
        self.assertTrue(any("RISK_PER_TRADE_FRACTION" in p for p in problems))

    def test_the_audited_daily_loss_value_is_rejected(self):
        # MAX_DAILY_LOSS_PCT = 0.60 was commented "30%". 60% is not a limit.
        from utils.config_validation import validate
        problems = validate(self._broken(MAX_DAILY_LOSS_FRACTION=0.60))
        self.assertTrue(any("MAX_DAILY_LOSS_FRACTION" in p for p in problems))

    def test_a_zero_balance_floor_is_rejected(self):
        from utils.config_validation import validate
        problems = validate(self._broken(MIN_ACCOUNT_BALANCE=0))
        self.assertTrue(any("MIN_ACCOUNT_BALANCE" in p for p in problems))

    def test_a_boolean_is_not_accepted_as_a_number(self):
        from utils.config_validation import validate
        problems = validate(self._broken(MAX_CONCURRENT_POSITIONS=True))
        self.assertTrue(any("boolean" in p for p in problems))

    def test_relationships_are_checked(self):
        from utils.config_validation import validate
        self.assertTrue(any("EMA_FAST" in p for p in
                            validate(self._broken(EMA_FAST=30, EMA_SLOW=26))))
        self.assertTrue(any("EMERGENCY_CLOSE" in p for p in validate(
            self._broken(EMERGENCY_CLOSE_DRAWDOWN_FRACTION=0.1,
                         MAX_DRAWDOWN_FRACTION=0.2))))

    def test_all_problems_are_reported_at_once(self):
        from utils.config_validation import validate
        problems = validate(self._broken(RISK_PER_TRADE_FRACTION=0.5,
                                         TIMEFRAME="M7", MIN_ACCOUNT_BALANCE=0))
        self.assertGreaterEqual(len(problems), 3)

    def test_secrets_are_never_printed(self):
        from utils.config_validation import validate
        problems = validate(self._broken(NEWS_API_KEY=12345678901234))
        joined = "\n".join(problems)
        self.assertNotIn("12345678901234", joined)

    def test_startup_validates_before_connecting(self):
        tree = ast.parse(_read("main.py"))
        main_fn = next(n for n in tree.body
                       if isinstance(n, ast.FunctionDef) and n.name == "main")
        source = ast.get_source_segment(_read("main.py"), main_fn)
        self.assertLess(source.index("assert_valid(config)"),
                        source.index("main_loop()"))

    def test_unit_ambiguous_names_are_gone(self):
        for key in ("MIN_HOLDING_TIME", "MAX_POSITION_AGE", "MT5_TIMEOUT",
                    "EMERGENCY_CLOSE_THRESHOLD", "ORDER_DEVIATION",
                    "ORDER_RETRY", "MAX_LOT_SIZE", "MIN_LOT_SIZE",
                    "MAX_CORRELATED_POSITIONS", "CORRELATION_CLOSE_ENABLED",
                    "SCALING_ENABLED", "TRAILING_STOP_ACTIVATION_PRICE"):
            self.assertFalse(hasattr(self.config, key), key)

    def test_scaling_is_gone_with_its_config(self):
        from execution.trade_executor import TradeExecutor
        self.assertFalse(hasattr(TradeExecutor, "scale_up_position"))
        for key in ("ADAPTIVE_SCALING_ENABLED", "MAX_ADDITIONAL_POSITIONS",
                    "SCALING_LOT_SIZE_MULTIPLIER", "SCALING_FALLBACK_SL_ATR"):
            self.assertFalse(hasattr(self.config, key), key)




class TestTrailingThrottleOnRealPositions(unittest.TestCase):
    """The throttle wrote to the position object -- immutable in real MT5."""

    def _real_position(self, ticket=1):
        from collections import namedtuple
        TradePosition = namedtuple("TradePosition",
                                   "ticket type price_open sl symbol")
        return TradePosition(ticket, 0, 2000.0, 1990.0, "XAUUSD")

    def test_works_on_an_immutable_position(self):
        ex = make_executor()
        position = self._real_position()
        with self.assertRaises(AttributeError):
            position.last_trail_update = 1          # what the old code did
        self.assertTrue(ex.should_update_trailing_stop(position, min_interval=300))

    def test_throttle_survives_a_refetched_position(self):
        ex = make_executor()
        now = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
        self.assertTrue(ex.should_update_trailing_stop(
            self._real_position(), min_interval=300, now=now))
        # Next loop: a brand-new object for the same ticket, 60s later.
        self.assertFalse(ex.should_update_trailing_stop(
            self._real_position(), min_interval=300,
            now=now + timedelta(seconds=60)))
        self.assertTrue(ex.should_update_trailing_stop(
            self._real_position(), min_interval=300,
            now=now + timedelta(seconds=301)))

    def test_forgetting_a_position_clears_its_throttle(self):
        ex = make_executor()
        ex.should_update_trailing_stop(self._real_position(5), min_interval=300)
        ex.forget_position(5)
        self.assertNotIn(5, ex._last_trail_update)


if __name__ == "__main__":
    unittest.main()

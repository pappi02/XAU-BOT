"""Tests for the Phase 1 fixes.

Every one of these would have failed before Phase 1 and must keep passing.
None of them touch a broker: MetaTrader5 is mocked throughout.
"""

import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import make_executor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import config
import data.connect_mt5 as connect_mod
from data.connect_mt5 import AccountIdentityError
from execution.trade_executor import (
    TradeExecutor,
    TradingDisabled,
    disable_trading_writes,
    enable_trading_writes,
)


def project_py_files():
    skip = {"env", "venv", ".venv", "__pycache__", ".git"}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


class TestNoConflictMarkers(unittest.TestCase):
    """C-01: 177 conflict-marker lines across six modules."""

    def test_no_conflict_markers_in_any_python_file(self):
        offenders = []
        for path in project_py_files():
            text = io.open(path, encoding="utf-8", errors="surrogateescape").read()
            for lineno, line in enumerate(text.split("\n"), 1):
                if (line.startswith("<<<<<<<") or line.startswith(">>>>>>>")
                        or line == "======="):
                    offenders.append("%s:%d" % (path, lineno))
        self.assertEqual(offenders, [], "conflict markers found")

    def test_no_conflict_markers_in_gitignore(self):
        text = io.open(os.path.join(ROOT, ".gitignore"),
                       encoding="utf-8", errors="surrogateescape").read()
        for marker in ("<<<<<<<", "=======", ">>>>>>>"):
            self.assertNotIn(marker, text)

    def test_every_module_compiles(self):
        # Compile from source text rather than py_compile: os.devnull is "nul"
        # on Windows and py_compile refuses to write a non-regular cfile.
        for path in project_py_files():
            text = io.open(path, encoding="utf-8", errors="surrogateescape").read()
            try:
                compile(text, path, "exec")
            except SyntaxError as exc:
                self.fail("%s does not compile: %s" % (path, exc))


class TestConfigIntegrity(unittest.TestCase):
    """M-08 / M-14: duplicate and dead config keys."""

    def test_contract_size_is_not_configurable_at_all(self):
        # Phase 1.3 deduplicated CONTRACT_SIZE to the correct 100.0; Phase 2.1
        # deleted it outright. Contract size is a broker fact, read via
        # SymbolSpec -- a config key for it is the bug, whatever its value.
        self.assertFalse(hasattr(config, "CONTRACT_SIZE"))

    def test_no_duplicate_top_level_assignments(self):
        import ast
        tree = ast.parse(io.open(os.path.join(ROOT, "config.py"),
                                 encoding="utf-8").read())
        seen, dupes = set(), []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        if t.id in seen:
                            dupes.append(t.id)
                        seen.add(t.id)
        self.assertEqual(dupes, [])

    def test_dead_keys_are_gone(self):
        for key in ("TRADE_AMOUNT", "INITIAL_BALANCE", "TRADE_ACCOUNT_MODE",
                    "API_KEY", "SECRET_KEY", "LEVERAGE"):
            self.assertFalse(hasattr(config, key),
                             "%s should have been deleted" % key)

    def test_news_api_key_has_no_hardcoded_fallback(self):
        # H-10: the revoked key must not reappear as a default.
        text = io.open(os.path.join(ROOT, "config.py"), encoding="utf-8").read()
        self.assertNotIn("2287da19b4ca4f6a9d2711431ca2278b", text)


class TestNoStarImports(unittest.TestCase):
    """1.5: `from config import *` is what allowed silent shadowing."""

    def test_no_star_import_of_config(self):
        # Built at runtime so this file does not match its own assertion.
        needle = "from config import " + "*"
        offenders = []
        for p in project_py_files():
            if os.path.abspath(p) == os.path.abspath(__file__):
                continue
            if needle in io.open(p, encoding="utf-8",
                                 errors="surrogateescape").read():
                offenders.append(p)
        self.assertEqual(offenders, [])

    def test_main_does_not_shadow_config_flags(self):
        import main
        text = io.open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
        for flag in ("TRAILING_STOP_ENABLED", "SCALING_ENABLED",
                     "AUTO_CLOSE_ENABLED"):
            self.assertNotIn("\n%s = " % flag, text,
                             "%s is redefined at module level in main.py" % flag)


class TestSingleWriteChokePoint(unittest.TestCase):
    """1.4: the dashboard may query state, never place orders."""

    def setUp(self):
        enable_trading_writes()
        self.executor = make_executor()

    def tearDown(self):
        enable_trading_writes()

    def test_writes_allowed_by_default(self):
        self.assertIsNotNone(self.executor._send_order({"a": 1}))

    def test_writes_raise_when_disabled(self):
        disable_trading_writes("unit test")
        with self.assertRaises(TradingDisabled):
            self.executor._send_order({"a": 1})

    def test_send_order_does_not_recurse(self):
        # A regression guard: _send_order once called itself.
        self.executor.mt5.order_send.return_value = "sentinel"
        self.assertEqual(self.executor._send_order({"a": 1}), "sentinel")

    def test_no_direct_order_send_outside_choke_point(self):
        offenders = []
        for path in project_py_files():
            if path.endswith(("trade_executor.py",)) or "tests" in path:
                continue
            text = io.open(path, encoding="utf-8", errors="surrogateescape").read()
            for lineno, line in enumerate(text.split("\n"), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if ".order_send(" in line:
                    offenders.append("%s:%d" % (path, lineno))
        self.assertEqual(offenders, [],
                         "order_send called outside TradeExecutor._send_order")


class TestAccountIdentity(unittest.TestCase):
    """H-06: never trade whatever account the terminal happens to have open."""

    def setUp(self):
        self._real_mt5 = connect_mod.mt5
        connect_mod.mt5 = MagicMock()
        connect_mod.mt5.ACCOUNT_TRADE_MODE_DEMO = 0
        os.environ.pop("ALLOW_LIVE", None)

    def tearDown(self):
        connect_mod.mt5 = self._real_mt5
        os.environ.pop("ALLOW_LIVE", None)

    def test_missing_credential_raises_and_never_touches_terminal(self):
        for creds in [(None, "p", "s"), (1, None, "s"), (1, "p", None),
                      (1, "p", ""), (None, None, None)]:
            with self.assertRaises(AccountIdentityError):
                connect_mod.connect_mt5(*creds)
        connect_mod.mt5.initialize.assert_not_called()
        connect_mod.mt5.login.assert_not_called()

    def test_live_account_refused_without_allow_live(self):
        connect_mod.mt5.account_info.return_value = MagicMock(
            trade_mode=2, login=999, server="Real-1")
        with self.assertRaises(AccountIdentityError):
            connect_mod.assert_account_identity()

    def test_live_account_allowed_with_allow_live_and_rollout_conditions(self):
        # Phase 13: ALLOW_LIVE is necessary, not sufficient -- the micro-rollout
        # conditions (execution/rollout.py) must also hold.
        from unittest.mock import patch
        os.environ["ALLOW_LIVE"] = "true"
        connect_mod.mt5.account_info.return_value = MagicMock(
            trade_mode=2, login=999, server="Real-1")
        with patch("execution.rollout.live_rollout_problems", return_value=[]):
            self.assertIsNotNone(connect_mod.assert_account_identity())

    def test_live_account_refused_with_allow_live_alone(self):
        os.environ["ALLOW_LIVE"] = "true"
        connect_mod.mt5.account_info.return_value = MagicMock(
            trade_mode=2, login=999, server="Real-1")
        with self.assertRaises(connect_mod.AccountIdentityError):
            connect_mod.assert_account_identity()

    def test_demo_account_always_allowed(self):
        connect_mod.mt5.account_info.return_value = MagicMock(
            trade_mode=0, login=111, server="Demo-1")
        self.assertIsNotNone(connect_mod.assert_account_identity())

    def test_timeout_is_passed_through_not_dropped(self):
        # L-06: connect_mt5 accepted a timeout and discarded it.
        connect_mod.mt5.initialize.return_value = True
        connect_mod.mt5.login.return_value = True
        connect_mod.mt5.account_info.return_value = MagicMock(
            trade_mode=0, login=1, server="Demo-1")
        connect_mod.connect_mt5(1, "p", "s", timeout=1234)
        self.assertEqual(
            connect_mod.mt5.initialize.call_args.kwargs.get("timeout"), 1234)


class TestLauncherHasNoImportSideEffects(unittest.TestCase):
    """1.4: importing run_bot used to connect to a broker."""

    def test_importing_run_bot_does_not_connect(self):
        import MetaTrader5 as mt5
        with patch.object(mt5, "initialize") as init, \
                patch.object(mt5, "login") as login:
            for mod in ("run_bot",):
                sys.modules.pop(mod, None)
            import run_bot  # noqa: F401
            init.assert_not_called()
            login.assert_not_called()

    def test_run_bot_has_no_trading_loop(self):
        import run_bot
        self.assertFalse(hasattr(run_bot, "trading_bot"),
                         "run_bot must not define a competing trading loop")


class TestNewsDegradesCleanly(unittest.TestCase):
    """H-10 follow-through: no key must not mean a silent 401."""

    def test_no_api_key_returns_unavailable_without_network_call(self):
        import utils.news_reader as nr
        with patch.object(nr, "NEWS_API_KEY", None),                 patch.object(nr.requests, "get") as get:
            result = nr.get_latest_forex_news()
        get.assert_not_called()
        self.assertFalse(result["available"])
        self.assertEqual(result["sentiment"], "neutral")
        self.assertIn("NEWS_API_KEY", result["reason"])

    def test_empty_string_key_is_treated_as_absent(self):
        # `NEWS_API_KEY=` in .env yields "", which is not None.
        import config as cfg
        self.assertIsNot(cfg.NEWS_API_KEY, "")


if __name__ == "__main__":
    unittest.main()

"""Phase 8 tests: see what it did, and stop it without killing the process."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.control import (CircuitBreaker, HealthReport, KillSwitch,
                               ShutdownHandler)
from logger_config import DecisionLog, setup_logger


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestFileLogging(TempDirTest):
    """8.1 (H-11): there was no FileHandler anywhere, despite the README."""

    def test_a_log_file_is_written(self):
        import logging
        name = "xau_test_%d" % id(self)
        logger = setup_logger(name, log_dir=self.dir)
        logger.info("hello from the test")
        for handler in logger.handlers:
            handler.flush()

        path = os.path.join(self.dir, "%s.log" % name)
        self.assertTrue(os.path.exists(path), "no log file was created")
        with open(path, encoding="utf-8") as fh:
            self.assertIn("hello from the test", fh.read())
        logging.getLogger(name).handlers = []

    def test_repeated_setup_does_not_stack_handlers(self):
        import logging
        name = "xau_idem_%d" % id(self)
        first = setup_logger(name, log_dir=self.dir)
        count = len(first.handlers)
        setup_logger(name, log_dir=self.dir)
        setup_logger(name, log_dir=self.dir)
        self.assertEqual(len(first.handlers), count)
        logging.getLogger(name).handlers = []

    def test_an_unwritable_log_dir_does_not_crash(self):
        import logging
        name = "xau_bad_%d" % id(self)
        logger = setup_logger(name, log_dir=os.path.join(self.dir, "x\0y"))
        logger.info("still works")
        logging.getLogger(name).handlers = []


class TestDecisionLog(TempDirTest):
    """8.1: the structured record that makes 'why didn't it trade?' answerable."""

    def test_records_are_appended_as_json_lines(self):
        log = DecisionLog(path=os.path.join(self.dir, "d.jsonl"))
        log.record(bar="2026-01-05T08:00:00Z", signal="BUY", strength=71.2,
                   entry_blocked=None, action="entry")
        log.record(bar="2026-01-05T08:05:00Z", signal="BUY", strength=40.0,
                   entry_blocked="strength 40.0% < 65.0% minimum", action="none")

        records = log.read_all()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["action"], "entry")
        self.assertIn("strength", records[1]["entry_blocked"])

    def test_every_record_is_timestamped(self):
        log = DecisionLog(path=os.path.join(self.dir, "d.jsonl"))
        self.assertIn("ts", log.record(signal="HOLD"))

    def test_non_serialisable_values_do_not_break_it(self):
        log = DecisionLog(path=os.path.join(self.dir, "d.jsonl"))
        log.record(thing=object(), when=MagicMock())
        self.assertEqual(len(log.read_all()), 1)

    def test_corrupt_lines_are_skipped_not_fatal(self):
        path = os.path.join(self.dir, "d.jsonl")
        log = DecisionLog(path=path)
        log.record(signal="BUY")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        log.record(signal="SELL")
        self.assertEqual(len(log.read_all()), 2)

    def test_an_unwritable_path_does_not_raise(self):
        DecisionLog(path=os.path.join(self.dir, "nope\0", "d.jsonl")).record(a=1)


class TestCircuitBreaker(unittest.TestCase):
    """8.2: a broker rejecting everything used to look like a healthy bot."""

    def test_trips_after_the_threshold(self):
        breaker = CircuitBreaker(threshold=3)
        self.assertFalse(breaker.record_failure("boom"))
        self.assertFalse(breaker.record_failure("boom"))
        self.assertTrue(breaker.record_failure("boom"))
        self.assertTrue(breaker.is_tripped)

    def test_a_success_clears_the_consecutive_count(self):
        breaker = CircuitBreaker(threshold=3)
        breaker.record_failure("a")
        breaker.record_failure("b")
        breaker.record_success()
        breaker.record_failure("c")
        self.assertFalse(breaker.is_tripped)
        self.assertEqual(breaker.consecutive_failures, 1)

    def test_stays_tripped_until_reset(self):
        breaker = CircuitBreaker(threshold=1)
        breaker.record_failure("x")
        breaker.record_success()
        self.assertTrue(breaker.is_tripped, "a success must not silently rearm")
        breaker.reset()
        self.assertFalse(breaker.is_tripped)

    def test_status_is_reportable(self):
        breaker = CircuitBreaker(threshold=2, name="orders")
        breaker.record_failure("rejected")
        status = breaker.status()
        self.assertEqual(status["name"], "orders")
        self.assertEqual(status["consecutive_failures"], 1)
        self.assertEqual(status["last_error"], "rejected")

    def test_total_failures_accumulate_across_recoveries(self):
        breaker = CircuitBreaker(threshold=10)
        for _ in range(3):
            breaker.record_failure("x")
            breaker.record_success()
        self.assertEqual(breaker.total_failures, 3)
        self.assertEqual(breaker.consecutive_failures, 0)


class TestKillSwitch(TempDirTest):
    """8.3: stop opening positions without killing the process."""

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.dir, "STOP")
        self.switch = KillSwitch(self.path)

    def test_absent_by_default(self):
        self.assertFalse(self.switch.is_engaged())

    def test_creating_the_file_engages_it(self):
        open(self.path, "w").close()
        self.assertTrue(self.switch.is_engaged())

    def test_removing_the_file_releases_it(self):
        self.switch.engage("test")
        self.assertTrue(self.switch.is_engaged())
        self.switch.release()
        self.assertFalse(self.switch.is_engaged())

    def test_engage_records_a_reason(self):
        self.switch.engage("daily loss limit")
        with open(self.path, encoding="utf-8") as fh:
            self.assertIn("daily loss limit", fh.read())

    def test_release_when_absent_is_harmless(self):
        self.switch.release()


class TestShutdownHandler(unittest.TestCase):
    def test_first_signal_requests_a_clean_stop(self):
        handler = ShutdownHandler()
        self.assertFalse(handler.should_stop)
        handler._handle(15, None)
        self.assertTrue(handler.should_stop)

    def test_second_signal_forces_an_exit(self):
        handler = ShutdownHandler()
        handler._handle(2, None)
        with self.assertRaises(KeyboardInterrupt):
            handler._handle(2, None)

    def test_install_is_safe_off_the_main_thread(self):
        import threading
        outcome = {}

        def run():
            try:
                ShutdownHandler().install()
                outcome["ok"] = True
            except Exception as exc:      # must not propagate
                outcome["ok"] = False
                outcome["exc"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        thread.join()
        self.assertTrue(outcome.get("ok"), outcome.get("exc"))


class TestHealthReport(TempDirTest):
    """8.4: last loop time, connection, positions, P&L, breaker state."""

    def test_update_writes_every_field(self):
        report = HealthReport(os.path.join(self.dir, "health.json"))
        report.update(connected=True, open_positions=1, daily_pnl=-12.5,
                      circuit_breaker={"tripped": False}, kill_switch=False)
        data = report.read()
        self.assertTrue(data["connected"])
        self.assertEqual(data["open_positions"], 1)
        self.assertAlmostEqual(data["daily_pnl"], -12.5)
        self.assertIsNotNone(data["last_loop_time"])

    def test_read_before_any_run_returns_none(self):
        self.assertIsNone(HealthReport(os.path.join(self.dir, "nope.json")).read())

    def test_write_is_atomic(self):
        path = os.path.join(self.dir, "health.json")
        report = HealthReport(path)
        for i in range(20):
            report.update(open_positions=i)
            with open(path, encoding="utf-8") as fh:
                json.load(fh)       # never a truncated file


class TestLoopWiring(unittest.TestCase):
    """The controls must actually be consulted by the loop."""

    def _loop_source(self):
        import inspect, textwrap
        import main
        return textwrap.dedent(inspect.getsource(main.main_loop))

    def test_loop_checks_the_kill_switch(self):
        self.assertIn("kill_switch.is_engaged()", self._loop_source())

    def test_loop_feeds_the_circuit_breaker(self):
        source = self._loop_source()
        self.assertIn("breaker.record_failure", source)
        self.assertIn("breaker.record_success", source)

    def test_loop_honours_a_shutdown_request(self):
        self.assertIn("shutdown.should_stop", self._loop_source())

    def test_loop_writes_a_decision_record_and_health(self):
        source = self._loop_source()
        self.assertIn("decisions.record", source)
        self.assertIn("health.update", source)

    def test_health_command_never_connects_to_a_broker(self):
        # It reads a file. Connecting to a broker to answer "are you healthy?"
        # is how a diagnostic becomes a side effect.
        import MetaTrader5 as mt5
        import main

        def forbid(*args, **kwargs):
            raise AssertionError("--health contacted the broker")

        with patch.object(mt5, "initialize", forbid), \
                patch.object(mt5, "login", forbid):
            self.assertEqual(main.main(["--health"]), 0)

    def test_flatten_is_separate_from_the_kill_switch(self):
        import main
        self.assertTrue(callable(main.flatten))

    def test_loop_runs_the_volatility_regime_assertion(self):
        # Phase 12 follow-up: VolatilityRegime.assert_thresholds_are_reachable
        # was documented as "the startup assertion the plan asks for" but was
        # never called from anywhere -- the exact class of bug (M-03) it was
        # written to catch would recur silently. Now checked once the loop has
        # enough ATR history.
        self.assertIn("assert_thresholds_are_reachable", self._loop_source())


class TestNoUndefinedNamesInMainLoop(unittest.TestCase):
    """Regression: main_loop() called a bare `get_open_positions(...)`.

    That name is not imported anywhere in main.py -- every other call site in
    the file correctly uses `executor.get_open_positions(...)`. It would have
    raised NameError the first time AUTO_CLOSE_ENABLED was true and a position
    was open, which `python -m compileall` cannot catch (it is a runtime name
    lookup, not a syntax error) and no test exercised until now.

    This checks the whole module for the same shape of mistake: a bare Call to
    a name that only ever appears elsewhere in the file as an attribute access
    (`x.name(...)`), never as an import, a module-level def, or a genuine
    bare-name call. That pattern is how a `self.`/`executor.` prefix goes
    missing during an edit.
    """

    def test_every_bare_call_in_main_is_a_real_name(self):
        import ast
        import inspect
        import main

        source = inspect.getsource(main)
        tree = ast.parse(source)

        module_names = set(dir(__builtins__)) if isinstance(__builtins__, dict) \
            else set(dir(__builtins__))
        import builtins
        module_names = set(dir(builtins))

        bound = set()
        attr_only = set()   # names ONLY ever seen as `x.name`, never bound

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import,)):
                for a in node.names:
                    bound.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    bound.add(a.asname or a.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
            elif isinstance(node, ast.Attribute):
                attr_only.add(node.attr)

        # Bare calls: `name(...)` where `name` is a plain identifier.
        bare_calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        # A name that is called bare, is never bound/imported/defined at
        # module or function scope, AND is used elsewhere only as an
        # attribute -- that is exactly the get_open_positions shape: someone
        # meant `executor.get_open_positions(...)` and dropped the prefix.
        suspicious = sorted(
            (bare_calls - bound - module_names) & attr_only
        )
        self.assertEqual(
            suspicious, [],
            "bare call(s) to a name only ever seen elsewhere as an attribute "
            "access -- likely a missing 'executor.'/'self.' prefix: %s"
            % suspicious)

    def test_get_open_positions_is_always_qualified(self):
        import re
        import inspect
        import main
        source = inspect.getsource(main)
        for lineno, line in enumerate(source.split("\n"), 1):
            if re.search(r"(?<![.\w])get_open_positions\(", line):
                self.fail("main.py:%d calls get_open_positions() unqualified "
                         "-- it is not imported in this module" % lineno)


if __name__ == "__main__":
    unittest.main()

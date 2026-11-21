"""Phase 10 tests: news and the economic calendar (audit H-05).

Three defects in one subsystem, each of which made a feature fail silently
while appearing to work.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.news_reader as nr
from utils.economic_calendar import HIGH, MEDIUM, EconomicCalendar


class TestDictStringComparison(unittest.TestCase):
    """Defect 1: every news check in the system silently evaluated false."""

    def test_a_dict_never_equals_a_string(self):
        news = {"sentiment": "bearish", "available": True}
        self.assertNotEqual(news, "bearish")
        self.assertFalse(news == "bearish")

    def test_sentiment_of_normalises_a_dict(self):
        self.assertEqual(nr.sentiment_of({"sentiment": "bearish"}), "bearish")

    def test_sentiment_of_passes_a_string_through(self):
        self.assertEqual(nr.sentiment_of("bullish"), "bullish")

    def test_sentiment_of_handles_none(self):
        self.assertEqual(nr.sentiment_of(None), "neutral")

    def test_every_live_comparison_site_normalises(self):
        """No module may compare a raw news value against a sentiment string."""
        import ast
        import pathlib

        offenders = []
        root = pathlib.Path(__file__).resolve().parent.parent
        for path in root.rglob("*.py"):
            parts = set(path.parts)
            if parts & {"env", "tests", "scripts", "__pycache__", "backtest"}:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                left = node.left
                if not (isinstance(left, ast.Name)
                        and "news_sentiment" == left.id):
                    continue
                for comparator in node.comparators:
                    if (isinstance(comparator, ast.Constant)
                            and comparator.value in ("bullish", "bearish")):
                        offenders.append("%s:%d" % (path.name, node.lineno))
        self.assertEqual(offenders, [],
                         "raw dict compared against a sentiment string (H-05)")

    def test_the_news_exit_can_now_fire_when_enabled(self):
        """With the dict/string bug fixed, the factor is reachable again.

        It is OFF by default (NEWS_SENTIMENT_CLOSE = False) because headline
        tone over "gold OR USD OR forex OR XAU" is ambiguous by construction.
        This enables it to prove the fix, then restores the default.
        """
        from fakes import make_executor
        import config

        executor = make_executor()
        executor.config = config
        news = {"sentiment": "bearish", "available": True,
                "avg_sentiment_score": -0.6}

        previous = config.NEWS_SENTIMENT_CLOSE
        config.NEWS_SENTIMENT_CLOSE = True
        try:
            self.assertTrue(executor._check_news_economic_event("BUY", news))
            self.assertFalse(executor._check_news_economic_event("SELL", news))
        finally:
            config.NEWS_SENTIMENT_CLOSE = previous

    def test_the_news_exit_is_off_by_default(self):
        from fakes import make_executor
        import config
        executor = make_executor()
        executor.config = config
        news = {"sentiment": "bearish", "available": True}
        self.assertFalse(executor._check_news_economic_event("BUY", news),
                         "sentiment-based closing must stay off until it "
                         "demonstrates out-of-sample value")


class TestRequestTimeout(unittest.TestCase):
    """Defect 2: no timeout, inside the trading loop."""

    def test_a_timeout_is_always_supplied(self):
        with patch.object(nr, "NEWS_API_KEY", "test-key"), \
                patch.object(nr.requests, "get") as get:
            get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"articles": []},
                raise_for_status=lambda: None)
            nr.get_latest_forex_news(force=True)
        self.assertIn("timeout", get.call_args.kwargs)
        self.assertEqual(get.call_args.kwargs["timeout"], nr.REQUEST_TIMEOUT)

    def test_a_network_failure_does_not_raise_into_the_loop(self):
        with patch.object(nr, "NEWS_API_KEY", "test-key"), \
                patch.object(nr.requests, "get",
                             side_effect=nr.requests.exceptions.Timeout("hung")):
            result = nr.get_latest_forex_news(force=True)
        self.assertFalse(result["available"])
        self.assertIn("network error", result["reason"])


class TestCacheAgeUnboundLocal(unittest.TestCase):
    """Defect 3: the fallback paths raised UnboundLocalError."""

    def setUp(self):
        nr.news_cache["data"] = None
        nr.news_cache["timestamp"] = None

    def tearDown(self):
        nr.news_cache["data"] = None
        nr.news_cache["timestamp"] = None

    def test_rate_limit_fallback_with_no_cache_does_not_crash(self):
        error = nr.requests.exceptions.HTTPError()
        error.response = MagicMock(status_code=429)
        with patch.object(nr, "NEWS_API_KEY", "test-key"), \
                patch.object(nr.requests, "get", side_effect=error):
            result = nr.get_latest_forex_news(force=True)
        self.assertFalse(result["available"])
        self.assertIn("rate limited", result["reason"])

    def test_rate_limit_fallback_serves_a_warm_cache(self):
        now = datetime.now()
        nr.news_cache["data"] = {"sentiment": "bullish", "available": True,
                                 "article_count": 5,
                                 "avg_sentiment_score": 0.3, "reason": "cached"}
        nr.news_cache["timestamp"] = now - timedelta(minutes=45)

        error = nr.requests.exceptions.HTTPError()
        error.response = MagicMock(status_code=429)
        with patch.object(nr, "NEWS_API_KEY", "test-key"), \
                patch.object(nr.requests, "get", side_effect=error):
            result = nr.get_latest_forex_news(force=True, now=now)
        self.assertEqual(result["sentiment"], "bullish")
        self.assertIn("serving cache", result["reason"])

    def test_a_very_stale_cache_is_refused(self):
        now = datetime.now()
        nr.news_cache["data"] = {"sentiment": "bullish", "available": True}
        nr.news_cache["timestamp"] = now - timedelta(hours=12)
        error = nr.requests.exceptions.HTTPError()
        error.response = MagicMock(status_code=429)
        with patch.object(nr, "NEWS_API_KEY", "test-key"), \
                patch.object(nr.requests, "get", side_effect=error):
            result = nr.get_latest_forex_news(force=True, now=now)
        self.assertFalse(result["available"])

    def test_no_api_key_never_calls_the_network(self):
        with patch.object(nr, "NEWS_API_KEY", None), \
                patch.object(nr.requests, "get") as get:
            result = nr.get_latest_forex_news(force=True)
        get.assert_not_called()
        self.assertFalse(result["available"])


class TestEconomicCalendar(unittest.TestCase):
    """There was no economic calendar at all."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "cal.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, events):
        with io.open(self.path, "w", encoding="utf-8") as fh:
            json.dump(events, fh)

    def test_an_event_inside_the_window_blocks_trading(self):
        when = datetime(2026, 1, 13, 13, 30, tzinfo=timezone.utc)
        self._write([{"name": "US CPI", "when": when.isoformat(),
                      "impact": "high"}])
        calendar = EconomicCalendar(self.path)
        blocked, reason = calendar.is_blackout(
            now=when - timedelta(minutes=10), before_minutes=30)
        self.assertTrue(blocked)
        self.assertIn("US CPI", reason)

    def test_trading_resumes_after_the_window(self):
        when = datetime(2026, 1, 13, 13, 30, tzinfo=timezone.utc)
        self._write([{"name": "US CPI", "when": when.isoformat(),
                      "impact": "high"}])
        calendar = EconomicCalendar(self.path)
        blocked, _ = calendar.is_blackout(now=when + timedelta(hours=2))
        self.assertFalse(blocked)

    def test_the_window_covers_after_the_release_too(self):
        when = datetime(2026, 1, 13, 13, 30, tzinfo=timezone.utc)
        self._write([{"name": "NFP", "when": when.isoformat(),
                      "impact": "high"}])
        calendar = EconomicCalendar(self.path)
        blocked, reason = calendar.is_blackout(
            now=when + timedelta(minutes=5), after_minutes=15)
        self.assertTrue(blocked, "the spread is widest just AFTER a release")
        self.assertIn("ago", reason)

    def test_low_impact_events_do_not_block(self):
        when = datetime(2026, 1, 13, 13, 30, tzinfo=timezone.utc)
        self._write([{"name": "Minor survey", "when": when.isoformat(),
                      "impact": "low"}])
        calendar = EconomicCalendar(self.path)
        blocked, _ = calendar.is_blackout(now=when, min_impact=HIGH)
        self.assertFalse(blocked)

    def test_a_quiet_day_does_not_block(self):
        self._write([])
        calendar = EconomicCalendar(self.path)
        blocked, reason = calendar.is_blackout(
            now=datetime(2026, 3, 4, 9, 0, tzinfo=timezone.utc))
        self.assertFalse(blocked)
        self.assertIsNone(reason)

    def test_malformed_entries_are_skipped_not_fatal(self):
        self._write([{"name": "good",
                      "when": "2026-01-13T13:30:00+00:00", "impact": "high"},
                     {"name": "bad", "when": "not-a-date"},
                     "not even an object"])
        calendar = EconomicCalendar(self.path)
        self.assertEqual(len(calendar.events), 1)

    def test_an_unreadable_calendar_is_unknown_not_empty(self):
        # "I do not know what is scheduled" must not read as "nothing is".
        with io.open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        calendar = EconomicCalendar(self.path, use_recurring_fallback=False)
        blocked, reason = calendar.is_blackout()
        self.assertTrue(blocked)
        self.assertIn("unknown", reason)

    def test_a_missing_file_falls_back_to_recurring_releases(self):
        calendar = EconomicCalendar(os.path.join(self.dir, "nope.json"))
        # Mid-month 13:30 UTC is the CPI slot.
        blocked, reason = calendar.is_blackout(
            now=datetime(2026, 1, 13, 13, 30, tzinfo=timezone.utc))
        self.assertTrue(blocked)
        self.assertIn("recurring estimate", reason)

    def test_next_event_is_reported(self):
        when = datetime.now(timezone.utc) + timedelta(days=2)
        self._write([{"name": "FOMC", "when": when.isoformat(),
                      "impact": "high"}])
        calendar = EconomicCalendar(self.path)
        self.assertEqual(calendar.next_event().name, "FOMC")


class TestPhase10IsWired(unittest.TestCase):
    def _loop_source(self):
        import ast, inspect, textwrap
        import main
        return textwrap.dedent(inspect.getsource(main.main_loop))

    def test_the_loop_checks_for_an_event_blackout(self):
        self.assertIn("is_blackout", self._loop_source())

    def test_the_loop_reads_cached_news_not_the_network(self):
        source = self._loop_source()
        self.assertIn("NewsRefresher.current()", source)

    def test_sentiment_close_is_off_until_validated(self):
        import importlib, config
        importlib.reload(config)
        self.assertFalse(config.NEWS_SENTIMENT_CLOSE)

    def test_the_calendar_is_enabled(self):
        import config
        self.assertTrue(config.ECONOMIC_CALENDAR_ENABLED)


if __name__ == "__main__":
    unittest.main()

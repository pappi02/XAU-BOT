"""Live/backtest fidelity: broker clock, shared rules, live-rules engine, report.

Every test here guards a defect found while making the backtest measure the
system that actually trades (docs/SECURITY-DECISIONS.md, Phase 12 follow-up).
"""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import fake_config

from utils.market_time import (BrokerClock, in_weekend_close_window,
                               market_session, minutes_to_weekly_close,
                               weekly_close_utc)

UTC = timezone.utc


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


class TestBrokerClock(unittest.TestCase):
    """Server time = New York + 7 h, measured from the demo's daily break."""

    def setUp(self):
        self.clock = BrokerClock()

    def test_daily_break_is_17_new_york_in_both_seasons(self):
        self.assertEqual(self.clock.server_naive_to_utc(datetime(2025, 7, 15)), utc(2025, 7, 14, 21))
        self.assertEqual(self.clock.server_naive_to_utc(datetime(2026, 1, 15)), utc(2026, 1, 14, 22))

    def test_round_trip(self):
        for when in (utc(2026, 3, 2, 10, 5), utc(2026, 8, 20, 23, 55)):
            epoch = self.clock.utc_to_server_epoch(when)
            self.assertEqual(self.clock.server_epoch_to_utc(epoch), when)

    def test_position_age_is_not_off_by_the_offset(self):
        now = utc(2026, 9, 10, 12, 0)
        opened = self.clock.utc_to_server_epoch(now - timedelta(minutes=20))
        self.assertAlmostEqual(self.clock.age_seconds(opened, now), 1200.0)
        # The old arithmetic (now - server epoch) was three hours negative.
        self.assertLess(now.timestamp() - opened, 0)

    def test_index_conversion(self):
        index = pd.DatetimeIndex(["2025-07-15 00:00", "2026-01-15 00:00"], tz="UTC")
        converted = self.clock.index_to_utc(index)
        self.assertEqual(list(converted), [pd.Timestamp("2025-07-14 21:00", tz="UTC"),
                                           pd.Timestamp("2026-01-14 22:00", tz="UTC")])

    def test_from_config_ignores_non_values(self):
        clock = BrokerClock.from_config(MagicMock())
        self.assertEqual(clock.shift, timedelta(hours=7))

    def test_measured_offset(self):
        now = utc(2026, 9, 10, 12).timestamp()
        self.assertEqual(self.clock.measured_offset_hours(now + 3 * 3600 + 20, now), 3.0)
        self.assertIsNone(self.clock.measured_offset_hours(now - 40 * 3600 - 700, now))

    def _mt5(self, tick_epoch):
        mt5 = MagicMock()
        mt5.symbol_info_tick.return_value = SimpleNamespace(time=tick_epoch)
        return mt5

    def test_verify_ok_mismatch_and_unverifiable(self):
        now = utc(2026, 9, 10, 12).timestamp()
        self.assertEqual(self.clock.verify(self._mt5(now + 3 * 3600), "XAUUSD", now)[0], "ok")
        self.assertEqual(self.clock.verify(self._mt5(now + 2 * 3600), "XAUUSD", now)[0], "mismatch")
        self.assertEqual(self.clock.verify(self._mt5(now - 90000), "XAUUSD", now)[0], "unverifiable")
        self.assertEqual(self.clock.verify(self._mt5(now - 90037), "XAUUSD", now)[0], "unverifiable")
        none = MagicMock()
        none.symbol_info_tick.return_value = None
        self.assertEqual(self.clock.verify(none, "XAUUSD", now)[0], "unverifiable")


class TestTradingCalendar(unittest.TestCase):
    def test_weekly_close_follows_new_york_dst(self):
        self.assertEqual(weekly_close_utc(utc(2026, 9, 9)), utc(2026, 9, 11, 21))
        self.assertEqual(weekly_close_utc(utc(2026, 1, 7)), utc(2026, 1, 9, 22))

    def test_weekend_window(self):
        self.assertFalse(in_weekend_close_window(utc(2026, 9, 11, 20, 0), 30))
        self.assertTrue(in_weekend_close_window(utc(2026, 9, 11, 20, 31), 30))
        self.assertTrue(in_weekend_close_window(utc(2026, 9, 12, 12), 30))     # Saturday
        self.assertTrue(in_weekend_close_window(utc(2026, 9, 13, 20), 30))     # Sunday 16:00 NY
        self.assertFalse(in_weekend_close_window(utc(2026, 9, 13, 23), 30))    # Sunday 19:00 NY
        self.assertFalse(in_weekend_close_window(utc(2026, 9, 9, 20, 45), 30))  # Wednesday

    def test_minutes_to_close(self):
        self.assertAlmostEqual(minutes_to_weekly_close(utc(2026, 9, 11, 20)), 60.0)

    def test_sessions(self):
        self.assertEqual(market_session(utc(2026, 7, 15, 12, 45)), "London/NY overlap")
        self.assertEqual(market_session(utc(2026, 1, 15, 12, 45)), "London")
        self.assertEqual(market_session(utc(2026, 1, 15, 3)), "Asian")


class TestCalendarFallbackUsesNewYorkTime(unittest.TestCase):
    def setUp(self):
        from utils.economic_calendar import EconomicCalendar
        self.cal = EconomicCalendar(path=os.path.join(tempfile.gettempdir(), "absent-cal.json"))

    def test_summer_nfp_blacks_out_at_1230_utc(self):
        # First Friday of July 2026 is the 3rd; 08:30 New York = 12:30 UTC.
        self.assertTrue(self.cal.is_blackout(now=utc(2026, 7, 3, 12, 30))[0])
        self.assertFalse(self.cal.is_blackout(now=utc(2026, 7, 3, 13, 30))[0])

    def test_fomc_uses_published_dates(self):
        self.assertTrue(self.cal.is_blackout(now=utc(2026, 9, 16, 18, 0))[0])   # 14:00 NY
        self.assertFalse(self.cal.is_blackout(now=utc(2026, 9, 23, 18, 0))[0])  # not a meeting


class TestDealSyncWindowIsInServerTime(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_recent_deal_is_inside_the_window_and_stored_as_utc(self):
        from execution.position_state import PositionStateStore
        store = PositionStateStore(os.path.join(self.dir, "t.db"), clock=BrokerClock())
        closed = datetime.now(UTC) - timedelta(minutes=2)
        deal = SimpleNamespace(ticket=5, position_id=9, order=3, symbol="XAUUSD", type=1,
                               entry=1, volume=0.01, price=4000.0, profit=-3.0,
                               commission=0.0, swap=0.0, comment="",
                               time=BrokerClock().utc_to_server_epoch(closed))
        seen = {}

        def history(since, until):
            seen["window"] = (since, until)
            return [deal] if since.timestamp() <= deal.time <= until.timestamp() else []

        mt5 = MagicMock()
        mt5.history_deals_get.side_effect = history
        self.assertEqual(store.sync_deals(mt5), 1)
        self.assertEqual(store.consecutive_losses(), 1)


class TestTradePlan(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(NEWS_SENTIMENT_TRADING_ENABLED=False)
        self.signal = {"signal": "BUY", "strength": 70.0,
                       "components": {"ema_signal": 1, "rsi_condition": "neutral"}}

    def test_atr_ratio(self):
        from strategies.trade_plan import atr_ratio
        self.assertAlmostEqual(atr_ratio([2.0] * 50 + [4.0]), 2.0)
        self.assertIsNone(atr_ratio([2.0] * 5))

    def test_plan_is_scale_free(self):
        from strategies.trade_plan import plan_entry
        history = [3.0] * 100
        cheap = plan_entry(self.signal, 3.0, history, None, self.config)
        dear = plan_entry(self.signal, 30.0, [30.0] * 100, None, self.config)
        self.assertEqual(cheap.sl_multiplier, dear.sl_multiplier)
        self.assertEqual(cheap.rr, dear.rr)
        self.assertAlmostEqual(dear.sl_distance, cheap.sl_distance * 10)

    def test_levels(self):
        from strategies.trade_plan import TradePlan
        plan = TradePlan(1.0, 5.0, 2.0)
        self.assertEqual(plan.levels("BUY", 100.0), (95.0, 110.0))
        self.assertEqual(plan.levels("SELL", 100.0), (105.0, 90.0))

    def test_unusable_atr(self):
        from strategies.trade_plan import plan_entry
        self.assertIsNone(plan_entry(self.signal, float("nan"), [], None, self.config))

    def test_news_ignored_unless_enabled(self):
        from strategies.trade_plan import news_blocks_entry, plan_entry
        bearish = {"sentiment": "bearish"}
        self.assertFalse(news_blocks_entry("BUY", bearish, self.config))
        base = plan_entry(self.signal, 3.0, [3.0] * 50, None, self.config)
        self.assertEqual(plan_entry(self.signal, 3.0, [3.0] * 50, bearish, self.config), base)
        self.config.NEWS_SENTIMENT_TRADING_ENABLED = True
        self.assertTrue(news_blocks_entry("BUY", bearish, self.config))
        self.assertFalse(news_blocks_entry("SELL", bearish, self.config))

    def test_dynamic_stop_reads_news_dicts(self):
        from utils.indicators import dynamic_stop_loss
        plain = dynamic_stop_loss(70, 1.0, "neutral", 1, "neutral", "BUY")
        news = dynamic_stop_loss(70, 1.0, {"sentiment": "bullish"}, 1, "neutral", "BUY")
        self.assertGreater(news, plain)


class TestExitRules(unittest.TestCase):
    def setUp(self):
        self.config = fake_config(SESSION_END_CLOSE=True)

    def ctx(self, **kw):
        from strategies.exit_rules import ExitContext
        base = dict(position_type="BUY", age_seconds=5000, readings=[],
                    now_utc=utc(2026, 9, 9, 12))
        base.update(kw)
        return ExitContext(**base)

    def test_risk_exits_ignore_min_hold(self):
        from strategies.exit_rules import triggered_factors
        friday_late = utc(2026, 9, 11, 20, 45)
        young = self.ctx(age_seconds=60, now_utc=friday_late, drawdown_breached=True,
                         readings=[(1, "SELL", 90), (2, "SELL", 90)])
        self.assertEqual(triggered_factors(young, self.config, risk_only=True),
                         ["market_session_end", "portfolio_drawdown"])

    def test_entry_cutoff_before_weekly_close(self):
        from strategies.exit_rules import entry_too_close_to_weekly_close
        # 30 buffer + 5 min hold (300 s) + 5 min bar = 40 min before 21:00 UTC.
        self.config.MIN_HOLDING_SECONDS = 300
        self.assertTrue(entry_too_close_to_weekly_close(utc(2026, 9, 11, 20, 25), self.config, 300))
        self.assertFalse(entry_too_close_to_weekly_close(utc(2026, 9, 11, 20, 15), self.config, 300))
        self.config.SESSION_END_CLOSE = False
        self.assertFalse(entry_too_close_to_weekly_close(utc(2026, 9, 11, 20, 50), self.config, 300))

    def test_record_reading_one_per_bar(self):
        from strategies.exit_rules import record_reading
        history = []
        record_reading(history, "b1", "SELL", 50)
        record_reading(history, "b1", "SELL", 90)
        record_reading(history, "b2", "SELL", 91)
        record_reading(history, "b3", "BUY", 10)
        self.assertEqual(history, [("b2", "SELL", 91), ("b3", "BUY", 10)])

    def test_executor_blocks_young_but_allows_risk_exit(self):
        from fakes import make_executor
        from tests_helpers_clock import server_time_ago
        # SESSION_END_CLOSE off: the check reads the real clock, and the suite
        # must not depend on the weekday it runs on.
        cfg = fake_config(SESSION_END_CLOSE=False, VOLATILITY_SPIKE_ENABLED=False,
                          BREAK_OF_STRUCTURE_ENABLED=False, TREND_REVERSAL_CLOSE=False,
                          NEWS_SENTIMENT_CLOSE=False)
        ex = make_executor(config=cfg)
        ex.risk_manager.state.drawdown_fraction.return_value = 0.5
        pos = MagicMock(ticket=1, type=0, time=server_time_ago(30), profit=0.0,
                        price_current=2000.0, symbol="XAUUSD")
        frame = pd.DataFrame({"close": [1.0] * 3, "high": [1.0] * 3, "low": [1.0] * 3},
                             index=pd.date_range("2026-01-05", periods=3, freq="5min", tz="UTC"))
        strategy = MagicMock()
        strategy.generate_signal.return_value = {"signal": "HOLD", "strength": 0}
        strategy.detect_trend_reversal.return_value = {}
        decision = ex.should_close_trade(pos, frame, strategy, None)
        self.assertEqual(decision["reason"], "portfolio_drawdown")


class TestRollovers(unittest.TestCase):
    def test_wednesday_triple(self):
        from backtest.live_engine import rollovers_between
        # Wednesday 16:00 NY -> Thursday 18:00 NY: Wednesday's rollover (x3)
        # and Thursday's (x1).
        self.assertEqual(rollovers_between(utc(2026, 9, 9, 20), utc(2026, 9, 10, 22)), (2, 4))
        self.assertEqual(rollovers_between(utc(2026, 9, 9, 20), utc(2026, 9, 9, 22)), (1, 3))
        self.assertEqual(rollovers_between(utc(2026, 9, 10, 20), utc(2026, 9, 10, 20, 30)), (0, 0))
        # Friday 16:00 NY -> Monday 10:00 NY: Friday's rollover only.
        self.assertEqual(rollovers_between(utc(2026, 9, 11, 20), utc(2026, 9, 14, 14)), (1, 1))


def synthetic_frame(bars=1500, seed=3):
    rng = np.random.default_rng(seed)
    closes = 4000 + np.cumsum(rng.normal(0, 1.5, bars)) + 30 * np.sin(np.arange(bars) / 60)
    index = pd.date_range("2026-03-02 01:00", periods=bars, freq="5min", tz="UTC")
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) + 0.8,
                         "low": np.minimum(opens, closes) - 0.8, "close": closes,
                         "spread": 20}, index=index)


class TestLiveRulesEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import config
        from backtest.costs import CostModel
        from backtest.live_engine import LiveRulesBacktester, prepare_frame
        from strategies.strategy_basic import BasicTradingStrategy
        cls.config = config
        cls.strategy = BasicTradingStrategy()
        cls.frame = prepare_frame(synthetic_frame(), cls.strategy, config,
                                  already_utc=True).iloc[300:]
        cls.result = LiveRulesBacktester(cls.strategy, config, cost_model=CostModel(),
                                         initial_balance=10000.0).run(cls.frame)

    def test_trades_and_reconciliation(self):
        self.assertGreater(len(self.result.trades), 5)
        self.assertTrue(self.result.reconciles())

    def test_stops_come_from_the_shared_plan(self):
        for trade in self.result.trades:
            distance = abs(trade.entry_price - trade.stop_loss)
            self.assertGreater(distance, 0)
            ratio = abs(trade.take_profit - trade.entry_price) / distance
            self.assertGreaterEqual(ratio, 1.2 - 1e-6)
            self.assertLessEqual(ratio, 4.0 + 1e-6)

    def test_exits_use_live_reasons(self):
        reasons = {t.exit_reason.split(" ")[0] for t in self.result.trades}
        allowed = {"stop_loss", "take_profit", "end_of_data"} | set(
            __import__("strategies.exit_rules", fromlist=["FACTOR_ORDER"]).FACTOR_ORDER)
        self.assertTrue(reasons <= allowed, reasons)

    def test_one_position_at_a_time(self):
        trades = sorted(self.result.trades, key=lambda t: t.entry_time)
        for a, b in zip(trades, trades[1:]):
            self.assertLessEqual(a.exit_time, b.entry_time)

    def test_gates_are_counted(self):
        self.assertIn("strength below minimum", self.result.blocked)

    def test_spread_gate(self):
        from backtest.costs import CostModel
        from backtest.live_engine import LiveRulesBacktester
        wide = self.frame.copy()
        wide["spread"] = 500
        result = LiveRulesBacktester(self.strategy, self.config, cost_model=CostModel(),
                                     initial_balance=10000.0).run(wide)
        self.assertEqual(result.trades, [])
        self.assertGreater(result.blocked.get("spread too wide", 0), 0)

    def test_bar_gate_uses_the_actual_data_timeframe(self):
        # Regression: LiveRulesBacktester used to build BarGate from
        # config.TIMEFRAME regardless of what timeframe the DATA was at, so
        # running H1 data with config still at "M5" mis-measured every
        # bars-based hold (reversal hold, weekly-close cutoff) by 12x.
        from backtest.costs import CostModel
        from backtest.live_engine import LiveRulesBacktester
        bt = LiveRulesBacktester(self.strategy, self.config, cost_model=CostModel(),
                                 initial_balance=10000.0, timeframe="H1")
        self.assertEqual(bt.bar_seconds, 3600)
        self.assertEqual(bt.timeframe, "H1")

    def test_defaults_to_config_timeframe(self):
        from backtest.costs import CostModel
        from backtest.live_engine import LiveRulesBacktester
        bt = LiveRulesBacktester(self.strategy, self.config, cost_model=CostModel(),
                                 initial_balance=10000.0)
        self.assertEqual(bt.timeframe, self.config.TIMEFRAME)

    def test_overrides_change_behaviour(self):
        from backtest.costs import CostModel
        from backtest.live_engine import LiveRulesBacktester
        strict = LiveRulesBacktester(self.strategy, self.config, cost_model=CostModel(),
                                     initial_balance=10000.0,
                                     overrides={"MIN_ENTRY_STRENGTH": 100.1}).run(self.frame)
        self.assertEqual(strict.trades, [])

    def test_gap_through_stop_fills_at_open(self):
        from backtest.engine import Backtester, Trade
        trade = Trade(direction="BUY", lots=0.1, entry_price=100.0, stop_loss=95.0,
                      take_profit=110.0)
        price, reason = Backtester()._exit_on_bar(
            trade, {"open": 90.0, "high": 91.0, "low": 89.0, "close": 90.5})
        self.assertEqual((price, reason), (90.0, "stop_loss (gap)"))


class TestPerformanceReport(unittest.TestCase):
    def records(self):
        t0 = utc(2026, 1, 5, 10)
        pnls = [10.0, -5.0, -5.0, -5.0, 20.0, 0.0]
        return [{"entry_time": t0 + timedelta(hours=i), "exit_time": t0 + timedelta(hours=i, minutes=30),
                 "direction": "BUY" if i % 2 else "SELL", "lots": 0.01, "entry_price": 1,
                 "exit_price": 1, "net_pnl": p, "gross_pnl": p + 1, "spread": 0.5,
                 "commission": 0.07, "swap": 0.0, "slippage": 0.1,
                 "exit_reason": "take_profit" if p > 0 else "stop_loss", "session": "London",
                 "holding_seconds": 1800, "risk_money": 5.0}
                for i, p in enumerate(pnls)]

    def test_statistics(self):
        from backtest.report import format_report, performance_report
        report = performance_report(self.records(), 1000.0, {"halts": {"drawdown": 0}})
        self.assertEqual(report["total_trades"], 6)
        self.assertEqual((report["total_wins"], report["total_losses"], report["breakeven_trades"]), (2, 3, 1))
        self.assertAlmostEqual(report["win_rate_pct"], 33.33)
        self.assertEqual(report["maximum_win"]["net_pnl"], 20.0)
        self.assertEqual(report["maximum_loss"]["net_pnl"], -5.0)
        self.assertEqual(report["net_profit"], 15.0)
        self.assertAlmostEqual(report["profit_factor"], 2.0)
        self.assertEqual(report["longest_losing_streak"], 3)
        self.assertEqual(report["max_drawdown_money"], 15.0)
        self.assertEqual(report["average_holding_minutes"], 30.0)
        self.assertEqual(report["expectancy_r"], 0.5)
        self.assertEqual(report["by_exit_reason"]["take_profit"]["trades"], 2)
        text = format_report(report, "t")
        for label in ("Win rate", "Maximum win", "Maximum loss", "Total trades", "Max drawdown"):
            self.assertIn(label, text)

    def test_empty(self):
        from backtest.report import format_report, performance_report
        report = performance_report([], 1000.0)
        self.assertEqual(report["total_trades"], 0)
        self.assertIsNone(report["maximum_win"])
        format_report(report)

    def test_save(self):
        from backtest.report import performance_report, save_report
        directory = tempfile.mkdtemp()
        try:
            stem = os.path.join(directory, "r")
            save_report(performance_report(self.records(), 1000.0), "text", stem)
            self.assertTrue(os.path.exists(stem + ".json") and os.path.exists(stem + ".txt"))
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

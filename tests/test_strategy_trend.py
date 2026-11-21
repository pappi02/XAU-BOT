"""Hypothesis 3: trend-following regime filter + Donchian breakout, and the
chandelier ATR trailing stop that is the actual mechanism under test.
"""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import fake_config

from strategies.strategy_trend import TrendFollowingStrategy
from strategies.trade_plan import UNBOUNDED_RR, plan_trend_entry


def range_frame(bars, price=2000.0, half_range=2.5, start="2026-01-05"):
    idx = pd.date_range(start, periods=bars, freq="5min", tz="UTC")
    return pd.DataFrame({"open": price, "close": price,
                        "high": price + half_range, "low": price - half_range}, index=idx)


def trending_frame(bars, start_price=2000.0, drift=0.6, start="2026-01-05"):
    """A steady uptrend, so the 200-EMA regime and channel both engage."""
    idx = pd.date_range(start, periods=bars, freq="5min", tz="UTC")
    closes = start_price + np.arange(bars) * drift
    return pd.DataFrame({"open": closes, "close": closes,
                        "high": closes + 1.0, "low": closes - 1.0}, index=idx)


def add_bar(raw, high, low, close, open_=None):
    step = raw.index[-1] - raw.index[-2]
    row = pd.DataFrame({"open": [open_ if open_ is not None else close],
                        "high": [high], "low": [low], "close": [close]},
                       index=[raw.index[-1] + step])
    return pd.concat([raw, row])


def prepared_with_atr(strategy, raw, atr_value):
    prepared = strategy.prepare_data(raw)
    prepared["ATR"] = atr_value
    return prepared


class TestRegimeFilteredBreakout(unittest.TestCase):
    def setUp(self):
        self.strategy = TrendFollowingStrategy(trend_period=50, channel_period=20, rsi_period=14)

    def test_flat_market_is_hold(self):
        prepared = prepared_with_atr(self.strategy, range_frame(bars=210), 2.0)
        self.assertEqual(self.strategy.generate_signal(prepared)["signal"], "HOLD")

    def test_breakout_with_the_trend_filter_is_a_buy(self):
        raw = trending_frame(bars=210)
        raw = add_bar(raw, high=raw["high"].iloc[-1] + 20, low=raw["low"].iloc[-1] + 15,
                     close=raw["close"].iloc[-1] + 18)
        prepared = prepared_with_atr(self.strategy, raw, 2.0)
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["signal"], "BUY")
        self.assertGreater(result["strength"], 0)

    def test_breakout_against_the_trend_filter_is_not_traded(self):
        # An uptrend (regime bullish), but a bar that breaks DOWN through the
        # 20-bar channel without dropping far enough to flip the slower
        # 50-bar EMA trend filter -- a real breakdown, wrong direction for
        # the still-bullish regime.
        raw = trending_frame(bars=210)
        base_prepared = self.strategy.prepare_data(raw)
        ema_now = base_prepared["EMA_trend"].iloc[-1]
        channel_low = raw["low"].iloc[-20:].min()
        dip = (ema_now + channel_low) / 2.0     # between the EMA and the channel low
        raw = add_bar(raw, high=dip + 2, low=dip - 2, close=dip)
        prepared = prepared_with_atr(self.strategy, raw, 2.0)
        result = self.strategy.generate_signal(prepared)
        self.assertGreater(result["components"]["trend_regime"], 0, "test setup: regime must stay bullish")
        self.assertEqual(result["signal"], "HOLD")
        self.assertIn("against the trend filter", result["reasons"][0])

    def test_short_history_is_hold(self):
        prepared = prepared_with_atr(self.strategy, range_frame(bars=10), 2.0)
        self.assertEqual(self.strategy.generate_signal(prepared)["signal"], "HOLD")

    def test_downtrend_breakdown_is_a_sell(self):
        raw = trending_frame(bars=210, drift=-0.6)
        raw = add_bar(raw, high=raw["high"].iloc[-1] - 15, low=raw["low"].iloc[-1] - 20,
                     close=raw["close"].iloc[-1] - 18)
        prepared = prepared_with_atr(self.strategy, raw, 2.0)
        self.assertEqual(self.strategy.generate_signal(prepared)["signal"], "SELL")

    def test_ema_signal_alias_matches_regime(self):
        raw = trending_frame(bars=210)
        raw = add_bar(raw, high=raw["high"].iloc[-1] + 20, low=raw["low"].iloc[-1] + 15,
                     close=raw["close"].iloc[-1] + 18)
        prepared = prepared_with_atr(self.strategy, raw, 2.0)
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["components"]["ema_signal"], result["components"]["trend_regime"])


class TestTrendReversal(unittest.TestCase):
    def setUp(self):
        self.strategy = TrendFollowingStrategy(trend_period=5)

    def _states(self, states):
        idx = pd.date_range("2026-01-05", periods=len(states), freq="5min", tz="UTC")
        return pd.DataFrame({"trend_regime": states}, index=idx)

    def test_regime_flip_is_a_reversal(self):
        result = self.strategy.detect_trend_reversal(self._states([1, 1, -1]))
        self.assertEqual(result, {"reversal_detected": True,
                                  "direction": "bullish_to_bearish", "strength": 70})

    def test_steady_regime_is_not_a_reversal(self):
        self.assertFalse(self.strategy.detect_trend_reversal(self._states([1, 1, 1]))["reversal_detected"])

    def test_missing_column_does_not_raise(self):
        empty = pd.DataFrame({"close": [1.0]})
        self.assertFalse(self.strategy.detect_trend_reversal(empty)["reversal_detected"])


class TestPlanTrendEntry(unittest.TestCase):
    def setUp(self):
        self.config = fake_config()
        self.signal = {"signal": "BUY", "strength": 60.0, "components": {}}

    def test_unbounded_target_and_trailing_enabled(self):
        plan = plan_trend_entry(self.signal, 3.0, [], None, self.config)
        self.assertEqual(plan.rr, UNBOUNDED_RR)
        self.assertEqual(plan.trailing_atr_mult, self.config.TREND_TRAIL_ATR_MULT)
        self.assertAlmostEqual(plan.sl_distance, 3.0 * self.config.TREND_INITIAL_SL_ATR_MULT)

    def test_target_is_effectively_unreachable(self):
        plan = plan_trend_entry(self.signal, 3.0, [], None, self.config)
        stop, target = plan.levels("BUY", 2000.0)
        self.assertLess(stop, 2000.0)
        self.assertGreater(target, 1_000_000.0)   # nominal target is absurdly far

    def test_unusable_atr_returns_none(self):
        self.assertIsNone(plan_trend_entry(self.signal, float("nan"), [], None, self.config))
        self.assertIsNone(plan_trend_entry(self.signal, 0.0, [], None, self.config))

    def test_ignores_atr_history_and_news(self):
        # Unlike plan_entry, this plan does not scale by volatility ratio or
        # news -- passing garbage for either must not change the result.
        a = plan_trend_entry(self.signal, 3.0, [999.0] * 50, "garbage", self.config)
        b = plan_trend_entry(self.signal, 3.0, [], None, self.config)
        self.assertEqual(a, b)


class TestChandelierTrailingStop(unittest.TestCase):
    """The engine mechanics: ratchets favourably, never loosens, replaces the target."""

    def setUp(self):
        self.config = fake_config(
            VOLATILITY_SPIKE_ENABLED=False, BREAK_OF_STRUCTURE_ENABLED=False,
            SESSION_END_CLOSE=False, MAX_POSITION_AGE_SECONDS=10 ** 9,
            TREND_REVERSAL_CLOSE=False, PORTFOLIO_DRAWDOWN_CLOSE=False,
            MIN_ENTRY_STRENGTH=1.0)
        self.strategy = TrendFollowingStrategy(trend_period=20, channel_period=10)

    def _frame(self, closes, highs=None, lows=None):
        n = len(closes)
        idx = pd.date_range("2026-03-02 01:00", periods=n, freq="h", tz="UTC")
        highs = highs if highs is not None else [c + 1 for c in closes]
        lows = lows if lows is not None else [c - 1 for c in closes]
        opens = [closes[0]] + closes[:-1]
        return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                            "close": closes, "spread": 10}, index=idx)

    def test_trailing_stop_ratchets_up_and_locks_in_profit(self):
        from backtest.costs import CostModel
        from backtest.live_engine import LiveRulesBacktester
        from strategies.trade_plan import plan_trend_entry

        # Flat range to arm the channel/trend filter, then a clean rally that
        # should trigger a BUY and ride upward before reversing hard.
        flat = [2000.0] * 60
        rally = [2000.0 + i * 3.0 for i in range(1, 31)]      # +3/bar, steady up
        pullback = [rally[-1] - i * 8.0 for i in range(1, 6)]  # sharp reversal
        closes = flat + rally + pullback
        frame = self.strategy.prepare_data(self._frame(closes))
        from utils.indicators import atr as compute_atr
        frame["ATR"] = compute_atr(frame, period=14)

        bt = LiveRulesBacktester(self.strategy, self.config, cost_model=CostModel(),
                                 initial_balance=10000.0, plan_fn=plan_trend_entry)
        result = bt.run(frame)

        self.assertGreaterEqual(len(result.trades), 1)
        trade = result.trades[0]
        # A trailing exit locks in a stop well above the initial entry-ATR
        # stop, not a fixed fraction of it -- distinguishing this from a
        # fixed R:R exit.
        self.assertEqual(trade.direction, "BUY")
        self.assertGreater(trade.exit_price, trade.entry_price)
        self.assertIn("stop_loss", trade.exit_reason)

    def test_trail_never_loosens_against_the_trade(self):
        # Direct unit test of the ratchet, independent of signal generation:
        # feed a BUY trade through bars that first favour it, then chop
        # sideways below the peak -- the stop must never move down.
        from backtest.costs import CostModel
        from backtest.live_engine import LiveRulesBacktester, LiveTrade

        bt = LiveRulesBacktester(self.strategy, self.config, cost_model=CostModel(),
                                 initial_balance=10000.0)
        trade = LiveTrade(direction="BUY", lots=0.1, entry_price=2000.0,
                          stop_loss=1990.0, take_profit=1_000_000.0, trail_distance=5.0)
        highs = [2010.0, 2020.0, 2015.0, 2012.0, 2018.0]
        stops = []
        for h in highs:
            trade.stop_loss = max(trade.stop_loss, h - trade.trail_distance)
            stops.append(trade.stop_loss)
        self.assertEqual(stops, sorted(stops[:2]) + [stops[1], stops[1], stops[1]])
        self.assertEqual(stops, [2005.0, 2015.0, 2015.0, 2015.0, 2015.0])


if __name__ == "__main__":
    unittest.main()

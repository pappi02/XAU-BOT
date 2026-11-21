"""Hypothesis 2: Donchian breakout confirmed by ATR expansion.

Each case has a positive AND a negative variant, same discipline as
tests/test_exit_factors_phase5.py: a factor that can never fire and one that
always fires are both invisible to a one-sided test.
"""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.strategy_breakout import BreakoutStrategy


def range_frame(bars=40, price=2000.0, half_range=2.5, start="2026-01-05"):
    """A quiet range: every bar's high/low stays inside [price-hr, price+hr]."""
    idx = pd.date_range(start, periods=bars, freq="5min", tz="UTC")
    return pd.DataFrame({
        "open": price, "close": price,
        "high": price + half_range, "low": price - half_range,
    }, index=idx)


def add_bar(raw, high, low, close, open_=None):
    """Raw OHLC frame + one more bar (still just OHLC -- no derived columns)."""
    step = raw.index[-1] - raw.index[-2]
    row = pd.DataFrame({"open": [open_ if open_ is not None else close],
                        "high": [high], "low": [low], "close": [close]},
                       index=[raw.index[-1] + step])
    return pd.concat([raw, row])


def prepared_with_atr(strategy, raw, history_atr, last_atr=None):
    """strategy.prepare_data(raw) plus a full ATR column: constant ``history_atr``
    for every bar except the last, which gets ``last_atr`` (default: same)."""
    prepared = strategy.prepare_data(raw)
    prepared["ATR"] = history_atr
    if last_atr is not None:
        prepared.loc[prepared.index[-1], "ATR"] = last_atr
    return prepared


class TestChannelFormation(unittest.TestCase):
    def setUp(self):
        self.strategy = BreakoutStrategy(channel_period=20, rsi_period=14)

    def test_short_history_is_hold(self):
        prepared = prepared_with_atr(self.strategy, range_frame(bars=10), 2.0)
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["signal"], "HOLD")

    def test_channel_excludes_the_current_bar(self):
        # If the channel included the current bar, a bar making a new high
        # could never close ABOVE its own high -- unsatisfiable, like the
        # break_of_structure bug Phase 5.3 fixed.
        raw = range_frame(bars=30)
        prepared = prepared_with_atr(self.strategy, raw, 2.0)
        last = prepared.iloc[-1]
        self.assertAlmostEqual(last["channel_high"], raw["high"].iloc[-2])


class TestBreakoutSignal(unittest.TestCase):
    def setUp(self):
        self.strategy = BreakoutStrategy(channel_period=20, atr_expansion_min=1.1,
                                         rsi_period=14)
        self.raw = range_frame(bars=40)

    def test_no_breakout_is_hold(self):
        prepared = prepared_with_atr(self.strategy, self.raw, 2.0)
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["signal"], "HOLD")

    def test_breakout_up_without_expansion_is_hold(self):
        # ATR history all at 2.0 including the breakout bar: no expansion.
        raw = add_bar(self.raw, high=2010.0, low=2005.0, close=2009.0)
        prepared = prepared_with_atr(self.strategy, raw, 2.0)
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["signal"], "HOLD")
        self.assertIn("without volatility expansion", result["reasons"][0])

    def test_breakout_up_with_expansion_is_buy(self):
        raw = add_bar(self.raw, high=2010.0, low=2005.0, close=2009.0)
        prepared = prepared_with_atr(self.strategy, raw, 2.0, last_atr=5.0)
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["signal"], "BUY")
        self.assertGreater(result["strength"], 0)

    def test_breakout_down_with_expansion_is_sell(self):
        raw = add_bar(self.raw, high=1996.0, low=1990.0, close=1991.0)
        prepared = prepared_with_atr(self.strategy, raw, 2.0, last_atr=5.0)
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["signal"], "SELL")

    def test_breakout_down_without_expansion_is_hold(self):
        raw = add_bar(self.raw, high=1996.0, low=1990.0, close=1991.0)
        prepared = prepared_with_atr(self.strategy, raw, 2.0)
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["signal"], "HOLD")

    def test_strength_increases_with_distance_and_expansion(self):
        near = add_bar(self.raw, high=2001.5, low=1998.0, close=2001.2)
        far = add_bar(self.raw, high=2012.0, low=2005.0, close=2011.0)
        near_prepared = prepared_with_atr(self.strategy, near, 2.0, last_atr=2.3)
        far_prepared = prepared_with_atr(self.strategy, far, 2.0, last_atr=6.0)
        near_strength = self.strategy.generate_signal(near_prepared)["strength"]
        far_strength = self.strategy.generate_signal(far_prepared)["strength"]
        self.assertGreater(far_strength, near_strength)

    def test_strength_is_bounded(self):
        raw = add_bar(self.raw, high=2100.0, low=2005.0, close=2090.0)
        prepared = prepared_with_atr(self.strategy, raw, 2.0, last_atr=50.0)
        result = self.strategy.generate_signal(prepared)
        self.assertLessEqual(result["strength"], 100.0)

    def test_missing_atr_column_never_crashes(self):
        prepared = self.strategy.prepare_data(self.raw)  # no ATR at all
        result = self.strategy.generate_signal(prepared)
        self.assertEqual(result["signal"], "HOLD")


class TestTrendReversal(unittest.TestCase):
    def setUp(self):
        self.strategy = BreakoutStrategy(channel_period=5)

    def _states(self, states):
        n = len(states)
        idx = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
        return pd.DataFrame({"channel_state": states}, index=idx)

    def test_flip_up_to_down_is_a_reversal(self):
        result = self.strategy.detect_trend_reversal(self._states([1, 1, 1, -1]))
        self.assertEqual(result, {"reversal_detected": True,
                                  "direction": "bullish_to_bearish", "strength": 70})

    def test_flip_down_to_up_is_a_reversal(self):
        result = self.strategy.detect_trend_reversal(self._states([-1, -1, 1]))
        self.assertEqual(result["direction"], "bearish_to_bullish")

    def test_move_to_inside_the_channel_is_not_a_reversal(self):
        result = self.strategy.detect_trend_reversal(self._states([1, 1, 0]))
        self.assertFalse(result["reversal_detected"])

    def test_steady_state_is_not_a_reversal(self):
        result = self.strategy.detect_trend_reversal(self._states([1, 1, 1]))
        self.assertFalse(result["reversal_detected"])

    def test_missing_column_or_short_history_does_not_raise(self):
        empty = pd.DataFrame({"close": [1.0]})
        self.assertFalse(self.strategy.detect_trend_reversal(empty)["reversal_detected"])


class TestFullPipeline(unittest.TestCase):
    """Real prepared data end to end, mirroring backtest/live_engine.prepare_frame."""

    def test_synthetic_breakout_series_produces_both_directions(self):
        from utils.indicators import atr as compute_atr

        rng = np.random.default_rng(11)
        n = 600
        # Alternating quiet-range / expansion regimes so both a genuine
        # breakout-with-expansion and plain chop occur.
        closes = [2000.0]
        vol = 1.0
        for i in range(1, n):
            if i % 100 == 0:
                vol = 6.0 if vol == 1.0 else 1.0
            closes.append(closes[-1] + rng.normal(0, vol))
        closes = np.array(closes)
        idx = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
        raw = pd.DataFrame({
            "open": closes, "close": closes,
            "high": closes + np.abs(rng.normal(0.5, 0.3, n)),
            "low": closes - np.abs(rng.normal(0.5, 0.3, n)),
        }, index=idx)

        strategy = BreakoutStrategy(channel_period=20)
        prepared = strategy.prepare_data(raw)
        prepared["ATR"] = compute_atr(prepared, period=14)

        signals = {strategy.generate_signal(prepared.iloc[:i])["signal"]
                  for i in range(60, n)}
        self.assertIn("BUY", signals)
        self.assertIn("SELL", signals)
        self.assertIn("HOLD", signals)

    def test_should_close_trade_accepts_this_strategy(self):
        # Exercises the real integration point: TradeExecutor calls
        # strategy.generate_signal and strategy.detect_trend_reversal without
        # knowing which strategy it is.
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "tests"))
        from fakes import make_executor
        from utils.indicators import atr as compute_atr

        strategy = BreakoutStrategy(channel_period=10)
        rng = np.random.default_rng(3)
        n = 80
        closes = 2000 + np.cumsum(rng.normal(0, 1.0, n))
        idx = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
        raw = pd.DataFrame({"open": closes, "close": closes,
                            "high": closes + 1, "low": closes - 1}, index=idx)
        prepared = strategy.prepare_data(raw)
        prepared["ATR"] = compute_atr(prepared, period=14)

        ex = make_executor()
        position = type("P", (), dict(ticket=1, type=0, time=0,
                                      symbol="XAUUSD", profit=0.0))()
        decision = ex.should_close_trade(position, prepared, strategy, "neutral")
        self.assertIn("should_close", decision)


if __name__ == "__main__":
    unittest.main()

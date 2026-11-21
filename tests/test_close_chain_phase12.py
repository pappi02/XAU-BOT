"""Phase 12.2: the live auto-close decision chain and trend-reversal detector.

``should_close_trade`` runs on every bar with AUTO_CLOSE_ENABLED=True and had
no direct tests. Writing them found three defects, fixed alongside:

* the chain read the global ``config`` module, ignoring the injected config;
* the signal-weakening factor was unsatisfiable (strength < 30 AND >= 70);
* "two consecutive candles" was one list shared by all positions and appended
  per call, so two positions on ONE bar looked like two bars.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import fake_config, make_executor

from strategies.strategy_basic import BasicTradingStrategy
from utils.market_time import BrokerClock


def position(ticket=1, type_=0, age=1000, **overrides):
    # MT5 stamps positions in broker SERVER time, not UTC.
    opened = datetime.now(timezone.utc) - timedelta(seconds=age)
    fields = dict(ticket=ticket, symbol="XAUUSDm", type=type_, volume=0.1,
                  price_open=2000.0, price_current=2000.0, sl=1990.0,
                  tp=2020.0, time=int(BrokerClock().utc_to_server_epoch(opened)),
                  magic=987654321,
                  profit=0.0)
    fields.update(overrides)
    return MagicMock(**fields)


def flat_frame(bars=30, start="2026-01-05"):
    """Flat prices: no structure break, no reversal."""
    closes = [2000.0] * bars
    return pd.DataFrame({
        "close": closes,
        "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes],
    }, index=pd.date_range(start, periods=bars, freq="5min", tz="UTC"))


def next_bar(frame):
    """The same frame advanced by one bar."""
    step = frame.index[-1] - frame.index[-2]
    row = frame.iloc[[-1]].copy()
    row.index = [frame.index[-1] + step]
    return pd.concat([frame, row])


def strategy_reading(signal="HOLD", strength=0, reversal=None):
    strategy = MagicMock()
    strategy.generate_signal.return_value = {"signal": signal, "strength": strength}
    strategy.detect_trend_reversal.return_value = reversal or {
        "reversal_detected": False, "direction": None, "strength": 0}
    return strategy


class ChainHarness(unittest.TestCase):
    def setUp(self):
        # Everything that could fire on a flat frame is switched off, so each
        # test turns on exactly the factor it is about.
        self.config = fake_config(
            VOLATILITY_SPIKE_ENABLED=False, BREAK_OF_STRUCTURE_ENABLED=False,
            PORTFOLIO_DRAWDOWN_CLOSE=False, TREND_REVERSAL_CLOSE=False,
            NEWS_SENTIMENT_CLOSE=False)
        self.ex = make_executor(config=self.config)

    def decide(self, pos, frame, strategy, news="neutral", atr=None):
        return self.ex.should_close_trade(pos, frame, strategy, news, atr_value=atr)

    def two_bars(self, pos, strategy, **kwargs):
        first = flat_frame()
        self.decide(pos, first, strategy, **kwargs)
        return self.decide(pos, next_bar(first), strategy, **kwargs)


class TestChainGuards(ChainHarness):
    def test_uses_the_injected_config_not_the_global_module(self):
        self.config.AUTO_CLOSE_ENABLED = False
        decision = self.decide(position(), flat_frame(), strategy_reading())
        self.assertEqual(decision, {"should_close": False, "reason": "auto_close_disabled"})

    def test_young_position_is_never_closed(self):
        self.config.MAX_POSITION_AGE_SECONDS = 1     # would otherwise fire
        decision = self.decide(position(age=10), flat_frame(), strategy_reading())
        self.assertFalse(decision["should_close"])
        self.assertTrue(decision["reason"].startswith("position_too_young"))

    def test_quiet_market_keeps_the_position(self):
        decision = self.decide(position(), flat_frame(), strategy_reading("BUY", 90))
        self.assertEqual(decision, {"should_close": False, "reason": None})


class TestOppositeSignal(ChainHarness):
    def test_one_opposite_bar_is_not_enough(self):
        decision = self.decide(position(), flat_frame(), strategy_reading("SELL", 90))
        self.assertFalse(decision["should_close"])

    def test_two_opposite_bars_close_a_buy(self):
        decision = self.two_bars(position(), strategy_reading("SELL", 90))
        self.assertTrue(decision["should_close"])
        self.assertEqual(decision["reason"], "opposite_signal")
        self.assertEqual(decision["position_info"]["type"], "BUY")

    def test_two_opposite_bars_close_a_sell(self):
        decision = self.two_bars(position(type_=1), strategy_reading("BUY", 90))
        self.assertEqual(decision["reason"], "opposite_signal")

    def test_weak_opposite_bars_do_not_close(self):
        decision = self.two_bars(position(), strategy_reading("SELL", 69))
        self.assertFalse(decision["should_close"])

    def test_same_direction_bars_do_not_close(self):
        decision = self.two_bars(position(), strategy_reading("BUY", 95))
        self.assertFalse(decision["should_close"])

    def test_re_evaluating_the_same_bar_is_not_a_second_candle(self):
        pos, frame, strategy = position(), flat_frame(), strategy_reading("SELL", 90)
        for _ in range(5):
            decision = self.decide(pos, frame, strategy)
        self.assertFalse(decision["should_close"])

    def test_positions_do_not_share_confirmation_history(self):
        frame, strategy = flat_frame(), strategy_reading("SELL", 90)
        self.decide(position(ticket=1), frame, strategy)
        decision = self.decide(position(ticket=2), frame, strategy)
        self.assertFalse(decision["should_close"])

    def test_history_is_forgotten_with_the_position(self):
        pos, strategy, first = position(), strategy_reading("SELL", 90), flat_frame()
        self.decide(pos, first, strategy)
        self.ex.forget_position(pos.ticket)
        decision = self.decide(pos, next_bar(first), strategy)
        self.assertFalse(decision["should_close"])


class TestSignalWeakening(ChainHarness):
    def test_off_by_default(self):
        decision = self.two_bars(position(), strategy_reading("HOLD", 5))
        self.assertFalse(decision["should_close"])

    def test_two_weak_bars_close_when_enabled(self):
        self.config.SIGNAL_WEAKENING_CLOSE = True
        decision = self.two_bars(position(), strategy_reading("HOLD", 5))
        self.assertEqual(decision["reason"], "signal_weakening")

    def test_one_weak_bar_does_not_close(self):
        self.config.SIGNAL_WEAKENING_CLOSE = True
        decision = self.decide(position(), flat_frame(), strategy_reading("HOLD", 5))
        self.assertFalse(decision["should_close"])

    def test_bars_at_the_threshold_do_not_close(self):
        self.config.SIGNAL_WEAKENING_CLOSE = True
        decision = self.two_bars(position(), strategy_reading("HOLD", 30))
        self.assertFalse(decision["should_close"])


class TestOtherFactors(ChainHarness):
    def test_time_based_exit(self):
        self.config.MAX_POSITION_AGE_SECONDS = 500
        decision = self.decide(position(age=1000), flat_frame(), strategy_reading())
        self.assertEqual(decision["reason"], "time_based_exit")

    def test_volatility_spike_uses_the_atr_recorded_at_entry(self):
        self.config.VOLATILITY_SPIKE_ENABLED = True
        self.ex._entry_atr[1] = 2.0
        self.assertFalse(self.decide(position(), flat_frame(), strategy_reading(), atr=4.0)["should_close"])
        decision = self.decide(position(), flat_frame(), strategy_reading(), atr=4.1)
        self.assertEqual(decision["reason"], "volatility_spike")

    def test_portfolio_drawdown(self):
        self.config.PORTFOLIO_DRAWDOWN_CLOSE = True
        self.ex.risk_manager.state.drawdown_fraction.return_value = 0.40
        decision = self.decide(position(), flat_frame(), strategy_reading())
        self.assertEqual(decision["reason"], "portfolio_drawdown")

    def test_news_needs_score_sentiment_and_two_opposite_bars(self):
        self.config.NEWS_SENTIMENT_CLOSE = True
        news = {"sentiment": "bearish", "avg_sentiment_score": 0.8}
        decision = self.two_bars(position(), strategy_reading("SELL", 90), news=news)
        names = [f["factor"] for f in decision["all_factors"]]
        self.assertIn("news_economic_event", names)

        self.ex.signal_history.clear()
        weak_news = {"sentiment": "bearish", "avg_sentiment_score": 0.2}
        decision = self.two_bars(position(), strategy_reading("SELL", 90), news=weak_news)
        self.assertNotIn("news_economic_event", [f["factor"] for f in decision["all_factors"]])

    def test_every_triggered_factor_is_reported_first_one_as_reason(self):
        self.config.MAX_POSITION_AGE_SECONDS = 500
        decision = self.two_bars(position(), strategy_reading("SELL", 90))
        names = [f["factor"] for f in decision["all_factors"]]
        self.assertEqual(names, ["opposite_signal", "time_based_exit"])
        self.assertEqual(decision["reason"], "opposite_signal")


class TestTrendReversalFactor(ChainHarness):
    def setUp(self):
        super().setUp()
        self.config.TREND_REVERSAL_CLOSE = True
        self.bearish = {"reversal_detected": True, "direction": "bullish_to_bearish", "strength": 100}

    def factors(self, decision):
        return [f["factor"] for f in decision.get("all_factors", [])]

    def test_bearish_reversal_with_confirmation_closes_a_buy(self):
        decision = self.two_bars(position(), strategy_reading("SELL", 90, self.bearish))
        self.assertIn("trend_reversal", self.factors(decision))

    def test_bearish_reversal_does_not_close_a_sell(self):
        decision = self.two_bars(position(type_=1), strategy_reading("SELL", 90, self.bearish))
        self.assertNotIn("trend_reversal", self.factors(decision))

    def test_reversal_without_confirmation_does_not_close(self):
        decision = self.two_bars(position(), strategy_reading("HOLD", 10, self.bearish))
        self.assertFalse(decision["should_close"])

    def test_rsi_reversal_directions_never_close(self):
        rsi = {"reversal_detected": True, "direction": "from_overbought", "strength": 70}
        decision = self.two_bars(position(), strategy_reading("SELL", 90, rsi))
        self.assertNotIn("trend_reversal", self.factors(decision))


class TestDetectTrendReversal(unittest.TestCase):
    def setUp(self):
        self.strategy = BasicTradingStrategy()

    def frame(self, ema_signal, rsi=None, rsi_column="RSI_14"):
        n = len(ema_signal)
        data = {"close": np.full(n, 2000.0), "EMA_signal": ema_signal}
        data[rsi_column] = rsi if rsi is not None else np.full(n, 50.0)
        return pd.DataFrame(data)

    def test_too_little_history(self):
        result = self.strategy.detect_trend_reversal(self.frame([1] * 5 + [-1] * 4))
        self.assertFalse(result["reversal_detected"])

    def test_bullish_to_bearish_crossover(self):
        result = self.strategy.detect_trend_reversal(self.frame([1] * 11 + [-1]))
        self.assertEqual(result, {"reversal_detected": True,
                                  "direction": "bullish_to_bearish", "strength": 100})

    def test_bearish_to_bullish_crossover(self):
        result = self.strategy.detect_trend_reversal(self.frame([-1] * 11 + [1]))
        self.assertEqual(result["direction"], "bearish_to_bullish")

    def test_crossover_from_flat_is_half_strength(self):
        result = self.strategy.detect_trend_reversal(self.frame([0] * 11 + [1]))
        self.assertEqual(result["strength"], 50)

    def test_move_to_flat_is_not_a_reversal(self):
        result = self.strategy.detect_trend_reversal(self.frame([1] * 11 + [0]))
        self.assertFalse(result["reversal_detected"])

    def test_steady_trend_is_not_a_reversal(self):
        result = self.strategy.detect_trend_reversal(self.frame([1] * 12))
        self.assertFalse(result["reversal_detected"])

    def test_rsi_leaving_oversold(self):
        rsi = [50.0] * 10 + [25.0, 40.0]
        result = self.strategy.detect_trend_reversal(self.frame([1] * 12, rsi))
        self.assertEqual(result["direction"], "from_oversold")

    def test_rsi_leaving_overbought(self):
        rsi = [50.0] * 10 + [75.0, 60.0]
        result = self.strategy.detect_trend_reversal(self.frame([1] * 12, rsi))
        self.assertEqual(result["direction"], "from_overbought")

    def test_rsi_still_extreme_is_not_a_reversal(self):
        rsi = [50.0] * 10 + [25.0, 33.0]
        result = self.strategy.detect_trend_reversal(self.frame([1] * 12, rsi))
        self.assertFalse(result["reversal_detected"])

    def test_uses_the_configured_rsi_period(self):
        strategy = BasicTradingStrategy(rsi_period=21)
        rsi = [50.0] * 10 + [75.0, 60.0]
        result = strategy.detect_trend_reversal(self.frame([1] * 12, rsi, "RSI_21"))
        self.assertEqual(result["direction"], "from_overbought")

    def test_missing_indicator_columns_do_not_raise(self):
        data = pd.DataFrame({"close": np.full(12, 2000.0)})
        self.assertFalse(self.strategy.detect_trend_reversal(data)["reversal_detected"])

    def test_nan_rsi_warmup_is_not_a_reversal(self):
        rsi = [np.nan] * 12
        result = self.strategy.detect_trend_reversal(self.frame([1] * 12, rsi))
        self.assertFalse(result["reversal_detected"])

    def test_real_prepared_data_round_trip(self):
        rng = np.random.default_rng(7)
        closes = 2000 + np.cumsum(rng.normal(0, 2, 300))
        raw = pd.DataFrame({"open": closes, "high": closes + 1, "low": closes - 1, "close": closes})
        prepared = self.strategy.prepare_data(raw)
        seen = {self.strategy.detect_trend_reversal(prepared.iloc[:i])["direction"]
                for i in range(30, len(prepared))}
        self.assertIn("bullish_to_bearish", seen)
        self.assertIn("bearish_to_bullish", seen)


if __name__ == "__main__":
    unittest.main()

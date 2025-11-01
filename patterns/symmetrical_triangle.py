"""
Symmetrical Triangle pattern detection for M5 timeframe.
"""

import numpy as np
from .base_pattern import BasePattern

class SymmetricalTriangle(BasePattern):
    """
    Detects a Symmetrical Triangle pattern on the chart (M5 timeframe by default).
    75% of these patterns are continuation patterns; 25% signal reversal.
    """

    def __init__(self, candles, timeframe="M5"):
        super().__init__(candles)
        self.timeframe = timeframe

    def detect(self):
        # Use last 40 candles for analysis
        candles = self.candles[-40:]

        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        closes = np.array([c["close"] for c in candles])

        # Calculate simple linear regression (trendlines)
        x = np.arange(len(candles))
        high_slope, high_intercept = np.polyfit(x, highs, 1)
        low_slope, low_intercept = np.polyfit(x, lows, 1)

        # Convergence condition: highs trend down, lows trend up
        converging = (high_slope < 0) and (low_slope > 0)

        # Detect proximity (if upper and lower lines are close)
        spread_ratio = (highs[-1] - lows[-1]) / np.mean(highs)
        tight_convergence = spread_ratio < 0.015  # within 1.5%

        detected = converging and tight_convergence

        # Identify current direction
        last_close = closes[-1]
        prev_trend = "bullish" if closes[-10] < closes[-1] else "bearish"

        # Probability logic based on market statistics
        continuation_chance = 0.75
        reversal_chance = 0.25

        if detected:
            if prev_trend == "bullish":
                direction = "bullish" if np.random.random() < continuation_chance else "bearish"
            else:
                direction = "bearish" if np.random.random() < continuation_chance else "bullish"
            confidence = 0.8
        else:
            direction = None
            confidence = 0.0

        breakout_price = float(last_close) if detected else None

        return {
            "detected": detected,
            "direction": direction,
            "timeframe": self.timeframe,
            "breakout_price": breakout_price,
            "confidence": confidence,
            "prev_trend": prev_trend
        }

    def describe(self):
        return (
            "A symmetrical triangle forms when highs and lows converge, creating narrowing price action. "
            "It reflects market indecision followed by a breakout. "
            "Statistically, 75% of symmetrical triangles are continuation patterns and 25% are reversals. "
            "This pattern is analyzed on the 5-minute (M5) timeframe."
        )

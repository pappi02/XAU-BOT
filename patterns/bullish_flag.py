# patterns/bullish_flag.py

import numpy as np
from .base_pattern import BasePattern

class BullishFlag(BasePattern):
    """
    Detects a Bullish Flag pattern on the chart.
    A Bullish Flag is a short-term continuation pattern that forms after a strong upward move,
    followed by a period of consolidation in a downward-sloping channel or sideways range.
    """

    def __init__(self, candles, timeframe="M5"):
        super().__init__(candles)
        self.timeframe = timeframe

    def detect(self):
        # Use the last 50 candles for structure analysis
        candles = self.candles[-50:]

        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        closes = np.array([c["close"] for c in candles])

        # --- Step 1: Detect strong upward impulse (the "flagpole") ---
        # Compare last 50 vs 20 candles ago — price must have risen sharply.
        pole_gain = (closes[-20] - closes[0]) / closes[0]
        strong_up_impulse = pole_gain > 0.015  # >1.5% upward move

        # --- Step 2: Identify consolidation (the "flag") ---
        # After impulse, detect mild downward/sideways channel
        consolidation_highs = highs[-20:]
        consolidation_lows = lows[-20:]

        x = np.arange(len(consolidation_highs))
        high_slope, _ = np.polyfit(x, consolidation_highs, 1)
        low_slope, _ = np.polyfit(x, consolidation_lows, 1)

        # The flag typically slopes slightly downward or moves sideways
        flag_shape = (high_slope < 0 and low_slope < 0) or (abs(high_slope) < 0.0005)

        # --- Step 3: Detect breakout potential ---
        last_close = closes[-1]
        flag_high = np.max(consolidation_highs)
        breakout_condition = last_close > flag_high * 0.998  # price touching or nearing breakout

        # --- Step 4: Confirm pattern detection ---
        detected = strong_up_impulse and flag_shape
        confidence = 0.0
        direction = None
        breakout_price = None

        if detected:
            direction = "bullish"
            confidence = 0.85 if breakout_condition else 0.7
            breakout_price = float(flag_high)

        return {
            "detected": detected,
            "direction": direction,
            "timeframe": self.timeframe,
            "breakout_price": breakout_price,
            "confidence": confidence,
            "flag_slope": (high_slope + low_slope) / 2,
            "pole_gain": pole_gain,
        }

    def describe(self):
        return (
            "The Bullish Flag pattern is a short-term continuation formation that appears "
            "after a sharp upward movement (the flagpole). It is followed by a mild downward "
            "or sideways consolidation (the flag). When price breaks above the flag’s upper boundary, "
            "it often signals the continuation of the bullish trend. Typically forms over 1–3 weeks, "
            "but on the M5 timeframe it’s interpreted as a short consolidation phase."
        )

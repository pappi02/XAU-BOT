import numpy as np
from .base_pattern import BasePattern

class BearishFlag(BasePattern):
    """
    Detects a Bearish Flag pattern on the chart.
    A Bearish Flag is a short-term continuation pattern that forms after a strong downward move,
    followed by a period of consolidation in an upward-sloping channel or sideways range.
    """

    def __init__(self, candles, timeframe="M5"):
        super().__init__(candles)
        self.timeframe = timeframe

    def detect(self):
        # Use the last 50 candles for analysis
        candles = self.candles[-50:]
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        closes = np.array([c["close"] for c in candles])

        # --- Step 1: Detect strong downward impulse (the "flagpole") ---
        # Compare last 50 vs 20 candles ago — price must have fallen sharply.
        pole_loss = (closes[-20] - closes[0]) / closes[0]
        strong_down_impulse = pole_loss < -0.015  # <-1.5% downward move

        # --- Step 2: Identify consolidation (the "flag") ---
        # After impulse, detect mild upward/sideways channel
        consolidation_highs = highs[-20:]
        consolidation_lows = lows[-20:]
        x = np.arange(len(consolidation_highs))
        high_slope, _ = np.polyfit(x, consolidation_highs, 1)
        low_slope, _ = np.polyfit(x, consolidation_lows, 1)

        # The flag typically slopes slightly upward or moves sideways
        flag_shape = (high_slope > 0 and low_slope > 0) or (abs(high_slope) < 0.0005)

        # --- Step 3: Detect breakout potential ---
        last_close = closes[-1]
        flag_low = np.min(consolidation_lows)
        breakout_condition = last_close < flag_low * 1.002  # price touching or nearing breakout (below low)

        # --- Step 4: Confirm pattern detection ---
        detected = strong_down_impulse and flag_shape
        confidence = 0.0
        direction = None
        breakout_price = None
        if detected:
            direction = "bearish"
            confidence = 0.85 if breakout_condition else 0.7
            breakout_price = float(flag_low)

        return {
            "detected": detected,
            "direction": direction,
            "timeframe": self.timeframe,
            "breakout_price": breakout_price,
            "confidence": confidence,
            "flag_slope": (high_slope + low_slope) / 2,
            "pole_loss": pole_loss,
        }

    def describe(self):
        return (
            "The Bearish Flag pattern is a short-term continuation formation that appears "
            "after a sharp downward movement (the flagpole). It is followed by a mild upward "
            "or sideways consolidation (the flag). When price breaks below the flag’s lower boundary, "
            "it often signals the continuation of the bearish trend. Typically forms over 1–3 weeks, "
            "but on the M5 timeframe it’s interpreted as a short consolidation phase."
        )

import numpy as np
from .base_pattern import BasePattern

class RisingWedge(BasePattern):
    """
    Detects a Rising Wedge pattern on the chart.
    A Rising Wedge is a bearish continuation or reversal pattern that forms in an uptrend.
    It is characterized by two converging trendlines that slope upward: a rising support line 
    (higher lows) and a rising resistance line (higher highs), but with the resistance rising 
    more steeply, indicating weakening momentum. The pattern is completed when price breaks 
    below the support line.
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

        # --- Step 1: Confirm uptrend context ---
        # Check if overall trend is upward (price gain over period)
        trend_gain = (closes[-1] - closes[0]) / closes[0]
        uptrend = trend_gain > 0.01  # >1% gain indicating uptrend

        # --- Step 2: Identify wedge shape (converging rising lines) ---
        # Last 20 candles for the pattern formation
        wedge_highs = highs[-20:]
        wedge_lows = lows[-20:]

        x = np.arange(len(wedge_highs))
        high_slope, high_intercept = np.polyfit(x, wedge_highs, 1)
        low_slope, low_intercept = np.polyfit(x, wedge_lows, 1)

        # Rising wedge: both lines rising, but resistance (highs) steeper than support (lows)
        rising_support = low_slope > 0
        rising_resistance = high_slope > low_slope > 0  # high_slope > low_slope for convergence
        wedge_shape = rising_support and rising_resistance

        # Convergence check: lines getting closer
        initial_spread = wedge_highs[0] - wedge_lows[0]
        final_spread = wedge_highs[-1] - wedge_lows[-1]
        converging = final_spread < initial_spread * 0.85  # narrowing by at least 15%

        # --- Step 3: Detect breakout potential (bearish break below support) ---
        last_close = closes[-1]
        support_line = low_slope * (len(closes) - 1) + low_intercept  # project support at end
        breakout_condition = last_close < support_line * 1.002  # price touching or breaking below support

        # --- Step 4: Confirm pattern detection ---
        detected = uptrend and wedge_shape and converging
        confidence = 0.0
        direction = None
        breakout_price = None

        if detected:
            direction = "bearish"
            confidence = 0.85 if breakout_condition else 0.7
            breakout_price = float(support_line)

        return {
            "detected": detected,
            "direction": direction,
            "timeframe": self.timeframe,
            "breakout_price": breakout_price,
            "confidence": confidence,
            "high_slope": high_slope,
            "low_slope": low_slope,
            "trend_gain": trend_gain,
            "convergence_ratio": final_spread / initial_spread if initial_spread > 0 else 0,
        }

    def describe(self):
        return (
            "The Rising Wedge pattern is a bearish reversal or continuation formation that appears "
            "in an uptrend. It features two converging upward-sloping trendlines: a rising support "
            "(higher lows) and a steeper rising resistance (higher highs), indicating diminishing "
            "buying pressure. When price breaks below the support line, it often signals a reversal "
            "or continuation of the downtrend. Typically forms over a few weeks, but on the M5 timeframe "
            "it’s interpreted as short-term weakening momentum in an uptrend."
        )

class FallingWedge(BasePattern):
    """
    Detects a Falling Wedge pattern on the chart.
    A Falling Wedge is a bullish continuation or reversal pattern that forms in a downtrend.
    It is characterized by two converging trendlines that slope downward: a falling support line 
    (lower lows) and a falling resistance line (lower highs), but with the support falling 
    more steeply, indicating increasing buying interest. The pattern is completed when price breaks 
    above the resistance line.
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

        # --- Step 1: Confirm downtrend context ---
        # Check if overall trend is downward (price loss over period)
        trend_loss = (closes[0] - closes[-1]) / closes[0]
        downtrend = trend_loss > 0.01  # >1% loss indicating downtrend

        # --- Step 2: Identify wedge shape (converging falling lines) ---
        # Last 20 candles for the pattern formation
        wedge_highs = highs[-20:]
        wedge_lows = lows[-20:]

        x = np.arange(len(wedge_highs))
        high_slope, high_intercept = np.polyfit(x, wedge_highs, 1)
        low_slope, low_intercept = np.polyfit(x, wedge_lows, 1)

        # Falling wedge: both lines falling, but support (lows) steeper than resistance (highs)
        falling_support = low_slope < 0
        falling_resistance = high_slope < low_slope < 0  # low_slope < high_slope for convergence (since both negative)
        wedge_shape = falling_support and falling_resistance

        # Convergence check: lines getting closer
        initial_spread = wedge_highs[0] - wedge_lows[0]
        final_spread = wedge_highs[-1] - wedge_lows[-1]
        converging = final_spread < initial_spread * 0.85  # narrowing by at least 15%

        # --- Step 3: Detect breakout potential (bullish break above resistance) ---
        last_close = closes[-1]
        resistance_line = high_slope * (len(closes) - 1) + high_intercept  # project resistance at end
        breakout_condition = last_close > resistance_line * 0.998  # price touching or breaking above resistance

        # --- Step 4: Confirm pattern detection ---
        detected = downtrend and wedge_shape and converging
        confidence = 0.0
        direction = None
        breakout_price = None

        if detected:
            direction = "bullish"
            confidence = 0.85 if breakout_condition else 0.7
            breakout_price = float(resistance_line)

        return {
            "detected": detected,
            "direction": direction,
            "timeframe": self.timeframe,
            "breakout_price": breakout_price,
            "confidence": confidence,
            "high_slope": high_slope,
            "low_slope": low_slope,
            "trend_loss": trend_loss,
            "convergence_ratio": final_spread / initial_spread if initial_spread > 0 else 0,
        }

    def describe(self):
        return (
            "The Falling Wedge pattern is a bullish reversal or continuation formation that appears "
            "in a downtrend. It features two converging downward-sloping trendlines: a falling support "
            "(lower lows) and a steeper falling resistance (lower highs), indicating increasing "
            "buying pressure. When price breaks above the resistance line, it often signals a reversal "
            "or continuation of the uptrend. Typically forms over a few weeks, but on the M5 timeframe "
            "it’s interpreted as short-term strengthening momentum in a downtrend."
        )

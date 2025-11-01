"""
Channel pattern detection module.
Contains functions for detecting bullish, bearish, and horizontal channels.
"""

import numpy as np
from scipy.stats import linregress

def _fit_regression(data):
    x = np.arange(len(data))
    slope, intercept, r_value, _, _ = linregress(x, data)
    return slope, intercept, r_value


def detect_bullish_channel(df, lookback=120, tolerance=0.05):
    """
    Detect upward-sloping parallel channel → Bullish continuation pattern
    """
    if len(df) < lookback:
        return {"detected": False, "confidence": 0.0}

    data = df[-lookback:]
    highs = data['high'].values
    lows = data['low'].values

    slope_high, _, r_high = _fit_regression(highs)
    slope_low, _, r_low = _fit_regression(lows)

    if slope_high <= 0 or slope_low <= 0:
        return {"detected": False, "confidence": 0.0}

    slope_diff = abs(slope_high - slope_low)
    max_slope = max(abs(slope_high), abs(slope_low))

    if slope_diff > tolerance * max_slope:
        return {"detected": False, "confidence": 0.0}

    confidence = (
        0.5 * (1 - abs(slope_diff / max_slope)) +
        0.25 * abs(r_high) +
        0.25 * abs(r_low)
    )

    return {
        "detected": True,
        "confidence": round(confidence, 3),
        "type": "bullish_channel"
    }


def detect_bearish_channel(df, lookback=120, tolerance=0.05):
    """
    Detect downward-sloping parallel channel → Bearish continuation pattern
    """
    if len(df) < lookback:
        return {"detected": False, "confidence": 0.0}

    data = df[-lookback:]
    highs = data['high'].values
    lows = data['low'].values

    slope_high, _, r_high = _fit_regression(highs)
    slope_low, _, r_low = _fit_regression(lows)

    if slope_high >= 0 or slope_low >= 0:
        return {"detected": False, "confidence": 0.0}

    slope_diff = abs(slope_high - slope_low)
    max_slope = max(abs(slope_high), abs(slope_low))

    if slope_diff > tolerance * max_slope:
        return {"detected": False, "confidence": 0.0}

    confidence = (
        0.5 * (1 - abs(slope_diff / max_slope)) +
        0.25 * abs(r_high) +
        0.25 * abs(r_low)
    )

    return {
        "detected": True,
        "confidence": round(confidence, 3),
        "type": "bearish_channel"
    }


def detect_horizontal_channel(df, lookback=180, tolerance=0.01):
    """
    Sideways / Range-bound channel — horizontal accumulation or distribution
    Works best over longer periods (can last months)
    """
    if len(df) < lookback:
        return {"detected": False, "confidence": 0.0}

    data = df[-lookback:]
    highs = data['high'].values
    lows = data['low'].values

    slope_high, _, r_high = _fit_regression(highs)
    slope_low, _, r_low = _fit_regression(lows)

    # Slopes must be ~0 (horizontal)
    if abs(slope_high) > tolerance or abs(slope_low) > tolerance:
        return {"detected": False, "confidence": 0.0}

    # Confidence factors: flatness + line fit
    flat_score = 1 - (abs(slope_high) + abs(slope_low)) / (2 * tolerance)
    confidence = (
        0.4 * flat_score +
        0.3 * abs(r_high) +
        0.3 * abs(r_low)
    )

    return {
        "detected": True,
        "confidence": round(confidence, 3),
        "type": "horizontal_channel"
    }

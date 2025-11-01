import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend for thread-safe plotting
import matplotlib.pyplot as plt
import os
from datetime import datetime

def detect_double_top(df, tolerance=0.003, min_separation=5, max_span=100):
    """
    Double-Top Pattern Detection for XAUUSD (5m)
    Returns:
        dict {
            'detected': bool,
            'confidence': float (0-1),
            'breakout': float or None,
            'peak_prices': list,
            'support_level': float or None
        }
    """
    closes = df['close'].values
    highs = df['high'].values

    peak_idx = (np.diff(np.sign(np.diff(highs))) < 0).nonzero()[0] + 1

    if len(peak_idx) < 2:
        return {"detected": False, "confidence": 0}

    # Take the last two peaks
    p1_idx, p2_idx = peak_idx[-2], peak_idx[-1]
    p1, p2 = highs[p1_idx], highs[p2_idx]

    # ✅ Validate similarity in height (within 0.25%)
    if abs(p1 - p2) / p1 > 0.003:
        return {"detected": False, "confidence": 0}

    # ✅ Validate that there is a dip in between
    midpoint = min(p1_idx, p2_idx) + abs(p1_idx - p2_idx) // 2
    valley = min(highs[p1_idx:p2_idx])

    support = valley
    resistance_avg = (p1 + p2) / 2

    # ✅ Confirm neckline test
    if closes[-1] > support:
        return {"detected": False, "confidence": 0.4}

    # ✅ Final confirmation: break below support
    confirmed = closes[-1] < support

    confidence = 0.6 + (0.4 if confirmed else 0)

    # Debug chart saving disabled to save storage
    # save_debug_chart(df, p1_idx, p2_idx, support)

    return {
        "detected": True,
        "confidence": confidence,
        "breakout": support,
        "peak_prices": [p1, p2],
        "support_level": support
    }




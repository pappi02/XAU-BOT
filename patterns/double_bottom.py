import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
from datetime import datetime

def detect_double_bottom(df, tolerance=0.003, min_separation=5, max_span=100):
    """
    Double-Bottom Pattern Detection for XAUUSD (5m)
    Returns:
        dict {
            'detected': bool,
            'confidence': float,
            'breakout': float or None,
            'bottom_prices': list,
            'neckline': float or None
        }
    """
    closes = df['close'].values
    lows = df['low'].values

    # Find local lows
    low_idx = (np.diff(np.sign(np.diff(lows))) > 0).nonzero()[0] + 1

    if len(low_idx) < 2:
        return {"detected": False, "confidence": 0}

    # Use the last two lows
    b1_idx, b2_idx = low_idx[-2], low_idx[-1]
    b1, b2 = lows[b1_idx], lows[b2_idx]

    # ✅ Validate similarity in low height (within 0.25%)
    if abs(b1 - b2) / b1 > 0.003:
        return {"detected": False, "confidence": 0}

    # ✅ Neckline = swing high between bottoms
    midpoint = min(b1_idx, b2_idx) + abs(b1_idx - b2_idx) // 2
    neckline = max(closes[b1_idx:b2_idx])

    # ✅ Confirmation rule: breakout above neckline
    confirmed = closes[-1] > neckline

    confidence = 0.6 + (0.4 if confirmed else 0)

    # Debug chart saving disabled to save storage
    # save_debug_chart(df, b1_idx, b2_idx, neckline)

    return {
        "detected": True,
        "confidence": confidence,
        "breakout": neckline,
        "bottom_prices": [b1, b2],
        "neckline": neckline
    }




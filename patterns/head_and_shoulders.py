import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend for thread-safe plotting
import matplotlib.pyplot as plt
import os
from datetime import datetime

# ---------------------------
# Head & Shoulders detector
# ---------------------------
# Detects both regular Head & Shoulders (bearish reversal) and
# Inverse Head & Shoulders (bullish reversal).
#
# Heuristics:
# - Find local peaks and troughs (simple derivative sign changes)
# - Look for pattern: shoulder1 - head - shoulder2 (peaks) with troughs between
# - Head must be sufficiently higher/lower than shoulders (head_prominence)
# - Shoulders heights should be reasonably similar (shoulder_symmetry_tol)
# - Neckline defined by line connecting two troughs; breakout requires a close beyond neckline
#
# Returns a dict with:
#   - detected: bool
#   - type: "head_and_shoulders" | "inverse_head_and_shoulders" | None
#   - confidence: 0..1
#   - neckline: float or None
#   - head_idx, left_shoulder_idx, right_shoulder_idx
#   - debug_chart: path or None
#
# This implementation is intentionally dependency-light (numpy/matplotlib only).

def _local_extrema(arr):
    """Return indices of local minima and maxima."""
    # simple derivative sign change approach
    d = np.diff(arr)
    sign = np.sign(d)
    sign_change = np.diff(sign)
    # maxima where sign_change < 0 ( +1 -> -1 ) ; minima where > 0
    max_idx = np.where(sign_change < 0)[0] + 1
    min_idx = np.where(sign_change > 0)[0] + 1
    return np.asarray(min_idx, dtype=int), np.asarray(max_idx, dtype=int)

def detect_head_and_shoulders(df,
                              price_col='close',
                              lookback=300,
                              head_prominence=0.005,
                              shoulder_symmetry_tol=0.03,
                              min_shoulder_distance=3,
                              max_shoulder_distance=60,
                              neckline_break_confirm_bars=1,
                              debug=True,
                              tolerance=None,
                              min_separation=None,
                              max_span=None):
    """
    Detect head & shoulders or inverse head & shoulders in provided OHLC pandas-like df.
    df must have numeric columns including the price_col and ideally 'low'/'high' for plotting.
    lookback: how many recent bars to analyze (default 300)
    head_prominence: minimal relative difference required between head and average shoulders (fraction)
    shoulder_symmetry_tol: how similar the two shoulders must be (relative tolerance)
    min_shoulder_distance/max_shoulder_distance: index distance constraints between shoulders and head
    neckline_break_confirm_bars: number of bars after breakout to consider confirmation (1 uses current close)
    debug: save debug chart
    """
    prices = df[price_col].values
    n = len(prices)
    if n < 30:
        return {"detected": False, "type": None, "confidence": 0.0}

    # limit to lookback window
    prices = prices[-lookback:]
    offset = max(0, len(df) - lookback)

    mins, maxs = _local_extrema(prices)
    if len(mins) < 2 or len(maxs) < 3:
        return {"detected": False, "type": None, "confidence": 0.0}

    # Search for triplet of peaks (shoulder-left, head, shoulder-right)
    results = []
    for i in range(len(maxs)):
        for j in range(i+1, len(maxs)):
            for k in range(j+1, len(maxs)):
                l_idx, h_idx, r_idx = maxs[i], maxs[j], maxs[k]
                # ensure order and distances
                if not (l_idx < h_idx < r_idx):
                    continue
                dist_lh = h_idx - l_idx
                dist_hr = r_idx - h_idx
                # ensure shoulders aren't too close or too far
                if dist_lh < min_shoulder_distance or dist_hr < min_shoulder_distance:
                    continue
                if dist_lh > max_shoulder_distance or dist_hr > max_shoulder_distance:
                    continue

                left_shoulder = prices[l_idx]
                head = prices[h_idx]
                right_shoulder = prices[r_idx]

                # Candidate for H&S (head higher than shoulders) or IH&S (head lower than shoulders)
                avg_shoulders = (left_shoulder + right_shoulder) / 2.0

                # relative differences
                if head > avg_shoulders:  # possible regular H&S (bearish reversal)
                    rel = (head - avg_shoulders) / avg_shoulders
                    if rel < head_prominence:
                        continue
                    # shoulders similarity
                    if abs(left_shoulder - right_shoulder) / avg_shoulders > shoulder_symmetry_tol:
                        continue
                    pattern_type = "head_and_shoulders"
                else:  # possible inverse H&S (bullish reversal)
                    rel = (avg_shoulders - head) / avg_shoulders
                    if rel < head_prominence:
                        continue
                    if abs(left_shoulder - right_shoulder) / avg_shoulders > shoulder_symmetry_tol:
                        continue
                    pattern_type = "inverse_head_and_shoulders"

                # find troughs between peaks to define neckline points
                # trough between left_shoulder and head
                trough_candidates = mins[(mins > l_idx) & (mins < h_idx)]
                if trough_candidates.size == 0:
                    continue
                trough_left = trough_candidates[np.argmin(prices[trough_candidates])]

                # trough between head and right_shoulder
                trough_candidates = mins[(mins > h_idx) & (mins < r_idx)]
                if trough_candidates.size == 0:
                    continue
                trough_right = trough_candidates[np.argmin(prices[trough_candidates])]

                neckline_y1 = prices[trough_left]
                neckline_y2 = prices[trough_right]
                neckline_idx1 = trough_left
                neckline_idx2 = trough_right

                # neckline equation (linear): y = m*x + b, we'll compute at latest index
                x1, x2 = neckline_idx1, neckline_idx2
                m = (neckline_y2 - neckline_y1) / (x2 - x1) if (x2 != x1) else 0.0
                b = neckline_y1 - m * x1

                # compute neckline value at last bar index
                last_idx = len(prices) - 1
                neckline_at_last = m * last_idx + b

                # Confirmation: breakout condition
                latest_close = prices[-1]
                breakout = False
                if pattern_type == "head_and_shoulders":
                    # bearish: price closes below the neckline
                    breakout = latest_close < neckline_at_last
                else:
                    # inverse: price closes above the neckline
                    breakout = latest_close > neckline_at_last

                # compute confidence: base + shape quality + breakout bonus
                shape_quality = min(1.0, rel / (head_prominence * 4))  # normalized
                symmetry_quality = 1.0 - min(1.0, abs(left_shoulder - right_shoulder) / avg_shoulders)
                dist_quality = 1.0 - (abs(dist_lh - dist_hr) / max(dist_lh, dist_hr) if max(dist_lh, dist_hr) > 0 else 0)
                confidence = 0.4 * shape_quality + 0.3 * symmetry_quality + 0.2 * dist_quality + (0.1 if breakout else 0.0)
                confidence = float(max(0.0, min(1.0, confidence)))

                results.append({
                    "type": pattern_type,
                    "left_shoulder_idx": l_idx + offset,
                    "head_idx": h_idx + offset,
                    "right_shoulder_idx": r_idx + offset,
                    "neckline_idx1": neckline_idx1 + offset,
                    "neckline_idx2": neckline_idx2 + offset,
                    "neckline_value": float((neckline_y1 + neckline_y2) / 2.0),
                    "neckline_at_last": float(neckline_at_last),
                    "breakout": bool(breakout),
                    "confidence": confidence,
                    "indices_relative": (l_idx, h_idx, r_idx, neckline_idx1, neckline_idx2)
                })

    if not results:
        return {"detected": False, "type": None, "confidence": 0.0}

    # pick best candidate by confidence
    best = max(results, key=lambda x: x["confidence"])

    # Debug chart saving disabled to save storage
    debug_path = None
    # if debug:
    #     debug_path = _save_debug_chart(df, best, price_col, lookback)

    return {
        "detected": True,
        "type": best["type"],
        "confidence": best["confidence"],
        "neckline": best["neckline_value"],
        "neckline_at_last": best["neckline_at_last"],
        "breakout": best["breakout"],
        "left_shoulder_idx": best["left_shoulder_idx"],
        "head_idx": best["head_idx"],
        "right_shoulder_idx": best["right_shoulder_idx"],
        "debug_chart": debug_path
    }



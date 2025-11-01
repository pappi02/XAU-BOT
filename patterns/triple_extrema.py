import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# NOTE: function assumes df has columns: ['open','high','low','close','volume'(optional)]
# Index is integer 0..N-1 (use df.reset_index(drop=True) before passing)

def _find_peaks(arr, lookback=3):
    """Return indices of local maxima using simple neighborhood check."""
    peaks = []
    for i in range(lookback, len(arr) - lookback):
        window = arr[i - lookback:i + lookback + 1]
        if arr[i] == max(window):
            # strict local max (not necessarily unique)
            peaks.append(i)
    return peaks

def _find_troughs(arr, lookback=3):
    troughs = []
    for i in range(lookback, len(arr) - lookback):
        window = arr[i - lookback:i + lookback + 1]
        if arr[i] == min(window):
            troughs.append(i)
    return troughs

def detect_triple_top(df,
                      lookback=3,
                      tolerance=0.004,            # max relative difference between tops
                      min_separation=6,           # min candles between tops
                      max_span=60,                # max span (candles) from first to last top
                      confirmation_lookforward=3, # candles to confirm neckline breach
                      require_neckline_break=True,
                      min_strength=60):
    """
    Detect Triple Top pattern. Returns dict or None.
    """
    closes = df['close'].to_numpy()
    highs = df['high'].to_numpy()

    # find peaks in highs
    peaks = _find_peaks(highs, lookback=lookback)
    if len(peaks) < 3:
        return None

    # consider last window of peaks (sliding)
    for i in range(len(peaks) - 2):
        p1, p2, p3 = peaks[i], peaks[i+1], peaks[i+2]
        # spacing constraints
        if not ( (p2 - p1) >= min_separation and (p3 - p2) >= min_separation):
            continue
        if (p3 - p1) > max_span:
            continue

        top1, top2, top3 = highs[p1], highs[p2], highs[p3]
        mean_top = np.mean([top1, top2, top3])
        # tolerance check (relative)
        if any(abs(t - mean_top)/mean_top > tolerance for t in (top1, top2, top3)):
            continue

        # neckline: local lows between tops -> typically the highest of the two troughs between tops
        between1_low = np.min(df['low'].iloc[p1:p2+1])
        between2_low = np.min(df['low'].iloc[p2:p3+1])
        neckline = max(between1_low, between2_low)

        # confirmation: does price break below neckline in next confirmation_lookforward candles?
        confirmed = False
        if require_neckline_break:
            end_idx = min(len(closes)-1, p3 + confirmation_lookforward)
            # check any close below neckline after p3 (including p3+1..end_idx)
            for j in range(p3+1, end_idx+1):
                if closes[j] < neckline:
                    confirmed = True
                    confirm_index = j
                    break
        else:
            confirmed = True
            confirm_index = p3

        if not confirmed:
            continue

        # strength scoring
        score = 50
        # deeper neckline (bigger top-to-neck height) => stronger
        height = mean_top - neckline
        rel_height = height / mean_top if mean_top != 0 else 0
        score += min(30, int(rel_height * 300))  # scales: ~0.1 -> 30
        # closer equal tops adds score
        tops_dev = np.std([top1, top2, top3]) / mean_top if mean_top!=0 else 1
        score += max(0, int((1 - tops_dev) * 20))
        # volume or candle confirmation bonus (if available)
        if 'volume' in df.columns:
            vol_avg = df['volume'].iloc[p1:p3].mean()
            vol_confirm = df['volume'].iloc[confirm_index] if confirm_index < len(df) else 0
            if vol_confirm > vol_avg * 1.1:
                score += 10

        score = int(min(100, score))

        return {
            "pattern": "triple_top",
            "p1": int(p1), "p2": int(p2), "p3": int(p3),
            "top1": float(top1), "top2": float(top2), "top3": float(top3),
            "neckline": float(neckline),
            "confirm_index": int(confirm_index),
            "height": float(height),
            "strength": score
        }
    return None

def detect_triple_bottom(df,
                         lookback=3,
                         tolerance=0.004,
                         min_separation=6,
                         max_span=60,
                         confirmation_lookforward=3,
                         require_neckline_break=True,
                         min_strength=60):
    """
    Detect Triple Bottom pattern. Returns dict or None.
    """
    closes = df['close'].to_numpy()
    lows = df['low'].to_numpy()

    troughs = _find_troughs(lows, lookback=lookback)
    if len(troughs) < 3:
        return None

    for i in range(len(troughs) - 2):
        t1, t2, t3 = troughs[i], troughs[i+1], troughs[i+2]
        if not ( (t2 - t1) >= min_separation and (t3 - t2) >= min_separation):
            continue
        if (t3 - t1) > max_span:
            continue

        low1, low2, low3 = lows[t1], lows[t2], lows[t3]
        mean_low = np.mean([low1, low2, low3])
        if any(abs(l - mean_low)/mean_low > tolerance for l in (low1, low2, low3)):
            continue

        # neckline = min of highs between bottoms (resistance)
        between1_high = np.max(df['high'].iloc[t1:t2+1])
        between2_high = np.max(df['high'].iloc[t2:t3+1])
        neckline = min(between1_high, between2_high)

        # confirmation: close above neckline
        confirmed = False
        if require_neckline_break:
            end_idx = min(len(closes)-1, t3 + confirmation_lookforward)
            for j in range(t3+1, end_idx+1):
                if closes[j] > neckline:
                    confirmed = True
                    confirm_index = j
                    break
        else:
            confirmed = True
            confirm_index = t3

        if not confirmed:
            continue

        score = 50
        height = neckline - mean_low
        rel_height = height / neckline if neckline != 0 else 0
        score += min(30, int(rel_height * 300))
        tops_dev = np.std([low1, low2, low3]) / mean_low if mean_low!=0 else 1
        score += max(0, int((1 - tops_dev) * 20))

        if 'volume' in df.columns:
            vol_avg = df['volume'].iloc[t1:t3].mean()
            vol_confirm = df['volume'].iloc[confirm_index] if confirm_index < len(df) else 0
            if vol_confirm > vol_avg * 1.1:
                score += 10

        score = int(min(100, score))

        return {
            "pattern": "triple_bottom",
            "t1": int(t1), "t2": int(t2), "t3": int(t3),
            "low1": float(low1), "low2": float(low2), "low3": float(low3),
            "neckline": float(neckline),
            "confirm_index": int(confirm_index),
            "height": float(height),
            "strength": score
        }
    return None

def plot_pattern(df, pattern):
    """Generic plotting for triple patterns. Use st.pyplot() in Streamlit to show."""
    plt.figure(figsize=(12,5))
    plt.plot(df['close'].values, label='close', linewidth=1.2)
    idxs = []
    if pattern['pattern'] == 'triple_top':
        idxs = [pattern['p1'], pattern['p2'], pattern['p3']]
        yvals = [pattern['top1'], pattern['top2'], pattern['top3']]
        plt.scatter(idxs, yvals, marker='^', s=120, label='tops', color='red')
    else:
        idxs = [pattern['t1'], pattern['t2'], pattern['t3']]
        yvals = [pattern['low1'], pattern['low2'], pattern['low3']]
        plt.scatter(idxs, yvals, marker='v', s=120, label='bottoms', color='green')

    # neckline
    plt.axhline(pattern['neckline'], linestyle='--', label='neckline')
    plt.axvline(pattern['confirm_index'], color='orange', alpha=0.6, label='confirm index')
    plt.title(f"{pattern['pattern']} detected | strength {pattern['strength']}%")
    plt.legend()
    plt.tight_layout()
    plt.show()

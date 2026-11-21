"""Continuous signal strength from separable inputs (Phase 9.3, audit H-08).

What the audited scorer actually did, verified by exhaustive enumeration over
every reachable state:

* ``strength`` took **four** distinct values: ``{0, 20.0, 40.0, 100.0}``.
  (The audit said three; ``40.0`` is reachable. The conclusion is unchanged.)
* Six of the seven separately-tuned thresholds -- 55, 65, 70, 75, 80, 85 --
  partition that set **identically**. Every one is equivalent to
  ``strength == 100``. Only the 30 threshold differs, admitting 40 as well.
* The three "independent" indicators were not independent. ``bb_signal`` was
  *defined* as a conjunction with ``ema_signal``; both bonus terms were
  EMA-gated; and EMA carried 0.45 of the 0.80 available weight. Enumerating all
  RSI values 0-100 against every reachable Bollinger state shows RSI and BB
  **cannot change the signal at all**: the decision is exactly the sign of
  ``EMA_fast - EMA_slow``.

So the system had seven tuning knobs that were one knob, and three indicators
that were one indicator. A threshold on a constant is not configuration.

This replacement produces a genuinely continuous score from four inputs chosen
to be separable, each contributing independently of the others' state:

1. **EMA separation in ATR units** -- trend, scale-free. Raw price separation
   is not comparable between gold at $1200 and gold at $3000; dividing by ATR
   makes "how far apart, relative to how much this instrument moves" mean the
   same thing in any regime.
2. **RSI distance from 50** -- momentum, independent of the EMA state.
3. **Bollinger %B** -- position in the volatility envelope, computed from the
   bands themselves rather than gated on the trend.
4. **Volatility regime** -- a percentile of the trailing ATR distribution
   (Phase 3.2), damping confidence when volatility is extreme.

**A caveat that matters more than the code.** Making the score continuous does
not make it predictive. It removes a measurement artefact that made every
threshold meaningless; whether these inputs have any edge on M5 gold is exactly
what Phase 9.4 exists to find out, and the honest prior is that they do not.
"""

import math


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def ema_separation_score(ema_fast, ema_slow, atr):
    """Signed trend score in [-1, 1] from EMA separation measured in ATRs.

    Returns 0.0 when ATR is unusable rather than guessing -- a trend score
    computed against an unknown scale is noise with a number attached.
    """
    if not atr or atr <= 0 or ema_fast is None or ema_slow is None:
        return 0.0
    separation_in_atr = (float(ema_fast) - float(ema_slow)) / float(atr)
    # tanh saturates smoothly: 1 ATR of separation scores ~0.76, 2 ATR ~0.96,
    # so extreme separations do not dominate the blend.
    return math.tanh(separation_in_atr)


def rsi_score(rsi):
    """Signed momentum score in [-1, 1] from RSI distance above/below 50.

    Deliberately NOT the audited contrarian reading (oversold => bullish).
    Direction is a hypothesis to be tested in 9.4, not asserted here; this is
    the straightforward momentum reading, and 9.4 will say whether either sign
    has an edge.
    """
    if rsi is None or rsi != rsi:
        return 0.0
    return _clamp((float(rsi) - 50.0) / 50.0, -1.0, 1.0)


def bollinger_score(close, upper, lower):
    """Signed score in [-1, 1] from %B, the position within the bands.

    Computed from the bands alone. The audited version was gated on the EMA
    state, which is what made it non-independent.
    """
    if upper is None or lower is None or close is None:
        return 0.0
    width = float(upper) - float(lower)
    if width <= 0:
        return 0.0
    percent_b = (float(close) - float(lower)) / width      # 0 at lower, 1 at upper
    return _clamp((percent_b - 0.5) * 2.0, -1.0, 1.0)


def volatility_damping(atr, atr_history, low_pct=20.0, high_pct=80.0,
                       min_samples=30):
    """Confidence multiplier in [0.5, 1.0] from the volatility regime.

    Extreme volatility widens spreads and makes stops less meaningful, so a
    signal formed in it deserves less weight. Returns 1.0 when there is too
    little history to judge -- not a guess dressed as a measurement.
    """
    from risk.volatility import VolatilityRegime

    regime = VolatilityRegime(low_pct, high_pct)
    label = regime.classify(atr, atr_history, min_samples=min_samples)
    if label is None:
        return 1.0
    return 0.7 if label == VolatilityRegime.HIGH else 1.0


DEFAULT_WEIGHTS = {"ema": 0.40, "rsi": 0.25, "bb": 0.25, "trend_agreement": 0.10}


def compute_strength(ema_fast, ema_slow, rsi, close, bb_upper, bb_lower, atr,
                     atr_history=None, weights=None):
    """A continuous 0-100 strength with a direction.

    Returns:
        dict with ``signal`` ('BUY'/'SELL'/'HOLD'), ``strength`` (0-100 float),
        ``score`` (signed, -1..1) and ``components`` for logging.

    The score is a weighted blend of four signed sub-scores. Because each is
    continuous and computed independently, the blend takes a continuous range
    of values -- which is what makes a threshold on it meaningful.
    """
    weights = weights or DEFAULT_WEIGHTS

    ema_component = ema_separation_score(ema_fast, ema_slow, atr)
    rsi_component = rsi_score(rsi)
    bb_component = bollinger_score(close, bb_upper, bb_lower)

    # Agreement term: rewards the sub-scores pointing the same way, without
    # letting any one of them gate another.
    signs = [s for s in (ema_component, rsi_component, bb_component) if s != 0]
    if signs:
        agreement = sum(1 if s > 0 else -1 for s in signs) / float(len(signs))
    else:
        agreement = 0.0

    score = (weights["ema"] * ema_component
             + weights["rsi"] * rsi_component
             + weights["bb"] * bb_component
             + weights["trend_agreement"] * agreement)

    score *= volatility_damping(atr, atr_history)
    score = _clamp(score, -1.0, 1.0)

    strength = round(abs(score) * 100.0, 2)
    if score > 0:
        signal = "BUY"
    elif score < 0:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "signal": signal,
        "strength": strength,
        "score": round(score, 6),
        "components": {
            "ema_separation_atr": round(ema_component, 4),
            "rsi": round(rsi_component, 4),
            "bollinger_pct_b": round(bb_component, 4),
            "agreement": round(agreement, 4),
        },
    }


def distribution_report(strengths):
    """Summarise a strength distribution.

    Phase 9.3 asks CI to assert more than 10 distinct values and non-zero
    variance over a year of M5 data. The audited scorer produced four values
    and would have failed this immediately -- which is the point of asserting
    it rather than eyeballing a chart.
    """
    values = [float(s) for s in strengths if s is not None and s == s]
    if not values:
        return {"count": 0, "distinct": 0, "variance": 0.0,
                "min": 0.0, "max": 0.0, "mean": 0.0}

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return {
        "count": len(values),
        "distinct": len(set(round(v, 2) for v in values)),
        "variance": variance,
        "min": min(values),
        "max": max(values),
        "mean": mean,
    }

# analysis/decision_engine.py
import math
import numpy as np
import logging
from datetime import datetime
from utils.trade_logger import log_signal  # we'll add this function in the logger

logger = logging.getLogger(__name__)

# default weights (tune to taste). Total should sum to 1.0
DEFAULT_WEIGHTS = {
    "multi_tf": 0.30,      # combined multi-timeframe bias
    "ema_alignment": 0.15,
    "rsi": 0.12,
    "momentum": 0.10,      # e.g., MACD or price momentum
    "atr_volatility": 0.10,
    "price_action": 0.10,  # support/resistance, pattern
    "news": 0.08,
    "recent_perf": 0.05
}

# Confidence bands (0..1)
CONFIDENCE_BANDS = {
    "aggressive": 0.9,
    "standard": 0.70,
    "cautious": 0.55
}

def safe_normalize(val, min_val=-1, max_val=1):
    """normalize indicator-like values into 0..1 domain (positive bias -> >0.5)"""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    # assume val in [-1,1] where -1 strong sell, +1 strong buy
    clipped = max(min_val, min(max_val, val))
    # map -1..1 -> 0..1
    return (clipped + 1) / 2.0

def compute_confluence(factor_inputs, weights=None, require_news=False):
    """
    factor_inputs: dict of factor_name -> signed value in [-1..1] or None
      e.g. { "ema_alignment": 1, "rsi": 0.5, "atr_volatility": -0.2, "news": None, ... }
    weights: weights dict (same keys)
    require_news: if True, treat missing news as neutral (0) but mark applied=False
    Returns:
      {
        "confluence_score": float (0..1),
        "direction_score": float (-1..1),
        "factor_scores": dict factor -> normalized 0..1 or None,
        "applied_weights_sum": float,
        "notes": {...}
      }
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    factor_scores = {}         # normalized 0..1
    weighted_sum = 0.0
    applied_weight = 0.0
    missing = []

    for name, w in weights.items():
        raw = factor_inputs.get(name, None)
        norm = safe_normalize(raw)  # None if missing
        factor_scores[name] = norm
        if norm is None:
            # If news optional and missing => skip weight, will normalize later
            missing.append(name)
            continue
        weighted_sum += norm * w
        applied_weight += w

    # if some weights missing (e.g., news None and we want to skip it), normalize to total weight 1
    if applied_weight == 0:
        # Nothing available: return neutral
        direction_score = 0.0
        confluence = 0.0
        notes = {"status": "no_factors_available", "missing": missing}
        return {
            "confluence_score": confluence,
            "direction_score": direction_score,
            "factor_scores": factor_scores,
            "applied_weights_sum": applied_weight,
            "notes": notes
        }

    # Normalize weighted sum into 0..1 by dividing by applied weight
    confluence = weighted_sum / applied_weight  # still 0..1
    # Convert confluence back to direction scale -1..1 for directional decision convenience:
    direction_score = (confluence - 0.5) * 2.0  # maps 0..1 -> -1..1

    notes = {
        "missing_factors": missing,
        "raw_weighted_sum": weighted_sum,
        "applied_weight": applied_weight
    }

    return {
        "confluence_score": round(confluence, 4),
        "direction_score": round(direction_score, 4),
        "factor_scores": factor_scores,
        "applied_weights_sum": round(applied_weight, 4),
        "notes": notes
    }

def decide_action(conflux_result, thresholds=None, bias_preference=None, recent_trend=None, atr=None):
    """
    Decide single best action based on confluence result and tie-breakers.
    thresholds: dict to override confidence bands
    bias_preference: optional ('trend', 'momentum', 'price_action') prefer these factors during tie-breaks
    recent_trend: -1..1 (overall higher timeframe trend) used as tiebreaker
    atr: volatility measure used to scale action (if too volatile, downgrade)
    Returns:
      {
        "action": "BUY"|"SELL"|"HOLD"|"WAIT"|"REDUCE_SIZE",
        "confidence": 0..1,
        "rationale": "...",
        "recommendation": {
            "lot_adjustment": 1.0,   # multiplier to lot (0.5 reduce, >1 increase)
            "sl_adjustment": 1.0     # multiplier on suggested SL distance
        }
      }
    """
    if thresholds is None:
        thresholds = CONFIDENCE_BANDS

    conf = conflux_result["confluence_score"]  # 0..1
    dir_score = conflux_result["direction_score"]  # -1..1

    rationale = []
    action = "HOLD"
    lot_adj = 1.0
    sl_adj = 1.0

    # If very high confidence
    if conf >= thresholds["aggressive"]:
        # strong decision: direction from dir_score
        if dir_score > 0.05:
            action = "BUY"
            rationale.append("High confidence bullish")
        elif dir_score < -0.05:
            action = "SELL"
            rationale.append("High confidence bearish")
        else:
            # neutral direction but very high confluence (rare) -> prefer recent trend
            if recent_trend is not None:
                action = "BUY" if recent_trend > 0 else "SELL"
                rationale.append("High confidence but neutral — using recent trend as tiebreaker")
            else:
                action = "WAIT"
                rationale.append("High confluence but neutral direction")
        # if volatility very high, reduce lot
        if atr and atr > 2.5:
            lot_adj *= 0.6
            rationale.append("High ATR → reduce lot")
    # standard confidence
    elif conf >= thresholds["standard"]:
        # require clearer direction
        if dir_score >= 0.2:
            action = "BUY"
            rationale.append("Standard confidence bullish")
        elif dir_score <= -0.2:
            action = "SELL"
            rationale.append("Standard confidence bearish")
        else:
            # mixed signals — take conservative action: WAIT or REDUCE_SIZE if bias exists
            if bias_preference:
                # if bias factor suggests a side, take a reduced-size trade
                bias_val = conflux_result["factor_scores"].get(bias_preference)
                if bias_val is not None:
                    if bias_val > 0.6:
                        action = "BUY"
                        lot_adj *= 0.5
                        rationale.append(f"Mixed signals: bias pref '{bias_preference}' bullish → reduced-size BUY")
                    elif bias_val < 0.4:
                        action = "SELL"
                        lot_adj *= 0.5
                        rationale.append(f"Mixed signals: bias pref '{bias_preference}' bearish → reduced-size SELL")
                    else:
                        action = "WAIT"
                        rationale.append("Mixed signals, bias pref neutral → WAIT")
                else:
                    action = "WAIT"
                    rationale.append("Mixed signals → WAIT")
            else:
                action = "WAIT"
                rationale.append("Mixed signals → WAIT")
    else:
        # low confidence: typically do not trade
        action = "WAIT"
        rationale.append("Low confidence — skip")
        # but if slight directional edge and very low volatility and no recent losses, maybe small trade
        if abs(dir_score) > 0.4 and atr is not None and atr < 0.8:
            action = "REDUCE_SIZE"
            lot_adj *= 0.3
            rationale.append("Low confidence but directional edge + low ATR → small reduce-size trade")

    # Final safety clamp: if action is BUY/SELL/REDUCE_SIZE but applied weight is tiny, set to WAIT
    if conflux_result["applied_weights_sum"] < 0.1 and action in ("BUY", "SELL", "REDUCE_SIZE"):
        rationale.append("Insufficient available factors -> override to WAIT")
        action = "WAIT"

    result = {
        "action": action,
        "confidence": conf,
        "direction_score": dir_score,
        "rationale": "; ".join(rationale),
        "recommendation": {"lot_multiplier": round(lot_adj, 2), "sl_multiplier": round(sl_adj, 2)},
        "timestamp": datetime.utcnow().isoformat()
    }
    return result


def analyze_and_decide(factor_inputs, **kwargs):
    """
    Combined helper: compute confluence and then decide final action.
    Returns dict containing conflux result, decision, and full factor breakdown.
    """
    conflux = compute_confluence(factor_inputs, weights=kwargs.get("weights"))
    decision = decide_action(
        conflux,
        thresholds=kwargs.get("thresholds"),
        bias_preference=kwargs.get("bias_preference"),
        recent_trend=kwargs.get("recent_trend"),
        atr=kwargs.get("atr")
    )

    # merge for logging/return
    out = {
        "confluence": conflux,
        "decision": decision,
        "raw_factors": factor_inputs
    }

    # log summary to trade_logger (implement log_signal)
    try:
        log_signal({
            "symbol": kwargs.get("symbol"),
            "confluence_score": conflux["confluence_score"],
            "direction_score": conflux["direction_score"],
            "factor_scores": conflux["factor_scores"],
            "decision": decision["action"],
            "confidence": decision["confidence"],
            "rationale": decision["rationale"],
            "timestamp": decision["timestamp"]
        })
    except Exception as e:
        logger.warning(f"Failed to log signal: {e}")

    return out

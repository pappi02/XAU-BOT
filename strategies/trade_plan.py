"""Stop distance and target for a new entry -- shared by live and backtest.

The live loop sized its stop with ``dynamic_stop_loss`` and its target with
``dynamic_rr_ratio``; the backtester used a fixed 2 x ATR stop and a fixed
TP_RISK_REWARD target. Gate C therefore tested different stops and targets
from the ones the bot places. This module is the one implementation.

News sentiment only reaches the plan when NEWS_SENTIMENT_TRADING_ENABLED is on
(default off): headline tone cannot be reproduced historically, so a plan that
depends on it cannot be backtested.
"""

from dataclasses import dataclass

from utils.indicators import dynamic_rr_ratio, dynamic_stop_loss

ATR_RATIO_WINDOW_BARS = 288      # one trading day of M5 bars


# A trend-following plan has no fixed take-profit: the payoff distribution's
# whole point is letting a winner run further than any fixed multiple would
# allow. `rr` this large puts the nominal target far enough away that the
# trailing stop (backtest/live_engine.py) governs every realistic exit,
# without needing a second code path through TradePlan.levels() for "no target".
UNBOUNDED_RR = 1_000_000.0


@dataclass(frozen=True)
class TradePlan:
    sl_multiplier: float          # stop = ATR x this
    sl_distance: float            # price units
    rr: float                     # target = stop distance x this
    # None for Hypotheses 1/2 (fixed target, no trailing). A value enables a
    # chandelier ATR trailing stop in backtest/live_engine.py: ratchets to
    # (peak favourable excursion - trailing_atr_mult x ATR-at-entry), only
    # ever moving in the trade's favour, replacing the fixed target above.
    trailing_atr_mult: float = None

    def levels(self, direction, entry_price):
        """(stop, target) prices for an entry at ``entry_price``."""
        if direction == "BUY":
            return (entry_price - self.sl_distance,
                    entry_price + self.sl_distance * self.rr)
        return (entry_price + self.sl_distance,
                entry_price - self.sl_distance * self.rr)


def atr_ratio(atr_values, window=ATR_RATIO_WINDOW_BARS):
    """Newest ATR divided by the median of the last ``window`` ATR values.

    None when there is not enough clean history.
    """
    clean = [float(v) for v in list(atr_values)[-window:] if v is not None and v == v and v > 0]
    if len(clean) < 20:
        return None
    ordered = sorted(clean)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
    return clean[-1] / median if median > 0 else None


def plan_entry(signal_info, atr, atr_history, news_sentiment, config):
    """Build the stop and target for ``signal_info``.

    Args:
        signal_info: generate_signal() output (signal, strength, components).
        atr: ATR of the newest closed bar, price units.
        atr_history: recent ATR values, newest last (for the volatility ratio).
        news_sentiment: live news dict/str; ignored unless enabled in config.

    Returns:
        TradePlan, or None when ATR is unusable (no stop can be sized).
    """
    if atr is None or atr != atr or atr <= 0:
        return None
    if not config.NEWS_SENTIMENT_TRADING_ENABLED:
        news_sentiment = "neutral"

    direction = signal_info["signal"]
    strength = float(signal_info["strength"])
    components = signal_info.get("components", {})
    ratio = atr_ratio(atr_history)
    common = dict(signal_strength=strength, atr_ratio=ratio,
                  news_sentiment=news_sentiment,
                  trend_strength=components.get("ema_signal", 0),
                  rsi_condition=components.get("rsi_condition", "neutral"),
                  position_type=direction)

    multiplier = dynamic_stop_loss(**common)
    rr = dynamic_rr_ratio(**common)
    return TradePlan(sl_multiplier=multiplier, sl_distance=float(atr) * multiplier, rr=rr)


def plan_trend_entry(signal_info, atr, atr_history, news_sentiment, config):
    """Build the initial stop for a trend-following entry (Hypothesis 3).

    Same signature as ``plan_entry`` so the two are interchangeable wherever
    a plan is built (main.py, backtest/live_engine.py) -- ``atr_history`` and
    ``news_sentiment`` are accepted but unused: this plan does not scale by
    volatility ratio or news, it scales by the config's fixed ATR multiples.

    Returns:
        TradePlan with trailing_atr_mult set, or None when ATR is unusable.
    """
    if atr is None or atr != atr or atr <= 0:
        return None

    multiplier = float(config.TREND_INITIAL_SL_ATR_MULT)
    return TradePlan(sl_multiplier=multiplier, sl_distance=float(atr) * multiplier,
                     rr=UNBOUNDED_RR, trailing_atr_mult=float(config.TREND_TRAIL_ATR_MULT))


def news_blocks_entry(direction, news_sentiment, config):
    """True when enabled headline sentiment opposes ``direction``."""
    if not config.NEWS_SENTIMENT_TRADING_ENABLED:
        return False
    from utils.news_reader import sentiment_of
    label = sentiment_of(news_sentiment)
    return ((label == "bullish" and direction == "SELL")
            or (label == "bearish" and direction == "BUY"))

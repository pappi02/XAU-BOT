"""Discretionary exit rules, shared by the live executor and the backtester.

Before this module the rules lived only inside ``TradeExecutor.should_close_trade``
and the backtester modelled nothing but SL/TP. Gate C therefore measured a
system that closed only at its stop or target, while the live bot also closed
on opposite signals, trend reversals, structure breaks, volatility spikes and
age. One implementation, called from both places, is the only way to keep a
backtest honest about what runs.

Every function is pure: no broker, no clock, no config module. State that only
the live bot can know (peak profit, account drawdown, broker position count)
arrives as a precomputed boolean.
"""

from dataclasses import dataclass, field

from utils.market_time import in_weekend_close_window, minutes_to_weekly_close

# Order in which factors are reported. The first triggered one is the "reason".
FACTOR_ORDER = (
    "opposite_signal", "signal_weakening", "news_economic_event",
    "volatility_spike", "time_based_exit", "market_session_end",
    "break_of_structure", "rr_ratio_reversal", "portfolio_drawdown",
    "max_total_positions", "trend_reversal",
)

# Exits that protect the account rather than express a view. They ignore the
# minimum holding time: a position opened at 16:40 New York on a Friday must
# still be flat before the weekend gap, and a drawdown breach cannot wait.
RISK_FACTORS = ("market_session_end", "portfolio_drawdown")


@dataclass
class ExitContext:
    position_type: str                 # BUY or SELL
    age_seconds: float
    readings: list                     # last <=2 (bar_key, signal, strength), newest last
    frame: object = None               # closed bars, newest last (high/low/close)
    reversal: dict = field(default_factory=dict)
    atr: float = None
    entry_atr: float = None
    now_utc: object = None
    news_label: str = "neutral"
    news_score: float = 0.0
    drawdown_breached: bool = False
    rr_retraced: bool = False
    too_many_positions: bool = False


def opposite_of(position_type):
    return "SELL" if position_type == "BUY" else "BUY"


def two_opposite_readings(position_type, readings, min_strength):
    """Two consecutive bars carrying the opposite signal at reversal strength."""
    opposite = opposite_of(position_type)
    return len(readings) >= 2 and all(
        signal == opposite and strength >= min_strength
        for _, signal, strength in readings[-2:])


def two_weak_readings(readings, max_strength):
    """Two consecutive bars below the weakening threshold."""
    return len(readings) >= 2 and all(
        strength < max_strength for _, _, strength in readings[-2:])


def news_against(position_type, news_label):
    return ((position_type == "BUY" and news_label == "bearish")
            or (position_type == "SELL" and news_label == "bullish"))


def volatility_spike(atr, entry_atr, multiplier):
    if atr is None or entry_atr is None or entry_atr == 0:
        return False
    return atr > entry_atr * multiplier


def break_of_structure(frame, position_type, fractal_period):
    """Close beyond the range of the PRIOR ``2 * fractal_period`` bars (Phase 5.3).

    The window ends before the current bar: a close can never be below its own
    bar's low, so including it made the audited version unsatisfiable (M-01).
    """
    lookback = int(fractal_period) * 2
    if frame is None or len(frame) < lookback + 1:
        return False
    close = frame["close"].iloc[-1]
    if position_type == "BUY":
        return close < frame["low"].iloc[-(lookback + 1):-1].min()
    return close > frame["high"].iloc[-(lookback + 1):-1].max()


def trend_reversal_against(position_type, reversal):
    if not reversal or not reversal.get("reversal_detected"):
        return False
    direction = reversal.get("direction")
    return ((position_type == "BUY" and direction == "bullish_to_bearish")
            or (position_type == "SELL" and direction == "bearish_to_bullish"))


def min_hold_seconds(config):
    return config.MIN_HOLDING_SECONDS


def entry_too_close_to_weekly_close(now_utc, config, bar_seconds):
    """Block entries that could not be flattened before the weekend.

    A new position cannot be closed for MIN_HOLDING_SECONDS by a view-based
    exit, and the weekend close fires SESSION_END_BUFFER_MINUTES before the
    Friday close. An entry later than that would be opened only to be closed
    at the next bar -- paying the spread twice for nothing.
    """
    if not config.SESSION_END_CLOSE or now_utc is None:
        return False
    cutoff = (float(config.SESSION_END_BUFFER_MINUTES)
              + float(config.MIN_HOLDING_SECONDS) / 60.0
              + float(bar_seconds) / 60.0)
    return (in_weekend_close_window(now_utc, config.SESSION_END_BUFFER_MINUTES)
            or minutes_to_weekly_close(now_utc) <= cutoff)


def triggered_factors(ctx, config, risk_only=False):
    """Names of every exit factor that fires, in FACTOR_ORDER.

    The caller enforces AUTO_CLOSE_ENABLED. ``risk_only`` evaluates only
    RISK_FACTORS, for positions younger than the minimum holding time.
    """
    opposite = two_opposite_readings(ctx.position_type, ctx.readings,
                                     config.EXIT_REVERSAL_MIN_STRENGTH)
    checks = {
        "opposite_signal": opposite,
        "signal_weakening": (config.SIGNAL_WEAKENING_CLOSE
                             and two_weak_readings(ctx.readings,
                                                   config.EXIT_WEAKENING_MAX_STRENGTH)),
        "news_economic_event": (config.NEWS_SENTIMENT_CLOSE and ctx.news_score > 0.5
                                and news_against(ctx.position_type, ctx.news_label)
                                and opposite),
        "volatility_spike": (config.VOLATILITY_SPIKE_ENABLED
                             and volatility_spike(ctx.atr, ctx.entry_atr,
                                                  config.ATR_SPIKE_MULTIPLIER)),
        "time_based_exit": ctx.age_seconds > config.MAX_POSITION_AGE_SECONDS,
        "market_session_end": (config.SESSION_END_CLOSE and ctx.now_utc is not None
                               and in_weekend_close_window(
                                   ctx.now_utc, config.SESSION_END_BUFFER_MINUTES)),
        "break_of_structure": (config.BREAK_OF_STRUCTURE_ENABLED
                               and break_of_structure(ctx.frame, ctx.position_type,
                                                      config.FRACTAL_PERIOD)),
        "rr_ratio_reversal": config.RR_REVERSAL_ENABLED and ctx.rr_retraced,
        "portfolio_drawdown": config.PORTFOLIO_DRAWDOWN_CLOSE and ctx.drawdown_breached,
        "max_total_positions": (config.MAX_TOTAL_POSITIONS_CLOSE_ENABLED
                                and ctx.too_many_positions),
        "trend_reversal": (config.TREND_REVERSAL_CLOSE and opposite
                           and trend_reversal_against(ctx.position_type, ctx.reversal)),
    }
    names = RISK_FACTORS if risk_only else FACTOR_ORDER
    return [name for name in FACTOR_ORDER if name in names and checks[name]]


def record_reading(history, bar_key, signal, strength):
    """Append one reading per bar to ``history`` (a list), keeping the last two.

    Re-evaluating the same bar replaces its reading instead of adding a second.
    """
    if history and history[-1][0] == bar_key:
        history[-1] = (bar_key, signal, strength)
    else:
        history.append((bar_key, signal, strength))
        del history[:-2]
    return list(history)

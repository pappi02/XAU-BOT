"""Fail-fast configuration validation (Phase 12.4).

Every key in config.py is declared here with a type, an allowed range and a
UNIT. ``validate()`` reports every problem at once; ``assert_valid()`` raises
before the bot touches a broker.

Why this exists: most of the audit's worst findings were configuration that was
accepted without complaint and meant something other than it said --
CONTRACT_SIZE at 1000x its real value, MAX_DAILY_LOSS_PCT = 0.60 commented as
30%, ATR thresholds unreachable by an order of magnitude, a 0 balance floor that
made its check always pass. A schema cannot catch every wrong number, but it
catches the ones that are impossible, and it forces each new key to state what
unit it is in. A test fails if a key is added to config.py without an entry.
"""

VALID_TIMEFRAMES = {"M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15",
                    "M20", "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12",
                    "D1", "W1"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

NUM = (int, float)
BOOL = (bool,)
INT = (int,)
STR = (str,)
OPT_STR = (str, type(None))

# key: (types, minimum, maximum, unit, secret)
SCHEMA = {
    # --- credentials & connection ------------------------------------------
    "MT5_ACCOUNT":        ((int, type(None)), 1, None, "login number", False),
    "MT5_PASSWORD":       (OPT_STR, None, None, "secret", True),
    "MT5_SERVER":         (OPT_STR, None, None, "server name", False),
    "MT5_PATH":           (STR, None, None, "filesystem path", False),
    "MT5_TIMEOUT_MS":     (INT, 1000, 300000, "milliseconds", False),
    "NEWS_API_KEY":       (OPT_STR, None, None, "secret", True),

    # --- instrument & data -------------------------------------------------
    "SYMBOL":             (STR, None, None, "broker symbol name", False),
    "BROKER_SERVER_TZ":   (STR, None, None, "IANA zone the server clock follows", False),
    "BROKER_SERVER_SHIFT_HOURS": (NUM, -14.0, 14.0, "hours added to that zone", False),
    "SYMBOL_PHASE5":      (STR, None, None, "broker symbol name (alias)", False),
    "TIMEFRAME":          (STR, None, None, "MT5 timeframe code", False),
    "NUM_CANDLES":        (INT, 100, 99999, "bars", False),

    # --- indicators --------------------------------------------------------
    "EMA_FAST":           (INT, 2, 500, "bars", False),
    "EMA_SLOW":           (INT, 3, 1000, "bars", False),
    "RSI_PERIOD":         (INT, 2, 500, "bars", False),
    "BB_PERIOD":          (INT, 2, 500, "bars", False),
    "BB_STD_DEV":         (NUM, 0.5, 5.0, "standard deviations", False),
    "ATR_PERIOD":         (INT, 2, 500, "bars", False),
    "FRACTAL_PERIOD":     (INT, 1, 100, "bars", False),

    # --- risk --------------------------------------------------------------
    "RISK_PER_TRADE_FRACTION":     (NUM, 0.0001, 0.05, "fraction of equity", False),
    "MAX_DAILY_LOSS_FRACTION":     (NUM, 0.001, 0.25, "fraction of day-open balance", False),
    "MAX_DRAWDOWN_FRACTION":       (NUM, 0.01, 0.9, "fraction below equity peak", False),
    "EMERGENCY_CLOSE_DRAWDOWN_FRACTION": (NUM, 0.01, 0.95, "fraction below equity peak", False),
    "MAX_PORTFOLIO_RISK_FRACTION": (NUM, 0.0001, 0.25, "fraction of equity", False),
    "MIN_ACCOUNT_BALANCE":         (NUM, 0.01, None, "account currency", False),
    "MAX_CONSECUTIVE_LOSSES":      (INT, 1, 100, "trades", False),
    "MAX_LOTS_PER_ORDER":          (NUM, 0.01, 100.0, "lots", False),
    "MAX_CONCURRENT_POSITIONS":    (INT, 1, 50, "positions", False),
    "MAX_OPEN_TRADES":             (INT, 1, 50, "positions", False),
    "MAX_TOTAL_POSITIONS":         (INT, 1, 50, "positions", False),
    "CIRCUIT_BREAKER_THRESHOLD":   (INT, 1, 100, "consecutive failures", False),

    # --- entries -----------------------------------------------------------
    "MIN_ENTRY_STRENGTH":          (NUM, 0.0, 100.0, "strength score 0-100", False),
    "SIGNAL_REVERSAL_MIN_STRENGTH": (NUM, 0.0, 100.0, "strength score 0-100", False),
    "MIN_SIGNAL_HOLD_BARS":        (INT, 0, 1000, "bars", False),
    "MAX_ENTRY_SPREAD_POINTS":     (NUM, 1, 10000, "broker points", False),
    "ORDER_DEVIATION_POINTS":      (INT, 0, 10000, "broker points", False),
    "ORDER_MAX_ATTEMPTS":          (INT, 1, 10, "attempts", False),

    # --- exits -------------------------------------------------------------
    "AUTO_CLOSE_ENABLED":          (BOOL, None, None, "switch", False),
    "EXIT_REVERSAL_MIN_STRENGTH":  (NUM, 0.0, 100.0, "strength score 0-100", False),
    "SIGNAL_WEAKENING_CLOSE":      (BOOL, None, None, "switch", False),
    "EXIT_WEAKENING_MAX_STRENGTH": (NUM, 0.0, 100.0, "strength score 0-100", False),
    "MIN_HOLDING_SECONDS":         (INT, 0, 604800, "seconds", False),
    "MAX_POSITION_AGE_SECONDS":    (INT, 60, 2592000, "seconds", False),
    "VOLATILITY_SPIKE_ENABLED":    (BOOL, None, None, "switch", False),
    "ATR_SPIKE_MULTIPLIER":        (NUM, 1.0, 20.0, "multiple of entry ATR", False),
    "NEWS_SENTIMENT_TRADING_ENABLED": (BOOL, None, None, "switch", False),
    "TREND_INITIAL_SL_ATR_MULT":   (NUM, 0.1, 20.0, "multiple of ATR", False),
    "TREND_TRAIL_ATR_MULT":        (NUM, 0.1, 20.0, "multiple of ATR", False),
    "LIVE_MAX_LOTS_PER_ORDER":    (NUM, 0.01, 1.0, "lots, live accounts", False),
    "LIVE_MAX_DAILY_LOSS_FRACTION": (NUM, 0.001, 0.05, "fraction, live accounts", False),
    "SESSION_END_CLOSE":           (BOOL, None, None, "switch", False),
    "SESSION_END_BUFFER_MINUTES":  (INT, 0, 720, "minutes", False),
    "BREAK_OF_STRUCTURE_ENABLED":  (BOOL, None, None, "switch", False),
    "RR_REVERSAL_ENABLED":         (BOOL, None, None, "switch", False),
    "RR_REVERSAL_THRESHOLD":       (NUM, 0.0, 1.0, "fraction of peak profit", False),
    "PORTFOLIO_DRAWDOWN_CLOSE":    (BOOL, None, None, "switch", False),
    "MAX_TOTAL_POSITIONS_CLOSE_ENABLED": (BOOL, None, None, "switch", False),
    "TREND_REVERSAL_CLOSE":        (BOOL, None, None, "switch", False),
    "NEWS_SENTIMENT_CLOSE":        (BOOL, None, None, "switch", False),

    # --- stop modification -------------------------------------------------
    "TRAILING_STOP_ENABLED":       (BOOL, None, None, "switch", False),
    "ADAPTIVE_TRAILING_STOP":      (BOOL, None, None, "switch", False),
    "TRAIL_START_PRICE":           (NUM, 0.01, 10000.0, "price units (USD)", False),
    "TRAIL_DISTANCE_PRICE":        (NUM, 0.01, 10000.0, "price units (USD)", False),
    "BREAK_EVEN_ENABLED":          (BOOL, None, None, "switch", False),
    "BREAK_EVEN_PROFIT_PRICE":     (NUM, 0.01, 10000.0, "price units (USD)", False),
    "BREAK_EVEN_BUFFER_PRICE":     (NUM, 0.0, 10000.0, "price units (USD)", False),
    "BREAK_EVEN_ATR_MULTIPLIER":   (NUM, 0.0, 10.0, "multiple of ATR", False),
    "BREAK_EVEN_TREND_STRENGTH_MULTIPLIER": (NUM, 0.0, 10.0, "price units per strength point", False),
    "BREAK_EVEN_NEWS_SENTIMENT_MULTIPLIER": (NUM, 0.0, 10.0, "price units per sentiment unit /100", False),
    "BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER": (NUM, 0.0, 10.0, "price units per minute held", False),
    "BREAK_EVEN_PROFIT_LEVEL_MULTIPLIER": (NUM, 0.0, 1.0, "fraction of profit", False),
    "BREAK_EVEN_MAX_BUFFER_FRACTION": (NUM, 0.0, 1.0, "fraction of profit", False),

    # --- calendar, logging -------------------------------------------------
    "ECONOMIC_CALENDAR_ENABLED":   (BOOL, None, None, "switch", False),
    "ECONOMIC_CALENDAR_PATH":      (OPT_STR, None, None, "filesystem path or None", False),
    "EVENT_BLACKOUT_BEFORE_MINUTES": (INT, 0, 1440, "minutes", False),
    "EVENT_BLACKOUT_AFTER_MINUTES": (INT, 0, 1440, "minutes", False),
    "LOG_LEVEL":                   (STR, None, None, "logging level name", False),
}


class ConfigError(ValueError):
    """Raised when configuration is unusable. Lists every problem found."""


def config_keys(config):
    return sorted(k for k in dir(config) if k.isupper() and not k.startswith("_"))


def _describe(key, value):
    """Never print a secret's value."""
    if key in SCHEMA and SCHEMA[key][4]:
        return "<secret, %d chars>" % len(value) if isinstance(value, str) else "<secret>"
    return repr(value)


def validate(config):
    """Return a list of human-readable problems. Empty means valid."""
    problems = []

    for key in config_keys(config):
        if key not in SCHEMA:
            problems.append("%s has no schema entry (declare its type, range "
                            "and unit in utils/config_validation.py)" % key)
            continue

        types, low, high, unit, _secret = SCHEMA[key]
        value = getattr(config, key)

        # bool is a subclass of int; do not let True pass as a number.
        if isinstance(value, bool) and bool not in types:
            problems.append("%s must be %s (%s), got a boolean"
                            % (key, "/".join(t.__name__ for t in types), unit))
            continue
        if not isinstance(value, types):
            problems.append("%s must be %s (%s), got %s %s"
                            % (key, "/".join(t.__name__ for t in types), unit,
                               type(value).__name__, _describe(key, value)))
            continue
        if isinstance(value, NUM) and not isinstance(value, bool):
            if low is not None and value < low:
                problems.append("%s = %s is below the minimum %s (%s)"
                                % (key, _describe(key, value), low, unit))
            if high is not None and value > high:
                problems.append("%s = %s is above the maximum %s (%s)"
                                % (key, _describe(key, value), high, unit))

    get = lambda k, d=None: getattr(config, k, d)

    # --- relationships a per-key range cannot express ----------------------
    if get("TIMEFRAME") not in VALID_TIMEFRAMES:
        problems.append("TIMEFRAME = %r is not a known MT5 timeframe"
                        % get("TIMEFRAME"))
    if str(get("LOG_LEVEL", "")).upper() not in VALID_LOG_LEVELS:
        problems.append("LOG_LEVEL = %r is not a logging level" % get("LOG_LEVEL"))
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(str(get("BROKER_SERVER_TZ")))
    except Exception:
        problems.append("BROKER_SERVER_TZ = %r is not an IANA time zone"
                        % get("BROKER_SERVER_TZ"))
    if not str(get("SYMBOL", "")).strip():
        problems.append("SYMBOL is empty")
    if get("SYMBOL_PHASE5") != get("SYMBOL"):
        problems.append("SYMBOL_PHASE5 (%r) disagrees with SYMBOL (%r) -- there "
                        "is one traded symbol" % (get("SYMBOL_PHASE5"), get("SYMBOL")))

    if _num(get("EMA_FAST")) and _num(get("EMA_SLOW")) and get("EMA_FAST") >= get("EMA_SLOW"):
        problems.append("EMA_FAST (%s) must be shorter than EMA_SLOW (%s)"
                        % (get("EMA_FAST"), get("EMA_SLOW")))
    if (_num(get("MAX_OPEN_TRADES")) and _num(get("MAX_CONCURRENT_POSITIONS"))
            and get("MAX_OPEN_TRADES") > get("MAX_CONCURRENT_POSITIONS")):
        problems.append("MAX_OPEN_TRADES (%s) exceeds MAX_CONCURRENT_POSITIONS "
                        "(%s)" % (get("MAX_OPEN_TRADES"), get("MAX_CONCURRENT_POSITIONS")))
    if (_num(get("RISK_PER_TRADE_FRACTION")) and _num(get("MAX_PORTFOLIO_RISK_FRACTION"))
            and get("RISK_PER_TRADE_FRACTION") > get("MAX_PORTFOLIO_RISK_FRACTION")):
        problems.append("RISK_PER_TRADE_FRACTION (%s) exceeds "
                        "MAX_PORTFOLIO_RISK_FRACTION (%s): no trade could pass "
                        "the portfolio check" % (get("RISK_PER_TRADE_FRACTION"),
                                                 get("MAX_PORTFOLIO_RISK_FRACTION")))
    if (_num(get("EMERGENCY_CLOSE_DRAWDOWN_FRACTION")) and _num(get("MAX_DRAWDOWN_FRACTION"))
            and get("EMERGENCY_CLOSE_DRAWDOWN_FRACTION") < get("MAX_DRAWDOWN_FRACTION")):
        problems.append("EMERGENCY_CLOSE_DRAWDOWN_FRACTION (%s) is below "
                        "MAX_DRAWDOWN_FRACTION (%s): positions would be "
                        "liquidated before new entries were even halted"
                        % (get("EMERGENCY_CLOSE_DRAWDOWN_FRACTION"),
                           get("MAX_DRAWDOWN_FRACTION")))

    return problems


def _num(value):
    return isinstance(value, NUM) and not isinstance(value, bool)


def assert_valid(config):
    """Raise ConfigError listing every problem. Call before connecting."""
    problems = validate(config)
    if problems:
        raise ConfigError(
            "config.py is invalid (%d problem%s):\n  - %s"
            % (len(problems), "" if len(problems) == 1 else "s",
               "\n  - ".join(problems)))
    return True

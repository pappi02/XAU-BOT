"""Data-quality validation (Phase 9.1, audit H-09 / M-10).

The audited bot could not tell a data outage from a quiet market. When bars
were missing, indicators came back as NaN, `ema_fast == ema_slow` evaluated
false-ish, and the strategy produced HOLD -- the same output as "the market is
doing nothing". So a broken feed and a calm Tuesday looked identical in the log,
and the bot waited politely through both.

A trading system must be able to say **"I do not have enough information to
decide"** as a distinct answer from "I have decided to do nothing". Everything
here exists to make that distinction explicit.
"""

import logging

logger = logging.getLogger("xau_bot")


class DataQualityError(RuntimeError):
    """Raised when the data cannot support a trading decision."""


def required_warmup_bars(ema_slow, rsi_period, bb_period, atr_period,
                         safety_multiple=3):
    """Minimum bars before every indicator is fully formed.

    ``safety_multiple`` covers the exponential indicators: an EMA is never
    strictly "complete", but after a few multiples of its period the influence
    of the seed value is negligible. Using the raw period would mean trading on
    indicators still dominated by their initialisation.
    """
    longest = max(int(ema_slow), int(rsi_period), int(bb_period), int(atr_period))
    return longest * int(safety_multiple)


def check_bar_count(df, minimum, label="data"):
    """Refuse to signal on too few bars."""
    count = 0 if df is None else len(df)
    if count < minimum:
        raise DataQualityError(
            "%s has %d bars but %d are needed for indicator warm-up. Refusing "
            "to signal: an incomplete indicator set produces HOLD, which is "
            "indistinguishable from a quiet market."
            % (label, count, minimum)
        )
    return True


def check_indicator_columns(df, required_columns):
    """Refuse to signal when an expected indicator column is absent.

    Audit M-10: the live loop read ``df['RSI_14']`` literally, so changing
    RSI_PERIOD raised KeyError on every iteration -- swallowed and retried
    forever. Naming the missing column is the difference between a five-second
    diagnosis and an afternoon.
    """
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise DataQualityError(
            "Indicator column(s) missing: %s. Present: %s. This usually means "
            "a period in config.py changed without the indicator being "
            "recomputed under the new name."
            % (", ".join(missing), ", ".join(map(str, df.columns)))
        )
    return True


def check_no_duplicate_timestamps(df):
    duplicates = df.index[df.index.duplicated()]
    if len(duplicates):
        raise DataQualityError(
            "%d duplicate timestamp(s), e.g. %s. Duplicate bars double-count "
            "in every rolling indicator."
            % (len(duplicates), duplicates[0])
        )
    return True


def check_monotonic(df):
    if not df.index.is_monotonic_increasing:
        raise DataQualityError(
            "Timestamps are not in increasing order. Every rolling calculation "
            "assumes they are."
        )
    return True


def find_gaps(df, bar_seconds, tolerance=1.5):
    """Bars missing from the series.

    Weekend boundaries are expected for an instrument that does not trade
    around the clock, so they are reported separately rather than as faults.
    Returns ``(intraday_gaps, weekend_gaps)`` as lists of
    ``(previous, next, missing_bars)``.
    """
    intraday, weekend = [], []
    if df is None or len(df) < 2:
        return intraday, weekend

    times = df.index
    for i in range(1, len(times)):
        delta = (times[i] - times[i - 1]).total_seconds()
        if delta <= bar_seconds * tolerance:
            continue
        missing = int(delta // bar_seconds) - 1
        entry = (times[i - 1], times[i], missing)
        # A gap spanning Saturday or Sunday is the weekend close.
        if times[i - 1].weekday() >= 4 and times[i].weekday() <= 1 and delta > 3600:
            weekend.append(entry)
        else:
            intraday.append(entry)
    return intraday, weekend


def check_not_stale(df, bar_seconds, now=None, max_age_bars=3):
    """Refuse to act on a series whose newest bar is old.

    A stale feed is the failure this whole module exists for: the data looks
    perfectly well-formed, and every indicator computes happily on prices from
    an hour ago.
    """
    from datetime import datetime, timezone

    if df is None or len(df) == 0:
        raise DataQualityError("No data at all.")

    now = now or datetime.now(timezone.utc)
    newest = df.index[-1]
    if newest.tzinfo is None:
        newest = newest.tz_localize("UTC")

    age = (now - newest).total_seconds()
    limit = bar_seconds * max_age_bars
    if age > limit:
        raise DataQualityError(
            "Newest bar is %s, which is %.0f seconds old (limit %.0f). The "
            "feed is stale -- indicators would compute cleanly on prices that "
            "no longer reflect the market." % (newest, age, limit)
        )
    return True


def check_prices_are_sane(df):
    """Catch impossible OHLC relationships and non-positive prices."""
    problems = []
    for column in ("open", "high", "low", "close"):
        if column not in df.columns:
            problems.append("column '%s' is missing" % column)
    if problems:
        raise DataQualityError("; ".join(problems))

    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        problems.append("non-positive prices present")
    if (df["high"] < df["low"]).any():
        problems.append("high < low on at least one bar")
    if (df["high"] < df["close"]).any() or (df["high"] < df["open"]).any():
        problems.append("high is below open or close on at least one bar")
    if (df["low"] > df["close"]).any() or (df["low"] > df["open"]).any():
        problems.append("low is above open or close on at least one bar")

    if problems:
        raise DataQualityError("Impossible OHLC data: " + "; ".join(problems))
    return True


def validate_for_trading(df, bar_seconds, required_columns=(), min_bars=0,
                         now=None, check_staleness=True):
    """Run every check. Raises DataQualityError on the first failure.

    Call this before generating a signal. The whole point is that it **raises**
    rather than returning a falsy value: a caller that ignores a return code
    carries on and trades, and that is how a data outage became a HOLD.

    Returns a report dict when the data is usable.
    """
    if df is None or len(df) == 0:
        raise DataQualityError("No data returned.")

    check_monotonic(df)
    check_no_duplicate_timestamps(df)
    check_prices_are_sane(df)
    if min_bars:
        check_bar_count(df, min_bars)
    if required_columns:
        check_indicator_columns(df, required_columns)
    if check_staleness:
        check_not_stale(df, bar_seconds, now=now)

    intraday, weekend = find_gaps(df, bar_seconds)
    if intraday:
        logger.warning(
            "%d intraday gap(s) in the series, e.g. %s -> %s missing %d bar(s). "
            "Rolling indicators will span the gap as though nothing happened.",
            len(intraday), intraday[0][0], intraday[0][1], intraday[0][2])

    return {
        "bars": len(df),
        "first": df.index[0],
        "last": df.index[-1],
        "intraday_gaps": len(intraday),
        "weekend_gaps": len(weekend),
    }

"""Volatility measured as a percentile of its own recent distribution (Phase 3.2).

Audit M-03: the code used absolute ATR thresholds, `ATR_LOW_THRESHOLD = 10` and
`ATR_HIGH_THRESHOLD = 30`, against M5 gold ATR(14) which sits at roughly 1.5-5.
So `atr < 10` was *always* true: the "low volatility, increase lot" multiplier
was applied permanently, **including during volatility spikes**, and the
high-volatility branch was unreachable. The sign of the adjustment was
effectively inverted.

Absolute thresholds cannot survive a change of timeframe or price level -- gold
at $1200 and gold at $3000 have different absolute ATRs and identical relative
ones. Percentiles of the trailing distribution are the fix: "the top decile of
recent volatility" means the same thing on any instrument, timeframe or decade.
"""

import logging

logger = logging.getLogger(__name__)


class VolatilityRegime(object):
    """Classifies the current ATR against its own trailing distribution."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

    def __init__(self, low_percentile=25.0, high_percentile=75.0):
        if not 0.0 <= low_percentile < high_percentile <= 100.0:
            raise ValueError(
                "Need 0 <= low (%r) < high (%r) <= 100"
                % (low_percentile, high_percentile)
            )
        self.low_percentile = low_percentile
        self.high_percentile = high_percentile

    @staticmethod
    def percentile(values, pct):
        """Linear-interpolated percentile. No numpy dependency, no surprises.

        Accepts a plain iterable, or an already-sorted list via
        ``_percentile_of_sorted`` when the caller (``classify``) needs more
        than one percentile from the same data -- sorting is O(n log n), and
        this was sorting the same history twice on every single call.
        """
        data = sorted(float(v) for v in values
                      if v is not None and v == v)      # drop None and NaN
        return VolatilityRegime._percentile_of_sorted(data, pct)

    @staticmethod
    def _percentile_of_sorted(data, pct):
        if not data:
            return None
        if len(data) == 1:
            return data[0]

        rank = (pct / 100.0) * (len(data) - 1)
        low = int(rank)
        high = min(low + 1, len(data) - 1)
        weight = rank - low
        return data[low] * (1.0 - weight) + data[high] * weight

    def classify(self, current_atr, atr_history, min_samples=30):
        """Return LOW / NORMAL / HIGH, or None when there is too little history.

        Returning None rather than guessing matters: a regime call made from
        five samples is noise, and acting on noise is how the original
        thresholds went unnoticed.
        """
        if current_atr is None or current_atr != current_atr:
            return None

        clean = sorted(v for v in (atr_history or []) if v is not None and v == v)
        if len(clean) < min_samples:
            logger.debug("Only %d ATR samples (need %d) -- regime unknown",
                         len(clean), min_samples)
            return None

        low = self._percentile_of_sorted(clean, self.low_percentile)
        high = self._percentile_of_sorted(clean, self.high_percentile)

        if current_atr >= high:
            return self.HIGH
        if current_atr <= low:
            return self.LOW
        return self.NORMAL

    def assert_thresholds_are_reachable(self, atr_history, min_samples=30):
        """Fail loudly if the configured thresholds sit outside observed ATR.

        This is the startup assertion the plan asks for. It is what would have
        caught M-03 on day one: thresholds of 10 and 30 against a distribution
        spanning 1.5-5 are not thresholds, they are dead code.
        """
        clean = [v for v in (atr_history or []) if v is not None and v == v]
        if len(clean) < min_samples:
            return True     # nothing to assert against yet

        observed_min, observed_max = min(clean), max(clean)
        low = self.percentile(clean, self.low_percentile)
        high = self.percentile(clean, self.high_percentile)

        logger.info(
            "ATR distribution over %d samples: min %.3f, p%.0f %.3f, "
            "p%.0f %.3f, max %.3f",
            len(clean), observed_min, self.low_percentile, low,
            self.high_percentile, high, observed_max,
        )

        # Percentile thresholds are reachable by construction; this guards
        # against a degenerate distribution (e.g. a flat/stale feed).
        if observed_min == observed_max:
            raise ValueError(
                "ATR is constant at %.3f over %d samples -- the volatility "
                "feed is stale or the symbol is not trading."
                % (observed_min, len(clean))
            )
        return True


def check_absolute_thresholds(atr_history, low_threshold, high_threshold,
                              min_samples=30):
    """Report whether absolute ATR thresholds are reachable at all.

    Kept as a diagnostic so the M-03 failure is detectable in any config that
    still uses absolute numbers.

    Returns a list of human-readable problems; empty means the thresholds sit
    inside the observed range.
    """
    clean = [v for v in (atr_history or []) if v is not None and v == v]
    if len(clean) < min_samples:
        return []

    observed_min, observed_max = min(clean), max(clean)
    problems = []

    if low_threshold is not None and low_threshold > observed_max:
        problems.append(
            "ATR_LOW_THRESHOLD=%g is above the observed maximum %.3f, so the "
            "'low volatility' branch is ALWAYS taken -- including during spikes."
            % (low_threshold, observed_max)
        )
    if high_threshold is not None and high_threshold > observed_max:
        problems.append(
            "ATR_HIGH_THRESHOLD=%g is above the observed maximum %.3f, so the "
            "'high volatility' branch is UNREACHABLE."
            % (high_threshold, observed_max)
        )
    if low_threshold is not None and low_threshold < observed_min:
        problems.append(
            "ATR_LOW_THRESHOLD=%g is below the observed minimum %.3f, so the "
            "'low volatility' branch is unreachable."
            % (low_threshold, observed_min)
        )
    return problems

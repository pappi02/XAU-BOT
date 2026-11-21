"""One entry per closed bar (Phase 4.2, audit C-02 / M-12).

The audited loop slept 60 seconds and re-evaluated. On an M5 timeframe that is
roughly five evaluations of the *same* bar -- and because the last row from MT5
is the still-forming bar, the indicator values mutated between evaluations. One
bar could therefore produce several different signals and several entries.

Dropping the forming bar (see ``data.fetch_candles.get_candles``) makes each
evaluation deterministic. This module supplies the second half: a record of
which bar we have already acted on, so re-evaluating a bar cannot act twice.

It also aligns the loop to the bar close, which is both correct and cheaper than
polling: there is no new information until a bar closes.
"""

import logging

logger = logging.getLogger(__name__)

# Seconds per bar, by MT5 timeframe name.
TIMEFRAME_SECONDS = {
    "M1": 60, "M2": 120, "M3": 180, "M4": 240, "M5": 300, "M6": 360,
    "M10": 600, "M12": 720, "M15": 900, "M20": 1200, "M30": 1800,
    "H1": 3600, "H2": 7200, "H3": 10800, "H4": 14400, "H6": 21600,
    "H8": 28800, "H12": 43200, "D1": 86400, "W1": 604800,
}


def timeframe_seconds(timeframe):
    """Bar length in seconds. Raises on an unknown timeframe rather than guessing.

    Guessing is what the old code did -- it hardcoded a 5-minute bar inside the
    candle fetch, and a 300-second hold in run_bot.py, both of which were silently
    wrong on any other timeframe.
    """
    key = str(timeframe).upper().strip()
    if key not in TIMEFRAME_SECONDS:
        raise ValueError(
            "Unknown timeframe %r. Known: %s"
            % (timeframe, ", ".join(sorted(TIMEFRAME_SECONDS)))
        )
    return TIMEFRAME_SECONDS[key]


class BarGate:
    """Tracks the last bar acted on, and refuses a second action on it."""

    def __init__(self, timeframe):
        self.timeframe = timeframe
        self.bar_seconds = timeframe_seconds(timeframe)
        self.last_entry_bar = None
        self.last_signal = None
        self.last_signal_bar = None

    # ---------------------------------------------------------------- entry

    def may_enter(self, bar_time):
        """True if no entry has been taken for this bar timestamp yet."""
        if bar_time is None:
            logger.warning("No bar timestamp available -- refusing entry.")
            return False
        if self.last_entry_bar == bar_time:
            logger.info("Already entered on bar %s -- skipping.", bar_time)
            return False
        return True

    def record_entry(self, bar_time):
        self.last_entry_bar = bar_time

    # ------------------------------------------------------- reversal hold

    def apply_reversal_hold(self, signal, strength, bar_time,
                            min_reversal_strength, min_hold_bars):
        """Suppress a weak or hasty signal reversal.

        Ported from ``run_bot.py::trading_bot`` (see
        docs/phase4-entry-gating.md), with its unit bug fixed: the original
        compared elapsed wall-clock seconds against ``min_hold_candles * 300``,
        hardcoding a 5-minute bar. This counts **bars**, so it is correct on any
        timeframe.

        Returns the signal to act on: the new one, or ``"HOLD"`` when the
        reversal is suppressed.

        Phase 12 follow-up: a suppressed reversal used to return the PREVIOUS
        signal. The caller kept the new bar's strength, so a SELL at 70% after
        a held BUY became a BUY entry at 70% -- a trade in the direction the
        current bar argues against. Suppressing a reversal now means "do not
        enter", and the previously held signal stays remembered.
        """
        if signal not in ("BUY", "SELL"):
            return signal

        previous = self.last_signal
        if previous in ("BUY", "SELL") and signal != previous:
            if strength < min_reversal_strength:
                logger.info(
                    "Reversal %s -> %s ignored: strength %.1f%% < %.1f%%",
                    previous, signal, strength, min_reversal_strength)
                return "HOLD"

            bars_held = self.bars_since_signal(bar_time)
            if bars_held is not None and bars_held < min_hold_bars:
                logger.info(
                    "Reversal %s -> %s ignored: held %d bars < %d required",
                    previous, signal, bars_held, min_hold_bars)
                return "HOLD"

        self.last_signal = signal
        self.last_signal_bar = bar_time
        return signal

    def bars_since_signal(self, bar_time):
        """Bars elapsed since the last recorded signal, or None if unknown."""
        if self.last_signal_bar is None or bar_time is None:
            return None
        try:
            elapsed = (bar_time - self.last_signal_bar).total_seconds()
        except (TypeError, AttributeError):
            return None
        return int(elapsed // self.bar_seconds)

    # ------------------------------------------------------------- timing

    def seconds_until_next_bar(self, now_epoch):
        """Seconds until the next bar closes, plus a small settle margin.

        Aligning to the bar close replaces the fixed 60s sleep. A couple of
        seconds of margin lets the broker publish the closed bar before we ask
        for it.
        """
        remainder = now_epoch % self.bar_seconds
        wait = self.bar_seconds - remainder
        if wait < 1:
            wait += self.bar_seconds
        return wait + 2.0

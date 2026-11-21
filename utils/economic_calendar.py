"""Economic calendar and no-trade windows (Phase 10, audit H-05).

`HIGH_IMPACT_NEWS_CLOSE` and `ECONOMIC_EVENT_CLOSE_MINUTES` were referenced
nowhere: **there was no economic calendar at all.** The bot traded straight
into CPI, NFP and FOMC with no awareness that anything was scheduled.

That matters more for gold than for most instruments. XAUUSD is a direct
expression of real-rate and dollar expectations, so it repices violently on
exactly these releases -- and in the seconds around them the spread widens,
liquidity vanishes and stops slip. A stop is a request, not a guarantee, and
these are the moments when the difference shows up on the statement.

**On the data source.** A live calendar needs a provider (ForexFactory,
Investing.com, FMP, Trading Economics). MetaTrader5's own
`mt5.calendar_event_get` exists but is not exposed by the Python package on
every build. Rather than hardcode a dependency on an API that may need a key or
may not exist, this module reads a **local JSON file** you can populate from any
source, and ships with the recurring US releases that move gold.

Deliberately conservative: an empty or unreadable calendar means "I do not know
what is scheduled", and `is_blackout()` reports that distinctly from "nothing is
scheduled". Trading blind is a choice, not a default.
"""

import io
import json
import logging
import os
from datetime import datetime, time as dt_time, timedelta, timezone

logger = logging.getLogger("xau_bot")

DEFAULT_CALENDAR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "economic_calendar.json")

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# Recurring US releases that reliably move gold, in NEW YORK local time. Used
# only when no calendar file is present -- a dated file always takes precedence.
#
# Phase 12 follow-up: these were UTC hours (13:30, 19:00), which are right only
# in US winter. In summer 08:30 New York is 12:30 UTC, so every blackout
# opened an hour after the release.
RECURRING_NY = [
    # (label, weekday or None, day-of-month rule, hh, mm, impact)
    ("US CPI", None, "monthly-mid", 8, 30, HIGH),
    ("US Non-Farm Payrolls", 4, "first-friday", 8, 30, HIGH),
    ("FOMC rate decision", 2, "fomc-day", 14, 0, HIGH),
    ("US initial jobless claims", 3, "weekly", 8, 30, MEDIUM),
]

# Scheduled FOMC decision days, as published by the Federal Reserve. Outside
# these years the fallback is any Wednesday in days 15-22 (conservative).
FOMC_DECISION_DAYS = {
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    "2026-09-16", "2026-10-28", "2026-12-09",
}


class Event:
    """One scheduled release."""

    def __init__(self, name, when, impact=HIGH, currency="USD"):
        self.name = name
        self.when = when
        self.impact = impact
        self.currency = currency

    def __repr__(self):
        return "<Event %s %s %s>" % (self.name, self.when.isoformat(), self.impact)

    def window(self, before_minutes, after_minutes):
        return (self.when - timedelta(minutes=before_minutes),
                self.when + timedelta(minutes=after_minutes))


class EconomicCalendar:
    """Scheduled events, loaded from a JSON file.

    File format -- a list of objects::

        [{"name": "US CPI", "when": "2026-01-13T13:30:00+00:00",
          "impact": "high", "currency": "USD"}]
    """

    def __init__(self, path=None, use_recurring_fallback=True):
        self.path = path or DEFAULT_CALENDAR
        self.use_recurring_fallback = use_recurring_fallback
        self.events = []
        self.loaded = False
        self.load_error = None
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.load_error = "calendar file not found: %s" % self.path
            logger.warning("No economic calendar at %s. %s", self.path,
                           "Falling back to recurring releases."
                           if self.use_recurring_fallback
                           else "No event awareness at all.")
            return self

        try:
            with io.open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as exc:
            self.load_error = "could not read calendar: %s" % exc
            logger.error("Economic calendar unreadable (%s). Treating the "
                         "schedule as UNKNOWN rather than empty.", exc)
            return self

        events = []
        for entry in raw if isinstance(raw, list) else []:
            try:
                when = datetime.fromisoformat(str(entry["when"]))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                events.append(Event(str(entry.get("name", "unnamed")), when,
                                    str(entry.get("impact", HIGH)).lower(),
                                    str(entry.get("currency", "USD"))))
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed calendar entry %r: %s",
                               entry, exc)

        self.events = sorted(events, key=lambda e: e.when)
        self.loaded = True
        self.load_error = None
        logger.info("Loaded %d calendar event(s) from %s.",
                    len(self.events), self.path)
        return self

    # ------------------------------------------------------------ queries

    def events_between(self, start, end, min_impact=HIGH):
        order = {LOW: 0, MEDIUM: 1, HIGH: 2}
        threshold = order.get(min_impact, 2)
        return [e for e in self.events
                if start <= e.when <= end
                and order.get(e.impact, 2) >= threshold]

    def next_event(self, now=None, min_impact=HIGH):
        now = now or datetime.now(timezone.utc)
        upcoming = self.events_between(now, now + timedelta(days=14), min_impact)
        return upcoming[0] if upcoming else None

    def is_blackout(self, now=None, before_minutes=30, after_minutes=15,
                    min_impact=HIGH):
        """Should trading be suspended right now?

        Returns ``(blocked, reason)``. Three distinct outcomes, deliberately:

        * ``(True, "...")``  -- an event is inside the window.
        * ``(False, None)``  -- the calendar is loaded and nothing is scheduled.
        * ``(True, "schedule unknown ...")`` when ``require_calendar`` applies --
          we do not know, and not knowing is not the same as nothing.
        """
        now = now or datetime.now(timezone.utc)

        if not self.loaded:
            if self.use_recurring_fallback:
                hit = self._recurring_blackout(now, before_minutes, after_minutes)
                if hit:
                    return True, hit
                return False, None
            return True, ("economic schedule unknown (%s) -- refusing to trade "
                          "blind into a possible release" % self.load_error)

        window_start = now - timedelta(minutes=after_minutes)
        window_end = now + timedelta(minutes=before_minutes)
        for event in self.events_between(window_start, window_end, min_impact):
            delta = (event.when - now).total_seconds() / 60.0
            return True, ("%s (%s impact) %s" % (
                event.name, event.impact,
                "in %.0f min" % delta if delta >= 0 else "%.0f min ago" % -delta))
        return False, None

    def _recurring_blackout(self, now, before_minutes, after_minutes):
        """Approximate blackout from the recurring release schedule.

        A coarse safety net for when no calendar file is present. It cannot
        know holidays or schedule changes, so it is not a substitute for a real
        calendar -- it just means the unconfigured case is not wide open.
        """
        from utils.market_time import NEW_YORK

        local = now.astimezone(NEW_YORK)
        years_known = {d[:4] for d in FOMC_DECISION_DAYS}
        for name, weekday, rule, hour, minute, impact in RECURRING_NY:
            if impact != HIGH:
                continue
            if weekday is not None and local.weekday() != weekday:
                continue
            if rule == "first-friday" and local.day > 7:
                continue
            if rule == "monthly-mid" and not (10 <= local.day <= 15 and local.weekday() < 5):
                continue
            if rule == "fomc-day":
                if str(local.year) in years_known:
                    if local.strftime("%Y-%m-%d") not in FOMC_DECISION_DAYS:
                        continue
                elif not (15 <= local.day <= 22):
                    continue

            event_time = local.replace(hour=hour, minute=minute, second=0,
                                       microsecond=0)
            start = event_time - timedelta(minutes=before_minutes)
            end = event_time + timedelta(minutes=after_minutes)
            if start <= local <= end:
                return ("%s (recurring estimate, no calendar file) at %s New York"
                        % (name, event_time.strftime("%H:%M")))
        return None

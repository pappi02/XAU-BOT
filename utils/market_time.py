"""Broker server time, UTC, and the gold trading calendar -- in one place.

MetaTrader 5 stamps ticks, bars, positions and deals in the broker's SERVER
time, encoded as if it were a Unix epoch. It is not UTC. Before this module the
code treated it as UTC everywhere, which meant:

* position age (``time.time() - position.time``) was off by the server offset
  -- on a UTC+3 server a new position looked three hours in the FUTURE, so the
  minimum hold never elapsed on time and the 24 h age exit fired 3 h late;
* the candle staleness check compared a UTC clock with server-time bars, so a
  feed up to three hours stale still passed;
* session boundaries were fixed UTC hours, an hour wrong for half of each year.

**The broker's clock (measured, 2026-09-13).** In 1.43 years of MetaQuotes-Demo
XAUUSD M5 bars the daily maintenance break sits at 00:00-01:00 server time in
both US summer and US winter. Gold's break is 17:00-18:00 New York time, so
server time = New York local time + 7 h (UTC+3 in US summer, UTC+2 in winter).
This is the common "New York close" server convention. It is configured
(``BROKER_SERVER_TZ`` / ``BROKER_SERVER_SHIFT_HOURS``) and checked against a
live tick at startup.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")

# Gold (spot/CFD) weekly close: Friday 17:00 New York.
WEEKLY_CLOSE_NY_HOUR = 17


class BrokerClock:
    """Converts between broker server time and real UTC."""

    def __init__(self, tz_name="America/New_York", shift_hours=7.0):
        self.zone = ZoneInfo(tz_name)
        self.shift = timedelta(hours=float(shift_hours))

    @classmethod
    def from_config(cls, config):
        # Only real values count: a partial test double answers every
        # attribute with a Mock. Production config is schema-validated.
        tz_name = getattr(config, "BROKER_SERVER_TZ", None)
        shift = getattr(config, "BROKER_SERVER_SHIFT_HOURS", None)
        return cls(tz_name if isinstance(tz_name, str) else "America/New_York",
                   shift if isinstance(shift, (int, float)) else 7.0)

    # ---------------------------------------------------------- conversion

    def offset_at(self, utc_dt):
        """Server-minus-UTC offset at a real UTC instant."""
        local = utc_dt.astimezone(self.zone)
        return local.utcoffset() + self.shift

    def server_epoch_to_utc(self, server_epoch):
        """An MT5 timestamp (server time as epoch seconds) -> aware UTC datetime."""
        naive = datetime(1970, 1, 1) + timedelta(seconds=float(server_epoch))
        return self.server_naive_to_utc(naive)

    def server_naive_to_utc(self, naive):
        """Server wall-clock time -> aware UTC datetime.

        The wall-clock ``-7 h`` is applied before attaching the zone, so the
        zone rules decide whether that New York time was EST or EDT.
        """
        naive = naive.replace(tzinfo=None)
        local = (naive - self.shift).replace(tzinfo=self.zone)
        return local.astimezone(UTC)

    def utc_to_server_epoch(self, utc_dt):
        return (utc_dt + self.offset_at(utc_dt)).replace(tzinfo=UTC).timestamp()

    def index_to_utc(self, index):
        """A pandas DatetimeIndex of server times (naive or tagged UTC) -> true UTC."""
        import pandas as pd

        naive = index.tz_localize(None) if index.tz is not None else index
        # US DST changes at 02:00 New York on a Sunday, inside gold's weekend
        # closure, so no real bar is ambiguous or nonexistent. The arguments
        # only keep a malformed series from raising.
        local = (naive - pd.Timedelta(self.shift)).tz_localize(
            self.zone, ambiguous=True, nonexistent="shift_forward")
        return local.tz_convert(UTC)

    def age_seconds(self, server_epoch, now_utc=None):
        """Seconds since a server-time stamp (e.g. ``position.time``)."""
        now_utc = now_utc or datetime.now(UTC)
        return (now_utc - self.server_epoch_to_utc(server_epoch)).total_seconds()

    # ------------------------------------------------------- verification

    def measured_offset_hours(self, tick_server_epoch, now_epoch):
        """Offset implied by a live tick, rounded to 30 min; None if the tick is stale.

        A tick more than two minutes older than its rounded offset means the
        market is closed or the feed is stale, and says nothing about the clock.
        """
        raw = float(tick_server_epoch) - float(now_epoch)
        rounded = round(raw / 1800.0) * 1800.0
        # Real UTC offsets lie within +/-14 h. A tick that is, say, exactly 25 h
        # old would otherwise round cleanly and pass as a clock offset.
        if abs(raw - rounded) > 120 or abs(rounded) > 14 * 3600:
            return None
        return rounded / 3600.0

    def expected_offset_hours(self, now_utc=None):
        return self.offset_at(now_utc or datetime.now(UTC)).total_seconds() / 3600.0

    def verify(self, mt5, symbol, now_epoch=None):
        """Check the configured rule against a live tick.

        Returns ``(status, message)`` where status is "ok", "mismatch" or
        "unverifiable" (market closed, or no tick). A mismatch means every
        age, staleness and weekend-close decision would be wrong by hours.
        """
        import time as _time

        now_epoch = _time.time() if now_epoch is None else now_epoch
        tick = mt5.symbol_info_tick(symbol)
        if tick is None or not getattr(tick, "time", None):
            return "unverifiable", "no tick for %s" % symbol
        measured = self.measured_offset_hours(tick.time, now_epoch)
        expected = self.expected_offset_hours(
            datetime.fromtimestamp(now_epoch, UTC))
        if measured is None:
            return "unverifiable", ("last %s tick is not current (market closed?); "
                                    "using configured offset %+.1f h" % (symbol, expected))
        if abs(measured - expected) > 0.01:
            return "mismatch", (
                "broker server clock is UTC%+.1f h but BROKER_SERVER_TZ/"
                "BROKER_SERVER_SHIFT_HOURS say UTC%+.1f h. Fix config before "
                "trading: position age, staleness and the weekend close depend "
                "on it." % (measured, expected))
        return "ok", "broker server clock UTC%+.1f h matches config" % measured


# ------------------------------------------------------------- sessions

def market_session(utc_dt):
    """Trading session at a UTC instant, following London and New York DST.

    London 08:00-16:00 London time; New York 08:00-17:00 New York time; the
    overlap is its own regime. Asian is 00:00-08:00 UTC outside both.
    """
    london = 8 <= utc_dt.astimezone(LONDON).hour < 16
    new_york = 8 <= utc_dt.astimezone(NEW_YORK).hour < 17
    if london and new_york:
        return "London/NY overlap"
    if london:
        return "London"
    if new_york:
        return "New York"
    if 0 <= utc_dt.astimezone(UTC).hour < 8:
        return "Asian"
    return "Other"


def weekly_close_utc(utc_dt):
    """The next (or current) Friday 17:00 New York close, in UTC."""
    local = utc_dt.astimezone(NEW_YORK)
    days_ahead = (4 - local.weekday()) % 7
    close = (local + timedelta(days=days_ahead)).replace(
        hour=WEEKLY_CLOSE_NY_HOUR, minute=0, second=0, microsecond=0)
    if close <= local:
        close += timedelta(days=7)
    return close.astimezone(UTC)


def minutes_to_weekly_close(utc_dt):
    return (weekly_close_utc(utc_dt) - utc_dt).total_seconds() / 60.0


def in_weekend_close_window(utc_dt, buffer_minutes):
    """True within ``buffer_minutes`` of the Friday close, or after it until Sunday."""
    local = utc_dt.astimezone(NEW_YORK)
    if local.weekday() == 5 or (local.weekday() == 4 and local.hour >= WEEKLY_CLOSE_NY_HOUR):
        return True
    if local.weekday() == 6 and local.hour < 18:
        return True
    return local.weekday() == 4 and minutes_to_weekly_close(utc_dt) <= float(buffer_minutes)

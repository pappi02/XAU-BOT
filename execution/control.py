"""Circuit breaker, kill switch and health reporting (Phase 8, audit H-11).

The audited loops wrapped everything in `except Exception` and slept. There was
no failure counter, so a broker rejecting every single order produced an
**indefinite silent outage that looked exactly like a running bot**: the process
was up, the log ticked over, and nothing traded. Nobody would notice until they
went looking.

There was also no way to stop it short of killing the process, which under
`run_bot.py` meant daemon threads dying instantly with open positions and no
cleanup.
"""

import json
import logging
import os
import signal
from datetime import datetime, timezone

logger = logging.getLogger("xau_bot")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_KILL_FILE = os.path.join(ROOT, "STOP")
DEFAULT_HEALTH_FILE = os.path.join(ROOT, "logs", "health.json")
DEFAULT_CANDLE_CACHE = os.path.join(ROOT, "logs", "candles.csv")


class CircuitBreaker:
    """Trips after N consecutive failures, and stays tripped until reset.

    Consecutive is the right counter, not a rate: one failure in a quiet hour
    is noise, but five in a row means something is systematically wrong -- a
    rejected filling mode, an expired session, a symbol that stopped trading.
    """

    def __init__(self, threshold=5, name="loop"):
        self.threshold = int(threshold)
        self.name = name
        self.consecutive_failures = 0
        self.total_failures = 0
        self.tripped_at = None
        self.last_error = None

    @property
    def is_tripped(self):
        return self.tripped_at is not None

    def record_success(self):
        if self.consecutive_failures:
            logger.info("Circuit breaker '%s': recovered after %d failure(s).",
                        self.name, self.consecutive_failures)
        self.consecutive_failures = 0

    def record_failure(self, error=None):
        """Count a failure. Returns True if this one tripped the breaker."""
        self.consecutive_failures += 1
        self.total_failures += 1
        self.last_error = str(error) if error is not None else None

        logger.error("Circuit breaker '%s': failure %d/%d -- %s",
                     self.name, self.consecutive_failures, self.threshold,
                     self.last_error)

        if self.consecutive_failures >= self.threshold and not self.is_tripped:
            self.tripped_at = datetime.now(timezone.utc)
            logger.critical(
                "CIRCUIT BREAKER TRIPPED ('%s') after %d consecutive failures. "
                "HALTING TRADING. Last error: %s. This is the state that used "
                "to present as a healthy running bot.",
                self.name, self.consecutive_failures, self.last_error)
            return True
        return False

    def reset(self):
        logger.warning("Circuit breaker '%s' reset.", self.name)
        self.consecutive_failures = 0
        self.tripped_at = None
        self.last_error = None

    def status(self):
        return {
            "name": self.name,
            "tripped": self.is_tripped,
            "tripped_at": self.tripped_at.isoformat() if self.tripped_at else None,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "threshold": self.threshold,
            "last_error": self.last_error,
        }


class KillSwitch:
    """A sentinel file that stops new positions without killing the process.

    A file, deliberately: it works from any shell, any user, any machine with
    access to the directory, and survives the bot not listening on a socket. To
    stop opening positions::

        touch STOP        (or: New-Item STOP)

    Existing positions are left alone -- stopping *entries* and closing
    *everything* are different decisions, and conflating them means the only
    way to pause is to liquidate.
    """

    def __init__(self, path=None):
        self.path = path or DEFAULT_KILL_FILE
        self._last_state = False

    def is_engaged(self):
        engaged = os.path.exists(self.path)
        if engaged != self._last_state:
            if engaged:
                logger.critical("KILL SWITCH ENGAGED (%s present). No new "
                                "positions will be opened. Existing positions "
                                "are untouched.", self.path)
            else:
                logger.warning("Kill switch released (%s removed). Trading "
                               "may resume.", self.path)
            self._last_state = engaged
        return engaged

    def engage(self, reason="engaged programmatically"):
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write("%s\n%s\n" % (datetime.now(timezone.utc).isoformat(),
                                       reason))
        except OSError as exc:
            logger.error("Could not create the kill-switch file: %s", exc)

    def release(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except OSError as exc:
            logger.error("Could not remove the kill-switch file: %s", exc)


class ShutdownHandler:
    """Turn SIGINT/SIGTERM into an orderly stop.

    Ctrl-C used to kill daemon threads instantly, with open positions and no
    cleanup. This sets a flag the loop checks, so the current iteration
    finishes and the connection closes properly. A second signal still
    hard-exits, because an unresponsive process must remain killable.
    """

    def __init__(self):
        self.should_stop = False
        self._signal_count = 0
        self._installed = False

    def install(self):
        try:
            signal.signal(signal.SIGINT, self._handle)
            signal.signal(signal.SIGTERM, self._handle)
            self._installed = True
        except (ValueError, AttributeError, OSError) as exc:
            # Not the main thread, or an unsupported platform.
            logger.warning("Could not install signal handlers: %s", exc)
        return self

    def _handle(self, signum, frame):
        self._signal_count += 1
        if self._signal_count == 1:
            self.should_stop = True
            logger.critical(
                "Signal %s received. Finishing the current iteration then "
                "shutting down cleanly. Send it again to force-exit.", signum)
        else:
            logger.critical("Second signal -- forcing exit.")
            raise KeyboardInterrupt()


class HealthReport:
    """Last-known state, written to a file the loop refreshes (Phase 8.4)."""

    def __init__(self, path=None):
        self.path = path or DEFAULT_HEALTH_FILE
        self.data = {
            "last_loop_time": None,
            "connected": None,
            "open_positions": None,
            "daily_pnl": None,
            "circuit_breaker": None,
            "kill_switch": None,
            "halted_reason": None,
        }
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except (OSError, ValueError):
            pass

    def update(self, **fields):
        self.data.update(fields)
        self.data["last_loop_time"] = datetime.now(timezone.utc).isoformat()
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, default=str)
            os.replace(tmp, self.path)
        except (OSError, ValueError) as exc:
            logger.error("Could not write the health report: %s", exc)
        return self.data

    def read(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None


def _plain(value):
    """JSON-safe scalar."""
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def broker_snapshot(mt5, symbol, positions=None):
    """Account, positions and last tick as plain JSON-safe data (Phase 12.1).

    The trading loop is the ONLY process that talks to MT5. It writes this
    snapshot into the health report every iteration; the read API and the
    dashboard read the file. That replaces run_bot.py's design, where a Flask
    thread, the trading thread and a Streamlit subprocess all shared one MT5
    terminal connection -- and the MetaTrader5 package is not documented as
    thread-safe and permits one connection per process.

    Never raises: a snapshot failure must not stop trading.
    """
    snapshot = {"account": None, "positions": [], "tick": None}

    try:
        account = mt5.account_info()
        if account is not None:
            snapshot["account"] = {
                "login": _plain(getattr(account, "login", None)),
                "server": _plain(getattr(account, "server", None)),
                "balance": _plain(getattr(account, "balance", None)),
                "equity": _plain(getattr(account, "equity", None)),
                "free_margin": _plain(getattr(account, "margin_free", None)),
                "margin_level": _plain(getattr(account, "margin_level", None)),
                "trade_mode": _plain(getattr(account, "trade_mode", None)),
            }
    except Exception as exc:
        logger.warning("Snapshot: account read failed: %s", exc)

    fields = ("ticket", "symbol", "type", "volume", "price_open",
              "price_current", "sl", "tp", "profit", "swap", "time", "magic",
              "comment")
    for pos in positions or []:
        snapshot["positions"].append(
            {f: _plain(getattr(pos, f, None)) for f in fields})

    try:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is not None:
            point = float(getattr(info, "point", 0.01) or 0.01)
            bid, ask = float(tick.bid), float(tick.ask)
            snapshot["tick"] = {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "spread_points": round((ask - bid) / point, 1),
                "volume": _plain(getattr(tick, "volume", None)),
                "time": _plain(getattr(tick, "time", None)),
            }
    except Exception as exc:
        logger.warning("Snapshot: tick read failed: %s", exc)

    return snapshot


def publish_candles(df, path=None, bars=500):
    """Write the most recent CLOSED bars for read-only consumers (Phase 12.1).

    The dashboard's chart and signal tabs used to call get_candles(), which
    calls mt5.initialize() itself -- a hidden extra MT5 client in a separate
    process. The trading loop already holds the bars; publishing them costs one
    small file write per bar and removes that connection entirely.

    Atomic (write-then-replace), so a reader never sees a half-written file.
    Never raises.
    """
    path = path or DEFAULT_CANDLE_CACHE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        columns = [c for c in ("open", "high", "low", "close", "tick_volume",
                               "spread") if c in df.columns]
        df[columns].tail(bars).to_csv(tmp)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.warning("Could not publish candle cache: %s", exc)
        return False

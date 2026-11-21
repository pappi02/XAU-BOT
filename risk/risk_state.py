"""Durable risk state (Phase 3.3, 3.4).

Two facts must outlive the process, or the limits built on them are theatre:

  * **The day's opening balance.** The daily loss limit measures against it. If
    it resets on restart, a bot that has lost 30% and been killed comes back
    believing it is flat -- and the limit that was supposed to stop trading
    instead authorises a fresh day of losses.
  * **The equity high-water mark.** Drawdown is measured from the peak equity
    ever observed. The audited code measured it from a hardcoded
    `INITIAL_ACCOUNT_BALANCE = 150.0`, which reads 33% permanently on a $100
    account and can never fire on a $500 one.

Stored as JSON next to the code. Small, human-readable, and easy to inspect when
something looks wrong -- which matters more here than write throughput.
"""

import io
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "risk_state.json"
)


class RiskState:
    """Persisted risk facts. Safe to construct when the file does not exist."""

    def __init__(self, path=None):
        self.path = path or DEFAULT_PATH
        self._data = {
            "trading_day": None,        # ISO date, broker/UTC
            "day_opening_balance": None,
            "equity_high_water_mark": None,
            "halted_reason": None,      # set when a limit trips; blocks entries
        }
        self.load()

    # ------------------------------------------------------------- storage

    def load(self):
        if not os.path.exists(self.path):
            return self
        try:
            with io.open(self.path, encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                self._data.update(stored)
        except (ValueError, OSError) as exc:
            # A corrupt state file must not silently become "no limits".
            logger.error("Could not read risk state %s: %s. Treating as halted "
                         "until it is repaired or deleted.", self.path, exc)
            self._data["halted_reason"] = "risk state file unreadable: %s" % exc
        return self

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with io.open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, sort_keys=True)
            os.replace(tmp, self.path)       # atomic on Windows and POSIX
        except OSError as exc:
            logger.error("Could not persist risk state to %s: %s",
                         self.path, exc)
        return self

    # -------------------------------------------------------------- fields

    @property
    def day_opening_balance(self):
        return self._data["day_opening_balance"]

    @property
    def equity_high_water_mark(self):
        return self._data["equity_high_water_mark"]

    @property
    def halted_reason(self):
        return self._data["halted_reason"]

    def halt(self, reason):
        """Block further entries until explicitly cleared."""
        if self._data["halted_reason"] != reason:
            logger.error("Trading halted: %s", reason)
        self._data["halted_reason"] = reason
        self.save()

    def clear_halt(self):
        self._data["halted_reason"] = None
        self.save()

    # ------------------------------------------------------------ updates

    def start_of_day(self, balance, now=None):
        """Roll the trading day over if needed, recording the opening balance.

        Returns True if a new day was started.
        """
        now = now or datetime.now(timezone.utc)
        today = now.date().isoformat()

        if self._data["trading_day"] == today:
            return False

        self._data["trading_day"] = today
        self._data["day_opening_balance"] = float(balance)
        # A new day lifts a halt that was caused by the previous day's loss.
        if self._data["halted_reason"] and "daily loss" in self._data["halted_reason"]:
            self._data["halted_reason"] = None
        logger.info("New trading day %s; opening balance %.2f", today, balance)
        self.save()
        return True

    def observe_equity(self, equity):
        """Update the high-water mark. Returns the current mark."""
        equity = float(equity)
        mark = self._data["equity_high_water_mark"]
        if mark is None or equity > mark:
            self._data["equity_high_water_mark"] = equity
            self.save()
        return self._data["equity_high_water_mark"]

    def drawdown_fraction(self, equity):
        """Fractional drawdown from the high-water mark, in [0, 1]."""
        mark = self.observe_equity(equity)
        if not mark or mark <= 0:
            return 0.0
        return max(0.0, (mark - float(equity)) / mark)

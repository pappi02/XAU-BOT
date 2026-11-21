"""Read-only data access for the dashboard (Phase 12.1, audit M-09).

Every value the dashboard shows comes through here, and everything here reads
files that ``main.py`` alone writes:

  * ``logs/health.json``      account, positions, last tick, control state
  * ``logs/candles.csv``      recent closed bars
  * ``logs/decisions.jsonl``  one record per trading decision
  * ``trades.db``             broker-sourced deals

Nothing in this module imports MetaTrader5, and a test enforces that. It also
imports no Streamlit, so it can be tested directly.

**Freshness is part of every answer.** A dashboard that shows the last known
balance without saying it is three hours old is showing a fiction. Readers get
``age_seconds`` and ``stale`` alongside the values.
"""

import os
from datetime import datetime, timezone

import pandas as pd

from execution.control import (DEFAULT_CANDLE_CACHE, HealthReport, KillSwitch)
from execution.position_state import PositionStateStore
from logger_config import DecisionLog
from utils import db

STALE_AFTER_SECONDS = 600

POSITION_TYPE_BUY = 0     # MT5 constant, restated so this module needs no MT5


def health():
    """The latest health report, or an empty dict if the bot has never run."""
    return HealthReport().read() or {}


def freshness(report=None):
    report = report if report is not None else health()
    stamp = report.get("last_loop_time")
    age = None
    if stamp:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(stamp)).total_seconds()
        except (TypeError, ValueError):
            age = None
    return {
        "last_loop_time": stamp,
        "age_seconds": age,
        "stale": age is None or age > STALE_AFTER_SECONDS,
        "never_ran": stamp is None,
    }


def account(report=None):
    report = report if report is not None else health()
    return report.get("account") or {}


def positions(report=None):
    """Open positions as a DataFrame with a human-readable side column."""
    report = report if report is not None else health()
    rows = report.get("positions") or []
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    if "type" in frame.columns:
        frame["side"] = frame["type"].map(
            lambda t: "BUY" if t == POSITION_TYPE_BUY else "SELL")
    return frame


def tick(report=None):
    report = report if report is not None else health()
    return report.get("tick") or {}


def controls(report=None):
    report = report if report is not None else health()
    return {
        "circuit_breaker": report.get("circuit_breaker") or {},
        "kill_switch_reported": report.get("kill_switch"),
        "kill_switch_file": KillSwitch().is_engaged(),
        "halted_reason": report.get("halted_reason"),
    }


def candles(path=None):
    """Recent closed bars published by the bot, or an empty frame."""
    path = path or DEFAULT_CANDLE_CACHE
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
    except (OSError, ValueError):
        return pd.DataFrame()
    return frame


def statistics():
    """Realised statistics from broker deals (never local reconstruction)."""
    return PositionStateStore().compute_statistics()


def deals(limit=200):
    """Most recent broker deals, newest first."""
    store = PositionStateStore()
    with db.connect(store.db_path) as conn:
        frame = pd.read_sql_query(
            "SELECT deal_ticket, position_ticket, symbol, volume, price, "
            "profit, commission, swap, net_pnl, deal_time, comment "
            "FROM broker_deals ORDER BY deal_time DESC LIMIT ?",
            conn, params=(int(limit),))
    return frame


def closed_trades(limit=500):
    """Closed positions, newest first: open and close deals aggregated.

    One row per position, with the commission charged on the OPEN included.
    Listing raw deals made every opening deal look like a trade.
    """
    rows = PositionStateStore().closed_trades()[-int(limit):][::-1]
    columns = ["position_ticket", "direction", "lots", "entry_time", "exit_time",
               "entry_price", "exit_price", "net_pnl", "commission", "swap",
               "exit_reason", "holding_seconds"]
    return pd.DataFrame([{c: r.get(c) for c in columns} for r in rows], columns=columns)


def loss_streak():
    return PositionStateStore().consecutive_losses()


def decisions(limit=200):
    records = DecisionLog().read_all()[-int(limit):]
    return pd.DataFrame(records[::-1])


def engage_kill_switch(reason="engaged from dashboard"):
    """The REAL kill switch: the STOP file the trading loop checks every bar.

    Not a broker write, and not a session variable. The audited dashboard's
    "EMERGENCY KILL SWITCH" set st.session_state.kill_switch -- which the bot
    never reads -- and then displayed "All trading stopped!" while trading
    continued.
    """
    switch = KillSwitch()
    switch.engage(reason)
    return switch.is_engaged()


def release_kill_switch():
    switch = KillSwitch()
    switch.release()
    return not switch.is_engaged()

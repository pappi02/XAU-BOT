"""Read-only dashboard API and launcher (Phase 12.1, audit M-09).

This process NEVER connects to MetaTrader 5.

The previous design shared one MT5 terminal connection across three consumers:
a Flask thread, the trading thread, and a Streamlit subprocess. The MetaTrader5
Python package is not documented as thread-safe and permits one connection per
process, so that arrangement's correctness depended on luck. It also launched
the dashboard with ``subprocess.Popen([...], shell=True)`` and, before Phase 1,
connected to the broker as a side effect of being imported.

Now there is exactly one MT5 client: ``main.py``. It publishes its state every
loop iteration to files it alone writes:

  * ``logs/health.json``      account, positions, last tick, control state
  * ``trades.db``             broker-sourced deals and per-position state
  * ``logs/decisions.jsonl``  one record per trading decision

This API reads those files and nothing else. If the bot is not running, the
API reports stale state honestly (via ``last_loop_time``) rather than
reconnecting on its own.

Run the bot:        python main.py
Run the dashboard:  python run_bot.py
"""

import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify

import config
from execution.control import HealthReport
from execution.position_state import PositionStateStore
from logger_config import DecisionLog, setup_logger

logger = setup_logger(level=config.LOG_LEVEL)

API_HOST = "127.0.0.1"
API_PORT = 5001

# A snapshot older than this is reported as stale -- the bot has stopped
# writing, and the numbers are history, not the present.
STALE_AFTER_SECONDS = 600

app = Flask(__name__)


def _health():
    return HealthReport().read() or {}


def _age_seconds(health):
    stamp = health.get("last_loop_time")
    if not stamp:
        return None
    try:
        return (datetime.now(timezone.utc)
                - datetime.fromisoformat(stamp)).total_seconds()
    except (TypeError, ValueError):
        return None


def _freshness(health):
    age = _age_seconds(health)
    return {
        "last_loop_time": health.get("last_loop_time"),
        "age_seconds": age,
        "stale": age is None or age > STALE_AFTER_SECONDS,
    }


@app.route("/status")
def status():
    """Account state as last published by the trading loop."""
    health = _health()
    account = health.get("account") or {}
    fresh = _freshness(health)
    return jsonify({
        # "connected" means: the bot reported a connection recently. The API
        # itself is never connected, and says so rather than implying it.
        "connected": bool(health.get("connected")) and not fresh["stale"],
        "login": account.get("login"),
        "balance": account.get("balance"),
        "equity": account.get("equity"),
        "free_margin": account.get("free_margin"),
        "margin_level": account.get("margin_level"),
        "circuit_breaker": health.get("circuit_breaker"),
        "kill_switch": health.get("kill_switch"),
        "halted_reason": health.get("halted_reason"),
        **fresh,
    })


@app.route("/positions")
def positions():
    """Open positions as last published by the trading loop."""
    return jsonify(_health().get("positions") or [])


@app.route("/market_data")
def market_data():
    """Last tick as last published by the trading loop."""
    health = _health()
    tick = health.get("tick")
    if not tick:
        return jsonify({"error": "no market data published yet -- is main.py running?"}), 503
    return jsonify({
        "symbol": tick.get("symbol"),
        "bid": tick.get("bid"),
        "ask": tick.get("ask"),
        "spread": tick.get("spread_points"),
        "volume": tick.get("volume"),
        "time": tick.get("time"),
        **_freshness(health),
    })


@app.route("/statistics")
def statistics():
    """Realised statistics from broker deals (never local reconstruction)."""
    return jsonify(PositionStateStore().compute_statistics())


@app.route("/decisions")
def decisions():
    """The most recent structured decision records."""
    return jsonify(DecisionLog().read_all()[-100:])


# The /signals route was DELETED in Phase 12.1. It recomputed indicators from a
# live MT5 query on the API thread, hardcoded the symbol as "XAUUSDm" -- which
# does not exist on the configured broker -- and was called by nothing.


def run_api():
    app.run(host=API_HOST, port=API_PORT, debug=False, use_reloader=False)


def launch_dashboard():
    """Start Streamlit without a shell.

    ``shell=True`` passed the command through the platform shell for no
    benefit; invoking the current interpreter's module avoids both the shell
    and any mismatch between the ``streamlit`` on PATH and this environment.
    """
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "dashboard.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )


if __name__ == "__main__":
    threading.Thread(target=run_api, daemon=True, name="read-api").start()
    logger.info("Read-only API on http://%s:%d (no MT5 connection).",
                API_HOST, API_PORT)

    dashboard = launch_dashboard()
    logger.info("Streamlit dashboard started (pid %s).", dashboard.pid)

    try:
        while dashboard.poll() is None:
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Shutting down dashboard launcher.")
    finally:
        if dashboard.poll() is None:
            dashboard.terminate()

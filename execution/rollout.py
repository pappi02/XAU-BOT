"""Phase 13 guardrails: a live account trades only inside the micro-rollout.

The plan's Phase 13 is "only after Gates A-D": minimum lot, one position at a
time, a hard daily loss limit, and a daily manual review. ALLOW_LIVE=true was
the only thing between the bot and a live account; it said nothing about
whether the strategy had earned one. This module makes those conditions
checkable, and ``data.connect_mt5`` refuses a live login that fails them.

Evidence lives in ``docs/reports/gates.json``, written by the tools that
measure it:

* ``gate_c``  -- scripts/run_gate_c.py (the validation gauntlet);
* ``gate_d``  -- scripts/forward_test_report.py (automatic checks) plus a
  person's sign-off: ``"signed_off_by": "<name>"``;
* ``daily_review`` -- ``python main.py --record-review``.

Demo accounts are never restricted by this module.
"""

import json
import os
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES_PATH = os.path.join(ROOT, "docs", "reports", "gates.json")

REVIEW_MAX_AGE = timedelta(hours=36)


def load_gates(path=None):
    path = path or GATES_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_gates(gates, path=None):
    path = path or GATES_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(gates, fh, indent=2)


def record_gate(name, entry, path=None):
    gates = load_gates(path)
    gates.setdefault(name, {}).update(entry)
    save_gates(gates, path)
    return gates


def record_daily_review(reviewer, now=None, path=None):
    now = now or datetime.now(timezone.utc)
    return record_gate("daily_review", {"last_reviewed": now.isoformat(timespec="seconds"),
                                        "reviewed_by": reviewer}, path)


def review_overdue(gates, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = (gates.get("daily_review") or {}).get("last_reviewed")
    try:
        return now - datetime.fromisoformat(stamp) > REVIEW_MAX_AGE
    except (TypeError, ValueError):
        return True


def live_rollout_problems(config, gates=None, now=None):
    """Everything that forbids trading a LIVE account right now. Empty = allowed."""
    gates = load_gates() if gates is None else gates
    problems = []

    gate_c = gates.get("gate_c") or {}
    if gate_c.get("passed") is not True:
        problems.append("Gate C (validation gauntlet) has not passed: %s"
                        % (gate_c.get("verdict") or "not run"))
    gate_d = gates.get("gate_d") or {}
    if gate_d.get("automatic_checks_passed") is not True:
        problems.append("Gate D (demo forward test) automatic checks have not passed")
    if not str(gate_d.get("signed_off_by") or "").strip():
        problems.append("Gate D has no human sign-off (gate_d.signed_off_by)")

    if config.MAX_OPEN_TRADES != 1 or config.MAX_CONCURRENT_POSITIONS != 1:
        problems.append("micro-rollout is one position at a time "
                        "(MAX_OPEN_TRADES and MAX_CONCURRENT_POSITIONS must be 1)")
    if config.MAX_LOTS_PER_ORDER > config.LIVE_MAX_LOTS_PER_ORDER:
        problems.append("MAX_LOTS_PER_ORDER %.2f exceeds LIVE_MAX_LOTS_PER_ORDER %.2f"
                        % (config.MAX_LOTS_PER_ORDER, config.LIVE_MAX_LOTS_PER_ORDER))
    if config.MAX_DAILY_LOSS_FRACTION > config.LIVE_MAX_DAILY_LOSS_FRACTION:
        problems.append("MAX_DAILY_LOSS_FRACTION %.3f exceeds LIVE_MAX_DAILY_LOSS_FRACTION %.3f"
                        % (config.MAX_DAILY_LOSS_FRACTION, config.LIVE_MAX_DAILY_LOSS_FRACTION))
    if review_overdue(gates, now):
        problems.append("daily manual review is overdue (python main.py --record-review)")
    return problems

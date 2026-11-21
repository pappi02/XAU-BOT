"""Phase 11 forward-test report: the demo month, measured like the backtest.

    python scripts/forward_test_report.py [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                                          [--backtest docs/reports/<name>.json]
                                          [--reconcile]

OFFLINE by default. Reads realised trades from trades.db (broker deals, synced
by the running bot) and produces the same detailed report as a backtest: win
rate, total trades, wins, losses, maximum win and loss, drawdown, streaks,
holding time, costs, and breakdowns by direction, exit reason, session and
month. Then compares the forward test with the backtest on the Gate D measures.

``--reconcile`` makes ONE read-only broker connection to compare the bot's
records with the broker's own deal history for the period. It places no
orders.

Writes docs/reports/forward-test-<since>_<until>.{json,txt} and updates the
Gate D entry in docs/reports/gates.json (automatic checks only -- Gate D also
needs a person's sign-off; see execution/rollout.py).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.report import format_report, performance_report, save_report
from utils.market_time import market_session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(ROOT, "docs", "reports")
DEFAULT_BACKTEST = os.path.join(REPORT_DIR, "backtest-xauusd-m5-live-rules-no-halts.json")

# Gate D: "live trade frequency and cost profile match the backtest within a
# stated tolerance". Stated here.
TOLERANCES = {
    "trades_per_week": 0.35,            # +/-35% relative
    "average_holding_minutes": 0.35,
    "cost_per_lot": 0.35,
    "win_rate_pct": 10.0,               # +/-10 percentage points
}
MIN_FORWARD_DAYS = 28


def _date(text):
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def forward_records(store, since, until):
    records = []
    for trade in store.closed_trades():
        if trade["exit_time"] is None or not (since <= trade["exit_time"] < until):
            continue
        trade = dict(trade)
        trade["session"] = market_session(trade["entry_time"] or trade["exit_time"])
        records.append(trade)
    return records


def _per_week(report, days):
    return report["total_trades"] / (days / 7.0) if days > 0 else None


def _cost_per_lot(report):
    lots = report["total_lots"]
    c = report["costs"]
    return (c["commission"] + c["swap"]) / lots if lots else None


def compare(forward, forward_days, backtest):
    """Rows of (measure, forward, backtest, within_tolerance)."""
    first = datetime.fromisoformat(backtest["period"]["first_entry"])
    last = datetime.fromisoformat(backtest["period"]["last_exit"])
    backtest_days = max(1.0, (last - first).total_seconds() / 86400.0)

    rows = []

    def relative(name, f, b):
        ok = None if f is None or not b else abs(f - b) / abs(b) <= TOLERANCES[name]
        rows.append((name, f, b, ok))

    relative("trades_per_week", _per_week(forward, forward_days),
             _per_week(backtest, backtest_days))
    relative("average_holding_minutes", forward["average_holding_minutes"],
             backtest["average_holding_minutes"])
    # Spread and slippage are inside real fill prices, so only commission and
    # swap are comparable as explicit costs.
    relative("cost_per_lot", _cost_per_lot(forward), _cost_per_lot(backtest))
    f, b = forward["win_rate_pct"], backtest["win_rate_pct"]
    rows.append(("win_rate_pct", f, b, abs(f - b) <= TOLERANCES["win_rate_pct"]))
    rows.append(("expectancy_per_trade", forward["expectancy_per_trade"],
                 backtest["expectancy_per_trade"], None))
    return rows


def reconcile(store, since, until):
    """Compare recorded closed positions with the broker's deal history."""
    import MetaTrader5 as mt5

    import config
    from data.connect_mt5 import connect_mt5, disconnect_mt5
    from utils.market_time import BrokerClock

    if not connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD, config.MT5_SERVER,
                       config.MT5_TIMEOUT_MS):
        return {"error": "could not connect"}
    try:
        clock = BrokerClock.from_config(config)

        def server(dt):
            return datetime.fromtimestamp(clock.utc_to_server_epoch(dt), timezone.utc)

        deals = mt5.history_deals_get(server(since), server(until)) or ()
        broker = {}
        for d in deals:
            if int(getattr(d, "entry", -1)) in (1, 2, 3) and d.symbol == config.SYMBOL:
                broker[int(d.ticket)] = float(d.profit) + float(d.commission) + float(d.swap)
        with store._connect() as conn:
            rows = conn.execute("SELECT deal_ticket, net_pnl FROM broker_deals "
                                "WHERE entry_type IN (1, 2, 3)").fetchall()
        recorded = {int(r["deal_ticket"]): float(r["net_pnl"]) for r in rows}
        missing = sorted(set(broker) - set(recorded))
        mismatched = sorted(t for t in broker if t in recorded
                            and abs(broker[t] - recorded[t]) > 0.01)
        return {"broker_closing_deals": len(broker), "missing_from_bot": missing,
                "pnl_mismatches": mismatched,
                "zero_discrepancies": not missing and not mismatched}
    finally:
        disconnect_mt5()


def update_gates(entry):
    path = os.path.join(REPORT_DIR, "gates.json")
    gates = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            gates = json.load(fh)
    gates.setdefault("gate_d", {}).update(entry)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(gates, fh, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--backtest", default=DEFAULT_BACKTEST)
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--balance", type=float, default=1000.0)
    args = parser.parse_args(argv)

    from execution.position_state import PositionStateStore

    until = _date(args.until) if args.until else datetime.now(timezone.utc)
    since = _date(args.since) if args.since else until - timedelta(days=30)
    days = (until - since).total_seconds() / 86400.0
    store = PositionStateStore(args.db) if args.db else PositionStateStore()

    records = forward_records(store, since, until)
    report = performance_report(records, args.balance, {
        "notes": "forward test from broker deals, %s -> %s" % (since.date(), until.date())})
    title = "XAUUSD forward test %s -> %s" % (since.date(), until.date())
    lines = [format_report(report, title)]

    rows = []
    if os.path.exists(args.backtest):
        with open(args.backtest, encoding="utf-8") as fh:
            rows = compare(report, days, json.load(fh))
        lines += ["", "  Compared with backtest (%s)" % os.path.basename(args.backtest),
                  "    %-26s %14s %14s  %s" % ("measure", "forward", "backtest", "within tolerance")]
        for name, f, b, ok in rows:
            fmt = lambda v: "n/a" if v is None else "%.3f" % v
            lines.append("    %-26s %14s %14s  %s" % (
                name, fmt(f), fmt(b), {True: "yes", False: "NO", None: "-"}[ok]))
    else:
        lines.append("\n  No backtest report at %s to compare with." % args.backtest)

    reconciliation = reconcile(store, since, until) if args.reconcile else None
    if reconciliation is not None:
        lines += ["", "  Broker reconciliation: %s" % reconciliation]

    text = "\n".join(lines)
    print(text)
    os.makedirs(REPORT_DIR, exist_ok=True)
    stem = os.path.join(REPORT_DIR, "forward-test-%s_%s" % (since.date(), until.date()))
    report["comparison"] = [{"measure": n, "forward": f, "backtest": b, "ok": ok}
                            for n, f, b, ok in rows]
    report["reconciliation"] = reconciliation
    save_report(report, text, stem)

    automatic = (days >= MIN_FORWARD_DAYS and bool(rows)
                 and all(ok is not False for _, _, _, ok in rows)
                 and bool(reconciliation and reconciliation.get("zero_discrepancies")))
    update_gates({"automatic_checks_passed": automatic,
                  "period": [since.isoformat(), until.isoformat()],
                  "report": os.path.relpath(stem + ".txt", ROOT),
                  "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print("\nGate D automatic checks: %s (also requires >= %d days, --reconcile, and a "
          "person's sign-off in docs/reports/gates.json)"
          % ("PASS" if automatic else "NOT PASSED", MIN_FORWARD_DAYS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

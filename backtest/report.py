"""Detailed performance report for backtests and forward tests.

One function, ``performance_report``, used for every result the project
publishes: a backtest's trades, or broker deals from a forward test. Both are
reduced to the same record -- open time, close time, direction, lots, net P&L,
costs, exit reason -- so a demo month can be compared to its backtest line by
line.
"""

import json
import math
from collections import OrderedDict
from datetime import datetime


def _num(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value == value else default


def trade_records(trades):
    """Backtest trades -> plain dicts."""
    records = []
    for t in trades:
        records.append({
            "entry_time": t.entry_time, "exit_time": t.exit_time,
            "direction": t.direction, "lots": t.lots,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "net_pnl": t.net_pnl, "gross_pnl": t.gross_pnl,
            "spread": t.spread_cost, "commission": t.commission_cost,
            "swap": t.swap_cost, "slippage": t.slippage_cost,
            "exit_reason": getattr(t, "exit_reason", ""),
            "session": getattr(t, "session", ""),
            "holding_seconds": getattr(t, "holding_seconds", None),
            "risk_money": getattr(t, "risk_money", 0.0),
            "mfe_price": getattr(t, "mfe_price", None),
            "mae_price": getattr(t, "mae_price", None),
        })
    return records


def _streaks(pnls):
    best_win = best_loss = cur_win = cur_loss = 0
    for p in pnls:
        if p > 0:
            cur_win, cur_loss = cur_win + 1, 0
        elif p < 0:
            cur_win, cur_loss = 0, cur_loss + 1
        else:
            cur_win = cur_loss = 0
        best_win, best_loss = max(best_win, cur_win), max(best_loss, cur_loss)
    return best_win, best_loss


def _drawdown(initial, pnls, times):
    equity = peak = initial
    worst_money = worst_frac = 0.0
    peak_time, longest = times[0] if times else None, 0.0
    for pnl, when in zip(pnls, times):
        equity += pnl
        if equity >= peak:
            if peak_time is not None and when is not None:
                longest = max(longest, (when - peak_time).total_seconds())
            peak, peak_time = equity, when
        worst_money = max(worst_money, peak - equity)
        if peak > 0:
            worst_frac = max(worst_frac, (peak - equity) / peak)
    if times and peak_time is not None and times[-1] is not None:
        longest = max(longest, (times[-1] - peak_time).total_seconds())
    return worst_money, worst_frac, longest / 86400.0


def _group(records, key):
    groups = OrderedDict()
    for r in records:
        name = key(r)
        g = groups.setdefault(name, {"trades": 0, "wins": 0, "net_pnl": 0.0})
        g["trades"] += 1
        g["wins"] += 1 if r["net_pnl"] > 0 else 0
        g["net_pnl"] += r["net_pnl"]
    for g in groups.values():
        g["win_rate_pct"] = 100.0 * g["wins"] / g["trades"] if g["trades"] else 0.0
        g["expectancy"] = g["net_pnl"] / g["trades"] if g["trades"] else 0.0
    return dict(groups)


def performance_report(records, initial_balance, extras=None):
    """Every statistic the operator asked for, from a list of trade dicts."""
    records = sorted(records, key=lambda r: (r["exit_time"] is None, r["exit_time"]))
    pnls = [_num(r["net_pnl"]) for r in records]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n = len(pnls)
    net = sum(pnls)
    gross_profit, gross_loss = sum(wins), -sum(losses)
    best_streak, worst_streak = _streaks(pnls)
    times = [r["exit_time"] for r in records]
    dd_money, dd_frac, dd_days = _drawdown(initial_balance, pnls, times)

    def extreme(fn, pool):
        if not pool:
            return None
        r = fn(records, key=lambda x: _num(x["net_pnl"]))
        return {"net_pnl": round(_num(r["net_pnl"]), 2),
                "direction": r["direction"], "lots": r["lots"],
                "entry_time": str(r["entry_time"]), "exit_time": str(r["exit_time"]),
                "exit_reason": r.get("exit_reason", "")}

    holding = [r["holding_seconds"] for r in records if r.get("holding_seconds") is not None]
    r_multiples = [_num(r["net_pnl"]) / r["risk_money"] for r in records
                   if _num(r.get("risk_money")) > 0]
    mean = net / n if n else 0.0
    sd = (math.sqrt(sum((p - mean) ** 2 for p in pnls) / (n - 1)) if n > 1 else 0.0)

    costs = {k: round(sum(abs(_num(r.get(k))) for r in records), 2)
             for k in ("spread", "commission", "swap", "slippage")}
    total_costs = sum(costs.values())
    gross = sum(_num(r.get("gross_pnl")) for r in records)

    report = OrderedDict([
        ("period", {"first_entry": str(records[0]["entry_time"]) if records else None,
                    "last_exit": str(records[-1]["exit_time"]) if records else None}),
        ("initial_balance", round(initial_balance, 2)),
        ("final_balance", round(initial_balance + net, 2)),
        ("net_profit", round(net, 2)),
        ("return_pct", round(100.0 * net / initial_balance, 2) if initial_balance else None),
        ("total_trades", n),
        ("total_wins", len(wins)),
        ("total_losses", len(losses)),
        ("breakeven_trades", n - len(wins) - len(losses)),
        ("win_rate_pct", round(100.0 * len(wins) / n, 2) if n else 0.0),
        ("loss_rate_pct", round(100.0 * len(losses) / n, 2) if n else 0.0),
        ("gross_profit", round(gross_profit, 2)),
        ("gross_loss", round(-gross_loss, 2)),
        ("profit_factor", round(gross_profit / gross_loss, 3) if gross_loss else None),
        ("expectancy_per_trade", round(mean, 4)),
        ("expectancy_r", round(sum(r_multiples) / len(r_multiples), 4) if r_multiples else None),
        ("std_dev_per_trade", round(sd, 4)),
        ("t_statistic", round(mean / (sd / math.sqrt(n)), 3) if n > 1 and sd > 0 else None),
        ("average_win", round(gross_profit / len(wins), 2) if wins else 0.0),
        ("average_loss", round(-gross_loss / len(losses), 2) if losses else 0.0),
        ("payoff_ratio", round((gross_profit / len(wins)) / (gross_loss / len(losses)), 3)
         if wins and losses else None),
        ("maximum_win", extreme(max, wins)),
        ("maximum_loss", extreme(min, losses)),
        ("longest_winning_streak", best_streak),
        ("longest_losing_streak", worst_streak),
        ("max_drawdown_money", round(dd_money, 2)),
        ("max_drawdown_pct", round(100.0 * dd_frac, 2)),
        ("longest_drawdown_days", round(dd_days, 1)),
        ("average_holding_minutes", round(sum(holding) / len(holding) / 60.0, 1) if holding else None),
        ("total_lots", round(sum(_num(r["lots"]) for r in records), 2)),
        ("costs", dict(costs, total=round(total_costs, 2),
                       gross_pnl_before_commission_swap=round(gross, 2),
                       costs_pct_of_gross=round(100.0 * total_costs / abs(gross), 1) if gross else None)),
        ("by_direction", _group(records, lambda r: r["direction"])),
        ("by_exit_reason", _group(records, lambda r: r.get("exit_reason") or "unknown")),
        ("by_session", _group(records, lambda r: r.get("session") or "unknown")),
        ("by_month", _group(records, lambda r: str(r["exit_time"])[:7])),
        ("by_year", _group(records, lambda r: str(r["exit_time"])[:4])),
    ])
    for section in ("by_direction", "by_exit_reason", "by_session", "by_month", "by_year"):
        for g in report[section].values():
            g["net_pnl"] = round(g["net_pnl"], 2)
            g["win_rate_pct"] = round(g["win_rate_pct"], 1)
            g["expectancy"] = round(g["expectancy"], 3)
    if extras:
        report.update(extras)
    return report


def format_report(report, title="Performance report"):
    """Plain-text rendering for the terminal and for docs."""
    lines = [title, "=" * len(title)]

    def row(label, value):
        lines.append("  %-30s %s" % (label, value))

    def money(v):
        return "n/a" if v is None else "$%s" % format(v, ",.2f")

    row("Period", "%s -> %s" % (report["period"]["first_entry"], report["period"]["last_exit"]))
    row("Initial / final balance", "%s -> %s" % (money(report["initial_balance"]),
                                                  money(report["final_balance"])))
    row("Net profit (return)", "%s (%s%%)" % (money(report["net_profit"]), report["return_pct"]))
    row("Total trades", report["total_trades"])
    row("Wins / losses / breakeven", "%d / %d / %d" % (report["total_wins"],
                                                        report["total_losses"],
                                                        report["breakeven_trades"]))
    row("Win rate", "%.2f%%" % report["win_rate_pct"])
    row("Gross profit / gross loss", "%s / %s" % (money(report["gross_profit"]),
                                                   money(report["gross_loss"])))
    row("Profit factor", report["profit_factor"])
    row("Expectancy per trade", "%s (%s R)" % (money(report["expectancy_per_trade"]),
                                               report["expectancy_r"]))
    row("t-statistic of mean", report["t_statistic"])
    row("Average win / average loss", "%s / %s" % (money(report["average_win"]),
                                                    money(report["average_loss"])))
    row("Payoff ratio", report["payoff_ratio"])
    for label, key in (("Maximum win", "maximum_win"), ("Maximum loss", "maximum_loss")):
        e = report[key]
        row(label, "n/a" if not e else "%s %s %s lots, %s (%s)" % (
            money(e["net_pnl"]), e["direction"], e["lots"], e["exit_time"], e["exit_reason"]))
    row("Longest win / loss streak", "%d / %d" % (report["longest_winning_streak"],
                                                   report["longest_losing_streak"]))
    row("Max drawdown", "%s (%.2f%%), longest %.1f days" % (
        money(report["max_drawdown_money"]), report["max_drawdown_pct"],
        report["longest_drawdown_days"]))
    row("Average holding time", "%s min" % report["average_holding_minutes"])
    row("Total lots traded", report["total_lots"])
    c = report["costs"]
    row("Costs", "spread %s, commission %s, swap %s, slippage %s = %s (%s%% of gross)" % (
        money(c["spread"]), money(c["commission"]), money(c["swap"]),
        money(c["slippage"]), money(c["total"]), c["costs_pct_of_gross"]))

    for section, heading in (("by_direction", "By direction"),
                             ("by_exit_reason", "By exit reason"),
                             ("by_session", "By session"),
                             ("by_year", "By year"),
                             ("by_month", "By month")):
        lines.append("")
        lines.append("  %s" % heading)
        lines.append("    %-34s %7s %8s %12s %11s" % ("", "trades", "win %", "net P&L", "expectancy"))
        for name, g in report[section].items():
            lines.append("    %-34s %7d %7.1f%% %12s %11s" % (
                str(name)[:34], g["trades"], g["win_rate_pct"], money(g["net_pnl"]),
                money(g["expectancy"])))

    for key in ("blocked_entries", "halts", "declined_trades", "bars", "notes"):
        if key in report:
            lines.append("")
            value = report[key]
            if isinstance(value, dict):
                lines.append("  %s" % key.replace("_", " ").capitalize())
                for k, v in sorted(value.items(), key=lambda kv: -kv[1] if isinstance(kv[1], (int, float)) else 0):
                    lines.append("    %-40s %s" % (k, v))
            else:
                row(key.replace("_", " ").capitalize(), value)
    return "\n".join(lines)


def save_report(report, text, path_stem):
    """Write ``<stem>.json`` and ``<stem>.txt``."""
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)
    with open(path_stem + ".json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=default)
    with open(path_stem + ".txt", "w", encoding="utf-8") as fh:
        fh.write(text + "\n")

"""Backtest the LIVE bot's rules, not a simplified stand-in.

The Phase 9 engine (engine.Backtester) entered on strength alone, sized a fixed
2 x ATR stop with a fixed reward:risk, and exited only at SL or TP. The live
bot does none of that: it holds reversals, gates entries on the calendar,
spread, daily loss, drawdown and loss streak, sizes stop and target with
``strategies.trade_plan``, and closes early on ``strategies.exit_rules``. Gate
C therefore measured a system nobody runs.

This engine calls the same modules the live loop calls. What it cannot
reproduce is stated, not hidden:

* News sentiment: no historical headlines. The live default is OFF
  (NEWS_SENTIMENT_TRADING_ENABLED / NEWS_SENTIMENT_CLOSE), so nothing differs.
* Economic calendar: the same recurring New York-time schedule the live bot
  uses when no calendar file is present.
* Loss-streak halt: live, a person clears it. Here it is assumed cleared at
  the next UTC trading day, and every halt is counted in the report.
* Drawdown halt: sticky for the rest of the run, as live.

Timing mirrors the live loop, which decides after a bar closes and acts at the
next available price: decisions on bar i execute at bar i+1's open.
"""

import random
from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd

from execution import bar_gate as bar_gate_module
from execution.bar_gate import BarGate
from strategies import exit_rules
from strategies.trade_plan import ATR_RATIO_WINDOW_BARS, plan_entry
from utils.market_time import NEW_YORK, market_session

from .engine import Backtester, BacktestResult, Trade


class ConfigView:
    """``config`` with some values overridden (for sensitivity analysis)."""

    def __init__(self, config, overrides=None):
        self._config = config
        self._overrides = dict(overrides or {})

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._config, name)


@dataclass
class LiveTrade(Trade):
    session: str = ""
    entry_strength: float = 0.0
    exit_factors: list = field(default_factory=list)
    holding_seconds: float = 0.0
    risk_money: float = 0.0          # loss at the stop, before costs
    mfe_price: float = 0.0           # best move in favour while open
    mae_price: float = 0.0           # worst move against while open
    rollovers: int = 0
    trail_distance: float = 0.0      # > 0 enables the chandelier trailing stop


@dataclass
class LiveBacktestResult(BacktestResult):
    blocked: dict = field(default_factory=dict)     # entry-gate reason -> count
    halts: dict = field(default_factory=dict)       # halt kind -> count
    start: object = None
    end: object = None


def rollovers_between(start_utc, end_utc):
    """(rollovers, swap_days) between two instants.

    Brokers charge swap at the daily rollover, 17:00 New York, and charge
    Wednesday's rollover three times to cover the weekend.
    """
    if start_utc is None or end_utc is None or end_utc <= start_utc:
        return 0, 0
    local = start_utc.astimezone(NEW_YORK)
    boundary = local.replace(hour=17, minute=0, second=0, microsecond=0)
    if boundary <= local:
        boundary += timedelta(days=1)
    count = days = 0
    end_local = end_utc.astimezone(NEW_YORK)
    while boundary <= end_local:
        if boundary.weekday() < 5:
            count += 1
            days += 3 if boundary.weekday() == 2 else 1
        boundary += timedelta(days=1)
    return count, days


class LiveRulesBacktester(Backtester):
    """Bar-by-bar simulation of main.py's decision loop."""

    def __init__(self, strategy, config, calendar=None, overrides=None,
                 cost_model=None, initial_balance=1000.0, spec_fields=None,
                 seed=42, timeframe=None, bar_seconds=None, plan_fn=None):
        """
        Args:
            timeframe: MT5 timeframe code (e.g. "H1") for the data being run.
                Defaults to ``config.TIMEFRAME``. Drives BarGate's bar length
                (the reversal hold counts BARS, not seconds) and the
                weekly-close entry cutoff. Getting this wrong on data fetched
                at a different timeframe than config silently miscounts both.
            bar_seconds: override for the bar length in seconds. Normally
                derived from ``timeframe``; only pass this directly if the
                data's bar spacing does not match a named MT5 timeframe.
            plan_fn: builds the TradePlan for a new entry; same signature as
                ``strategies.trade_plan.plan_entry`` (the default). Pass
                ``strategies.trade_plan.plan_trend_entry`` for a plan with no
                fixed target and a chandelier trailing stop enabled.
        """
        self.config = ConfigView(config, overrides)
        super().__init__(cost_model=cost_model, initial_balance=initial_balance,
                         risk_fraction=self.config.RISK_PER_TRADE_FRACTION,
                         min_entry_strength=self.config.MIN_ENTRY_STRENGTH,
                         spec_fields=spec_fields, seed=seed)
        self.strategy = strategy
        self.calendar = calendar
        self.timeframe = timeframe or self.config.TIMEFRAME
        self.bar_seconds = int(bar_seconds) if bar_seconds is not None \
            else bar_gate_module.timeframe_seconds(self.timeframe)
        self.plan_fn = plan_fn or plan_entry

    # ----------------------------------------------------------------- run

    def run(self, df, signal_fn=None, session_fn=None, atr_column="ATR"):
        with self._quiet_logging():
            return self._run_live(df, session_fn or market_session)

    def _block(self, result, reason):
        result.blocked[reason] = result.blocked.get(reason, 0) + 1

    def _run_live(self, df, session_fn):
        cfg = self.config
        result = LiveBacktestResult(initial_balance=self.initial_balance,
                                    bars=len(df), cost_model=self.costs.describe(),
                                    start=df.index[0] if len(df) else None,
                                    end=df.index[-1] if len(df) else None)
        gate = BarGate(self.timeframe)
        balance = self.initial_balance
        peak_equity = balance
        day, day_open = None, balance
        drawdown_halted = False
        streak, streak_halt_day = 0, None
        readings = []
        trade = None
        entry_index = None
        pending_entry = None      # (plan, direction, strength, atr)
        pending_exit = None       # list of factor names
        bar = timedelta(seconds=self.bar_seconds)
        has_spread = "spread" in df.columns
        atr_values = df["ATR"].tolist()

        for i in range(len(df)):
            row = df.iloc[i]
            opened_at = df.index[i]
            closed_at = opened_at + bar
            session = session_fn(opened_at)
            half_spread = self.costs.half_spread_price(session)

            # ---- 1. act at this bar's open on last bar's decisions --------
            if trade is not None and pending_exit:
                balance += self._close_live(trade, float(row["open"]), pending_exit,
                                            opened_at, i - entry_index, session)
                result.trades.append(trade)
                streak = streak + 1 if trade.net_pnl < 0 else 0
                trade, pending_exit, readings = None, None, []

            if trade is None and pending_entry is not None:
                plan, direction, strength, atr_at_signal = pending_entry
                pending_entry = None
                trade = self._open_live(direction, plan, row, opened_at, balance,
                                        half_spread, strength, atr_at_signal,
                                        session, result)
                if trade is not None:
                    entry_index = i

            # ---- 2. server-side SL/TP inside this bar (pessimistic) ------
            if trade is not None:
                high, low = float(row["high"]), float(row["low"])
                if trade.direction == "BUY":
                    trade.mfe_price = max(trade.mfe_price, high - trade.entry_price)
                    trade.mae_price = max(trade.mae_price, trade.entry_price - low)
                else:
                    trade.mfe_price = max(trade.mfe_price, trade.entry_price - low)
                    trade.mae_price = max(trade.mae_price, high - trade.entry_price)

                # Chandelier trailing stop (Hypothesis 3): ratchets toward
                # price using this bar's favourable extreme, then this SAME
                # bar's opposite extreme is checked against it below --
                # pessimistic, consistent with the gap-through-stop and
                # ambiguous-bar conventions in engine.py.
                if trade.trail_distance > 0:
                    if trade.direction == "BUY":
                        trade.stop_loss = max(trade.stop_loss, high - trade.trail_distance)
                    else:
                        trade.stop_loss = min(trade.stop_loss, low + trade.trail_distance)

                exit_price, reason = self._exit_on_bar(trade, row)
                if exit_price is not None:
                    balance += self._close_live(trade, exit_price, [reason],
                                                closed_at, i - entry_index, session)
                    result.trades.append(trade)
                    streak = streak + 1 if trade.net_pnl < 0 else 0
                    trade, readings = None, []

            # ---- 3. equity, day roll, drawdown ---------------------------
            equity = balance
            if trade is not None:
                move = float(row["close"]) - trade.entry_price
                if trade.direction == "SELL":
                    move = -move
                equity += move * self.costs.contract_size * trade.lots
            result.equity_curve.append((opened_at, equity))

            if closed_at.date() != day:
                day, day_open = closed_at.date(), balance
            peak_equity = max(peak_equity, equity)
            drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
            if not drawdown_halted and drawdown >= cfg.MAX_DRAWDOWN_FRACTION:
                drawdown_halted = True
                result.halts["drawdown"] = result.halts.get("drawdown", 0) + 1

            # Loss-streak halt; assumed acknowledged at the next trading day.
            if streak_halt_day is not None and closed_at.date() > streak_halt_day:
                streak, streak_halt_day = 0, None
            if streak_halt_day is None and streak >= cfg.MAX_CONSECUTIVE_LOSSES:
                streak_halt_day = closed_at.date()
                result.halts["loss_streak"] = result.halts.get("loss_streak", 0) + 1

            # ---- 4. decide on this CLOSED bar ------------------------------
            frame = df.iloc[max(0, i - 600):i + 1]
            signal_info = self.strategy.generate_signal(frame)
            atr_now = atr_values[i]

            if trade is not None and cfg.AUTO_CLOSE_ENABLED:
                age = (closed_at - trade.entry_time).total_seconds()
                exit_rules.record_reading(readings, opened_at, signal_info["signal"],
                                          float(signal_info["strength"]))
                ctx = exit_rules.ExitContext(
                    position_type=trade.direction, age_seconds=age,
                    readings=list(readings), frame=frame,
                    reversal=self.strategy.detect_trend_reversal(frame),
                    atr=atr_now, entry_atr=trade_entry_atr(trade),
                    now_utc=closed_at,
                    drawdown_breached=drawdown >= cfg.EMERGENCY_CLOSE_DRAWDOWN_FRACTION)
                too_young = age < exit_rules.min_hold_seconds(cfg)
                factors = exit_rules.triggered_factors(ctx, cfg, risk_only=too_young)
                if factors:
                    pending_exit = factors

            signal = gate.apply_reversal_hold(
                signal_info["signal"], float(signal_info["strength"]), opened_at,
                cfg.SIGNAL_REVERSAL_MIN_STRENGTH, cfg.MIN_SIGNAL_HOLD_BARS)
            strength = float(signal_info["strength"])

            if signal not in ("BUY", "SELL"):
                continue
            if self.calendar is not None and self.calendar.is_blackout(
                    now=closed_at, before_minutes=cfg.EVENT_BLACKOUT_BEFORE_MINUTES,
                    after_minutes=cfg.EVENT_BLACKOUT_AFTER_MINUTES)[0]:
                self._block(result, "event blackout")
            elif strength < cfg.MIN_ENTRY_STRENGTH:
                self._block(result, "strength below minimum")
            elif trade is not None or pending_entry is not None:
                self._block(result, "position cap")
            elif exit_rules.entry_too_close_to_weekly_close(closed_at, cfg, self.bar_seconds):
                self._block(result, "too close to weekly close")
            elif not (atr_now and atr_now == atr_now and atr_now > 0):
                self._block(result, "ATR unusable")
            elif drawdown_halted:
                self._block(result, "drawdown halt")
            elif streak_halt_day is not None:
                self._block(result, "loss-streak halt")
            elif balance < cfg.MIN_ACCOUNT_BALANCE:
                self._block(result, "balance below floor")
            elif equity - day_open <= -day_open * cfg.MAX_DAILY_LOSS_FRACTION:
                self._block(result, "daily loss limit")
            elif has_spread and float(row["spread"]) > cfg.MAX_ENTRY_SPREAD_POINTS:
                self._block(result, "spread too wide")
            else:
                plan = self.plan_fn(signal_info, atr_now,
                                    atr_values[max(0, i - ATR_RATIO_WINDOW_BARS + 1):i + 1],
                                    "neutral", cfg)
                if plan is None:
                    self._block(result, "ATR unusable")
                else:
                    pending_entry = (plan, signal, strength, atr_now)
                    gate.record_entry(opened_at)

        if trade is not None:
            last = df.index[-1] + bar
            balance += self._close_live(trade, float(df.iloc[-1]["close"]),
                                        ["end_of_data"], last,
                                        len(df) - 1 - entry_index,
                                        session_fn(df.index[-1]))
            result.trades.append(trade)

        result.final_balance = balance
        return result

    # --------------------------------------------------------- fills

    def _open_live(self, direction, plan, row, timestamp, balance, half_spread,
                   strength, atr_at_signal, session, result):
        mid = float(row["open"])
        slippage = self.costs.slippage_price(self.rng)
        entry = mid + half_spread + slippage if direction == "BUY" else mid - half_spread - slippage

        lots = self.size_position(balance, plan.sl_distance)
        if lots is None:
            result.declined_trades += 1
            self._block(result, "sizing declined (below broker minimum)")
            return None

        stop, target = plan.levels(direction, entry)
        trail_distance = 0.0
        if plan.trailing_atr_mult and atr_at_signal:
            trail_distance = float(plan.trailing_atr_mult) * float(atr_at_signal)
        trade = LiveTrade(direction=direction, lots=lots, entry_time=timestamp,
                          entry_price=entry, stop_loss=stop, take_profit=target,
                          session=session, entry_strength=strength,
                          risk_money=plan.sl_distance * self.costs.contract_size * lots,
                          trail_distance=trail_distance)
        trade._entry_atr = atr_at_signal
        trade.spread_cost = half_spread * self.costs.contract_size * lots
        trade.slippage_cost = slippage * self.costs.contract_size * lots
        return trade

    def _close_live(self, trade, exit_price, factors, timestamp, bars_held, session):
        net = self._close(trade, exit_price, factors[0], timestamp, bars_held, session)
        # Replace the engine's calendar-night swap with broker rollovers.
        trade.net_pnl -= trade.swap_cost
        trade.rollovers, swap_days = rollovers_between(trade.entry_time, timestamp)
        trade.swap_cost = self.costs.swap(trade.lots, swap_days, trade.direction == "BUY")
        trade.net_pnl += trade.swap_cost
        trade.exit_factors = list(factors)
        trade.holding_seconds = (timestamp - trade.entry_time).total_seconds()
        return trade.net_pnl


def trade_entry_atr(trade):
    return getattr(trade, "_entry_atr", None)


def prepare_frame(df, strategy, config, clock=None, already_utc=False):
    """Indicators (including the ATR column the live loop now adds), UTC index."""
    from utils.indicators import atr

    frame = df.copy()
    if not already_utc:
        from utils.market_time import BrokerClock
        clock = clock or BrokerClock.from_config(config)
        frame.index = clock.index_to_utc(frame.index)
    frame = strategy.prepare_data(frame)
    frame["ATR"] = atr(frame, period=config.ATR_PERIOD)
    return frame

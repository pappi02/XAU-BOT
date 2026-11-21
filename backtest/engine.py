"""Event-driven backtester (Phase 9.2, audit C-07).

The audited `backtest()` branched on ``if signal == 'buy'`` while
``generate_signal`` returned ``'BUY'``. **It executed zero trades on any input**
and dutifully reported a 0.00% return. Nobody noticed, because a backtest that
reports "no edge" looks like an honest answer.

Even with the case fixed it modelled no spread, no commission, no swap, no
slippage, no stop loss, no take profit and no shorts; it sized at a percentage
of balance rather than by risk; and it referenced an unbound ``shares``
variable. So the plan is right that this is a rewrite, not a patch.

Two design decisions matter more than the rest:

**Intrabar ordering is pessimistic and explicit.** When a bar's range spans both
the stop and the target, this engine assumes **the stop was hit first**. OHLC
data cannot say which came first, and the optimistic assumption silently
converts losers into winners at exactly the rate that makes a mediocre strategy
look good. If the real answer depends on which assumption you choose, there is
no edge to find.

**Sizing and risk use the live code path.** `RiskManager` is driven here through
a broker adapter, rather than reimplemented. A backtest that sizes differently
from the live bot is measuring a system nobody will ever run -- and divergence
between the two is the single most common way backtests lie.
"""

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import timedelta

from .costs import CostModel

logger = logging.getLogger("xau_bot")


@dataclass
class Trade:
    """One completed round trip, with every cost itemised."""

    direction: str                  # BUY or SELL
    lots: float
    entry_time: object = None
    entry_price: float = 0.0
    exit_time: object = None
    exit_price: float = 0.0
    exit_reason: str = ""
    stop_loss: float = 0.0
    take_profit: float = 0.0
    gross_pnl: float = 0.0
    spread_cost: float = 0.0
    commission_cost: float = 0.0
    swap_cost: float = 0.0
    slippage_cost: float = 0.0
    net_pnl: float = 0.0
    bars_held: int = 0

    @property
    def total_costs(self):
        return (self.spread_cost + self.commission_cost
                + abs(self.swap_cost) + self.slippage_cost)


class BacktestBroker:
    """Minimal MT5-shaped adapter so RiskManager can run unchanged.

    This is what "share the live sizing code path" means in practice: rather
    than reimplementing the sizing formula (and letting the two drift), the
    real `RiskManager` is handed something that answers the handful of
    questions it asks.
    """

    def __init__(self, equity, spec_fields):
        self.equity = float(equity)
        self.balance = float(equity)
        self._spec = spec_fields
        self.positions = []

    def account_info(self):
        class _Account:
            pass
        account = _Account()
        account.balance = self.balance
        account.equity = self.equity
        account.profit = self.equity - self.balance
        account.margin_free = self.equity
        return account

    def symbol_info(self, symbol):
        class _Info:
            pass
        info = _Info()
        for key, value in self._spec.items():
            setattr(info, key, value)
        info.name = symbol
        return info

    def symbol_select(self, symbol, enable=True):
        return True

    def positions_get(self, symbol=None):
        return tuple(self.positions)

    def history_deals_get(self, *args, **kwargs):
        return ()


@dataclass
class BacktestResult:
    """Everything the plan asks a backtest to emit."""

    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    initial_balance: float = 0.0
    final_balance: float = 0.0
    declined_trades: int = 0
    bars: int = 0
    cost_model: dict = field(default_factory=dict)

    # ------------------------------------------------------------ metrics

    @property
    def net_pnls(self):
        return [t.net_pnl for t in self.trades]

    def reconciles(self, tolerance=0.01):
        """The trade log must add up to the final balance.

        Gauntlet step 1's real test. A trade log that does not reconcile is a
        trade log that is not describing the equity curve beside it.
        """
        expected = self.initial_balance + sum(self.net_pnls)
        return abs(expected - self.final_balance) <= tolerance

    def expectancy(self):
        """Mean net P&L per trade. The number that decides Gate C."""
        return sum(self.net_pnls) / len(self.net_pnls) if self.trades else 0.0

    def profit_factor(self):
        gross_win = sum(p for p in self.net_pnls if p > 0)
        gross_loss = abs(sum(p for p in self.net_pnls if p < 0))
        if gross_loss == 0:
            return float("inf") if gross_win > 0 else 0.0
        return gross_win / gross_loss

    def win_rate(self):
        if not self.trades:
            return 0.0
        return len([p for p in self.net_pnls if p > 0]) / len(self.trades) * 100.0

    def _returns(self):
        returns, previous = [], self.initial_balance
        for _, equity in self.equity_curve:
            if previous:
                returns.append((equity - previous) / previous)
            previous = equity
        return returns

    def sharpe(self, periods_per_year=252 * 288):
        """Annualised Sharpe. 288 M5 bars per trading day."""
        returns = self._returns()
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        sd = math.sqrt(variance)
        if sd == 0:
            return 0.0
        return (mean / sd) * math.sqrt(periods_per_year)

    def sortino(self, periods_per_year=252 * 288):
        """Like Sharpe, but only downside deviation is penalised."""
        returns = self._returns()
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        downside = [r for r in returns if r < 0]
        if not downside:
            return float("inf") if mean > 0 else 0.0
        dd = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
        if dd == 0:
            return 0.0
        return (mean / dd) * math.sqrt(periods_per_year)

    def max_drawdown(self):
        """Largest peak-to-trough fall, as a fraction."""
        peak, worst = self.initial_balance, 0.0
        for _, equity in self.equity_curve:
            peak = max(peak, equity)
            if peak > 0:
                worst = max(worst, (peak - equity) / peak)
        return worst

    def cost_breakdown(self):
        """What fraction of gross profit went to costs.

        The plan asks for this explicitly, and it is usually the most
        informative number in the whole report: a strategy whose costs exceed
        its gross profit does not have a cost problem, it has an edge problem.
        """
        gross = sum(t.gross_pnl for t in self.trades)
        spread = sum(t.spread_cost for t in self.trades)
        commission = sum(t.commission_cost for t in self.trades)
        swap = sum(abs(t.swap_cost) for t in self.trades)
        slippage = sum(t.slippage_cost for t in self.trades)
        total = spread + commission + swap + slippage
        return {
            "gross_pnl": gross,
            "spread": spread,
            "commission": commission,
            "swap": swap,
            "slippage": slippage,
            "total_costs": total,
            "net_pnl": sum(self.net_pnls),
            "costs_as_fraction_of_gross": (total / abs(gross)) if gross else None,
        }

    def summary(self):
        return {
            "trades": len(self.trades),
            "declined": self.declined_trades,
            "bars": self.bars,
            "initial_balance": self.initial_balance,
            "final_balance": self.final_balance,
            "reconciles": self.reconciles(),
            "expectancy": self.expectancy(),
            "profit_factor": self.profit_factor(),
            "win_rate": self.win_rate(),
            "sharpe": self.sharpe(),
            "sortino": self.sortino(),
            "max_drawdown": self.max_drawdown(),
            "costs": self.cost_breakdown(),
            "cost_model": self.cost_model,
        }


class Backtester:
    """Bar-by-bar simulation with explicit costs and pessimistic fills."""

    def __init__(self, cost_model=None, initial_balance=1000.0,
                 risk_fraction=0.01, sl_atr_multiple=2.0, rr=2.0,
                 min_entry_strength=65.0, spec_fields=None, seed=42,
                 max_open=1):
        self.costs = cost_model or CostModel()
        self.initial_balance = float(initial_balance)
        self.risk_fraction = float(risk_fraction)
        self.sl_atr_multiple = float(sl_atr_multiple)
        self.rr = float(rr)
        self.min_entry_strength = float(min_entry_strength)
        self.max_open = int(max_open)
        self.rng = random.Random(seed)
        self.spec_fields = spec_fields or {
            "digits": 2, "point": 0.01, "trade_contract_size": 100.0,
            "trade_tick_value": 1.0, "trade_tick_size": 0.01,
            "volume_min": 0.01, "volume_step": 0.01, "volume_max": 50.0,
            "trade_stops_level": 0, "trade_freeze_level": 0, "filling_mode": 2,
        }

    # ------------------------------------------------------------- sizing

    def size_position(self, equity, stop_distance):
        """Lots, via the LIVE RiskManager. None means the trade is declined."""
        from risk.risk_manager import RiskManager

        broker = BacktestBroker(equity, self.spec_fields)

        class _Config:
            pass
        cfg = _Config()
        cfg.RISK_PER_TRADE_FRACTION = self.risk_fraction
        cfg.SYMBOL_PHASE5 = "BACKTEST"
        cfg.SYMBOL = "BACKTEST"
        cfg.MAX_LOTS_PER_ORDER = self.spec_fields["volume_max"]
        cfg.RISK_STATE_PATH = None

        manager = RiskManager(broker, cfg)
        return manager.calculate_dynamic_lot_size(stop_distance)

    # -------------------------------------------------------------- fills

    def _exit_on_bar(self, trade, bar):
        """Did this bar close the position, and at what price?

        **Pessimistic intrabar rule.** When the bar's range contains both the
        stop and the target, we assume the STOP filled first. OHLC gives no
        intrabar sequence, and the optimistic choice turns losers into winners
        at precisely the rate that makes a coin-flip look like an edge.
        """
        high, low = float(bar["high"]), float(bar["low"])
        is_long = trade.direction == "BUY"

        stop_hit = (low <= trade.stop_loss) if is_long else (high >= trade.stop_loss)
        target_hit = (high >= trade.take_profit) if is_long else (low <= trade.take_profit)

        # A bar that OPENS beyond the stop gapped through it: a stop order fills
        # at the first available price, not at its level. Filling at the stop
        # would turn every weekend or news gap into a loss capped at 1R.
        opened = float(bar["open"]) if "open" in bar else None
        if opened is not None and ((is_long and opened <= trade.stop_loss)
                                   or (not is_long and opened >= trade.stop_loss)):
            return opened, "stop_loss (gap)"
        if stop_hit and target_hit:
            return trade.stop_loss, "stop_loss (ambiguous bar, pessimistic)"
        if stop_hit:
            return trade.stop_loss, "stop_loss"
        if target_hit:
            return trade.take_profit, "take_profit"
        return None, None

    # ---------------------------------------------------------------- run

    @staticmethod
    def _quiet_logging():
        """Suppress per-decision INFO logging for the duration of a run.

        The live sizing code logs its arithmetic on every call, which is
        exactly right in production and completely unusable across two years of
        M5 bars -- roughly 200,000 lines for one backtest. Sharing the live
        code path means inheriting its logging, so the run turns it down rather
        than forking the code to remove it.
        """
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            # Configure the logger FIRST. Several modules call setup_logger()
            # at import time and are imported lazily inside the run, so if the
            # logger is still unconfigured when we lower the level, the first
            # such import configures it -- back to INFO -- and undoes this.
            from logger_config import setup_logger
            bot = setup_logger()

            previous = bot.level
            bot.setLevel(logging.ERROR)
            try:
                yield
            finally:
                bot.setLevel(previous)
        return _ctx()

    def run(self, df, signal_fn, session_fn=None, atr_column="ATR"):
        """Simulate ``signal_fn`` over ``df``.

        Args:
            df: OHLC frame indexed by time, with an ATR column.
            signal_fn: ``(frame_up_to_and_including_i) -> {signal, strength}``.
                Given only closed bars, mirroring the live bot.
            session_fn: ``timestamp -> session name``, for the spread model.

        Returns:
            BacktestResult
        """
        with self._quiet_logging():
            return self._run(df, signal_fn, session_fn, atr_column)

    def _run(self, df, signal_fn, session_fn, atr_column):
        result = BacktestResult(initial_balance=self.initial_balance,
                                bars=len(df),
                                cost_model=self.costs.describe())
        balance = self.initial_balance
        open_trade = None
        entry_bar_index = None
        pending = None          # (bar_index_to_fill, direction, atr)

        session_fn = session_fn or (lambda ts: "London")

        for i in range(len(df)):
            bar = df.iloc[i]
            timestamp = df.index[i]
            session = session_fn(timestamp)
            half_spread = self.costs.half_spread_price(session)

            # 1. Close an open trade if this bar hit its stop or target.
            if open_trade is not None:
                exit_price, reason = self._exit_on_bar(open_trade, bar)
                if exit_price is not None:
                    balance += self._close(open_trade, exit_price, reason,
                                           timestamp, i - entry_bar_index,
                                           session)
                    result.trades.append(open_trade)
                    open_trade = None
                    entry_bar_index = None

            # 2. Fill a pending entry, modelling latency.
            if pending is not None and i >= pending[0] and open_trade is None:
                _, direction, atr_at_signal = pending
                pending = None
                open_trade = self._open(direction, bar, atr_at_signal,
                                        timestamp, balance, half_spread,
                                        result)
                if open_trade is not None:
                    entry_bar_index = i

            # 3. Decide, on closed bars only.
            if open_trade is None and pending is None:
                decision = signal_fn(df.iloc[:i + 1])
                signal = decision.get("signal")
                strength = float(decision.get("strength", 0.0))
                atr_value = bar.get(atr_column)

                if (signal in ("BUY", "SELL")
                        and strength >= self.min_entry_strength
                        and atr_value and atr_value == atr_value
                        and atr_value > 0):
                    pending = (i + max(1, self.costs.latency_bars),
                               signal, float(atr_value))

            equity = balance
            if open_trade is not None:
                move = (float(bar["close"]) - open_trade.entry_price)
                if open_trade.direction == "SELL":
                    move = -move
                equity += move * self.costs.contract_size * open_trade.lots
            result.equity_curve.append((timestamp, equity))

        # Close anything still open at the final close.
        if open_trade is not None:
            balance += self._close(open_trade, float(df.iloc[-1]["close"]),
                                   "end_of_data", df.index[-1],
                                   len(df) - 1 - entry_bar_index,
                                   session_fn(df.index[-1]))
            result.trades.append(open_trade)

        result.final_balance = balance
        return result

    def _open(self, direction, bar, atr_value, timestamp, balance,
              half_spread, result):
        """Open a position, charging the spread and slippage on entry."""
        mid = float(bar["open"])
        slippage = self.costs.slippage_price(self.rng)

        # Buy at the ask, sell at the bid, and slip adversely either way.
        if direction == "BUY":
            entry = mid + half_spread + slippage
        else:
            entry = mid - half_spread - slippage

        stop_distance = atr_value * self.sl_atr_multiple
        lots = self.size_position(balance, stop_distance)
        if lots is None:
            # The live sizing declined it: the account cannot take this stop
            # at the configured risk. A backtest that takes it anyway is
            # measuring a system the live bot would refuse to run.
            result.declined_trades += 1
            return None

        if direction == "BUY":
            stop = entry - stop_distance
            target = entry + stop_distance * self.rr
        else:
            stop = entry + stop_distance
            target = entry - stop_distance * self.rr

        trade = Trade(direction=direction, lots=lots, entry_time=timestamp,
                      entry_price=entry, stop_loss=stop, take_profit=target)
        trade.spread_cost = half_spread * self.costs.contract_size * lots
        trade.slippage_cost = slippage * self.costs.contract_size * lots
        return trade

    def _close(self, trade, exit_price, reason, timestamp, bars_held, session):
        """Close a position, charging the exit spread, slippage, commission, swap."""
        half_spread = self.costs.half_spread_price(session)
        slippage = self.costs.slippage_price(self.rng)

        # Exit a long at the bid, a short at the ask -- adverse both ways.
        if trade.direction == "BUY":
            fill = exit_price - half_spread - slippage
        else:
            fill = exit_price + half_spread + slippage

        move = fill - trade.entry_price
        if trade.direction == "SELL":
            move = -move

        trade.exit_time = timestamp
        trade.exit_price = fill
        trade.exit_reason = reason
        trade.bars_held = bars_held
        trade.gross_pnl = move * self.costs.contract_size * trade.lots

        trade.spread_cost += half_spread * self.costs.contract_size * trade.lots
        trade.slippage_cost += slippage * self.costs.contract_size * trade.lots
        trade.commission_cost = self.costs.commission(trade.lots)

        nights = 0
        if trade.entry_time is not None and timestamp is not None:
            try:
                nights = max(0, (timestamp.date() - trade.entry_time.date()).days)
            except AttributeError:
                nights = 0
        trade.swap_cost = self.costs.swap(trade.lots, nights,
                                          trade.direction == "BUY")

        # gross_pnl is already net of the spread and slippage built into the
        # fill prices; charge only commission and swap on top.
        trade.net_pnl = trade.gross_pnl - trade.commission_cost + trade.swap_cost
        return trade.net_pnl

import math
from datetime import datetime, timedelta, timezone

from logger_config import setup_logger
from .risk_state import RiskState

logger = setup_logger()


class RiskRefusal(RuntimeError):
    """Raised when a risk control declines a trade. Never swallow this."""


class RiskManager:
    def __init__(self, mt5_module, config):
        """
        mt5_module: MetaTrader5 module (imported as mt5 in caller)
        config: config module with constants
        """
        self.mt5 = mt5_module
        self.config = config
        self._symbol_specs = {}
        # Phase 3.3/3.4: the day's opening balance and the equity high-water
        # mark are persisted, so a restart cannot reset a tripped limit.
        # Only honour a configured path if it is actually a path. getattr on a
        # Mock config returns a Mock, which os.path.exists rejects.
        _state_path = getattr(config, "RISK_STATE_PATH", None)
        if not isinstance(_state_path, str):
            _state_path = None
        self.state = RiskState(_state_path)
        self.daily_start = datetime.now(timezone.utc).date()
        self.daily_pnl = 0.0

    def contract_size(self, symbol=None):
        """Contract size READ FROM THE BROKER (Phase 2.1, audit C-04).

        This used to be `config.CONTRACT_SIZE`, which was defined twice and
        resolved to the FX convention of 100000 instead of gold's 100 oz per
        lot -- making every position size wrong by 1000x. Contract size is a
        broker fact, so it is read, cached and never configured.
        """
        from execution.symbol_spec import SymbolSpec

        symbol = (symbol or getattr(self.config, "SYMBOL_PHASE5", None)
                  or getattr(self.config, "SYMBOL", None))

        spec = self._symbol_specs.get(symbol)
        if spec is None:
            spec = SymbolSpec.load(self.mt5, symbol)
            logger.info("Symbol spec loaded -- %s", spec.describe())
            self._symbol_specs[symbol] = spec
        return spec.contract_size

    @staticmethod
    def account_equity(account):
        """Equity as a float, falling back to balance.

        `getattr(account, "equity", account.balance)` is not enough: the
        attribute may exist but hold something that is not a number. Coerce
        and fall back on failure rather than propagating a TypeError out of a
        risk calculation.
        """
        try:
            return float(account.equity)
        except (AttributeError, TypeError, ValueError):
            return float(account.balance)

    @staticmethod
    def account_floating_pnl(account):
        """Floating P&L as a float; 0.0 when unreadable."""
        try:
            return float(account.profit)
        except (AttributeError, TypeError, ValueError):
            return 0.0

    def refresh_account(self):
        account = self.mt5.account_info()
        if account is None:
            raise RuntimeError("Failed to fetch MT5 account info")
        return account

    def realised_pnl_today(self, now=None):
        """Today's REALISED P&L: profit + commission + swap over closed deals.

        Phase 3.3 (H-03): the audited code had this logic in update_daily_pnl(),
        which was never called, while check_daily_loss_limit() read
        account.profit -- the FLOATING P&L of open positions. A day of ten
        realised losses passed the check because nothing was open.
        """
        from utils.market_time import BrokerClock

        now = now or datetime.now(timezone.utc)
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

        # Deal times are broker SERVER time. A window ending at real UTC "now"
        # hid the last 2-3 hours of losses from the daily loss limit.
        clock = BrokerClock.from_config(self.config)

        def server(dt):
            return datetime.fromtimestamp(clock.utc_to_server_epoch(dt), timezone.utc)

        history = self.mt5.history_deals_get(server(day_start), server(now))
        pnl = 0.0
        if history:
            for deal in history:
                for field in ("profit", "commission", "swap"):
                    try:
                        pnl += float(getattr(deal, field, 0.0) or 0.0)
                    except (TypeError, ValueError):
                        pass
        self.daily_pnl = pnl
        return pnl

    def update_daily_pnl(self):
        """Backwards-compatible alias for realised_pnl_today()."""
        return self.realised_pnl_today()

    def check_daily_loss_limit(self, now=None):
        """True if trading may continue; False if the daily limit is breached.

        Measures realised + floating P&L against the DAY'S OPENING BALANCE,
        which is persisted -- so killing and restarting the bot cannot reset a
        limit that has already tripped.
        """
        account = self.refresh_account()
        balance = float(account.balance)
        floating = self.account_floating_pnl(account)

        self.state.start_of_day(balance, now=now)
        opening = self.state.day_opening_balance or balance

        if self.state.halted_reason:
            logger.error("Trading halted: %s", self.state.halted_reason)
            return False

        realised = self.realised_pnl_today(now=now)
        total = realised + floating
        allowed_loss = opening * self.config.MAX_DAILY_LOSS_FRACTION

        logger.info(
            "Daily P&L: realised %.2f + floating %.2f = %.2f; "
            "limit -%.2f (%.1f%% of opening balance %.2f)",
            realised, floating, total, allowed_loss,
            self.config.MAX_DAILY_LOSS_FRACTION * 100, opening,
        )

        if total <= -allowed_loss:
            self.state.halt(
                "daily loss limit breached: %.2f vs allowed -%.2f"
                % (total, allowed_loss)
            )
            return False
        return True

    def enough_balance(self):
        """Phase 3.3: MIN_ACCOUNT_BALANCE was 0, making this always true."""
        account = self.refresh_account()
        balance = float(account.balance)
        floor = float(self.config.MIN_ACCOUNT_BALANCE)
        if balance < floor:
            logger.error("Balance %.2f is below the floor of %.2f", balance, floor)
            return False
        return True

    def check_drawdown(self):
        """True if drawdown from the equity high-water mark is acceptable.

        Phase 3.4 (L-04): drawdown was measured against a hardcoded
        INITIAL_ACCOUNT_BALANCE = 150.0. It is now measured from a persisted
        peak-equity mark, so it means the same thing on any account size.
        """
        account = self.refresh_account()
        equity = self.account_equity(account)
        drawdown = self.state.drawdown_fraction(equity)
        limit = self.config.MAX_DRAWDOWN_FRACTION

        logger.info("Drawdown %.1f%% from peak %.2f (limit %.1f%%)",
                    drawdown * 100, self.state.equity_high_water_mark or 0.0,
                    limit * 100)

        if drawdown >= limit:
            self.state.halt("drawdown %.1f%% exceeds limit %.1f%%"
                            % (drawdown * 100, limit * 100))
            return False
        return True

    def open_risk_fraction(self, symbol=None):
        """Fraction of equity currently at risk across all open positions.

        Risk per position is |entry - stop| * contract_size * volume. A position
        with no stop is treated as risking its full notional, because that is
        what it does.

        Raises:
            BrokerQueryFailed: position state is unknown (see broker_query.py).
                A disconnected terminal must never read as "no open risk" --
                that is the fail-open direction, understating risk right
                before a new order is sized against it.
        """
        from execution import broker_query

        account = self.refresh_account()
        equity = self.account_equity(account)
        if equity <= 0:
            return 1.0

        positions = broker_query.positions_or_raise(self.mt5)
        contract_size = self.contract_size(symbol)

        total = 0.0
        for pos in positions:
            volume = float(getattr(pos, "volume", 0.0) or 0.0)
            entry = float(getattr(pos, "price_open", 0.0) or 0.0)
            stop = float(getattr(pos, "sl", 0.0) or 0.0)
            if stop > 0:
                total += abs(entry - stop) * contract_size * volume
            else:
                # No stop: the whole notional is exposed.
                total += entry * contract_size * volume
        return total / equity

    def check_portfolio_risk(self, candidate_risk_money=0.0, symbol=None):
        """Phase 3.5: assert open risk + this trade stays within the cap.

        No such check existed between the entry decision and the order.
        """
        account = self.refresh_account()
        equity = self.account_equity(account)
        if equity <= 0:
            return False

        current = self.open_risk_fraction(symbol)
        candidate = float(candidate_risk_money) / equity
        total = current + candidate
        limit = self.config.MAX_PORTFOLIO_RISK_FRACTION

        logger.info("Portfolio risk: open %.2f%% + candidate %.2f%% = %.2f%% "
                    "(limit %.2f%%)", current * 100, candidate * 100,
                    total * 100, limit * 100)

        if total > limit:
            logger.warning("Portfolio risk cap would be exceeded -- declining.")
            return False
        return True

    def current_open_positions_count(self, symbol):
        """Raises BrokerQueryFailed when the answer is unknown (see broker_query.py)."""
        from execution import broker_query

        return len(broker_query.positions_or_raise(self.mt5, symbol))

    def compute_lot_size(self, stop_loss_price, entry_price, symbol=None):
        """Position size for a stop at ``stop_loss_price`` entering at ``entry_price``.

        Phase 3.1: this was a SECOND sizing implementation with the same defects
        as the first -- it read the now-deleted RISK_PER_TRADE_PCT, and when the
        computed size fell below the broker minimum it "adjusted to min lot",
        silently taking more risk than configured. There is now one sizing
        calculation; this is a thin wrapper that expresses the stop as a
        distance and delegates.

        Returns:
            float lots, or None if the trade must be declined.
        """
        distance = abs(float(entry_price) - float(stop_loss_price))
        return self.calculate_dynamic_lot_size(distance, symbol=symbol)


    def calculate_dynamic_sl_distance(self, entry_price, atr_value, sl_multiplier):
        """
        Calculate stop loss distance using ATR and dynamic multiplier.

        Args:
            entry_price (float): Entry price
            atr_value (float): Current ATR value
            sl_multiplier (float): Dynamic stop loss multiplier

        Returns:
            float: Stop loss distance in price units
        """
        if atr_value and atr_value > 0:
            sl_distance = atr_value * sl_multiplier
        else:
            # Fallback to percentage-based SL if ATR not available
            sl_distance = entry_price * 0.01  # 1% fallback

        return sl_distance

    def floor_to_step(self, value, step):
        """Round DOWN to a multiple of step. Rounding up increases real risk."""
        if step <= 0:
            return value
        steps = int(value / step + 1e-9)
        decimals = max(0, len(("%.10f" % step).rstrip("0").split(".")[1]))
        return round(steps * step, decimals)

    def calculate_dynamic_lot_size(self, stop_loss_distance, symbol=None):
        """Position size from risk, stop distance, and the broker's contract.

        Phase 3.1 (C-05). The audited version multiplied a base size by twelve
        heuristic multipliers, but because CONTRACT_SIZE was wrong by 1000x the
        raw lot was ~1e-5 for any account and the `max(MIN_LOT_SIZE, ...)` clamp
        discarded the whole calculation. The function was equivalent to
        `return 0.01`, which meant 2.5% risk on $150 and 0.04% on $10,000
        against an intended 1%.

        This version is the whole calculation:

            risk_money = equity * RISK_PER_TRADE_FRACTION
            raw_lots   = risk_money / (contract_size * stop_loss_distance)
            lots       = floor_to_step(raw_lots, volume_step)

        Phase 12.5: the eight heuristic arguments (signal_strength, atr_value,
        session, recent_perf, news_impact, trade_type, risk_mode) that were
        accepted and ignored since Phase 3.1 are gone. An argument that is
        silently ignored invites someone to believe it does something.

        Returns:
            float lots, or None if the trade must be DECLINED.

        Declining matters. If the smallest tradeable volume would risk more than
        configured, the account cannot take this trade at this stop distance.
        Silently rounding up to volume_min is exactly how a 1% risk becomes 2.5%.
        """
        from execution.symbol_spec import SymbolSpec

        stop_loss_distance = float(stop_loss_distance)
        if stop_loss_distance <= 0:
            logger.error("Invalid stop loss distance %r -- declining trade",
                         stop_loss_distance)
            return None

        account = self.refresh_account()
        equity = self.account_equity(account)
        if equity <= 0:
            logger.error("Non-positive equity %r -- declining trade", equity)
            return None

        symbol = (symbol or getattr(self.config, "SYMBOL_PHASE5", None)
                  or getattr(self.config, "SYMBOL", None))
        spec = self._symbol_specs.get(symbol)
        if spec is None:
            spec = SymbolSpec.load(self.mt5, symbol)
            self._symbol_specs[symbol] = spec

        risk_money = equity * self.config.RISK_PER_TRADE_FRACTION
        money_per_lot = spec.contract_size * stop_loss_distance
        raw_lots = risk_money / money_per_lot
        lots = self.floor_to_step(raw_lots, spec.volume_step)

        if lots < spec.volume_min:
            logger.warning(
                "DECLINING trade: risking %.2f (%.2f%% of %.2f equity) over a "
                "%.2f stop needs %.4f lots, but the broker minimum is %.2f. "
                "Taking the minimum would risk %.2f (%.2f%%) -- more than "
                "configured. The account is too small for this stop distance.",
                risk_money, self.config.RISK_PER_TRADE_FRACTION * 100, equity,
                stop_loss_distance, raw_lots, spec.volume_min,
                spec.volume_min * money_per_lot,
                spec.volume_min * money_per_lot / equity * 100,
            )
            return None

        if lots > spec.volume_max:
            logger.info("Capping %.2f lots at broker maximum %.2f",
                        lots, spec.volume_max)
            lots = spec.volume_max

        max_lot = getattr(self.config, "MAX_LOTS_PER_ORDER", None)
        if max_lot is not None and lots > max_lot:
            logger.info("Capping %.2f lots at MAX_LOTS_PER_ORDER %.2f", lots, max_lot)
            lots = self.floor_to_step(float(max_lot), spec.volume_step)

        logger.info(
            "Sizing: equity %.2f x %.2f%% = %.2f risk / (%.0f contract x %.2f "
            "stop) = %.4f -> %.2f lots (actual risk %.2f)",
            equity, self.config.RISK_PER_TRADE_FRACTION * 100, risk_money,
            spec.contract_size, stop_loss_distance, raw_lots, lots,
            lots * money_per_lot,
        )
        return lots

    def get_current_market_session(self):
        """Current market session, following London and New York DST.

        Phase 5.6 (audit M-06) named the London/NY overlap. The boundaries were
        still fixed UTC hours, an hour wrong for half of each year: in July
        12:45 UTC is already the overlap. utils/market_time.py follows the
        exchanges' own clocks.

        Returns:
            str: 'Asian', 'London', 'London/NY overlap', 'New York', or 'Other'
        """
        from utils.market_time import market_session
        return market_session(datetime.now(timezone.utc))

    # Phase 12.5 (audit M-07): get_recent_performance() returned the literal
    # "neutral" with the comment "in production, analyze actual trade history",
    # and get_news_impact_level() mapped any non-neutral sentiment to "medium".
    # Both only fed arguments that position sizing has ignored since Phase 3.1
    # deleted the streak and news multipliers. Deleted. Loss-streak protection
    # now exists for real, computed from broker deals:
    # PositionStateStore.consecutive_losses() and TradeExecutor.enter_trade().

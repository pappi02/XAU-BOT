import time
import uuid
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from logger_config import setup_logger
from .symbol_spec import SymbolSpec, price_to_money, money_to_price
from .order_validator import OrderValidator, Rejection, normalize_volume
from . import broker_query
from .position_state import PositionStateStore

logger = setup_logger()
MAGIC = 987654321

# Phase 6.1: retcodes that mean "the order definitely did NOT execute, and the
# same request may safely be sent again". Anything outside this set is either a
# hard rejection (resending changes nothing) or an unknown outcome (resending
# risks a duplicate position). Numeric literals because the MT5 module may be a
# double in tests.
TRADE_RETCODE_REQUOTE = 10004
TRADE_RETCODE_PRICE_CHANGED = 10020
TRADE_RETCODE_PRICE_OFF = 10021
RETRYABLE_RETCODES = frozenset({
    TRADE_RETCODE_REQUOTE,
    TRADE_RETCODE_PRICE_CHANGED,
    TRADE_RETCODE_PRICE_OFF,
})


class TradingDisabled(RuntimeError):
    """Raised when a broker write is attempted from a read-only context."""


# Re-exported: execution/broker_query.py is now the one place "what is open"
# is answered (RiskManager uses it too -- see that module's docstring for why
# a second implementation was worth removing rather than just noting).
from .broker_query import BrokerQueryFailed  # noqa: F401


_WRITES_DISABLED_REASON = None


def disable_trading_writes(reason):
    """Make every subsequent broker write raise TradingDisabled.

    Phase 1.4: the dashboard is a read-only view. It may query state; it may
    never place, modify or close an order. It calls this at import time, which
    makes the guarantee structural rather than a matter of not clicking the
    wrong button.
    """
    global _WRITES_DISABLED_REASON
    _WRITES_DISABLED_REASON = reason
    logger.warning("Broker writes disabled: %s", reason)


def enable_trading_writes():
    """Re-enable broker writes. Intended for tests."""
    global _WRITES_DISABLED_REASON
    _WRITES_DISABLED_REASON = None


def writes_disabled_reason():
    return _WRITES_DISABLED_REASON


class TradeExecutor:
    def get_symbol_spec(self, symbol=None):
        """The broker's contract specification for ``symbol``, read once.

        Phase 2.1: instrument facts come from the broker, not from config. The
        spec is cached per symbol for the life of the executor and logged the
        first time it is read, so a broker changing a contract specification is
        visible in the log rather than silently rewriting every calculation.
        """
        symbol = symbol or getattr(self.config, "SYMBOL_PHASE5", None) \
            or getattr(self.config, "SYMBOL", None)

        cached = self._symbol_specs.get(symbol)
        if cached is not None:
            return cached

        spec = SymbolSpec.load(self.mt5, symbol)
        logger.info("Symbol spec loaded -- %s", spec.describe())
        self._symbol_specs[symbol] = spec
        return spec

    def _resolve_position_ticket(self, symbol, result):
        """Find the real position ticket for a fill (Phase 2.5, audit L-08).

        ``result.order`` is the *order* ticket. The audit's finding was that the
        code used it as the *position* ticket, which holds on hedging accounts
        but is not guaranteed. Resolve the position by querying open positions
        for this symbol filtered to our magic number, and warn on a mismatch
        rather than silently tracking a ticket that does not exist.

        Falls back to ``result.order`` so a lookup failure degrades to the old
        behaviour instead of losing the position entirely.
        """
        order_ticket = getattr(result, "order", None)

        try:
            positions = self.get_open_positions(symbol)
        except Exception as exc:
            logger.warning("Could not resolve position ticket (%s); "
                           "falling back to order ticket %s", exc, order_ticket)
            return order_ticket

        ours = [p for p in positions if getattr(p, "magic", None) == MAGIC]
        if not ours:
            logger.warning(
                "No open position with magic %s found for %s after a fill; "
                "falling back to order ticket %s", MAGIC, symbol, order_ticket)
            return order_ticket

        # The position we just opened is the most recently opened one.
        newest = max(ours, key=lambda p: getattr(p, "time", 0))
        position_ticket = getattr(newest, "ticket", None)

        if position_ticket != order_ticket:
            logger.warning(
                "Order ticket %s != position ticket %s. This is normal on a "
                "netting account; tracking the position ticket.",
                order_ticket, position_ticket)

        return position_ticket if position_ticket is not None else order_ticket

    def get_order_validator(self, symbol=None):
        """An OrderValidator bound to this symbol's real constraints."""
        spec = self.get_symbol_spec(symbol)
        return OrderValidator(self.mt5, spec)

    def _send_order(self, request):
        """Single choke point for every broker write.

        All four order_send call sites route through here so the read-only
        interlock cannot be bypassed by adding a fifth (Phase 1.4).
        """
        if _WRITES_DISABLED_REASON is not None:
            raise TradingDisabled(_WRITES_DISABLED_REASON)
        return self.mt5.order_send(request)

    def __init__(self, mt5_module, config, risk_manager):
        """Build an executor bound to a real broker, config and risk manager.

        Phase 6.3 (audit M-05). These three arguments used to default to None,
        and __init__ would silently substitute `unittest.mock.Mock` objects --
        including an `order_send` returning `retcode=10009` (DONE). That is a
        fake broker that confirms every order, reachable from production by
        simply forgetting an argument: a misconfigured bot looked exactly like a
        working one, and "successful" trades appeared in the logs while nothing
        reached a market.

        The doubles now live in tests/fakes.py, where reaching them is
        deliberate. Use `tests.fakes.make_executor()` in tests.

        Raises:
            ValueError: if any dependency is missing.
        """
        missing = [name for name, value in (("mt5_module", mt5_module),
                                            ("config", config),
                                            ("risk_manager", risk_manager))
                   if value is None]
        if missing:
            raise ValueError(
                "TradeExecutor requires %s. Passing None used to substitute a "
                "mock broker that confirmed every order (audit M-05); it now "
                "fails loudly instead. Tests should use "
                "tests.fakes.make_executor()." % ", ".join(missing)
            )

        self.mt5 = mt5_module
        self.config = config
        self.risk_manager = risk_manager


        # Phase 2.1: cache of broker contract specs, keyed by symbol.
        self._symbol_specs = {}

        # Phase 5.1: peak favourable excursion per ticket. In-memory;
        # Phase 7 persists it.
        self._peak_profit = {}

        # Phase 5.7 factor 7: ATR at entry, per ticket. Without this the
        # volatility-spike check received entry_atr=None on every call and
        # returned False unconditionally.
        self._entry_atr = {}

        # Phase 12: trailing throttle, per ticket. Previously stored on the
        # (immutable, re-fetched) position object -- see
        # should_update_trailing_stop.
        self._last_trail_update = {}

        # Signal readings for two-bar confirmation: ticket -> [(bar_key, signal,
        # strength)], newest last, at most two. Phase 12: this was one list
        # shared by every position and appended on every call, so two positions
        # evaluated on the same bar counted as "two consecutive candles".
        self.signal_history = {}

        # Stop modifications that failed after retries (audit scenario 24).
        # main.py counts them against the circuit breaker.
        self.stop_failures = []
        self._stop_retry_delay = 0.5

        # Phase 7.1 (H-04): per-position state is PERSISTED and restored here,
        # so a restart does not reset entry ATR or peak profit.
        db_path = getattr(config, "TRADE_DB_PATH", None)
        # MT5 times are broker SERVER time; see utils/market_time.py.
        from utils.market_time import BrokerClock
        self.clock = BrokerClock.from_config(config)
        self.state = PositionStateStore(db_path if isinstance(db_path, str) else None,
                                        clock=self.clock)
        self._restore_position_state()

    def get_open_positions(self, symbol=None):
        """Open positions, or raise if the answer cannot be determined.

        See execution/broker_query.py: "no positions" and "unknown" (a
        disconnected terminal) must never collapse to the same value.

        Returns:
            list: the open positions (possibly empty).

        Raises:
            BrokerQueryFailed: the terminal could not be queried. Callers must
                treat this as "unknown" and refuse to trade, not as "none".
        """
        return broker_query.positions_or_raise(self.mt5, symbol)

    def _terminal_is_connected(self):
        """True when the terminal answers a trivial query."""
        return broker_query.terminal_is_connected(self.mt5)

    def get_open_positions_or_none(self, symbol=None):
        """Positions, or None when the query failed. For read-only callers."""
        try:
            return self.get_open_positions(symbol)
        except BrokerQueryFailed as exc:
            logger.error("Position query failed: %s", exc)
            return None

    def _restore_position_state(self):
        """Load durable state and reconcile it with the broker (Phase 7.1).

        Never silently re-initialises. A position the broker holds but we have
        no record of is ADOPTED in manage-only mode -- managed but never scaled,
        because its scaling history is unknown and assuming zero is precisely
        the H-04 bug.
        """
        try:
            positions = self.get_open_positions()
        except BrokerQueryFailed as exc:
            # Cannot reconcile against an unknown position set. Do not guess.
            logger.error("Cannot restore position state: %s. Treating all "
                         "positions as manage-only until reconciled.", exc)
            self._state_reconciled = False
            return

        symbol = getattr(self.config, "SYMBOL_PHASE5", None)
        report = self.state.reconcile([p.ticket for p in positions], symbol)
        self._state_reconciled = True

        for pos in positions:
            stored = self.state.get_position(pos.ticket) or {}
            if stored.get("entry_atr") is not None:
                self._entry_atr[pos.ticket] = float(stored["entry_atr"])
            if stored.get("peak_favourable_excursion"):
                self._peak_profit[pos.ticket] = float(
                    stored["peak_favourable_excursion"])

        if report["adopted"]:
            logger.warning(
                "%d position(s) adopted in manage-only mode: %s",
                len(report["adopted"]), report["adopted"])
        return report

    def sync_broker_deals(self, mt5_module=None):
        """Record realised P&L from the broker (Phase 7.2, H-07)."""
        return self.state.sync_deals(mt5_module or self.mt5)

    def _new_order_token(self):
        """A short unique tag for one entry attempt (Phase 6.1).

        Goes in the order comment, which MT5 limits to 31 characters, so it is
        deliberately compact. This is what makes a retry idempotent: before
        resending we can ask the broker whether this exact intent already
        became a position.
        """
        return "XAU-%s" % uuid.uuid4().hex[:10]

    def _find_order_by_token(self, symbol, token):
        """Return the position or deal carrying ``token``, else None.

        Checks open positions first, then recent order history -- an order can
        execute and close (or be filled and reported late) between attempts.
        """
        try:
            positions = self.mt5.positions_get(symbol=symbol) or []
            for pos in positions:
                if token in str(getattr(pos, "comment", "")):
                    logger.info("Token %s found on open position %s",
                                token, getattr(pos, "ticket", "?"))
                    return pos
        except Exception as exc:
            logger.error("Could not check positions for token %s: %s", token, exc)

        try:
            # Order history is stamped in broker SERVER time. A window ending
            # at real UTC "now" missed every order from the last 2-3 hours --
            # i.e. exactly the order a retry must find, which is what keeps
            # retries from sending a duplicate.
            now = datetime.now(timezone.utc)

            def server(dt):
                return datetime.fromtimestamp(self.clock.utc_to_server_epoch(dt),
                                              timezone.utc)

            history = self.mt5.history_orders_get(
                server(now - timedelta(minutes=10)), server(now + timedelta(minutes=10))) or []
            for order in history:
                if token in str(getattr(order, "comment", "")):
                    logger.info("Token %s found in order history (ticket %s)",
                                token, getattr(order, "ticket", "?"))
                    return order
        except Exception as exc:
            logger.error("Could not check history for token %s: %s", token, exc)

        return None

    def _log_fill_quality(self, result, request, intended_price):
        """Record actual fill vs intent (Phase 6.2).

        ``result.volume`` was never compared to the requested volume, so partial
        fills were invisible: the bot believed it held a position size it did
        not have. Slippage was never measured either -- and execution quality
        you do not measure is execution quality you cannot manage.
        """
        requested_volume = float(request.get("volume", 0.0))
        filled_volume = getattr(result, "volume", None)
        fill_price = getattr(result, "price", None)

        try:
            filled_volume = float(filled_volume)
        except (TypeError, ValueError):
            filled_volume = None
        try:
            fill_price = float(fill_price)
        except (TypeError, ValueError):
            fill_price = None

        slippage = None
        if fill_price is not None and intended_price:
            slippage = fill_price - float(intended_price)

        logger.info(
            "Fill: requested %.2f lots @ %.2f -> filled %s lots @ %s "
            "(slippage %s)",
            requested_volume, intended_price,
            "%.2f" % filled_volume if filled_volume is not None else "unknown",
            "%.2f" % fill_price if fill_price is not None else "unknown",
            "%+.2f" % slippage if slippage is not None else "unknown",
        )

        if filled_volume is not None and filled_volume > 0:
            shortfall = requested_volume - filled_volume
            if shortfall > 1e-9:
                # Policy: ACCEPT the partial fill. Topping up would place a
                # second order at a worse price to chase a size the market did
                # not offer -- and doubles the failure modes on the path that
                # Phase 6.1 just made safe. Recorded loudly instead.
                logger.warning(
                    "PARTIAL FILL: requested %.2f lots, filled %.2f (short by "
                    "%.2f). Accepting the partial fill; position size is "
                    "smaller than sizing intended.",
                    requested_volume, filled_volume, shortfall)

        return {"requested_volume": requested_volume,
                "filled_volume": filled_volume,
                "fill_price": fill_price,
                "slippage": slippage}

    def _place_market_order(self, symbol, is_buy, volume, sl_price, tp_price):
        terminal_info = self.mt5.terminal_info()
        if terminal_info is None or not terminal_info.trade_allowed:
            raise RuntimeError("Auto-trading is disabled in MetaTrader 5 terminal.")

        order_type = self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("No tick data available")
        price = float(tick.ask if is_buy else tick.bid)

        # Phase 2.3 (H-01): validate against the broker's own constraints before
        # sending. This rounds volume down to volume_step, rounds prices to the
        # symbol's digits, widens SL/TP to clear trade_stops_level, checks free
        # margin, and picks a filling mode the broker actually supports instead
        # of hardcoding IOC.
        validator = self.get_order_validator(symbol)
        validated = validator.normalize(
            order_type, volume, price,
            sl=sl_price if sl_price else None,
            tp=tp_price if tp_price else None,
        )
        if isinstance(validated, Rejection):
            raise RuntimeError("Order rejected before sending: %s" % validated)

        # Phase 12 follow-up: the lot size arrives ALREADY SIZED for the stop
        # distance the caller intended (main.py sizes before calling
        # enter_trade). enforce_stops_level(), just above, may have WIDENED
        # that stop to clear the broker's trade_stops_level -- and until now
        # nothing re-checked that the position's real dollar risk still
        # matched what was authorised. On this broker trade_stops_level is 0,
        # so this has never fired, but a broker with a real minimum distance
        # would have silently risked more than RISK_PER_TRADE_FRACTION.
        # Shrink the position instead: same intended risk, smaller size,
        # never silently more risk than configured.
        spec_for_resize = self.get_symbol_spec(symbol)
        if sl_price and validated["sl"] is not None:
            intended_distance = abs(price - float(sl_price))
            actual_distance = abs(validated["price"] - validated["sl"])
            if intended_distance > 0 and actual_distance > intended_distance * 1.0001:
                shrunk = normalize_volume(
                    spec_for_resize, validated["volume"] * intended_distance / actual_distance)
                if isinstance(shrunk, Rejection):
                    raise RuntimeError(
                        "Broker's minimum stop distance (%.2f) is wider than intended "
                        "(%.2f); the resulting position would need less than the "
                        "broker minimum lot to hold risk at the configured level -- "
                        "declining rather than risking more (%s)"
                        % (actual_distance, intended_distance, shrunk))
                logger.warning(
                    "Stop widened by the broker's minimum distance (%.2f -> %.2f "
                    "price units); reducing size %.2f -> %.2f lots to hold risk at "
                    "the level sizing authorised.",
                    intended_distance, actual_distance, validated["volume"], shrunk)
                validated["volume"] = shrunk

        # Phase 2.4: log the spread on every entry so the threshold can be
        # calibrated from real data rather than guessed.
        spec = self.get_symbol_spec(symbol)
        spread = spec.spread_points(self.mt5)
        max_spread = getattr(self.config, "MAX_ENTRY_SPREAD_POINTS", None)
        if spread is None:
            logger.warning("Spread unknown for %s -- spread gate not applied",
                           symbol)
        else:
            logger.info("Spread at entry: %.1f points (limit %s)",
                        spread, max_spread if max_spread is not None else "unset")
            if max_spread is not None and spread > max_spread:
                raise RuntimeError(
                    "Spread %.1f points exceeds MAX_ENTRY_SPREAD_POINTS=%s"
                    % (spread, max_spread)
                )

        # Phase 6.1: a unique token per entry attempt, carried in the comment.
        # It is what lets a retry ask "did this already execute?" instead of
        # blindly resending.
        token = self._new_order_token()
        intended_price = validated["price"]

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": validated["volume"],
            "type": order_type,
            "price": validated["price"],
            "sl": validated["sl"] if validated["sl"] else 0.0,
            "tp": validated["tp"] if validated["tp"] else 0.0,
            "deviation": self.config.ORDER_DEVIATION_POINTS,
            "magic": MAGIC,
            "comment": token,          # MT5 caps this at 31 chars
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": validated["type_filling"],
        }

        # Phase 6.1 (audit H-02). The old loop re-sent an IDENTICAL request up
        # to three times whenever the retcode was not DONE -- including when
        # `result` was None or attribute access raised, i.e. exactly when the
        # order's true status was unknown. A timeout after the broker filled
        # would therefore open a second position. The price was also computed
        # once and never refreshed, so retries competed with a stale quote.
        last_err = None
        for attempt in range(self.config.ORDER_MAX_ATTEMPTS):
            if attempt > 0:
                # Has the previous attempt actually executed? Asking is the
                # whole point: never re-send until we know we did not fill.
                existing = self._find_order_by_token(symbol, token)
                if existing is not None:
                    logger.warning(
                        "Attempt %d: order %s already executed -- not resending.",
                        attempt + 1, token)
                    return existing

                # Re-read the tick: a stale price guarantees another requote.
                tick = self.mt5.symbol_info_tick(symbol)
                if tick is None:
                    raise RuntimeError("No tick data available on retry")
                refreshed = spec.round_price(float(tick.ask if is_buy else tick.bid))
                logger.info("Refreshed price for retry: %s -> %s",
                            request["price"], refreshed)
                request["price"] = refreshed

            # Audit scenario 7: the send itself can raise AFTER the broker has
            # filled (an IPC failure reading the reply), and a result object's
            # retcode can be unreadable. Both mean "outcome unknown" -- the same
            # as a None result -- so both reconcile by token instead of
            # propagating an exception that leaves a real fill untracked.
            try:
                result = self._send_order(request)
            except TradingDisabled:
                raise
            except Exception as exc:
                logger.error("order_send raised on attempt %d (%s) -- outcome "
                             "UNKNOWN, reconciling by token.", attempt + 1, exc)
                result = None
            try:
                retcode = getattr(result, "retcode", None)
            except Exception:
                retcode = None

            if retcode == self.mt5.TRADE_RETCODE_DONE:
                self._log_fill_quality(result, request, intended_price)
                return result

            if retcode is None:
                # UNKNOWN, not failed. Reconcile instead of retrying.
                logger.error(
                    "Order attempt %d returned no retcode -- status UNKNOWN. "
                    "Reconciling by token rather than resending.", attempt + 1)
                existing = self._find_order_by_token(symbol, token)
                if existing is not None:
                    return existing
                raise RuntimeError(
                    "Order status unknown for token %s and no matching position "
                    "found. Refusing to resend -- reconcile manually." % token)

            if retcode not in RETRYABLE_RETCODES:
                raise RuntimeError(
                    "Order rejected with retcode %s (not retryable): %s"
                    % (retcode, getattr(result, "comment", "")))

            logger.warning("Order attempt %d requoted/priced off (retcode %s); "
                           "retrying.", attempt + 1, retcode)
            last_err = result
            time.sleep(1)

        # Final reconciliation: the last attempt may have landed after we
        # stopped waiting for it.
        existing = self._find_order_by_token(symbol, token)
        if existing is not None:
            logger.warning("Order %s executed after the final attempt.", token)
            return existing

        raise RuntimeError("Order failed after %d attempts: %s"
                           % (self.config.ORDER_MAX_ATTEMPTS, last_err))

    def enter_trade(self, symbol, signal, entry_price, stop_price, tp_price=None,
                    volume=None, entry_atr=None):
        is_buy = signal.upper() == "BUY"
        if volume is None:
            lots = self.risk_manager.compute_lot_size(stop_price, entry_price)
        else:
            lots = volume

        if lots is None or lots <= 0:
            # Phase 3.1: None means the sizing calculation DECLINED the trade --
            # the account cannot take it at the configured risk. That is a
            # decision, not a failure to compute.
            raise RuntimeError(
                "Trade declined by position sizing: the account cannot take "
                "this stop distance at the configured risk. See the sizing log "
                "line above for the arithmetic."
            )
        # Phase 6.4: never open a position while the existing position state is
        # unknown. A failed query used to read as "flat", which is the one
        # wrong answer -- it invites stacking a new position on top of ones we
        # cannot see.
        try:
            self.get_open_positions(symbol)
        except BrokerQueryFailed as exc:
            raise RuntimeError(
                "Refusing to trade: position state is unknown (%s)" % exc
            ) from exc

        # Phase 12.5 / audit scenario 19: halt after a run of losing trades,
        # counted from the broker's realised deals. Sticky until acknowledged
        # (python main.py --ack-loss-streak), because with entries blocked no
        # new winner can ever clear it.
        streak_limit = getattr(self.config, "MAX_CONSECUTIVE_LOSSES", None)
        if isinstance(streak_limit, (int, float)) and streak_limit > 0:
            streak = self.state.consecutive_losses()
            if streak >= streak_limit:
                raise RuntimeError(
                    "Loss-streak halt: %d consecutive losing trades (limit %d). "
                    "Review, then run `python main.py --ack-loss-streak`."
                    % (streak, streak_limit))

        if not self.risk_manager.enough_balance():
            raise RuntimeError("Account balance too low")
        if not self.risk_manager.check_daily_loss_limit():
            raise RuntimeError("Daily loss limit reached")

        # Phase 3.4: drawdown from the persisted equity high-water mark.
        if not self.risk_manager.check_drawdown():
            raise RuntimeError("Drawdown limit reached")

        # Phase 3.5: no portfolio-level check existed between the entry
        # decision and the order. Size the candidate's risk in money and assert
        # the total across all open positions stays within the cap. Both
        # queries can raise BrokerQueryFailed (broker_query.py) if position
        # state is unknown -- that must refuse the trade, not read as zero.
        try:
            candidate_risk = abs(float(entry_price) - float(stop_price)) * \
                self.risk_manager.contract_size(symbol) * float(lots)
            if not self.risk_manager.check_portfolio_risk(candidate_risk, symbol):
                raise RuntimeError("Portfolio risk cap would be exceeded")

            if self.risk_manager.current_open_positions_count(symbol) >= self.config.MAX_CONCURRENT_POSITIONS:
                raise RuntimeError("Max concurrent positions reached")
        except BrokerQueryFailed as exc:
            raise RuntimeError(
                "Refusing to trade: position state is unknown (%s)" % exc
            ) from exc

        logger.info(f"Placing {'BUY' if is_buy else 'SELL'} {lots} lots @ {entry_price}, SL={stop_price}, TP={tp_price}")
        result = self._place_market_order(symbol, is_buy, lots, stop_price, tp_price)

        # Record per-position state for new positions
        if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
            # Phase 2.5 (L-08): result.order is the ORDER ticket. On hedging
            # accounts it happens to equal the position ticket, but that is not
            # guaranteed -- on netting accounts a fill merges into an existing
            # position with a different ticket entirely. Resolve the real one.
            ticket = self._resolve_position_ticket(symbol, result)
            if ticket:
                if entry_atr is not None:
                    self._entry_atr[ticket] = float(entry_atr)

                # Phase 7.1: persist immediately, so a crash between here and
                # the next restart does not lose the entry ATR.
                try:
                    self.state.save_position(
                        ticket=ticket,
                        symbol=symbol,
                        entry_token=getattr(result, "comment", None),
                        entry_atr=entry_atr,
                        original_volume=lots,
                        total_volume=lots,
                        scaling_count=0,
                        manage_only=False,
                    )
                except Exception as exc:
                    logger.error("Could not persist state for %s: %s", ticket, exc)

                logger.info("Initialized and persisted state for position %s", ticket)

        return result

    def close_all_positions(self, symbol):
        positions = self.get_open_positions(symbol)
        if not positions:
            logger.info("No positions to close")
            return 0

        closed_count = 0
        for pos in positions:
            if self.close_position_by_ticket(pos.ticket):
                closed_count += 1
        logger.info(f"Closed {closed_count} positions for {symbol}")
        return closed_count

    def close_position_by_ticket(self, ticket):
        positions = self.mt5.positions_get(ticket=ticket)
        if not positions:
            logger.warning(f"No position found with ticket {ticket}")
            return False

        pos = positions[0]
        volume = pos.volume
        is_buy = pos.type == self.mt5.POSITION_TYPE_BUY
        symbol = pos.symbol

        order_type = self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"No tick data for {symbol}")
            return False

        price = float(tick.bid if is_buy else tick.ask)
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": self.config.ORDER_DEVIATION_POINTS,
            "magic": MAGIC,
            "comment": "Manual close",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        try:
            res = self._send_order(req)
        except Exception as exc:
            logger.error("Close of position %s raised: %s", ticket, exc)
            return False
        if res is not None and getattr(res, "retcode", None) == self.mt5.TRADE_RETCODE_DONE:
            logger.info(f"Successfully closed position {ticket}: {res}")
            return True
        # None means the terminal gave no answer; the position may or may not
        # be closed, and the next loop re-reads positions from the broker.
        logger.error(f"Failed to close position {ticket}: {res}")
        return False

    def should_update_trailing_stop(self, position, last_update_time=None,
                                    min_interval=600, now=None):
        """True if at least ``min_interval`` seconds have passed since this
        position's stop was last trailed.

        BUG FIX (Phase 12): the timestamp was stored ON the position object --
        ``position.last_trail_update = ...``. Real MT5 positions are immutable
        namedtuples, so that assignment raised on every real position; and
        positions are re-fetched from the terminal every loop, so even a
        mutable object would have forgotten the timestamp by the next
        iteration. The throttle could never have worked. State is now kept per
        ticket on the executor, which lives for the whole run.
        """
        now = now or datetime.now(timezone.utc)
        ticket = getattr(position, "ticket", None)
        last = self._last_trail_update.get(ticket)
        if last is not None and (now - last).total_seconds() < min_interval:
            return False
        self._last_trail_update[ticket] = now
        return True

    def calculate_trailing_stop(self, position, current_price, atr=None, volatility=None, trend_strength=None, news_sentiment=None):
        """
        Calculates a dynamic trailing stop based on market conditions.
        If adaptive mode is off, falls back to static trailing stop.
        """

        config = self.config
        adaptive_enabled = getattr(config, "ADAPTIVE_TRAILING_STOP", True)

        base_trail_price = self.config.TRAIL_DISTANCE_PRICE
        trail_distance = base_trail_price

        if adaptive_enabled:
            # Adjust trail distance based on volatility (ATR or custom)
            if atr and atr > 0:
                trail_distance *= (atr / 10)  # Example: if ATR = 20, trail widens

            # Adjust based on trend strength
            if trend_strength is not None:
                if trend_strength > 70:  # strong trend → looser trailing stop
                    trail_distance *= 1.3
                elif trend_strength < 40:  # weak trend → tighter trailing stop
                    trail_distance *= 0.8

            # Adjust for news sentiment
            if news_sentiment:
                sentiment_score = 0.0
                if isinstance(news_sentiment, dict):
                    sentiment_score = news_sentiment.get("avg_sentiment_score", 0.0)
                    sentiment_type = news_sentiment.get("sentiment", "")
                else:
                    sentiment_type = news_sentiment
                if sentiment_type == "bullish" and position.type == self.mt5.POSITION_TYPE_BUY:
                    trail_distance *= 0.9
                elif sentiment_type == "bearish" and position.type == self.mt5.POSITION_TYPE_SELL:
                    trail_distance *= 0.9
                else:
                    trail_distance *= 1.1  # increase margin under uncertainty

            # Phase 5.5 (audit M-04): the trail distance was multiplied by a
            # uniform jitter here, commented "prevent over-optimization". It
            # does not address overfitting -- it makes risk irreproducible,
            # incidents un-debuggable and tests impossible. Determinism is a
            # precondition for the Phase 9 measurement, so it is deleted.

        # Already in price units -- no conversion needed (Phase 2.2)
        trail_distance_price = trail_distance  # price units, not points

        # Add volatility-based buffer
        safety_buffer = 2 * self.mt5.symbol_info(position.symbol).point

        if position.type == self.mt5.POSITION_TYPE_BUY:
            new_sl = current_price - trail_distance_price - safety_buffer
            # Ensure SL doesn't go above current price
            if new_sl >= current_price:
                new_sl = current_price - (trail_distance_price * 1.2)
        else:
            new_sl = current_price + trail_distance_price + safety_buffer
            if new_sl <= current_price:
                new_sl = current_price + (trail_distance_price * 1.2)

        return round(new_sl, 2)

    def _check_trailing_stop(self, position, current_price, atr=None):
        """
        Determines whether the trailing stop should be updated safely.
        Prevents premature closes by ensuring SL stays far enough from current price.
        """
        config = self.config

        profit_price = (
            (current_price - position.price_open)
            if position.type == self.mt5.POSITION_TYPE_BUY
            else (position.price_open - current_price)
        )

        # Don't trail until the position has at least X of price movement
        if profit_price < config.TRAIL_START_PRICE:
            return False

        # Skip frequent updates (less than every 5 mins)
        if not self.should_update_trailing_stop(position, min_interval=300):
            return False

        # Calculate adaptive trailing stop.
        # Phase 12.3: this read config.CURRENT_ATR -- a static constant (12.5) that
        # nothing ever wrote. Live market state was being read from config.
        # The real ATR is now an argument; without it we do not trail.
        if atr is None or atr != atr or atr <= 0:
            logger.warning("No live ATR for position %s -- not trailing.",
                           getattr(position, "ticket", "?"))
            return False
        atr_value = float(atr)
        trail_distance_points = max((atr_value * 2), 10)  # at least 10 points away

        symbol_info = self.mt5.symbol_info(position.symbol)
        point = symbol_info.point
        spread = symbol_info.spread * point

        # Apply safe buffers
        safety_buffer = (trail_distance_points * point) + (spread * 2)

        if position.type == self.mt5.POSITION_TYPE_BUY:
            # Only move SL if price moved upward significantly beyond current SL
            new_sl = max(position.sl, current_price - safety_buffer)
            # SL must be at least 3x spread away from price
            if (current_price - new_sl) < (spread * 3):
                return False
        else:
            new_sl = min(position.sl or current_price, current_price + safety_buffer)
            if (new_sl - current_price) < (spread * 3):
                return False

        return round(new_sl, 2)

    def apply_break_even_sl(self, position, atr=None, trend_strength=None,
                            news_sentiment=None):
        """
        Applies adaptive break-even stop loss based on market factors.
        Moves SL to a dynamic level above entry price considering ATR, trend strength, news sentiment, etc.
        """
        config = self.config

        if not config.BREAK_EVEN_ENABLED:
            logger.info("Break-even disabled in config")
            return False

        # Check if position is profitable enough
        profit_price = (
            (position.price_current - position.price_open)
            if position.type == self.mt5.POSITION_TYPE_BUY
            else (position.price_open - position.price_current)
        )
        if profit_price < config.BREAK_EVEN_PROFIT_PRICE:
            logger.info(f"Position {position.ticket} not profitable enough for break-even: {profit_price:.2f} < {config.BREAK_EVEN_PROFIT_PRICE}")
            return False

        # Check if already at break-even (SL near entry)
        entry_sl_distance = abs(position.sl - position.price_open) if position.sl > 0 else float('inf')
        if entry_sl_distance < config.BREAK_EVEN_BUFFER_PRICE:
            logger.info(f"Position {position.ticket} already at break-even")
            return False

        # Calculate dynamic buffer
        base_buffer = config.BREAK_EVEN_BUFFER_PRICE

        # Phase 12.3: ATR, trend strength and news sentiment were read from
        # config.CURRENT_ATR / CURRENT_TREND_STRENGTH / CURRENT_NEWS_SENTIMENT --
        # static constants (12.5, 65, a hardcoded "bullish" dict) that nothing
        # ever updated. They are now arguments; a missing input contributes
        # nothing rather than contributing a stale made-up number.

        # ATR-based adjustment
        if atr is not None and atr == atr and atr > 0:
            base_buffer += config.BREAK_EVEN_ATR_MULTIPLIER * float(atr)

        # Trend strength adjustment
        if trend_strength is not None:
            trend_buffer = config.BREAK_EVEN_TREND_STRENGTH_MULTIPLIER * float(trend_strength)
            if trend_strength > 70:  # Strong trend, tighter buffer
                base_buffer -= trend_buffer
            elif trend_strength < 40:  # Weak trend, wider buffer
                base_buffer += trend_buffer

        # News sentiment adjustment
        if not isinstance(news_sentiment, dict):
            news_sentiment = {'sentiment': 'neutral', 'avg_sentiment_score': 0.0}
        sentiment_score = news_sentiment.get('avg_sentiment_score', 0.0) if isinstance(news_sentiment, dict) else 0.0
        sentiment_buffer = config.BREAK_EVEN_NEWS_SENTIMENT_MULTIPLIER * sentiment_score * 100  # scale sentiment [-1,1] into price units
        if position.type == self.mt5.POSITION_TYPE_BUY and news_sentiment.get('sentiment') == 'bullish':
            base_buffer -= sentiment_buffer
        elif position.type == self.mt5.POSITION_TYPE_SELL and news_sentiment.get('sentiment') == 'bearish':
            base_buffer -= sentiment_buffer
        else:
            base_buffer += sentiment_buffer

        # Time since entry adjustment.
        #
        # BUG FIX (Phase 5 follow-up): this grew by 0.01 price units per minute
        # with NO UPPER BOUND. After a week the buffer alone is ~100; with a
        # stale or zero position.time it reaches six figures. Capped at the
        # profit actually achieved -- a break-even buffer can never sensibly
        # exceed the profit it is protecting.
        time_since_entry = max(0.0, self.clock.age_seconds(position.time))
        time_buffer = config.BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER * (time_since_entry / 60)
        base_buffer += min(time_buffer, profit_price)

        # Profit level adjustment
        profit_buffer = config.BREAK_EVEN_PROFIT_LEVEL_MULTIPLIER * profit_price
        base_buffer += profit_buffer

        # Phase 5.5 (audit M-04): a multiplicative jitter was applied to the
        # break-even buffer here, commented "prevent over-optimization".
        # Deleted -- see the trailing-stop note above.

        # Bound the buffer. It must be at least one price unit, and can never
        # exceed the profit achieved -- a stop beyond current price is not a
        # stop, and the clamp below used to "fix" that by going the wrong way.
        max_fraction = getattr(config, "BREAK_EVEN_MAX_BUFFER_FRACTION", 0.9)
        base_buffer = max(1.0, min(base_buffer, profit_price * max_fraction))

        is_buy = position.type == self.mt5.POSITION_TYPE_BUY
        entry = float(position.price_open)
        current = float(position.price_current)
        buffer_price = base_buffer

        new_sl = entry + buffer_price if is_buy else entry - buffer_price

        # BUG FIX (Phase 5 follow-up): the old clamp was
        #     new_sl = price_current -/+ (buffer_price * 0.5)
        # which, with a large buffer, produced a stop far BELOW entry -- in the
        # worst case a negative price. A break-even stop below the entry it is
        # supposed to protect is not break-even; it is a loss with extra steps.
        #
        # The stop must land inside [entry, current) for a BUY, and
        # (current, entry] for a SELL. Clamp into that window, never outside it.
        if is_buy:
            new_sl = min(new_sl, current)
            new_sl = max(new_sl, entry)
        else:
            new_sl = max(new_sl, current)
            new_sl = min(new_sl, entry)

        # If the window has collapsed there is nothing protective to set.
        if (is_buy and new_sl >= current) or (not is_buy and new_sl <= current):
            logger.info(
                "Position %s: no protective break-even level available "
                "(entry %.2f, current %.2f) -- leaving the stop alone.",
                position.ticket, entry, current)
            return False

        # Never move a stop backwards.
        if position.sl and position.sl > 0:
            if is_buy and new_sl <= position.sl:
                return False
            if not is_buy and new_sl >= position.sl:
                return False

        logger.info(
            "Break-even SL for position %s: entry %.2f, current %.2f, "
            "new SL %.2f (buffer %.2f)",
            position.ticket, entry, current, new_sl, base_buffer)
        return self.modify_trade_sl(position, new_sl)

    def manage_open_positions(self, symbol=None, atr=None, trend_strength=None,
                              news_sentiment=None):
        """Move stops on open positions. NEVER closes anything (Phase 5.2, C-06).

        The audited code had three carefully written helpers -- ``modify_trade_sl``,
        ``apply_break_even_sl`` and ``calculate_trailing_stop`` -- that no live
        path ever called. Meanwhile ``_check_trailing_stop`` was consumed inside
        ``should_close_trade``, so the only thing "trailing" did was close the
        position at market.

        This is the missing step: it runs on its own cadence, computes a new
        stop, and issues TRADE_ACTION_SLTP. The only way a position closes from
        here is the broker's own server-side stop being hit.

        Returns the number of stops actually modified.
        """
        config = self.config

        symbol = symbol or getattr(self.config, "SYMBOL_PHASE5", None)
        modified = 0

        for position in self.get_open_positions(symbol):
            try:
                new_sl = None

                # Break-even first: once a position has paid for itself, protect
                # the entry before trying to trail further.
                if getattr(config, "BREAK_EVEN_ENABLED", False):
                    if self.apply_break_even_sl(position, atr=atr,
                                                trend_strength=trend_strength,
                                                news_sentiment=news_sentiment):
                        modified += 1
                        continue

                if getattr(config, "TRAILING_STOP_ENABLED", False):
                    tick = self.mt5.symbol_info_tick(position.symbol)
                    if tick is None:
                        continue
                    is_buy = position.type == self.mt5.POSITION_TYPE_BUY
                    current_price = float(tick.bid if is_buy else tick.ask)

                    if self._check_trailing_stop(position, current_price, atr=atr):
                        new_sl = self.calculate_trailing_stop(
                            position, current_price, atr=atr,
                            trend_strength=trend_strength,
                            news_sentiment=news_sentiment,
                        )

                if new_sl is None:
                    continue

                # Never move a stop backwards -- a trailing stop that can
                # retreat is not a stop, it is a widening of risk.
                is_buy = position.type == self.mt5.POSITION_TYPE_BUY
                if position.sl and position.sl > 0:
                    if is_buy and new_sl <= position.sl:
                        continue
                    if not is_buy and new_sl >= position.sl:
                        continue

                if self.modify_trade_sl(position, new_sl):
                    modified += 1

            except Exception as exc:
                logger.exception("Error managing position %s: %s",
                                 getattr(position, "ticket", "?"), exc)

        return modified

    def modify_trade_sl(self, position, new_sl):
        """
        Safely updates SL without triggering premature closure.
        Verifies SL is far enough from market price and valid per broker constraints.
        """
        try:
            symbol_info = self.mt5.symbol_info(position.symbol)
            point = symbol_info.point
            stop_level = symbol_info.trade_stops_level * point or (symbol_info.spread * point * 3)
            current_price = position.price_current

            # Enforce safe stop distance
            if position.type == self.mt5.POSITION_TYPE_BUY:
                if new_sl >= (current_price - stop_level):
                    logger.warning(f"⚠️ Skipped SL update for {position.ticket}: SL {new_sl} too close to BUY price {current_price}")
                    return False
            else:
                if new_sl <= (current_price + stop_level):
                    logger.warning(f"⚠️ Skipped SL update for {position.ticket}: SL {new_sl} too close to SELL price {current_price}")
                    return False

            request = {
                "action": self.mt5.TRADE_ACTION_SLTP,
                "position": position.ticket,
                "symbol": position.symbol,
                "sl": float(new_sl),
                "tp": float(position.tp),
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }

            # Audit scenario 24: a rejected modification used to be logged and
            # forgotten. Retry (a requote or a moved price is transient), then
            # escalate -- the position keeps its PREVIOUS server-side stop, but
            # a person must know the intended stop is not in place.
            attempts = max(1, int(getattr(self.config, "ORDER_MAX_ATTEMPTS", 3) or 1))
            last_error = None
            for attempt in range(1, attempts + 1):
                try:
                    result = self._send_order(request)
                    if result.retcode == self.mt5.TRADE_RETCODE_DONE:
                        logger.info(f"✅ SL updated for position {position.ticket} → {new_sl:.2f}")
                        return True
                    last_error = "retcode %s (%s)" % (result.retcode,
                                                      getattr(result, "comment", ""))
                except Exception as exc:
                    last_error = "exception: %s" % exc
                logger.warning("SL update for %s failed (attempt %d/%d): %s",
                               position.ticket, attempt, attempts, last_error)
                if attempt < attempts:
                    time.sleep(self._stop_retry_delay)
            self._escalate_stop_failure(position, new_sl, last_error)
            return False

        except Exception as e:
            logger.error(f"❌ Exception updating SL for {position.ticket}: {str(e)}")
            return False

    def _escalate_stop_failure(self, position, new_sl, error):
        """Make a failed stop modification impossible to miss."""
        record = {"ticket": getattr(position, "ticket", None), "intended_sl": new_sl,
                  "current_sl": getattr(position, "sl", None), "error": error,
                  "at": datetime.now(timezone.utc).isoformat()}
        self.stop_failures.append(record)
        logger.critical("STOP NOT MOVED for position %s: wanted %s, broker still "
                        "holds %s after retries (%s). Check the position in the "
                        "terminal.", record["ticket"], new_sl, record["current_sl"], error)

    def should_close_trade(self, position, current_data, strategy, news_sentiment, atr_value=None, entry_atr=None):
        """Decide whether to close ``position`` early, on the newest closed bar.

        The rules live in strategies/exit_rules.py, shared with the backtester,
        so Gate C measures the exits that actually run. This method gathers the
        live-only inputs: signal readings per ticket and bar, ATR at entry, the
        broker-clock position age, account drawdown, PFE state, position count.

        TP/SL are held server-side (Phase 5.6) and trailing modifies stops in
        manage_open_positions (Phase 5.2); neither is decided here.

        Returns:
            dict: ``should_close``, ``reason`` and, when closing, ``all_factors``
            and ``position_info``.
        """
        from strategies import exit_rules
        from utils.news_reader import score_of, sentiment_of

        config = self.config
        if not config.AUTO_CLOSE_ENABLED:
            return {'should_close': False, 'reason': 'auto_close_disabled'}

        position_type = 'BUY' if position.type == self.mt5.POSITION_TYPE_BUY else 'SELL'
        current_price = current_data['close'].iloc[-1] if len(current_data) > 0 else position.price_current
        position_age = int(self.clock.age_seconds(position.time))
        unrealized_profit = position.profit

        too_young = position_age < exit_rules.min_hold_seconds(config)

        signal_info = strategy.generate_signal(current_data)
        readings = self._record_signal_reading(position, current_data,
                                               signal_info['signal'],
                                               signal_info['strength'])

        # Phase 5.7: fall back to the ATR recorded at entry.
        if entry_atr is None:
            entry_atr = self._entry_atr.get(getattr(position, "ticket", None))

        ctx = exit_rules.ExitContext(
            position_type=position_type,
            age_seconds=position_age,
            readings=readings,
            frame=current_data,
            reversal=strategy.detect_trend_reversal(current_data),
            atr=atr_value,
            entry_atr=entry_atr,
            now_utc=datetime.now(timezone.utc),
            news_label=sentiment_of(news_sentiment),
            news_score=score_of(news_sentiment),
            # Live-only inputs are computed only when their factor is on: the
            # drawdown check fails CLOSED, and must not fire while disabled.
            drawdown_breached=(config.PORTFOLIO_DRAWDOWN_CLOSE
                               and self._check_portfolio_drawdown()),
            rr_retraced=(config.RR_REVERSAL_ENABLED
                         and self._check_rr_ratio_reversal(position, unrealized_profit)),
            too_many_positions=(config.MAX_TOTAL_POSITIONS_CLOSE_ENABLED
                                and self._check_max_total_positions(position.symbol)),
        )
        factors = exit_rules.triggered_factors(ctx, config, risk_only=too_young)
        if too_young and not factors:
            return {'should_close': False, 'reason': f'position_too_young_{position_age}s'}
        if factors:
            return {
                'should_close': True,
                'reason': factors[0],
                'all_factors': [{'factor': name, 'should_close': True} for name in factors],
                'position_info': {
                    'type': position_type,
                    'age_seconds': position_age,
                    'profit': unrealized_profit,
                    'current_price': current_price
                }
            }

        return {'should_close': False, 'reason': None}

    # _check_take_profit_reached() deleted in Phase 12: removed from the close path in Phase 5.6 (TP/SL are server-side).

    # _check_stop_loss_hit() deleted in Phase 12: removed from the close path in Phase 5.6 (TP/SL are server-side).

    # NOTE: a second, naive _check_trailing_stop was defined here and silently
    # shadowed the spread-aware implementation above (audit M-08). Deleted in
    # Phase 1.3; the spread-aware version is now the only one. Phase 5 rewires it.

    def _check_opposite_signal(self, position_type, current_signal, signal_strength):
        """One reading against the position at reversal strength."""
        from strategies.exit_rules import opposite_of
        return (signal_strength >= self.config.EXIT_REVERSAL_MIN_STRENGTH
                and current_signal == opposite_of(position_type))

    def _record_signal_reading(self, position, current_data, signal, strength):
        """Record one reading per (ticket, bar) and return the last two."""
        from strategies.exit_rules import record_reading
        bar_key = current_data.index[-1] if len(current_data) else None
        history = self.signal_history.setdefault(getattr(position, "ticket", None), [])
        return record_reading(history, bar_key, signal, strength)

    def _check_news_economic_event(self, position_type, news_sentiment):
        """Headline sentiment against the position (Phase 10: dict or string)."""
        from strategies.exit_rules import news_against
        from utils.news_reader import sentiment_of
        return (self.config.NEWS_SENTIMENT_CLOSE
                and news_against(position_type, sentiment_of(news_sentiment)))

    def _check_volatility_spike(self, current_atr, entry_atr):
        from strategies.exit_rules import volatility_spike
        return volatility_spike(current_atr, entry_atr, self.config.ATR_SPIKE_MULTIPLIER)

    def _check_time_based_exit(self, position_age):
        return position_age > self.config.MAX_POSITION_AGE_SECONDS

    def _check_market_session_end(self, now=None):
        """True within the buffer before the Friday 17:00 New York close.

        Phase 5.6 fixed the buffer arithmetic; the boundary was still a fixed
        22:00 UTC, an hour late for the half of the year New York observes DST.
        It now follows New York time (utils/market_time.py).
        """
        from utils.market_time import in_weekend_close_window
        now = now or datetime.now(timezone.utc)
        return in_weekend_close_window(now, self.config.SESSION_END_BUFFER_MINUTES)

    def _check_break_of_structure(self, current_data, position_type):
        """True when price has broken the recent structure against the position.

        Phase 5.3 (audit M-01). The window used ``.tail(n)``, which **includes
        the current bar**. Comparing ``close.iloc[-1] < low.tail(n).min()`` is
        then unsatisfiable: a bar's close is always >= its own low, so the
        minimum can never exceed it. The audit measured 0 firings in 20,000
        random walks in both directions -- the factor was dead code that looked
        like a risk control.

        The window now ends *before* the current bar, so "the recent range" is
        genuinely prior structure that the current close can break out of.
        """
        from strategies.exit_rules import break_of_structure
        return break_of_structure(current_data, position_type, self.config.FRACTAL_PERIOD)

    def record_peak_profit(self, position, unrealized_profit):
        """Track peak favourable excursion (PFE) per ticket (Phase 5.1).

        The RR-reversal factor's stated intent is "profit fell below half of
        what it reached". That is unimplementable without remembering what it
        reached, and the audited code remembered nothing.

        NOTE: this is in-memory only, so it resets on restart. Phase 7 persists
        it. Until then RR_REVERSAL_ENABLED stays False -- see below.
        """
        ticket = getattr(position, "ticket", None)
        if ticket is None:
            return None
        peak = self._peak_profit.get(ticket, 0.0)
        if unrealized_profit > peak:
            peak = float(unrealized_profit)
            self._peak_profit[ticket] = peak
            # Phase 7.1: persist, so a restart does not reset the peak to zero
            # and instantly "retrace" a winning position into a close.
            try:
                self.state.record_peak(ticket, peak)
            except Exception as exc:
                logger.error("Could not persist PFE for %s: %s", ticket, exc)
        return peak

    def forget_position(self, ticket):
        """Drop per-ticket state when a position closes.

        Phase 7.1: also clears the durable row. Previously state was only
        cleaned in close_position_by_ticket, so positions closed server-side by
        SL or TP leaked their entries forever.
        """
        self._peak_profit.pop(ticket, None)
        self._entry_atr.pop(ticket, None)
        self._last_trail_update.pop(ticket, None)
        self.signal_history.pop(ticket, None)
        try:
            self.state.forget_position(ticket)
        except Exception as exc:
            logger.error("Could not clear durable state for %s: %s", ticket, exc)

    def _check_rr_ratio_reversal(self, position, unrealized_profit):
        """True when profit has retraced from its peak by more than the threshold.

        Phase 5.1 (audit C-03). The original computed

            max_profit = |entry - sl| * TP_RISK_REWARD * volume * 100000

        which inflated the figure by ~1000x, making
        ``unrealized_profit < max_profit * 0.5`` **impossible to falsify**. On a
        0.01-lot position it demanded $12,500 of profit to avoid closing, so
        every position was market-closed the moment it became eligible. Phase
        2.2 fixed the arithmetic, but the semantics were still wrong: a fresh
        position at $0 profit trips ``0 < max_profit * 0.5`` immediately.

        This version measures what the name says -- retracement from the peak
        actually observed -- which requires PFE state.

        Default-OFF: ``RR_REVERSAL_ENABLED = False`` until Phase 7 makes the PFE
        durable. In-memory peaks reset on restart, and a peak of 0 after a
        restart would close a winning position instantly. A disabled factor is
        safe; an always-true one is not.
        """
        config = self.config
        if not config.RR_REVERSAL_ENABLED:
            return False

        peak = self.record_peak_profit(position, unrealized_profit)
        if peak is None or peak <= 0:
            # Never been in profit: there is no retracement to measure.
            return False

        # Require a meaningful peak before arming, so noise around break-even
        # cannot trigger an exit.
        min_peak = price_to_money(
            self.get_symbol_spec(position.symbol),
            abs(position.price_open - position.sl) if position.sl else 0.0,
            position.volume,
        )
        if min_peak <= 0 or peak < min_peak:
            return False

        return unrealized_profit < peak * config.RR_REVERSAL_THRESHOLD

    def _check_portfolio_drawdown(self):
        """True when drawdown is severe enough to close positions.

        Phase 3.4 (L-04 and the audit's fail-open finding). Two fixes:

        * Drawdown was measured against a hardcoded INITIAL_ACCOUNT_BALANCE of
          150.0 -- permanently 33% on a $100 account, unreachable on a $500 one.
          It now comes from the persisted equity high-water mark.
        * The bare `except: return False` made a RISK CONTROL FAIL OPEN: any
          error at all meant "no drawdown problem, carry on". It now fails
          CLOSED -- an error is treated as a drawdown breach and alerted.
        """
        config = self.config
        try:
            account = self.risk_manager.refresh_account()
            equity = float(getattr(account, "equity", account.balance))
            drawdown = self.risk_manager.state.drawdown_fraction(equity)
            return drawdown >= config.EMERGENCY_CLOSE_DRAWDOWN_FRACTION
        except Exception as exc:
            logger.error(
                "Drawdown check FAILED (%s). Failing closed: treating this as a "
                "drawdown breach so positions are protected rather than left "
                "unmonitored.", exc
            )
            return True

    def _check_max_total_positions(self, symbol=None):
        """True when the total number of open positions exceeds the cap.

        Phase 5.4 (audit M-02). This was called ``_check_correlation_conflict``
        and it measured **no correlation whatsoever**: it split positions into
        "same symbol" and "different symbol" and then added the two counts back
        together, which is just the total position count. `CORRELATION_THRESHOLD`
        was never read by anything.

        Renamed to say what it does. A mislabeled risk control is worse than no
        control: it creates the belief that correlation is being managed.

        Real correlation management -- measuring against DXY or XAGUSD -- is a
        genuine feature, not a rename, and belongs after Phase 9 shows the
        strategy is worth extending.
        """
        config = self.config
        return len(self.get_open_positions()) > config.MAX_TOTAL_POSITIONS

    # Scaling (evaluate_position_scaling, scale_up_position, scale_down_position,
    # close_position_partial) deleted: it had no caller in the live loop. See
    # docs/SECURITY-DECISIONS.md, Phase 12 follow-up.

if __name__ == "__main__":
    print("Testing trade executor...")
    print("Trade executor functions defined. Connect to MT5 to test.")

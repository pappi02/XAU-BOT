"""One safe way to ask the broker "what positions are open" (Phase 12 follow-up).

Phase 6.4 (audit H-04) fixed this once, inside ``TradeExecutor.get_open_positions``:
``positions_get()`` returns ``None`` both when there are no positions and when
the terminal is disconnected, and collapsing both to ``[]`` makes a dropped
connection look like a flat account -- which invites opening a second position
on top of ones the bot can no longer see.

An audit pass found that fix had not propagated: ``RiskManager.open_risk_fraction``
and ``RiskManager.current_open_positions_count`` called ``mt5.positions_get()``
directly and made the exact same "None means empty" mistake, in the portfolio
risk gate and the position-count gate respectively. Both are reachable only
after ``TradeExecutor.enter_trade`` has already asked the safe way earlier in
the same call, so the live bot was not exposed in practice -- but a second,
unsafe implementation of the same question is exactly the kind of duplication
that produced the original bug. This module is the one place that question is
answered, so it cannot happen a third time.
"""


class BrokerQueryFailed(RuntimeError):
    """Raised when a broker query fails and its answer is therefore UNKNOWN.

    "No positions" and "I could not find out" must never be the same value.
    """


def terminal_is_connected(mt5):
    """True when the terminal answers a trivial query."""
    try:
        info = mt5.terminal_info()
    except Exception:
        return False
    if info is None:
        return False
    return bool(getattr(info, "connected", True))


def positions_or_raise(mt5, symbol=None):
    """Open positions, or raise if the answer cannot be determined.

    Returns:
        list: the open positions (possibly empty).

    Raises:
        BrokerQueryFailed: the terminal could not be queried. Callers must
            treat this as "unknown" and refuse to trade, not as "none".
    """
    try:
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    except Exception as exc:
        raise BrokerQueryFailed(
            "positions_get(%s) raised: %s" % (symbol or "all", exc)
        ) from exc

    if positions is None:
        # Disambiguate using the terminal's own view. If the terminal is
        # reachable and simply has nothing open, that is a real empty list.
        if terminal_is_connected(mt5):
            return []
        raise BrokerQueryFailed(
            "positions_get(%s) returned None and the terminal is not "
            "connected -- position state is UNKNOWN" % (symbol or "all")
        )
    return list(positions)

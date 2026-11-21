"""Validate the configured symbol against the broker (Phase 9 follow-up).

`config.SYMBOL` was `'XAUUSDm'` -- an Exness-style micro suffix that does not
exist on a MetaQuotes demo account. The bot connected, failed the symbol
lookup, logged `Symbol 'XAUUSDm' not found` and exited. **It could not have
traded at all**, and the message gave no clue what the right name was.

A symbol name is a broker fact, like contract size (Phase 2.1). The difference
is that we cannot simply read it: only a human knows which of `XAUUSD`,
`XAUUSD.m`, `GOLD` or `XAUUSD_i` is the instrument they mean to trade.

So this module deliberately does **not** auto-select. Silently picking a
symbol that merely looks like gold is how a bot ends up trading a CFD on
mining shares, or a 1-oz contract when the account was sized for 100. It
validates the configured name, and when that fails it makes the fix obvious by
listing what the broker actually offers.
"""

import logging

logger = logging.getLogger("xau_bot")

# Substrings that suggest a gold instrument, for the diagnostic listing only.
GOLD_HINTS = ("XAU", "GOLD")


class SymbolNotAvailable(RuntimeError):
    """The configured symbol is not tradeable on this account."""


def candidate_symbols(mt5, hints=GOLD_HINTS, limit=25):
    """Symbols whose names suggest gold. Diagnostic only -- never auto-selected."""
    try:
        symbols = mt5.symbols_get()
    except Exception as exc:
        logger.error("Could not list broker symbols: %s", exc)
        return []

    if not symbols:
        return []

    found = []
    for symbol in symbols:
        name = str(getattr(symbol, "name", ""))
        if any(hint in name.upper() for hint in hints):
            found.append(name)
        if len(found) >= limit:
            break
    return sorted(found)


def resolve_symbol(mt5, symbol, require_tradeable=True):
    """Confirm ``symbol`` exists and is selectable. Returns its spec.

    Args:
        require_tradeable: reject a symbol with ``trade_mode=0`` (disabled
            for trading on this account). Pass ``False`` for a read-only
            caller that only fetches price history and will never place an
            order -- scripts/fetch_historical_data.py's whole purpose is
            historical bars for offline backtesting, and several real
            instruments (e.g. this demo account's index CFDs) are readable
            but not enabled for trading, which is irrelevant to reading
            their history.

    Raises:
        SymbolNotAvailable: with the broker's gold-like symbols listed, so the
            fix is a one-line config change rather than a hunt through Market
            Watch.
    """
    info = mt5.symbol_info(symbol)

    if info is None:
        # Not in Market Watch yet is not the same as not existing.
        try:
            selected = mt5.symbol_select(symbol, True)
        except Exception:
            selected = False
        if selected:
            info = mt5.symbol_info(symbol)

    if info is None:
        candidates = candidate_symbols(mt5)
        hint = ("The broker does offer: %s" % ", ".join(candidates)
                if candidates else
                "No gold-like symbols were found at all -- check that the "
                "terminal is logged in and Market Watch is populated.")
        raise SymbolNotAvailable(
            "Symbol %r is not available on this account. %s\n"
            "Set config.SYMBOL to the exact name, including any broker suffix."
            % (symbol, hint)
        )

    if not getattr(info, "visible", True):
        if not mt5.symbol_select(symbol, True):
            raise SymbolNotAvailable(
                "Symbol %r exists but could not be added to Market Watch. It "
                "may not be enabled for this account type." % symbol)
        info = mt5.symbol_info(symbol)

    if require_tradeable and not getattr(info, "trade_mode", 1):
        raise SymbolNotAvailable(
            "Symbol %r is present but disabled for trading (trade_mode=0)."
            % symbol)

    logger.info("Symbol %s confirmed available.", symbol)
    return info

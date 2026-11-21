"""Read-only check of which candidate symbols exist on this broker, and how
much M5/H1 history each retains. Places no orders.

    python scripts/probe_symbols.py EURUSD US30 US500 BTCUSD ...
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(
    __import__("os").path.abspath(__file__))))

import MetaTrader5 as mt5

import config
from data.connect_mt5 import connect_mt5, disconnect_mt5


def bars_available(symbol, timeframe):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, 99999)
    if rates is None or len(rates) == 0:
        return None, None
    import pandas as pd
    idx = pd.to_datetime(rates["time"], unit="s")
    return len(rates), (idx[0], idx[-1])


def main():
    candidates = sys.argv[1:] or ["EURUSD", "US30", "US30Cash", "US500", "US500Cash",
                                  "BTCUSD", "SPX500", "NAS100", "DJ30", "USTEC"]
    if not connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD, config.MT5_SERVER,
                       config.MT5_TIMEOUT_MS):
        print("Could not connect.")
        return 1
    try:
        # List everything so near-miss names (e.g. a Cash/.m suffix) are visible.
        all_symbols = [s.name for s in (mt5.symbols_get() or [])]
        print("Broker reports %d symbols total.\n" % len(all_symbols))

        for wanted in candidates:
            matches = [s for s in all_symbols if wanted.upper() in s.upper()]
            if not matches:
                print("%-12s NOT FOUND (no name contains it)" % wanted)
                continue
            for name in matches[:5]:
                mt5.symbol_select(name, True)
                info = mt5.symbol_info(name)
                if info is None:
                    print("%-12s -> %-14s symbol_info() None" % (wanted, name))
                    continue
                m5_count, m5_span = bars_available(name, mt5.TIMEFRAME_M5)
                h1_count, h1_span = bars_available(name, mt5.TIMEFRAME_H1)
                print("%-12s -> %-14s digits=%d point=%g contract=%g spread=%s" % (
                    wanted, name, info.digits, info.point, info.trade_contract_size,
                    info.spread))
                print("             M5: %s bars %s" % (
                    m5_count, ("(%s -> %s)" % m5_span if m5_span else "")))
                print("             H1: %s bars %s" % (
                    h1_count, ("(%s -> %s)" % h1_span if h1_span else "")))
        return 0
    finally:
        disconnect_mt5()


if __name__ == "__main__":
    sys.exit(main())

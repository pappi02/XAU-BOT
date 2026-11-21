"""One-shot READ-ONLY historical data fetch, for Gate C (Phase 9.4).

Authorized by explicit user instruction ("do backtest with the demo acc
credentials"). This script does exactly three things:

  1. Connect to MT5 (data.connect_mt5.connect_mt5 -- which refuses a live
     account unless ALLOW_LIVE=true, and that is not set).
  2. Page backward through closed M5 candles via copy_rates_from_pos
     (read-only), chunked because this terminal caps a single call at 99,999
     bars (measured: 99999 succeeds, 100000 returns "Invalid params").
  3. Save them to a local CSV and disconnect.

It calls NOTHING related to orders, positions, or trading: no order_send, no
TradeExecutor, no RiskManager. Every subsequent backtest run reads the saved
CSV and never touches the broker again.

Run:  env/Scripts/python.exe scripts/fetch_historical_data.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import MetaTrader5 as mt5

import config
from data.connect_mt5 import connect_mt5, disconnect_mt5, AccountIdentityError
from data.symbol_resolver import resolve_symbol, SymbolNotAvailable

# Timeframe and symbol can be overridden on the command line
# (e.g. `--timeframe H1 --symbol US500`) to fetch different data without
# touching config.TIMEFRAME/SYMBOL, which the live bot and several other
# modules (BarGate, the schema) key off of. Exploratory data only.
TIMEFRAME = (sys.argv[sys.argv.index("--timeframe") + 1]
            if "--timeframe" in sys.argv else config.TIMEFRAME).upper()
SYMBOL = (sys.argv[sys.argv.index("--symbol") + 1]
         if "--symbol" in sys.argv else config.SYMBOL).upper()

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "historical")
OUT_PATH = os.path.join(OUT_DIR, "%s_%s.csv" % (SYMBOL, TIMEFRAME))
SPEC_PATH = os.path.join(OUT_DIR, "%s_spec.json" % SYMBOL)

# Real broker fields worth capturing for the backtest cost model / sizing,
# so it uses what the broker actually reports rather than a guessed default.
SPEC_FIELDS = [
    "digits", "point", "trade_contract_size", "trade_tick_value",
    "trade_tick_size", "volume_min", "volume_step", "volume_max",
    "trade_stops_level", "trade_freeze_level", "filling_mode", "spread",
    "swap_long", "swap_short", "swap_mode",
]

CHUNK_SIZE = 99_999          # measured terminal cap for one call
MAX_CHUNKS = 12              # generous ceiling; stops earlier at history's edge


def fetch_all_closed_bars(symbol, timeframe):
    """Page backward from the most recent CLOSED bar to the earliest available.

    The forming (still-open) bar is dropped once, up front, by starting at
    position 1 instead of 0 -- every subsequent chunk is strictly older bars,
    so no further forming-bar handling is needed.
    """
    frames = []
    start_pos = 1   # skip the still-forming bar
    for chunk_num in range(1, MAX_CHUNKS + 1):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, start_pos, CHUNK_SIZE)
        if rates is None or len(rates) == 0:
            print("  chunk %d: no more data (start_pos=%d, error=%s)"
                  % (chunk_num, start_pos, mt5.last_error()))
            break

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        frames.append(df)
        print("  chunk %d: %d bars, %s -> %s"
              % (chunk_num, len(df),
                 df["time"].iloc[0], df["time"].iloc[-1]))

        if len(rates) < CHUNK_SIZE:
            print("  reached the earliest history this server retains.")
            break
        start_pos += CHUNK_SIZE

    if not frames:
        return pd.DataFrame()

    full = pd.concat(frames, ignore_index=True)
    full = full.drop_duplicates(subset="time").sort_values("time")
    full = full.set_index("time")
    return full


def main():
    print("=" * 70)
    print("READ-ONLY historical data fetch (chunked, up to %d chunks)"
          % MAX_CHUNKS)
    print("Symbol: %s | Timeframe: %s" % (SYMBOL, TIMEFRAME))
    print("=" * 70)

    try:
        if not connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD,
                           config.MT5_SERVER, config.MT5_TIMEOUT_MS):
            print("Failed to connect to MT5.")
            return 1
    except AccountIdentityError as exc:
        print("Refusing to connect: %s" % exc)
        return 1

    try:
        account = mt5.account_info()
        print("Connected: account %s on %s (trade_mode=%s -- 0 is DEMO)"
              % (account.login, account.server, account.trade_mode))

        try:
            # This script only reads price history (see the module docstring's
            # three-step guarantee) -- whether the symbol is enabled for
            # trading on this account is irrelevant to reading its history.
            info = resolve_symbol(mt5, SYMBOL, require_tradeable=False)
        except SymbolNotAvailable as exc:
            print("Symbol problem: %s" % exc)
            return 1

        spec = {field: getattr(info, field, None) for field in SPEC_FIELDS}
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(SPEC_PATH, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, indent=2)
        print("Real broker symbol spec: %s" % spec)
        print("Saved to %s" % SPEC_PATH)

        timeframe_map = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        tf = timeframe_map.get(TIMEFRAME, mt5.TIMEFRAME_M5)
        if TIMEFRAME not in timeframe_map:
            print("Unknown timeframe %r -- known: %s" % (TIMEFRAME, sorted(timeframe_map)))
            return 1

        print("Fetching candles (read-only copy_rates_from_pos, chunked)...")
        df = fetch_all_closed_bars(SYMBOL, tf)

        if df is None or df.empty:
            print("No data returned.")
            return 1

        print("\nTotal: %d closed bars: %s -> %s"
              % (len(df), df.index[0], df.index[-1]))
        span_days = (df.index[-1] - df.index[0]).days
        print("Span: %.1f days (%.2f years)" % (span_days, span_days / 365.25))

        os.makedirs(OUT_DIR, exist_ok=True)
        df.to_csv(OUT_PATH)
        print("Saved to %s" % OUT_PATH)
        return 0

    finally:
        disconnect_mt5()
        print("Disconnected. No trading calls were made.")


if __name__ == "__main__":
    sys.exit(main())

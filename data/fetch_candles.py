import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import logging
import time

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ✅ Mapping for string-based timeframes
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,
    "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4,
    "M5": mt5.TIMEFRAME_M5,
    "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10,
    "M12": mt5.TIMEFRAME_M12,
    "M15": mt5.TIMEFRAME_M15,
    "M20": mt5.TIMEFRAME_M20,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2,
    "H3": mt5.TIMEFRAME_H3,
    "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6,
    "H8": mt5.TIMEFRAME_H8,
    "H12": mt5.TIMEFRAME_H12,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}



def ensure_mt5_initialized():
    """
    Ensure MT5 terminal is initialized before making API calls.
    Auto-initializes if not already connected.
    """
    try:
        if not mt5.terminal_info():
            logger.warning("⚠️ MT5 not initialized. Attempting to initialize automatically...")
            if not mt5.initialize():
                err = mt5.last_error()
                logger.error(f"❌ Failed to initialize MT5 automatically. Error: {err}")
                return False
            logger.info("✅ MT5 initialized successfully as fallback.")
        return True
    except Exception as e:
        logger.exception(f"❌ Exception during MT5 initialization: {e}")
        return False




def _default_clock():
    import config
    from utils.market_time import BrokerClock
    return BrokerClock.from_config(config)


def get_candles(symbol="XAUUSD", timeframe=mt5.TIMEFRAME_M5, num_candles=500,
                max_retries=3, drop_forming_bar=True, clock=None):
    """Fetch candles from MT5. CLOSED BARS ONLY by default.

    Phase 4.2 (audit C-02, M-12, H-09). Two fixes:

    * ``copy_rates_range`` was called with a locally-computed date window
      (``datetime.now()`` minus ``num_candles * 5`` minutes -- which silently
      assumed an M5 timeframe, and mixed local time with broker time). It is now
      ``copy_rates_from_pos``, which is count-based and timezone-free.

    * The last row returned by MT5 is the **still-forming** bar. With a 60s loop
      on an M5 timeframe the same forming bar was evaluated ~5 times, with
      indicator values that mutate under it -- so one bar could produce several
      contradictory signals and several entries. ``drop_forming_bar`` removes
      it, so every decision is made on a bar that will never change again.

      Pass ``drop_forming_bar=False`` only for display (charts, dashboards),
      never for a trading decision.
    """
    try:
        # ✅ Auto initialize MT5 if not connected
        if not mt5.initialize():
            logger.warning("⚠️ MT5 was not initialized. Attempting auto-initialize...")
            if not mt5.initialize():
                logger.error("❌ Failed to auto-initialize MT5.")
                return pd.DataFrame()

        # Ensure account is logged in
        account_info = mt5.account_info()
        if account_info is None:
            logger.error("❌ MT5 account not logged in. Please connect to an account first.")
            return pd.DataFrame()

        # Convert string timeframe to MT5 constant if needed
        if isinstance(timeframe, str):
            timeframe = timeframe.upper().strip()
            if timeframe in TIMEFRAME_MAP:
                timeframe = TIMEFRAME_MAP[timeframe]
            else:
                logger.warning(f"⚠️ Unknown timeframe '{timeframe}', defaulting to M1.")
                timeframe = mt5.TIMEFRAME_M1

        # Validate symbol
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"❌ Symbol '{symbol}' not found in MT5.")
            return pd.DataFrame()

        if not symbol_info.visible:
            logger.info(f"ℹ️ Symbol '{symbol}' not visible in Market Watch. Attempting to add it...")
            if not mt5.symbol_select(symbol, True):
                logger.error(f"❌ Failed to add symbol '{symbol}' to Market Watch.")
                return pd.DataFrame()
            logger.info(f"✅ Successfully added symbol '{symbol}' to Market Watch.")

        # Retry fetching data
        for attempt in range(1, max_retries + 1):
            try:
                # Count-based and timezone-free: ask for N bars ending at the
                # current one, rather than guessing a date window.
                fetch_count = num_candles + (1 if drop_forming_bar else 0)
                rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, fetch_count)

                if rates is not None and len(rates) > 0:
                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"], unit="s")
                    df.set_index("time", inplace=True)
                    df = df.sort_index()
                    # MT5 bar times are broker SERVER time. Convert to real
                    # UTC so staleness, sessions and the weekend close are
                    # computed against the real clock (utils/market_time.py).
                    df.index = (clock or _default_clock()).index_to_utc(df.index)

                    if drop_forming_bar and len(df) > 1:
                        forming = df.index[-1]
                        df = df.iloc[:-1]
                        logger.debug("Dropped forming bar at %s; newest closed "
                                     "bar is %s", forming, df.index[-1])

                    logger.info("Fetched %d closed candles for %s (newest %s).",
                                len(df), symbol,
                                df.index[-1] if len(df) else "n/a")
                    return df

                logger.warning(f"⚠️ Attempt {attempt}/{max_retries}: No data returned. Error: {mt5.last_error()}")
                time.sleep(2)

            except Exception as inner_e:
                logger.warning(f"⚠️ Attempt {attempt}/{max_retries} failed: {inner_e}. Retrying...")
                time.sleep(2)

        logger.error(f"❌ Failed to fetch candles for {symbol} after {max_retries} attempts.")
        return pd.DataFrame()

    except Exception as e:
        logger.exception(f"❌ Unexpected error fetching candles: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    from data.connect_mt5 import connect_mt5, disconnect_mt5

    if connect_mt5():
        candles = get_candles(symbol="XAUUSDm", timeframe="H1", num_candles=100)
        if not candles.empty:
            print("✅ Sample Data:")
            print(candles.head())
            print(f"\n📊 Columns: {list(candles.columns)}")
            print(f"📅 Range: {candles.index[0]} → {candles.index[-1]}")
        else:
            print("⚠️ No data fetched.")
        disconnect_mt5()
    else:
        print("❌ Failed to connect to MT5.")

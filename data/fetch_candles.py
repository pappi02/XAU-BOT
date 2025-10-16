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




def get_candles(symbol="XAUUSDm", timeframe=mt5.TIMEFRAME_M5, num_candles=500, max_retries=3):
    """
    Fetch historical candlestick data from MetaTrader 5 with robust error handling and retries.
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
                now = datetime.now()
                delta = timedelta(minutes=num_candles * 5)
                from_date = now - delta

                rates = mt5.copy_rates_range(symbol, timeframe, from_date, now)
                if rates is not None and len(rates) > 0:
                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"], unit="s")
                    df.set_index("time", inplace=True)
                    df = df.sort_index()
                    logger.info(f"✅ Successfully fetched {len(df)} candles for {symbol}.")
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

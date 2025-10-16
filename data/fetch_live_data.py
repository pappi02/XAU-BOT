# fetch_live_data.py - Fetch live market data for XAU/USDm

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time

def get_live_price(symbol="XAUUSDm"):
    """
    Get the current live price for a symbol.

    Args:
        symbol (str): Trading symbol (default: "XAUUSDm")

    Returns:
        dict: Current bid/ask prices or None if failed
    """
    # Import the connection function for consistent initialization
    from data.connect_mt5 import connect_mt5, disconnect_mt5

    if not connect_mt5():
        print("❌ MT5 connection failed")
        return None

    try:
        # Ensure symbol is selected
        if not mt5.symbol_select(symbol, True):
            print(f"❌ Failed to select symbol '{symbol}'. MT5 error: {mt5.last_error()}")
            return None

        # Get current tick data
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print(f"❌ Failed to get tick data for {symbol}. MT5 error: {mt5.last_error()}")
            return None

        return {
            'symbol': symbol,
            'bid': tick.bid,
            'ask': tick.ask,
            'spread': tick.ask - tick.bid,
            'timestamp': datetime.fromtimestamp(tick.time)
        }

    except Exception as e:
        print(f"❌ Error getting live price: {e}. MT5 error: {mt5.last_error()}")
        return None
    finally:
        disconnect_mt5()

def get_live_ohlc(symbol="XAUUSDm", timeframe=mt5.TIMEFRAME_M1, bars=1):
    """
    Get live OHLC data for a symbol.

    Args:
        symbol (str): Trading symbol (default: "XAUUSDm")
        timeframe: MT5 timeframe constant (default: M1)
        bars (int): Number of bars to retrieve (default: 1)

    Returns:
        pd.DataFrame: OHLC data or None if failed
    """
    # Import the connection function for consistent initialization
    from data.connect_mt5 import connect_mt5, disconnect_mt5

    if not connect_mt5():
        print("❌ MT5 connection failed")
        return None

    try:
        # Ensure symbol is selected
        if not mt5.symbol_select(symbol, True):
            print(f"❌ Failed to select symbol '{symbol}'. MT5 error: {mt5.last_error()}")
            return None

        # Get rates using copy_rates_range for better reliability
        from_date = datetime.now() - timedelta(minutes=bars * (timeframe // 60 if timeframe >= 60 else 1))
        to_date = datetime.now()

        rates = mt5.copy_rates_range(symbol, timeframe, from_date, to_date)
        if rates is None or len(rates) == 0:
            print(f"❌ Failed to get rates for {symbol}. MT5 error: {mt5.last_error()}")
            return None

        # Sort by time and get the most recent bars
        rates = sorted(rates, key=lambda x: x[0], reverse=True)[:bars]
        rates = sorted(rates, key=lambda x: x[0])

        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)

        return df[['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']]

    except Exception as e:
        print(f"❌ Error getting live OHLC: {e}. MT5 error: {mt5.last_error()}")
        return None
    finally:
        disconnect_mt5()

def monitor_price_changes(symbol="XAUUSDm", interval_seconds=5, duration_minutes=1):
    """
    Monitor price changes over time.

    Args:
        symbol (str): Trading symbol
        interval_seconds (int): Check interval in seconds
        duration_minutes (int): Monitoring duration in minutes
    """
    print(f"📊 Monitoring {symbol} price changes...")

    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration_minutes)
    last_price = None

    while datetime.now() < end_time:
        price_data = get_live_price(symbol)
        if price_data:
            current_price = price_data['bid']

            if last_price is not None:
                change = current_price - last_price
                change_pct = (change / last_price) * 100
                direction = "📈" if change > 0 else "📉" if change < 0 else "➡️"

                print(f"{price_data['timestamp'].strftime('%H:%M:%S')} | "
                      f"Bid: {current_price:.2f} | "
                      f"{direction} {change:+.2f} ({change_pct:+.2f}%)")

            last_price = current_price

        time.sleep(interval_seconds)

    print("✅ Price monitoring completed")

if __name__ == "__main__":
    # Example usage
    print("🔄 Testing live data functions...")

    # Get current price
    price = get_live_price()
    if price:
        print(f"💰 Current XAU/USD Price: Bid={price['bid']:.2f}, Ask={price['ask']:.2f}")

    # Get recent OHLC
    ohlc = get_live_ohlc()
    if ohlc is not None:
        print("📊 Recent OHLC Data:")
        print(ohlc.tail())

    # Monitor price for 30 seconds
    monitor_price_changes(duration_minutes=0.5)

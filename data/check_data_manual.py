import MetaTrader5 as mt5
from datetime import datetime

symbol = "XAUUSDm"  # adjust to your broker's exact symbol
timeframe = mt5.TIMEFRAME_M15  # 15-min candles

if not mt5.initialize():
    print("Initialization failed")
    quit()

# Make sure symbol is visible and ready
if not mt5.symbol_select(symbol, True):
    print(f"Failed to select symbol {symbol}")
    mt5.shutdown()
    quit()

# Try fetching 10 candles
rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 10)

if rates is None:
    print("❌ Failed to fetch data. Check symbol name or connection.")
else:
    print(f"✅ Successfully fetched {len(rates)} candles for {symbol}")
    print(rates)

mt5.shutdown()

# SCALPING INDICATORS - QUICK START EXAMPLE

## 5-Minute Quick Start

### 1. Basic Signal Generation
```python
from signal_generation.signal_master import SignalMaster
import pandas as pd

# Load your OHLC data
data = pd.read_csv('xauusd_m5.csv', parse_dates=['timestamp'])
data = data.set_index('timestamp')

# Initialize signal generator with scalping optimizations
master = SignalMaster(sensitivity='aggressive', primary_timeframe='M5', mtf_enabled=True)

# Generate signal (includes all 3 scalping setups automatically)
signal = master.generate_signal(data)

# Extract scalping setup information
scalping = signal['components']['scalping_setups']

print(f"🎯 SCALPING SIGNAL")
print(f"Signal: {'BUY ✅' if scalping['signal'] == 1 else 'SELL ❌' if scalping['signal'] == -1 else 'NEUTRAL'}")
print(f"Confidence: {scalping['confidence']:.1f}%")
print(f"Setup Used: {scalping['best_setup']}")
print(f"Entry Price: {scalping['entry_zone']:.4f}")
print(f"Stop Loss: {scalping['stop_loss']:.4f}")
print(f"Take Profit: {scalping['take_profit']:.4f}")
print(f"Risk-Reward: {abs(scalping['entry_zone'] - scalping['take_profit']) / abs(scalping['entry_zone'] - scalping['stop_loss']):.2f}:1")
```

**Output Example:**
```
🎯 SCALPING SIGNAL
Signal: BUY ✅
Confidence: 78.5%
Setup Used: EMA_VWAP
Entry Price: 2650.45
Stop Loss: 2648.90
Take Profit: 2654.08
Risk-Reward: 1.50:1
```

### 2. Individual Setup Testing
```python
from signal_generation.scalping_setups import EmaVwapSetup, MacdRsiReversalSetup, SupertrendAtrSetup

# Test each setup individually
setups = {
    'EMA+VWAP': EmaVwapSetup(),
    'MACD+RSI': MacdRsiReversalSetup(),
    'Supertrend': SupertrendAtrSetup()
}

print("📊 INDIVIDUAL SETUP RESULTS")
print("=" * 80)

for name, setup in setups.items():
    result = setup.analyze(data)
    signal_text = '🟢 BUY' if result['signal'] == 1 else '🔴 SELL' if result['signal'] == -1 else '⚪ NO TRADE'
    
    print(f"\n{name} Setup:")
    print(f"  Signal: {signal_text}")
    print(f"  Confidence: {result['confidence']:.1f}%")
    print(f"  Condition: {result['condition']}")
    print(f"  Entry: {result['entry_zone']:.4f} | SL: {result['stop_loss']:.4f} | TP: {result['take_profit']:.4f}")
```

**Output Example:**
```
📊 INDIVIDUAL SETUP RESULTS
================================================================================

EMA+VWAP Setup:
  Signal: 🟢 BUY
  Confidence: 85.0%
  Condition: Bullish EMA+VWAP: Stack aligned, price above VWAP, near VWAP support, volume spike, strong momentum shift
  Entry: 2650.45 | SL: 2648.90 | TP: 2654.08

MACD+RSI Setup:
  Signal: ⚪ NO TRADE
  Confidence: 0.0%
  Condition: No reversal setup detected
  Entry: 2650.60 | SL: 0.00 | TP: 0.00

Supertrend Setup:
  Signal: 🟢 BUY
  Confidence: 68.0%
  Condition: Fresh Bullish Flip: Uptrend confirmed, strong trend, volume spike, near support line
  Entry: 2650.55 | SL: 2648.85 | TP: 2654.12
```

### 3. Complete Trading Logic
```python
from signal_generation.signal_master import SignalMaster
import MetaTrader5 as mt5

# Initialize
master = SignalMaster(sensitivity='aggressive', primary_timeframe='M5')

# Get fresh data and generate signal
def execute_trade(symbol='XAUUSD', timeframe='M5'):
    # Fetch data
    data = fetch_ohlc_data(symbol, timeframe, bars=100)
    
    # Generate signal
    signal = master.generate_signal(data)
    
    # Extract trading parameters
    scalping = signal['components']['scalping_setups']
    direction = scalping['signal']
    confidence = scalping['confidence']
    
    # Trading rules
    if confidence < 55:
        print(f"⚠️  Low confidence ({confidence:.1f}%) - skipping trade")
        return None
    
    if direction == 1:  # BUY
        order_type = mt5.ORDER_TYPE_BUY
        order_label = "SCALP_LONG"
    elif direction == -1:  # SELL
        order_type = mt5.ORDER_TYPE_SELL
        order_label = "SCALP_SHORT"
    else:  # NO TRADE
        print("⚫ No clear signal - waiting")
        return None
    
    # Place trade
    entry = scalping['entry_zone']
    sl = scalping['stop_loss']
    tp = scalping['take_profit']
    
    trade = {
        'symbol': symbol,
        'type': order_label,
        'entry': entry,
        'stop_loss': sl,
        'take_profit': tp,
        'setup': scalping['best_setup'],
        'confidence': confidence
    }
    
    print(f"✅ Trade Execution:")
    print(f"   Type: {order_label}")
    print(f"   Entry: {entry:.4f}")
    print(f"   SL: {sl:.4f}")
    print(f"   TP: {tp:.4f}")
    print(f"   Risk: {abs(entry - sl) * 100:.1f} pips")
    print(f"   Setup: {scalping['best_setup']} ({confidence:.1f}% confidence)")
    
    return trade

# Execute
trade = execute_trade()
```

## Configuration Customization

### Adjust for Your Timeframe
```python
from indicators.ema import calculate_ema_stack
from signal_generation.scalping_setups import EmaVwapSetup, MacdRsiReversalSetup, SupertrendAtrSetup

# For M1/M3 (very fast scalping):
ema_vwap_fast = EmaVwapSetup(
    ema_periods=[5, 10, 20],              # Much faster
    vwap_distance_threshold=0.2           # Tighter VWAP requirement
)

macd_rsi_fast = MacdRsiReversalSetup(
    rsi_period=5,                          # Much faster RSI
    macd_fast=5,
    macd_slow=13,
    rsi_oversold=25,                       # More extreme levels
    rsi_overbought=75
)

supertrend_fast = SupertrendAtrSetup(
    supertrend_period=7,                   # Faster trend detection
    supertrend_multiplier=2.5,             # Tighter bands
    atr_multiplier=1.0                     # Tighter stops
)

# For H1/H4 (swing trading):
ema_vwap_swing = EmaVwapSetup(
    ema_periods=[12, 26, 50],              # Standard periods
    vwap_distance_threshold=1.0            # Looser VWAP requirement
)

macd_rsi_swing = MacdRsiReversalSetup(
    rsi_period=14,                         # Standard RSI
    macd_fast=12,
    macd_slow=26,
    rsi_oversold=30,
    rsi_overbought=70
)
```

### Adjust Weights for Your Strategy
```python
from signal_generation.scalping_setups import ScalpingSetupsAnalyzer

# Trend-following strategy (prefer Supertrend)
trend_weights = {
    'ema_vwap': 0.25,
    'macd_rsi': 0.20,
    'supertrend': 0.55
}
analyzer_trend = ScalpingSetupsAnalyzer(weights=trend_weights)

# Reversal strategy (prefer MACD+RSI)
reversal_weights = {
    'ema_vwap': 0.20,
    'macd_rsi': 0.60,
    'supertrend': 0.20
}
analyzer_reversal = ScalpingSetupsAnalyzer(weights=reversal_weights)

# Balanced approach (default)
analyzer_balanced = ScalpingSetupsAnalyzer()  # Uses 0.35/0.30/0.35 by default
```

## Performance Monitoring

### Track Your Trades
```python
import pandas as pd

trades = []

while trading:
    signal = master.generate_signal(data)
    scalping = signal['components']['scalping_setups']
    
    if scalping['signal'] != 0:
        trade = {
            'timestamp': pd.Timestamp.now(),
            'setup': scalping['best_setup'],
            'direction': 'LONG' if scalping['signal'] == 1 else 'SHORT',
            'confidence': scalping['confidence'],
            'entry': scalping['entry_zone'],
            'stop_loss': scalping['stop_loss'],
            'take_profit': scalping['take_profit'],
            'status': 'OPEN'
        }
        
        trades.append(trade)

# Analyze results
df_trades = pd.DataFrame(trades)
print(f"Total Trades: {len(df_trades)}")
print(f"Win Rate: {(df_trades['result'] == 'WIN').sum() / len(df_trades) * 100:.1f}%")
print(f"Avg Confidence: {df_trades['confidence'].mean():.1f}%")
print(f"Best Setup: {df_trades['setup'].value_counts().index[0]}")
```

## Troubleshooting

### Problem: Import Errors
```python
# Make sure you're in the project root directory
import sys
sys.path.insert(0, '/path/to/XAU-BOT')

from indicators import calculate_vwap
from signal_generation.scalping_setups import ScalpingSetupsAnalyzer
```

### Problem: No Signals Generated
```python
# Check data quality
print(f"Data shape: {data.shape}")
print(f"Data columns: {data.columns.tolist()}")
print(f"Missing values: {data.isnull().sum()}")

# Verify data types
print(data.dtypes)

# Ensure required columns exist
required = ['open', 'high', 'low', 'close', 'volume']
if not all(col in data.columns for col in required):
    print("❌ Missing required columns!")
```

### Problem: Confidence Always Low
```python
# Check volume data
print(f"Average volume: {data['volume'].mean():.0f}")
print(f"Recent volume: {data['volume'].iloc[-1]:.0f}")

# Check for volume spikes
print(f"Max volume: {data['volume'].max():.0f}")
print(f"Min volume: {data['volume'].min():.0f}")

# Adjust volume spike threshold if needed
from signal_generation.scalping_setups import EmaVwapSetup
ema_vwap = EmaVwapSetup(vwap_distance_threshold=1.0)  # More lenient
```

## Next Steps

1. **Copy this example to your notebook:**
   ```bash
   cp SCALPING_QUICK_START.py /path/to/your/project
   ```

2. **Run with your own data:**
   ```python
   data = load_your_data()
   signal = master.generate_signal(data)
   print_signal(signal)
   ```

3. **Backtest your strategy:**
   ```bash
   python backtest_run.py --symbol XAUUSD --timeframe M5 --bars 2000
   ```

4. **Optimize parameters:**
   - Adjust EMA periods
   - Test different weights
   - Compare setup performance

5. **Go live:**
   - Paper trade first
   - Monitor for 1-2 days
   - Deploy with full position size

## Additional Resources

- **Full Guide**: See `SCALPING_SETUPS_GUIDE.md`
- **Implementation Status**: See `SCALPING_IMPLEMENTATION_STATUS.md`
- **Executive Summary**: See `SCALPING_SUMMARY.md`
- **Code Reference**: Check docstrings in indicator files

---

**Ready to trade!** 🚀


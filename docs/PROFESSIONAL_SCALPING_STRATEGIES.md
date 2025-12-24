# Professional Scalping Strategies - Integration Guide

## Overview

Your trading bot now includes **5 professional expert-level scalping strategies**, each optimized for different market conditions. The bot intelligently switches between strategies based on real-time market analysis.

## 📊 Available Strategies

### 1. **Breakout Scalping** (`breakout_scalping.py`)
**Best for:** High volatility with clear technical levels

**How it works:**
- Identifies key support/resistance levels from recent price action
- Waits for price to break above resistance or below support
- Confirms breakout with volume spike (1.5x average)
- Uses CCI, MACD, and Parabolic SAR for confluence
- Enters immediately after confirmed breakout

**Entry Criteria:**
- ✅ Price breaks above resistance (bullish) or below support (bearish)
- ✅ Volume confirms with 1.5x spike
- ✅ CCI extreme levels (>100 bullish, <-100 bearish)
- ✅ MACD histogram confirms direction
- ✅ Parabolic SAR aligns with breakout

**Risk Management:**
- Stop Loss: Just below/above breakout level (5-15 pips)
- Take Profit: 1:1.5 to 1:2 risk-reward ratio
- Position Size: 1-2% risk per trade

**Market Conditions:**
- High volatility periods
- London/NY session overlaps
- Clear support/resistance levels

---

### 2. **Momentum Scalping** (`momentum_scalping.py`)
**Best for:** Strong directional moves with momentum

**How it works:**
- Detects strong momentum using RSI (7-period for scalping)
- Confirms with MACD histogram and Stochastic
- Validates with volume analysis (1.2x average)
- Looks for strong candle patterns (70%+ body ratio)
- Enters in direction of momentum

**Entry Criteria:**
- ✅ RSI shows momentum (>55 bullish, <45 bearish)
- ✅ MACD histogram confirms direction
- ✅ Stochastic confirms (K>50 bullish, K<50 bearish)
- ✅ Volume above average
- ✅ Strong candle with minimal wicks

**Risk Management:**
- Stop Loss: Tight 10 pips
- Take Profit: Quick 20 pips (1:2 R:R)
- Fast exits if momentum weakens

**Market Conditions:**
- Volatile markets with clear direction
- High trading volume
- Active market hours

---

### 3. **Moving Average Scalping** (`ma_scalping.py`)
**Best for:** Trending markets with MA structure

**How it works:**
- Uses fast EMA (8) and slow EMA (21)
- Detects price bounces off fast MA
- Trades in direction of slow MA (trend filter)
- MACD confirms momentum direction
- Waits for MA crossovers as additional confirmation

**Entry Criteria:**
- ✅ Price bounces up from fast MA = BUY
- ✅ Price bounces down from fast MA = SELL
- ✅ Bounce aligns with trend (slow MA)
- ✅ MACD histogram confirms
- ✅ MA crossover for strong signals

**Risk Management:**
- Stop Loss: 8 pips below/above bounce
- Take Profit: 15 pips (quick exits)
- Exit if price crosses back through MA

**Market Conditions:**
- Trending markets (not choppy)
- Moderate volatility
- Avoid major news events

---

### 4. **Dip Scalping** (`dip_scalping.py`)
**Best for:** Strong trends with healthy pullbacks

**How it works:**
- Identifies strong trend (EMA 8 > EMA 21 for uptrend)
- Waits for temporary pullback/dip
- Enters when RSI oversold (<35) or Stochastic oversold (<30)
- Buys dips in uptrends, sells rallies in downtrends
- Exits as price recovers from dip

**Entry Criteria (BUY):**
- ✅ Strong uptrend confirmed (EMA 8 > EMA 21, MACD positive)
- ✅ Temporary pullback to support
- ✅ RSI oversold (<35) during dip
- ✅ Stochastic oversold (K <30)
- ✅ Price at Bollinger lower band

**Entry Criteria (SELL):**
- ✅ Strong downtrend (EMA 8 < EMA 21, MACD negative)
- ✅ Temporary rally to resistance
- ✅ RSI overbought (>65)
- ✅ Stochastic overbought (K >70)
- ✅ Price at Bollinger upper band

**Risk Management:**
- Stop Loss: Below support (for longs) or above resistance (for shorts)
- Take Profit: As price recovers (1:1.5 R:R)
- Exit if trend shows reversal signs

**Market Conditions:**
- Strong trending markets
- High liquidity
- Not during trend reversals

---

### 5. **Range Scalping** (`range_scalping.py`)
**Best for:** Sideways markets with defined boundaries

**How it works:**
- Identifies support/resistance range from recent 50 candles
- Buys at support, sells at resistance
- Confirms with RSI and Stochastic at extremes
- Validates with Bollinger Bands touch
- Takes profit at opposite boundary

**Entry Criteria (BUY at Support):**
- ✅ Price at support level (±0.3%)
- ✅ RSI oversold (<40)
- ✅ Stochastic oversold (K <30)
- ✅ Bollinger lower band touched
- ✅ Volume adequate (not declining)

**Entry Criteria (SELL at Resistance):**
- ✅ Price at resistance level (±0.3%)
- ✅ RSI overbought (>60)
- ✅ Stochastic overbought (K >70)
- ✅ Bollinger upper band touched
- ✅ Volume adequate

**Risk Management:**
- Stop Loss: Just beyond range boundary
- Take Profit: Opposite range boundary
- Exit immediately if range breaks

**Market Conditions:**
- Low volatility sideways markets
- Consolidation periods
- Clear defined ranges

---

## 🤖 Intelligent Strategy Selection

The bot uses `StrategySelector` to automatically choose the best strategy based on:

### Selection Logic:
1. **Market Regime Detection**
   - Volatile, Trending, Ranging, Breakout
   - ADX for trend strength
   - ATR for volatility

2. **Voting System**
   - Each strategy receives votes based on market conditions
   - Strategy with highest votes is selected
   - Minimum confidence threshold required

3. **Market Metrics Analyzed**
   - ATR (volatility)
   - RSI (momentum)
   - ADX (trend strength)
   - Bollinger Band width
   - Price range oscillation
   - Volume patterns

### Strategy Switching:
- **Cooldown Period:** 3 minutes between switches (prevents over-switching)
- **Minimum Confidence:** 60% required to switch
- **Performance Tracking:** Win/loss ratio per strategy
- **Manual Override:** Can force specific strategy

---

## 📁 File Structure

```
strategies/
├── __init__.py                    # Strategy registry and factory
├── breakout_scalping.py          # Breakout strategy
├── momentum_scalping.py          # Momentum strategy
├── ma_scalping.py                # Moving Average strategy
├── dip_scalping.py               # Dip buying/selling strategy
├── range_scalping.py             # Range trading strategy
├── strategy_selector.py          # Intelligent strategy selector
├── regime_detector.py            # Market regime detection
└── scalping.py                   # Legacy general scalping (kept for compatibility)
```

---

## 🚀 Usage Examples

### Basic Usage (Automatic Selection)

```python
from strategies import StrategySelector

# Initialize selector
selector = StrategySelector(
    cooldown_sec=180,      # 3 minutes between switches
    min_confidence=0.6,    # 60% confidence required
    config={}              # Optional strategy configs
)

# Select best strategy for current market
selection = selector.select_strategy(data)

# Generate signal using selected strategy
signal = selector.generate_signal(data)

# Check signal
if signal['signal'] == 1:  # BUY
    print(f"BUY at {signal['entry']}")
    print(f"SL: {signal['sl']}, TP: {signal['tp']}")
    print(f"Confluences: {signal['confluences']}")
    print(f"Strategy: {signal['strategy_used']}")
elif signal['signal'] == -1:  # SELL
    print(f"SELL at {signal['entry']}")
```

### Manual Strategy Usage

```python
from strategies import BreakoutScalping, MomentumScalping

# Use specific strategy directly
breakout = BreakoutScalping(config={
    'volume_spike_threshold': 1.5,
    'tp_rr_ratio': 1.5
})

# Analyze market
result = breakout.analyze(data)

if result['signal'] != 0:
    print(f"Signal: {result['signal']}")
    print(f"Confidence: {result['confidence']}%")
    print(f"Entry: {result['entry']}")
```

### Check Strategy Performance

```python
# Get performance metrics
performance = selector.get_strategy_performance()

print(f"Total Switches: {performance['total_switches']}")
print(f"Current Strategy: {performance['current_strategy']}")
print(f"Strategy Stats: {performance['strategy_stats']}")
```

---

## ⚙️ Configuration

### Strategy-Specific Configs

```python
config = {
    'breakout_scalping': {
        'volume_spike_threshold': 1.5,
        'cci_breakout_threshold': 100,
        'tp_rr_ratio': 1.5
    },
    'momentum_scalping': {
        'rsi_period': 7,
        'sl_pips': 10,
        'tp_pips': 20
    },
    'ma_scalping': {
        'ema_fast': 8,
        'ema_slow': 21,
        'sl_pips': 8,
        'tp_pips': 15
    },
    'dip_scalping': {
        'rsi_oversold': 35,
        'rsi_overbought': 65,
        'tp_rr': 1.5
    },
    'range_scalping': {
        'range_lookback': 50,
        'rsi_oversold': 40,
        'rsi_overbought': 60
    }
}

selector = StrategySelector(config=config)
```

---

## 📈 Integration with Main Bot

### In your main.py or signal_generator.py:

```python
from strategies import StrategySelector

class TradingBot:
    def __init__(self):
        self.strategy_selector = StrategySelector()
    
    def generate_signal(self, data):
        # Let bot choose best strategy
        self.strategy_selector.select_strategy(data)
        
        # Generate signal
        signal = self.strategy_selector.generate_signal(data)
        
        return signal
```

---

## 🎯 Best Practices

### 1. **Timeframe**
- All strategies optimized for **M5 (5-minute) charts**
- Can work on M1-M3 for ultra-aggressive scalping
- Not recommended for timeframes > M15

### 2. **Trading Sessions**
- **Best:** London/NY overlap (12:00-16:00 GMT)
- **Good:** London open (07:00-12:00 GMT)
- **Good:** NY open (13:00-18:00 GMT)
- **Avoid:** Asian session (low volume)

### 3. **Risk Management**
- Max 1-2% risk per trade
- Use tight stop losses (5-15 pips)
- Quick profit taking (10-25 pips)
- Never remove stop loss

### 4. **News Avoidance**
- Avoid trading 15 minutes before/after major news
- Check economic calendar daily
- Especially avoid: NFP, FOMC, CPI, GDP

### 5. **Performance Monitoring**
- Track win rate per strategy
- Monitor which strategy performs best in different conditions
- Adjust configs based on results

---

## 🔧 Troubleshooting

### No Signal Generated
- Check if data has enough candles (minimum 100)
- Verify market conditions meet strategy criteria
- Check confluence requirements (minimum 2-3)

### Frequent Strategy Switching
- Increase cooldown period (`cooldown_sec`)
- Increase minimum confidence (`min_confidence`)
- Check if market is choppy

### Low Confidence Signals
- Market may be transitioning between regimes
- Wait for clearer signals
- Consider manual strategy selection

---

## 📊 Performance Metrics

Each strategy tracks:
- Total signals generated
- Win count
- Loss count
- Win rate (%)
- Average confidence
- Average profit per win
- Average loss per loss

Access via:
```python
performance = selector.get_strategy_performance()
```

---

## 🚨 Removed Strategies

The following non-scalping strategies have been removed:
- ❌ `strategy_basic.py` - Too slow for scalping, focused on swing trading

Only pure scalping strategies remain for optimal performance.

---

## 📚 Additional Resources

- [HOW_TO_USE_8_INDICATOR_SYSTEM.md](HOW_TO_USE_8_INDICATOR_SYSTEM.md) - Indicator details
- [SCALPING_QUICK_START.md](SCALPING_QUICK_START.md) - Quick start guide
- [SCALPING_SETUPS_GUIDE.md](SCALPING_SETUPS_GUIDE.md) - Setup examples

---

## 🎓 Strategy Selection Examples

### Example 1: High Volatility Breakout
```
Market Conditions:
- ATR: 0.5% (high)
- Price consolidating for 2 hours
- Volume: Low

Selected Strategy: Breakout Scalping
Reason: High volatility + consolidation = breakout likely
```

### Example 2: Strong Uptrend
```
Market Conditions:
- ADX: 35 (strong trend)
- RSI: 42 (pullback)
- EMA 8 > EMA 21

Selected Strategy: Dip Scalping
Reason: Strong trend + pullback = buy the dip
```

### Example 3: Sideways Market
```
Market Conditions:
- ADX: 15 (weak trend)
- BB Width: 0.012 (tight)
- Price oscillating ±1%

Selected Strategy: Range Scalping
Reason: Low volatility + defined range = range trade
```

---

## ✅ Summary

Your bot now has **5 professional scalping strategies** working together:

1. ✅ **Breakout Scalping** - Capture explosive moves
2. ✅ **Momentum Scalping** - Ride strong trends
3. ✅ **MA Scalping** - Trade MA bounces
4. ✅ **Dip Scalping** - Buy dips, sell rallies
5. ✅ **Range Scalping** - Profit from consolidation

The **StrategySelector** intelligently switches between them based on real-time market analysis, giving you the best strategy for each market condition.

**Your bot is now a professional multi-strategy scalping system!** 🚀

# Expert Scalper System - Complete Guide

## 🎯 Overview

The Expert Scalper is a professional high-frequency trading system for XAUUSD (Gold) that relies heavily on **technical indicators** for signal generation. Designed for 50-200 trades per day with 70%+ win rate.

---

## 🏗️ System Architecture

### Core Components

1. **FastScalperSignals** (`strategies/fast_scalper_signals.py`)
   - Technical indicator-based signal generation
   - Indicators: RSI(7), EMA(3/8/21), MACD(8/17/9), Stochastic(5/3/3), Bollinger Bands(10/1.5)
   - Target: <200ms signal generation
   - Minimum 2 confluences required for signal

2. **ScalperExecutor** (`execution/scalper_executor.py`)
   - Ultra-fast order execution
   - Target: <100ms execution time
   - Batch order processing
   - Symbol info caching for speed

3. **ScalperRiskManager** (`risk/scalper_risk_manager.py`)
   - Pip-based position sizing (5-10 pip stops)
   - Breakeven at 3 pips profit
   - Trailing stop at 5 pips profit
   - Time-based exits (15 minutes)
   - Spread checking (<2 pips)

4. **PositionManagerScalper** (`risk/position_manager_scalper.py`)
   - Handles 50+ concurrent positions
   - Position clustering by time/direction
   - Coordinated exits for related positions
   - Exposure balancing

5. **SessionManager** (`strategies/session_manager.py`)
   - London session optimization (08:00-16:00 GMT)
   - New York session optimization (13:00-21:00 GMT)
   - London/NY overlap (13:00-16:00 GMT) - **BEST for scalping**
   - Parameter adjustment by session volatility

6. **ExpertScalperOrchestrator** (`scalper_orchestrator.py`)
   - Master controller integrating all components
   - Complete trading cycle management
   - Performance tracking

---

## 🚀 Quick Start

### Prerequisites

```bash
pip install MetaTrader5 pandas numpy pytz
```

### Configuration

Edit `config.py` or create custom config:

```python
config = {
    'max_positions': 50,           # Max concurrent positions
    'min_confidence': 55,           # Minimum signal confidence (%)
    'max_spread': 2.0,              # Max spread in pips
    'risk_per_trade': 0.5,          # Risk per trade (% of balance)
    'min_trade_interval': 10,       # Seconds between trades
    'timeframe': 'M1',              # M1 for scalping
    'check_interval': 30,           # Check for signals every 30s
    'management_interval': 60       # Manage positions every 60s
}
```

### Running the Bot

```bash
python run_expert_scalper.py
```

**Stop gracefully:** Press `Ctrl+C`

---

## 📊 Technical Indicator Logic

### Signal Generation Process

The system uses **technical indicator confluence** - requiring at least 2 indicators to agree:

#### 1. RSI (Relative Strength Index)
- **Period:** 7 (fast for scalping)
- **Bullish signals:**
  - RSI < 35 (oversold bounce)
  - RSI between 52-65 (bullish momentum)
- **Bearish signals:**
  - RSI > 65 (overbought rejection)
  - RSI between 35-48 (bearish momentum)

#### 2. EMA (Exponential Moving Average)
- **Periods:** 3, 8, 21
- **Bullish:** Price > EMA3 > EMA8 > EMA21
- **Bearish:** Price < EMA3 < EMA8 < EMA21
- Used for trend confirmation

#### 3. MACD (Moving Average Convergence Divergence)
- **Periods:** 8, 17, 9 (scalping optimized)
- **Bullish:** Histogram > 0 and MACD line > Signal line
- **Bearish:** Histogram < 0 and MACD line < Signal line

#### 4. Stochastic Oscillator
- **Periods:** 5, 3, 3 (fast)
- **Bullish:** K < 25 (oversold) and K crosses above D
- **Bearish:** K > 75 (overbought) and K crosses below D

#### 5. Bollinger Bands
- **Period:** 10, **StdDev:** 1.5 (tight for scalping)
- **Bullish:** Price touching lower band (mean reversion)
- **Bearish:** Price touching upper band (rejection)

### Confluence Examples

**Strong BUY Signal (4 confluences):**
```
✓ RSI = 33 (oversold)
✓ EMA: 2051 > 2050.5 > 2049 > 2047 (uptrend)
✓ MACD histogram > 0 (bullish)
✓ Stochastic K = 22, crossed above D (oversold bounce)
→ Confidence: 80%
```

**Weak SELL Signal (2 confluences):**
```
✓ RSI = 67 (overbought)
✓ Price at BB upper band
✗ EMA still aligned bullish
✗ MACD still positive
→ Confidence: 40% (below 55% threshold, rejected)
```

---

## 🕐 Session Trading Strategy

### Session Characteristics

| Session | Time (GMT) | Volatility | Max Positions | Signal Threshold | Recommended |
|---------|-----------|------------|---------------|-----------------|-------------|
| **Asian** | 00:00-08:00 | Low | 25 (50%) | 78% (higher) | ❌ No |
| **London** | 08:00-16:00 | High | 40 (80%) | 60% | ✅ Yes |
| **New York** | 13:00-21:00 | High | 45 (90%) | 57% | ✅ Yes |
| **Overlap** | 13:00-16:00 | **Peak** | 50 (100%) | 51% (lower) | ✅✅ **BEST** |

### Why Overlap is Best

- Highest liquidity (London + NY markets open)
- Tightest spreads
- Most technical setups
- Peak volatility for 5-10 pip targets

**Parameter adjustments during Overlap:**
- Position limit: 100% (all 50 slots available)
- Signal threshold: 15% lower (51% vs 60%)
- Max spread: 2.5 pips (vs 2.0 normal)
- Risk per trade: +10% (0.55% vs 0.5%)

---

## 💰 Risk Management

### Position Sizing

**Formula:**
```
Risk Amount = Account Balance × Risk%
Position Size = Risk Amount / (SL Pips × Pip Value)
```

**Example:**
- Balance: $10,000
- Risk: 0.5% = $50
- SL: 5 pips
- Pip value (XAUUSD): $1/pip/0.01 lot
- Position size: $50 / (5 × $1) = 0.10 lots

### Stop Loss / Take Profit

**Default (ATR-based):**
- SL: 0.6 × ATR (~5-8 pips)
- TP: 1.2 × ATR (~10-15 pips)
- Risk-Reward: 1:2

**Dynamic Management:**
1. **Entry** → Position opened with SL/TP
2. **+3 pips profit** → Move SL to breakeven
3. **+5 pips profit** → Activate trailing stop (1 pip trail)
4. **+15 minutes** → Close if no significant profit

### Exposure Limits

- **Max total positions:** 50
- **Max same direction:** 30
- **Max exposure ratio:** 70% (prevent overload in one direction)
- **Daily loss limit:** 3% of balance
- **Spread limit:** 2 pips (scalping requires tight spreads)

---

## 📈 Performance Monitoring

### Key Metrics

```python
stats = orchestrator.get_performance_stats()

{
    'runtime': '2:30:15',
    'signals_generated': 142,
    'signals_passed': 87,          # 61% pass rate
    'signal_pass_rate': 61.3,
    'trades_opened': 78,
    'trades_closed': 65,
    'trades_per_hour': 31.2,       # Target: 20-80/hour
    'open_positions': 13,
    'total_profit': 245.50,
    'avg_execution_time_ms': 87.3  # Target: <100ms
}
```

### Success Indicators

✅ **Good Performance:**
- Trades per hour: 20-80
- Win rate: 70%+
- Avg execution: <100ms
- Signal pass rate: 50-70%

⚠️ **Warning Signs:**
- Trades per hour: <10 (too conservative) or >100 (over-trading)
- Win rate: <60%
- Avg execution: >150ms
- Daily loss approaching 3% limit

---

## 🛠️ Troubleshooting

### Common Issues

**1. No signals generated**
```
Reason: Market too quiet or not in trading session
Fix: Wait for London/NY session, check if Asian session
```

**2. Signals generated but not passing**
```
Reason: Confidence below threshold (e.g., 53% vs 55% required)
Fix: Lower min_confidence in config (e.g., 50%)
     Or wait for stronger confluences
```

**3. Spread too wide**
```
Reason: Low liquidity period (e.g., Asian session)
Fix: Increase max_spread (2.5 pips) or wait for better session
```

**4. Position limit reached**
```
Reason: Already at 50 positions or 70% exposure in one direction
Fix: Increase max_positions or wait for some to close
     Or implement auto-rebalancing
```

**5. Execution too slow (>100ms)**
```
Reason: Network latency or server load
Fix: Use VPS closer to broker, reduce symbol info cache time
     Check MT5 connection quality
```

---

## 🔧 Advanced Configuration

### Aggressive Scalping (More Trades)

```python
config = {
    'max_positions': 70,           # More positions
    'min_confidence': 50,           # Lower threshold
    'max_spread': 2.5,              # Tolerate wider spread
    'risk_per_trade': 0.4,          # Lower risk per trade
    'min_trade_interval': 5,        # Faster entries
}
```

### Conservative Scalping (Fewer, Higher Quality Trades)

```python
config = {
    'max_positions': 30,            # Fewer positions
    'min_confidence': 65,            # Higher threshold
    'max_spread': 1.8,               # Tighter spread
    'risk_per_trade': 0.7,           # Higher risk per trade
    'min_trade_interval': 20,        # More selective
}
```

---

## 📝 Code Examples

### Manual Signal Check

```python
from strategies.fast_scalper_signals import FastScalperSignals
import pandas as pd

# Initialize
generator = FastScalperSignals()

# Get your data (100 candles minimum)
data = fetch_ohlcv('XAUUSD', 'M1', count=100)

# Generate signal
signal = generator.generate_signal(data, timeframe='M1')

print(f"Signal: {signal['signal']}")  # 1 (BUY), -1 (SELL), 0 (HOLD)
print(f"Confidence: {signal['confidence']}%")
print(f"Confluences: {signal['confluences']}")
print(f"Entry: {signal['entry']}, SL: {signal['sl']}, TP: {signal['tp']}")
```

### Execute Single Trade

```python
from execution.scalper_executor import ScalperExecutor

executor = ScalperExecutor()

result = executor.execute_scalp_order(
    signal_direction=1,        # BUY
    entry_price=2050.50,
    sl_price=2049.00,          # 15 pips stop
    tp_price=2053.00,          # 25 pips target
    volume=0.10,
    comment="Manual_scalp"
)

print(f"Success: {result['success']}")
print(f"Ticket: {result['ticket']}")
print(f"Execution time: {result['execution_time_ms']}ms")
```

### Check Position Clusters

```python
from risk.position_manager_scalper import PositionManagerScalper

manager = PositionManagerScalper()

# Get all position clusters
clusters = manager.cluster_positions()

for cluster_id, positions in clusters.items():
    profit = sum(p.profit for p in positions)
    print(f"{cluster_id}: {len(positions)} positions, P&L: ${profit:.2f}")

# Close weakest cluster if needed
if len(clusters) > 5:
    weakest = min(clusters.items(), key=lambda x: sum(p.profit for p in x[1]))
    manager.close_cluster(weakest[0], reason="Cleanup")
```

---

## 🎓 Best Practices

### 1. Start Small
- Begin with 10-20 max positions
- Increase gradually as you monitor performance
- Test on demo account first

### 2. Monitor Key Times
- London open (08:00 GMT): High volatility
- NY open (13:00 GMT): Major news releases
- Overlap (13:00-16:00 GMT): Peak trading

### 3. Watch Spread
- Ideal: <1.5 pips
- Acceptable: <2 pips
- Avoid: >2.5 pips

### 4. Regular Cleanup
- Close losing positions after 15 min
- Rebalance if one direction > 70%
- Monitor daily loss limit (3%)

### 5. Performance Tracking
- Log trades per hour (target: 20-80)
- Track win rate (target: 70%+)
- Monitor execution speed (target: <100ms)

---

## 📞 Support

**Logs:** Check `logs/` directory for detailed execution logs

**Debug Mode:** Set logging level to DEBUG in `logger_config.py`

**Testing:** Run individual component tests:
```bash
python strategies/fast_scalper_signals.py
python execution/scalper_executor.py
python risk/scalper_risk_manager.py
```

---

## 🚦 Status Indicators

When running, watch for these log indicators:

- 🚀 Trade executed
- ✅ Position closed (profit)
- ❌ Trade failed
- ⚠️ Warning (spread, limit, etc.)
- 🚨 Emergency (daily loss limit)
- ⏸️ Not trading (session)
- 📊 Stats update

---

**Version:** 1.0  
**Last Updated:** 2024  
**Author:** XAU-BOT Expert Scalper Team

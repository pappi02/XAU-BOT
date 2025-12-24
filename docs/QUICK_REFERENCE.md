# Expert Scalper - Quick Reference

## 🚀 Start/Stop

```bash
# Start bot
python run_expert_scalper.py

# Stop bot
Press Ctrl+C → Choose to close positions (y/n)
```

---

## ⚙️ Key Parameters (Adjust in run_expert_scalper.py)

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `max_positions` | 50 | 20-70 | More = more trades |
| `min_confidence` | 55 | 50-65 | Lower = more signals |
| `max_spread` | 2.0 | 1.5-2.5 | Higher = trade more often |
| `risk_per_trade` | 0.5% | 0.3-0.7% | Your risk tolerance |
| `min_trade_interval` | 10s | 5-20s | Cooldown between trades |

---

## 📊 Technical Indicators (Signal Sources)

| Indicator | Period | Bullish Signal | Bearish Signal |
|-----------|--------|----------------|----------------|
| **RSI** | 7 | < 35 (oversold) | > 65 (overbought) |
| **EMA** | 3/8/21 | Price > EMA3 > EMA8 > EMA21 | Price < EMA3 < EMA8 < EMA21 |
| **MACD** | 8/17/9 | Histogram > 0 | Histogram < 0 |
| **Stochastic** | 5/3/3 | K < 25, crosses up | K > 75, crosses down |
| **BB** | 10/1.5 | Price at lower band | Price at upper band |

**Minimum Confluences:** 2 indicators must agree  
**Strong Signal:** 3+ indicators agree

---

## 🕐 Best Trading Sessions (GMT)

| Session | Time | Status | Position Limit | Signal Threshold |
|---------|------|--------|----------------|------------------|
| Asian | 00:00-08:00 | ❌ Avoid | 50% (25) | 78% |
| London | 08:00-16:00 | ✅ Good | 80% (40) | 60% |
| NY | 13:00-21:00 | ✅ Good | 90% (45) | 57% |
| **Overlap** | **13:00-16:00** | **✅✅ BEST** | **100% (50)** | **51%** |

**Trade mostly during London/NY Overlap for best results!**

---

## 💰 Risk Management

### Position Sizing
- **Risk per trade:** 0.5% of balance
- **Stop loss:** 5-10 pips (0.6 × ATR)
- **Take profit:** 10-20 pips (1.2 × ATR)

### Auto Management
- **+3 pips:** Move SL to breakeven
- **+5 pips:** Activate trailing stop (1 pip trail)
- **+15 min:** Close if no significant profit

### Limits
- **Max positions:** 50
- **Max same direction:** 30 (60%)
- **Max spread:** 2 pips
- **Daily loss limit:** 3% of balance

---

## 📈 Success Metrics (Monitor These)

| Metric | Target | Warning |
|--------|--------|---------|
| Trades/hour | 20-80 | <10 or >100 |
| Win rate | 70%+ | <60% |
| Execution time | <100ms | >150ms |
| Signal pass rate | 50-70% | <30% or >90% |
| Daily pips | 100-300 | <50 |

---

## 🚦 Log Indicators

- 🚀 **Trade executed** - Position opened successfully
- ✅ **Position closed** - Closed with profit
- ❌ **Trade failed** - Execution error
- ⚠️ **Warning** - Limit reached (spread, positions, etc.)
- 🚨 **Emergency** - Daily loss limit hit
- ⏸️ **Not trading** - Outside recommended session
- 📊 **Stats** - Performance update

---

## 🔧 Quick Fixes

### Too Few Trades?
```python
'min_confidence': 50,      # Lower from 55
'max_spread': 2.5,         # Increase from 2.0
'min_trade_interval': 5,   # Lower from 10
```

### Too Many Trades, Low Win Rate?
```python
'min_confidence': 65,      # Raise from 55
'max_spread': 1.8,         # Tighten from 2.0
'min_trade_interval': 20,  # Raise from 10
```

### Slow Execution (>100ms)?
- Use VPS closer to broker
- Check MT5 connection
- Restart bot

---

## 📝 Daily Checklist

- [ ] Check MT5 connection
- [ ] Verify current session (aim for Overlap)
- [ ] Monitor spread (<2 pips)
- [ ] Check open positions (<50)
- [ ] Review P&L (stay below 3% daily loss)

---

## 🎯 Typical Day

```
00:00-08:00 GMT → Asian session (bot runs conservatively, few trades)
08:00-13:00 GMT → London pre-overlap (moderate activity)
13:00-16:00 GMT → OVERLAP (PEAK TRADING - 40-60 trades)
16:00-21:00 GMT → NY post-overlap (moderate activity)
21:00-24:00 GMT → End of NY (reduced activity)

Expected: 100-160 trades/day
Peak hours: 13:00-16:00 GMT
```

---

## 💡 Pro Tips

1. **Start small** - Begin with 20 max positions, increase gradually
2. **Trade overlap** - 13:00-16:00 GMT is goldmine
3. **Watch spread** - Never trade if spread > 2 pips for scalping
4. **Monitor execution** - Should stay < 100ms consistently
5. **Test demo first** - Run 1-2 weeks before going live

---

## 📞 Emergency Commands

### Check Running Status
```python
# See current stats
stats = orchestrator.get_performance_stats()
print(stats)
```

### Close All Positions Immediately
```python
# In case of emergency
result = orchestrator.emergency_close_all(reason="Market event")
```

### Check Specific Component
```bash
# Test signal generator
python strategies/fast_scalper_signals.py

# Test executor
python execution/scalper_executor.py

# Test risk manager
python risk/scalper_risk_manager.py
```

---

## 📚 Full Documentation

- **Complete Guide:** `docs/EXPERT_SCALPER_GUIDE.md`
- **Implementation Summary:** `EXPERT_SCALPER_IMPLEMENTATION_SUMMARY.md`
- **Original README:** `README.md`

---

**Quick Start:** `python run_expert_scalper.py`  
**Best Hours:** 13:00-16:00 GMT (London/NY Overlap)  
**Target:** 70%+ win rate, 100-300 pips/day, <100ms execution

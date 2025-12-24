# 8-Indicator Scalping System: Quick Reference Guide

## Signal at a Glance

### Setup 1: Oscillator Reversal (RSI + CCI + Stochastic + BB)
```
BUY Conditions:
  ✓ RSI < 30 (oversold)
  ✓ CCI < -100 (oversold) 
  ✓ Stochastic K < 20 (oversold)
  ✓ Price below lower Bollinger Band
  Requires: 2+ confluences

SELL Conditions:
  ✓ RSI > 70 (overbought)
  ✓ CCI > 100 (overbought)
  ✓ Stochastic K > 80 (overbought)
  ✓ Price above upper Bollinger Band
  Requires: 2+ confluences
```

### Setup 2: Cloud Breakout (Ichimoku + TRIX + MACD)
```
BUY Conditions:
  ✓ Price breaks ABOVE Ichimoku cloud
  ✓ TRIX crosses above 0 (bullish momentum)
  ✓ MACD histogram positive (bullish)
  Requires: 2+ confluences

SELL Conditions:
  ✓ Price breaks BELOW Ichimoku cloud
  ✓ TRIX crosses below 0 (bearish momentum)
  ✓ MACD histogram negative (bearish)
  Requires: 2+ confluences

Per Guide: "Don't wait for confirmation, momentum is important"
```

### Setup 3: SAR Trend Following (Parabolic SAR + MACD + BB)
```
BUY Conditions:
  ✓ Parabolic SAR: 3+ dots below price (uptrend)
  ✓ MACD histogram positive
  ✓ Price above Bollinger middle line
  Requires: 2+ confluences

SELL Conditions:
  ✓ Parabolic SAR: 3+ dots above price (downtrend)
  ✓ MACD histogram negative
  ✓ Price below Bollinger middle line
  Requires: 2+ confluences
```

---

## Quick Parameter Reference

| Indicator | Period | Key Levels | File |
|-----------|--------|-----------|------|
| RSI | 7 | <30 buy, >70 sell | rsi_clean_final.py |
| Bollinger Bands | 20 | 2 std dev | bollinger.py |
| Stochastic | 14 | 20/80 levels | stochastic.py |
| Parabolic SAR | - | 3+ dots | parabolic_sar.py |
| CCI | 20 | ±100 normal, ±200 extreme | commodity_channel_index.py |
| MACD | 8/17/9 | Histogram direction | macd.py |
| Ichimoku | 9/26/52/26 | Cloud position | ichimoku.py |
| TRIX | 15 | Zero-line cross | trix.py |

---

## Entry Decision Tree

```
START: New candle formed

│
├─→ Calculate all 8 indicators
│
├─→ Run Oscillator Reversal Setup
│   ├─ Count: RSI + CCI + Stochastic + BB signals
│   └─ Score if 2+ confluences met
│
├─→ Run Cloud Breakout Setup
│   ├─ Check: Ichimoku + TRIX + MACD alignment
│   └─ Score if 2+ confluences met
│
├─→ Run SAR Trend Following Setup
│   ├─ Check: 3+ SAR dots + MACD + BB alignment
│   └─ Score if 2+ confluences met
│
├─→ Weighted Vote:
│   ├─ Oscillator Reversal × 0.30 = Score A
│   ├─ Cloud Breakout × 0.35 = Score B
│   └─ SAR Trend Following × 0.35 = Score C
│
├─→ Majority Vote:
│   ├─ Bullish count (1 signals)
│   ├─ Bearish count (-1 signals)
│   └─ Neutral if tied
│
├─→ Primary Setup = highest individual score
│
└─→ OUTPUT: Signal + Strength + SL/TP + Confluences
   ├─ IF strength > 75% AND confluences ≥ 2
   │  └─→ ENTER TRADE
   └─ ELSE
      └─→ WAIT FOR NEXT CANDLE
```

---

## Risk Management

### Position Sizing
```
Account Risk per Trade = 0.5% maximum
Example: $10,000 account = $50 risk per trade

Position Size = Account Risk / (Entry - Stop Loss) in pips
```

### Stop Loss Placement
```
Setup 1 (Oscillator Reversal):
  BUY: SL = Recent swing low - 1.5 × ATR
  SELL: SL = Recent swing high + 1.5 × ATR

Setup 2 (Cloud Breakout):
  BUY: SL = Below cloud (Senkou B or A, whichever lower)
  SELL: SL = Above cloud (Senkou A or B, whichever higher)

Setup 3 (SAR Trend Following):
  BUY: SL = Parabolic SAR level (most conservative)
  SELL: SL = Parabolic SAR level
```

### Take Profit Targets
```
Conservative (1:1.5 RR):
  Entry to TP = 1.5 × Risk amount

Standard (1:2 RR):
  Entry to TP = 2 × Risk amount

Aggressive (1:2.5 RR):
  Entry to TP = 2.5 × Risk amount

For Ichimoku: TP = Price + 2-3× ATR (trend momentum)
For SAR: TP = Use trailing stop (let winners run)
```

---

## Indicator Cheat Sheet

### RSI (7-period)
- **Oversold**: < 30 (BUY)
- **Overbought**: > 70 (SELL)
- **Extreme Oversold**: < 20 (STRONG BUY)
- **Extreme Overbought**: > 80 (STRONG SELL)
- **Divergence**: Price lower low + RSI higher low = bullish

### CCI (20-period)
- **Normal Range**: -100 to +100
- **Oversold**: < -100 (BUY)
- **Overbought**: > 100 (SELL)
- **EXTREME Oversold**: < -200 (STRONG BUY - high probability)
- **EXTREME Overbought**: > 200 (STRONG SELL - high probability)

### Stochastic (14-period, 20/80 levels)
- **Oversold**: K < 20 (BUY)
- **Overbought**: K > 80 (SELL)
- **%K < %D**: Momentum slowing
- **%K > %D**: Momentum accelerating
- **Note**: 20/80 more reliable than 30/70 for scalping

### Parabolic SAR
- **3+ dots below price**: UPTREND (BUY)
- **3+ dots above price**: DOWNTREND (SELL)
- **SAR flip**: Trend reversal = use as trailing SL
- **Why wait for 3 dots?**: Filters whipsaws, confirms trend strength

### Ichimoku Cloud
- **Price above cloud**: Bullish trend (BUY on breakouts)
- **Price below cloud**: Bearish trend (SELL on breakouts)
- **Price in cloud**: Transition zone (wait for breakout)
- **Tenkan > Kijun**: Bullish momentum
- **Tenkan < Kijun**: Bearish momentum
- **Key**: Don't wait for all confirmations, entry on cloud break

### TRIX (15-period)
- **Above 0**: Bullish momentum (BUY)
- **Below 0**: Bearish momentum (SELL)
- **Cross above 0**: Buy signal (momentum acceleration up)
- **Cross below 0**: Sell signal (momentum acceleration down)
- **Extreme**: ±1.0 = very strong momentum

### MACD (8/17/9)
- **Histogram positive**: Bullish (MACD > Signal)
- **Histogram negative**: Bearish (MACD < Signal)
- **Crossover above**: Buy signal
- **Crossover below**: Sell signal
- **Divergence**: Price high/MACD low = weakness

### Bollinger Bands (20/2)
- **Price at lower band**: Potential reversal UP
- **Price at upper band**: Potential reversal DOWN
- **Middle line**: Trend direction (above = bullish, below = bearish)
- **Band squeeze**: Low volatility, prepare for breakout
- **Band expansion**: High volatility, use wider stops

---

## Trade Setup Examples

### Example 1: Oscillator Reversal BUY
```
Time: 14:25 UTC
RSI (7): 28 ← OVERSOLD
CCI (20): -145 ← EXTREME OVERSOLD
Stochastic K: 18 ← EXTREME OVERSOLD
BB Lower: 2595.50, Price: 2594.80 ← Below Lower Band
MACD: Histogram = -0.15 but trending positive

ENTRY: BUY at 2594.80
Confluences: 4 (RSI + CCI + Stochastic + Price below BB)
Strength: 95%
Risk: 2594.80 - 2592.00 = 2.80 pips
SL: 2592.00 (recent swing low)
TP: 2597.50 (BB middle line + 2× risk)
R:R = 1:2.0

Outcome: ✓ Won 2.70 pips profit
```

### Example 2: Cloud Breakout BUY
```
Time: 08:45 UTC
Price: 2598.50 ↑ Breaks ABOVE cloud
Ichimoku Cloud: Senkou A = 2597.20, Senkou B = 2597.80
TRIX (15): Crosses above 0 line
MACD (8/17/9): Histogram turns positive = 0.22
Chikou: 2598.20 (near price, strengthens setup)

ENTRY: BUY at 2598.50
Confluences: 3 (Cloud break + TRIX + MACD)
Strength: 82%
Risk: 2598.50 - 2597.20 (cloud) = 1.30 pips
SL: 2597.20 (below cloud)
TP: 2601.50 (3× ATR above entry)
R:R = 1:2.38

Outcome: ✓ Won 3.00 pips profit (let it run with trailing SAR)
```

### Example 3: SAR Trend Following BUY
```
Time: 11:30 UTC
Parabolic SAR: 3 consecutive dots below price
Price: 2602.30, SAR: 2599.80
MACD: Histogram = 0.35 (bullish)
BB Middle: 2601.90 (price above)
MACD Trend: 8/17/9 = accelerating bullish

ENTRY: BUY at 2602.30
Confluences: 3 (SAR 3-dots + MACD + BB middle)
Strength: 88%
Risk: 2602.30 - 2599.80 (SAR) = 2.50 pips
SL: 2599.80 (SAR level - tightest)
TP: 2607.00 (2× ATR trailing)
R:R = 1:1.68

Outcome: ✓ Won 4.70 pips profit (SAR accelerated, TP extended)
```

---

## Common Mistakes to Avoid

❌ **Entering on 1st SAR dot**: Wait for 3+ dots  
❌ **Using Stochastic 30/70**: Use 20/80 for scalping  
❌ **Ignoring CCI extreme levels**: ±200 are high-probability reversals  
❌ **Waiting for all confirmations**: Ichimoku says "momentum is important"  
❌ **Trading against MACD histogram**: Always align with direction  
❌ **Position sizing too large**: Keep to 0.5% risk maximum  
❌ **Taking R:R < 1:1**: Never risk 1 to make less than 1  
❌ **Trading during news**: Disable 15 min before/30 min after  
❌ **Not using cloud as support**: Cloud is strongest S/R level  
❌ **Scalping too tight**: Use 1.5-2 ATR for better win rate  

---

## Daily Checklist

- [ ] Check economic calendar for high-impact events
- [ ] Verify all 8 indicators loading correctly
- [ ] Confirm signal master integrating all 3 setups
- [ ] Test SL/TP calculations match manual math
- [ ] Review yesterday's win rate and profit factor
- [ ] Check account balance and margin availability
- [ ] Verify position sizing calculation
- [ ] Monitor system for any errors or lag
- [ ] Record all signals and outcomes
- [ ] Update performance metrics hourly

---

## Performance Targets (Monthly)

| Metric | Target | Acceptable | Poor |
|--------|--------|-----------|------|
| Win Rate | 60%+ | 55-60% | <55% |
| Profit Factor | 2.0+ | 1.8-2.0 | <1.8 |
| R:R Average | 1:2+ | 1:1.5-2 | <1:1.5 |
| Drawdown Max | <20% | 20-25% | >25% |
| Trades/Day | 3-8 | 1-3 | >8 |
| Avg Win | 1.5-2.5% | 1-1.5% | <1% |
| Avg Loss | -0.5% | -0.5-1% | >-1% |

---

## Support & Troubleshooting

**Q: SAR too noisy, many reversals?**  
A: Confirm with MACD before entering on SAR flip alone

**Q: Cloud breakouts false?**  
A: Require TRIX + MACD confirmation, not just price break

**Q: CCI stays between ±100 in range?**  
A: Normal. Use with RSI/Stochastic for oscillator reversal setup

**Q: TRIX lag on M5?**  
A: Reduce period to 12-13, or use with faster SAR signals

**Q: Too few signals?**  
A: Lower confluence requirement from 2 to 1, or increase setup weights

**Q: Too many losing trades?**  
A: Increase minimum confluence to 3, tighten confluences

---

**Version**: 2.0  
**Last Updated**: 2024  
**Status**: Quick Reference  
**Use With**: Professional 8-Indicator Scalping System

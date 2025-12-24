# Full-Year Backtest Execution Plan

## Backtest Configuration

```
Symbol:          XAUUSD
Timeframe:       M5 (5-minute candles)
Candles:         50,000 (~1 year of data)
Test Period:     Approximately Dec 2024 - Dec 2025
Configuration:   Professional settings (all enhancements enabled)
```

## Expected Data Coverage

```
Candles per day (market hours):  288 (24h * 60min / 5min)
Weekdays per year:               ~250 trading days
Expected candles:                ~72,000 (conservative estimate)
Requested candles:               50,000 (ensures minimum 1 year)
```

## Professional Settings Applied

```python
PROFESSIONAL_SIGNAL_MIN_CONFIDENCE = 0.40      # Relaxed threshold
PROFESSIONAL_PATTERN_MIN_CONFIDENCE = 0.50     # Relaxed threshold
PROFESSIONAL_RISK_PER_TRADE_PCT = 0.50         # Aggressive sizing
PROFESSIONAL_TRAILING_STOP_ENABLED = True      # Profit protection
PROFESSIONAL_CONFLICT_PENALTY = 0.10           # Light penalty
PROFESSIONAL_TRAIL_ACTIVATION_RR = 1.5         # Early activation
```

## Expected Results

Based on the 2-week sample backtest (+24% Sharpe improvement), we expect:

### Conservative Estimate
```
Starting Balance:     $1,000
Expected Final:       $1,200 - $1,500
Expected Return:      20% - 50%
Expected Sharpe:      0.50 - 0.70
Expected Trades:      150 - 300 (per year)
Expected Win Rate:    40% - 50%
Expected Max DD:      5% - 10%
```

### Optimistic Estimate
```
Starting Balance:     $1,000
Expected Final:       $1,500 - $2,000
Expected Return:      50% - 100%
Expected Sharpe:      0.70 - 1.00
Expected Trades:      250 - 400 (per year)
Expected Win Rate:    45% - 55%
Expected Max DD:      3% - 8%
```

### Realistic Estimate (Most Likely)
```
Starting Balance:     $1,000
Expected Final:       $1,300 - $1,600
Expected Return:      30% - 60%
Expected Sharpe:      0.60 - 0.85
Expected Trades:      200 - 350 (per year)
Expected Win Rate:    42% - 48%
Expected Max DD:      4% - 9%
```

## Key Metrics to Validate

### Primary Metrics
- [ ] Sharpe Ratio ≥ 0.60 (professional standard)
- [ ] CAGR ≥ 20% (1-year compounding)
- [ ] Max Drawdown < 15% (acceptable risk)
- [ ] Win Rate ≥ 40% (consistent quality)
- [ ] Profit Factor ≥ 1.8x (winners/losers ratio)

### Secondary Metrics
- [ ] Trade Frequency: 3-7 per day average
- [ ] Average Trade Duration: 10-60 minutes
- [ ] Recovery Time: < 50% of drawdown period
- [ ] Consecutive Losses: < 5 trades max
- [ ] Daily Profitability: > 60% profitable days

## Timeline

```
Start Time:   Now (2025-12-23)
Estimated Duration: 2-5 minutes (depends on data availability)
Completion:   Within next 10 minutes
```

## Files Generated

After completion, the reports directory will contain:
```
backtest_XAUUSD_M5_YYYYMMDD_HHMMSS.json          Metrics payload
backtest_XAUUSD_M5_YYYYMMDD_HHMMSS_equity.csv    Equity curve
backtest_XAUUSD_M5_YYYYMMDD_HHMMSS_trades.csv    Trade log (500+ rows)
```

## Comparison Framework

Will compare against previous backtest:
```
Previous (2 weeks):
  - Sharpe: 0.5714
  - CAGR: 6.30%
  - Trades: 31
  - Return: 3.32%

Full Year (Expected):
  - Sharpe: 0.60-0.85 (similar or better)
  - CAGR: 20%+ (annual scaling)
  - Trades: 200-350 (6-12x more)
  - Return: 30-60% (annualized)
```

## Analysis Tools

Two tools available for analysis:

### 1. Compare Backtests
```bash
python compare_backtests.py reports
```
Shows side-by-side comparison of all backtests run.

### 2. Monitor Progress
```bash
python monitor_backtest.py reports 10
```
Real-time monitoring of backtest results (checks every 10 seconds).

## What to Look For

### Green Flags ✅
- Sharpe > 0.60 (excellent risk-adjusted returns)
- Consistent daily profits
- Few consecutive losses
- Equity curve trending up with controlled drawdowns
- Trade distribution across all market conditions
- Win rate stable 40-55% range

### Yellow Flags ⚠️
- Large drawdown periods (> 15%)
- Sudden equity spikes (possible overfitting)
- Win rate < 35% or > 65% (suspicious)
- Clustering of trades in specific time windows
- Profit concentration in few winning trades

### Red Flags 🔴
- Sharpe < 0.40 (poor risk-adjusted returns)
- Negative CAGR (losing money)
- Max drawdown > 25% (excessive risk)
- Equity curve declining overall
- Highly clustered results (not robust)

## Next Steps After Completion

1. **View Results**
   ```bash
   python compare_backtests.py reports
   ```

2. **Analyze Trade Log**
   - Check win/loss distribution
   - Verify profit factor
   - Examine trade duration patterns

3. **Review Equity Curve**
   - Look for consistent uptrend
   - Identify drawdown periods
   - Calculate daily stats

4. **Validation Decision**
   - If Sharpe ≥ 0.60: Proceed to live trading
   - If Sharpe 0.40-0.60: Tune parameters
   - If Sharpe < 0.40: Review signal logic

## Professional Integration Validation

This backtest validates:
- ✓ Signal smoothing engine effectiveness across full year
- ✓ Conflict resolution handling diverse market conditions
- ✓ Professional risk sizing consistency
- ✓ Trailing stop profit capture
- ✓ System stability over extended period
- ✓ Scalability from short-term (2 weeks) to long-term (1 year)

## Success Criteria

The professional integration is considered **SUCCESSFUL** if:

```
✓ Sharpe Ratio ≥ 0.60 (vs 0.57 for 2-week backtest)
✓ CAGR ≥ 20% (5x improvement over 2-week)
✓ More than 150 trades (5x increase from 31)
✓ Win rate stable 40-50% across all periods
✓ Max drawdown controlled < 10%
✓ No significant equity curve deterioration
✓ Consistent daily/weekly profitability pattern
```

## Notes

- Full-year backtest provides more robust validation than short-term
- Includes diverse market conditions (trends, ranges, volatility changes)
- Larger sample size (200+ trades) ensures statistical significance
- Results less prone to curve-fitting bias
- Validates real-world sustainability of professional enhancements

**Status**: Executing full-year backtest with professional settings
**Expected Completion**: Within 10 minutes
**Monitor**: Use `python monitor_backtest.py reports` for live updates

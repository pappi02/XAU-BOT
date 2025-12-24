# News Gating & Economic Calendar Integration

## Overview

The bot now includes **economic calendar-based news gating** to prevent trading during high-impact events and degrade signal confidence during medium-impact events.

## Features

### 1. Economic Calendar (`utils/economic_calendar.py`)

- **EconomicCalendar**: Fetches upcoming economic events
  - Primary source: API integration (Investing.com or similar)
  - Fallback: Manually maintained list of major events (FOMC, NFP, ECB, etc.)
  - Supports high-impact (FOMC, NFP, ECB decisions) and medium-impact events (ISM, retail sales)

### 2. News-Aware Signal Filter (`utils/news_gate.py`)

- **NewsAwareSignalFilter**: Wraps signal generation with event awareness
  - **Gates trading** (blocks all signals) during high-impact events
  - **Degrades confidence** (reduces signal strength) near medium-impact events
  - **Requires higher confidence** near economic releases

### 3. Integration with Signal Generator

- Automatically applied in `signal_generator.py` when enabled
- Signals are checked against calendar before execution
- Gated signals return `HOLD` with reason annotation

## Configuration

In `config.py`:

```python
# Enable/disable economic calendar-based trading gating
NEWS_GATING_ENABLED = True

# High-impact event windows (e.g., FOMC, NFP, ECB decisions)
HIGH_IMPACT_GATE_BEFORE_MIN = 15   # Minutes before event to start gating
HIGH_IMPACT_GATE_AFTER_MIN = 30    # Minutes after event to continue gating

# Medium-impact event windows (e.g., ISM, retail sales)
MEDIUM_IMPACT_DEGRADE_BEFORE_MIN = 30  # Minutes before event to degrade
MEDIUM_IMPACT_DEGRADE_AFTER_MIN = 45   # Minutes after event to degrade

# Optional: Economic calendar API key
ECONOMIC_CALENDAR_API_KEY = os.getenv('ECONOMIC_CALENDAR_API_KEY')
```

In `.env` (optional):

```bash
ECONOMIC_CALENDAR_API_KEY=your_api_key_here
```

## How It Works

### High-Impact Events (Complete Gating)

**Examples:** FOMC decision, Non-Farm Payroll, ECB rate decision, BoE decision

**Behavior:**
- Trading is **completely blocked** within gating window
- Signals return `HOLD` with reason: `"🚫 Trading gated: USD NFP at 13:30"`
- Default windows: 15 min before, 30 min after

### Medium-Impact Events (Signal Degradation)

**Examples:** ISM Manufacturing, Retail Sales, CPI/PPI, Durable Goods

**Behavior:**
- Signal **confidence is reduced** by degradation factor
- Degradation factor depends on proximity and event impact
  - Far from events: `1.0` (no degradation)
  - 20 min before medium event: `0.8` (20% reduction)
  - 10 min before high event: `0.6` (40% reduction)
- Signal strength scaled proportionally
- Default windows: 30 min before, 45 min after

## Manual Event List (Fallback)

When no API key is provided, the calendar uses a manually maintained list of major recurring events:

- **US:** FOMC, NFP, CPI, PPI, Retail Sales, ISM, Jobless Claims
- **Eurozone:** ECB rate decisions, Economic Bulletin
- **UK:** BoE decisions, Governor speeches
- **Japan:** BoJ decisions, GDP
- **Switzerland:** SNB rate decisions
- **Australia:** RBA decisions

This list is updated quarterly. Event times are in **UTC**.

## Testing

Run the test suite:

```bash
python tests/test_news_gating.py
```

Tests cover:
1. Event detection from calendar
2. Proximity detection to events
3. Signal gating during high-impact
4. Signal degradation near medium-impact
5. Fallback to manual events
6. Configuration validation

## Usage Examples

### Checking if Trading is Gated

```python
from utils.news_gate import NewsAwareSignalFilter

filter = NewsAwareSignalFilter()
should_gate, reason = filter.should_gate_trading()

if should_gate:
    print(f"Trading blocked: {reason}")
else:
    print("Safe to trade")
```

### Applying Filters to Signals

```python
signal_dict = {
    'type': 'BUY',
    'confidence': 0.75,
    'reasons': ['Strong bullish setup']
}

filtered = filter.apply_signal_filters(signal_dict)

if filtered.get('gated'):
    print(f"Signal gated: {filtered['gate_reason']}")
else:
    print(f"Confidence: {filtered['confidence']:.2f}")
```

### Getting Degradation Factor

```python
from utils.economic_calendar import EconomicCalendar

calendar = EconomicCalendar()
factor = calendar.get_signal_degradation_factor()

print(f"Degradation factor: {factor:.2f}")
# 1.0 = no degradation, 0.3 = heavy degradation
```

## Disabling News Gating

To disable news gating entirely:

1. Set `NEWS_GATING_ENABLED = False` in `config.py`
2. Or pass `enable_news_gating=False` to `UnifiedSignalGenerator()`

```python
generator = UnifiedSignalGenerator(enable_news_gating=False)
```

## API Integration (Optional)

To enable live event data:

1. Get API key from Investing.com, Trading Economics, or similar service
2. Add to `.env`:
   ```bash
   ECONOMIC_CALENDAR_API_KEY=your_api_key_here
   ```
3. Calendar will automatically fetch real-time events

**Note:** Fallback to manual events works without API; real-time API provides more accuracy and additional events.

## Logging

News gating logs appear in the main log with prefixes:

- `⚠️  Trading gated due to: ...` — High-impact event blocking trade
- `📉 Signal confidence degraded: ...` — Medium-impact event reducing confidence
- `✅ News-aware signal filter initialized` — Startup confirmation

## Known Events Schedule

Major high-impact events typically occur on:

- **FOMC Decision:** Every 6 weeks (8 meetings/year)
- **Non-Farm Payroll:** First Friday of each month, 13:30 UTC
- **CPI/PPI:** Mid-month, 13:30 UTC
- **ECB Decision:** Every 6 weeks, 13:45 UTC
- **BoE Decision:** 8 meetings/year, 12:00 UTC
- **BoJ Decision:** 8 meetings/year, early morning UTC

See `utils/economic_calendar.py` for full manual event list.

## Troubleshooting

### "News gating initialization failed"

- Check that `pytz`, `requests` are installed
- Verify `utils/economic_calendar.py` and `utils/news_gate.py` exist
- Check logs for detailed error

### No Events Found

- Normal if no major events in next 2 days
- Fallback list covers recurring events only
- Consider adding API key for complete calendar

### Signal Still Executed During Event

- Check `NEWS_GATING_ENABLED = True` in config
- Verify signal generator initialized with `enable_news_gating=True`
- Check event time is within gating window
- Review logs for gating status

## Future Enhancements

- [ ] Integration with FXStreet or TradingEconomics API
- [ ] Currency-specific event filtering (only gate events affecting XAUUSD)
- [ ] Historical event impact analysis
- [ ] Adaptive gating windows based on realized impact
- [ ] Event surprise factor (actual vs forecast)

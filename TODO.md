# TODO: Implement 13 Factors for Automatic Trade Close

## Current Status: In Progress

### 1. Update Config (`config.py`)
- [x] Add configuration variables for all 13 auto-close factors
- [x] Add thresholds, enabled flags, and parameters for each factor

### 2. Enhance TradeExecutor (`execution/trade_executor.py`)
- [x] Add `should_close_trade()` method implementing all 13 factors
- [x] Add helper methods for each factor:
  - [x] `check_take_profit_reached()`
  - [x] `check_stop_loss_hit()`
  - [x] `check_trailing_stop()`
  - [x] `check_opposite_signal()`
  - [x] `check_signal_weakening()`
  - [x] `check_news_economic_event()`
  - [x] `check_volatility_spike()`
  - [x] `check_time_based_exit()`
  - [x] `check_market_session_end()`
  - [x] `check_break_of_structure()`
  - [x] `check_rr_ratio_reversal()`
  - [x] `check_portfolio_drawdown()`
  - [x] `check_correlation_conflict()`
- [x] Integrate with risk manager and indicators

### 3. Update Strategy (`strategies/strategy_basic.py`)
- [x] Modify `should_close_position()` to use new TradeExecutor logic
- [x] Add support for break of structure detection
- [x] Update method signatures to pass required data

### 4. Update Main Loop (`main.py`)
- [x] Modify position monitoring to use enhanced close logic
- [x] Add comprehensive logging for close reasons
- [x] Update close decision handling

### 5. Enhance Utils (if needed)
- [ ] Update `utils/news_reader.py` for economic event detection
- [ ] Add structure break detection utilities

### 6. Dynamic Lot Sizing Implementation
- [x] Add dynamic lot sizing configuration to config.py
- [x] Implement calculate_dynamic_lot_size() method in RiskManager
- [x] Add helper methods for market session, performance, and news impact
- [x] Integrate dynamic lot sizing into main.py trade execution
- [ ] Test dynamic lot sizing with various market conditions
- [ ] Validate lot size calculations and limits

### 7. Testing and Verification
- [ ] Test auto-close logic with various scenarios
- [ ] Verify all factors work correctly
- [ ] Add unit tests for new methods
- [ ] Validate integration with existing code
- [ ] Test dynamic lot sizing integration

### 8. Documentation
- [ ] Update docstrings for new methods
- [ ] Add comments explaining each factor
- [ ] Document configuration options
- [ ] Document dynamic lot sizing factors and multipliers

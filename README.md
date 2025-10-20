# XAU/USD Trading Bot

A sophisticated automated trading bot for XAU/USD (Gold vs US Dollar) pairs using MetaTrader 5, featuring advanced technical analysis, risk management, and real-time trading capabilities.

## Features

### Core Functionality
- **Real-Time Trading**: 24/7 automated trading with live market data
- **Analysis Mode**: Backtesting and signal generation on historical data
- **Phase 5 Enhanced Bot**: Advanced risk management with 13-factor auto-close logic
- **Multi-Timeframe Support**: M1, M5, M15, H1, H4, D1, W1, MN

### Technical Indicators
- Exponential Moving Averages (EMA)
- Relative Strength Index (RSI)
- Bollinger Bands
- Average True Range (ATR)
- Custom indicators for dynamic stop-loss and risk-reward ratios

### Risk Management
- Dynamic lot sizing based on signal strength, volatility, and market conditions
- 13-factor automatic position closing:
  - Take Profit & Stop Loss
  - Trailing Stop
  - Opposite Signal Detection
  - Signal Weakening
  - News & Economic Events
  - Volatility Spike Protection
  - Time-Based Exits
  - Market Session Management
  - Break of Structure Detection
  - Risk/Reward Ratio Reversal
  - Portfolio Drawdown Control
  - Correlation Risk Management
  - Trend Reversal Detection

### News Integration
- Real-time forex news sentiment analysis
- Automatic trade adjustments based on news impact
- Economic event awareness

### Data Sources
- MetaTrader 5 integration for live and historical data
- News API integration for market sentiment

## Installation

### Prerequisites
- Python 3.8+
- MetaTrader 5 terminal installed
- Demo or live trading account

### Setup
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd xau_bot
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv312
   venv312\Scripts\activate  # On Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   - Copy `.env.example` to `.env`
   - Fill in your MT5 credentials and API keys:
     ```
     MT5_ACCOUNT=your_account_number
     MT5_PASSWORD=your_password
     MT5_SERVER=your_server
     NEWS_API_KEY=your_news_api_key
     ```

5. Configure the bot in `config.py`:
   - Adjust trading parameters
   - Set risk management thresholds
   - Configure symbol and timeframe preferences

## Usage

### Running the Bot
Execute the main script:
```bash
python main.py
```

Choose from three modes:
1. **Real-Time Auto Trading**: Continuous automated trading
2. **Analysis Mode**: Historical analysis and backtesting
3. **Phase 5 Enhanced Bot**: Advanced trading with full risk management

### Configuration
Key settings in `config.py`:
- `TRADE_AMOUNT`: Base trade size in USD
- `RISK_PER_TRADE_PCT`: Risk percentage per trade
- `AUTO_CLOSE_ENABLED`: Enable/disable automatic position closing
- `DYNAMIC_LOT_SIZING_ENABLED`: Enable dynamic position sizing

### Monitoring
- Logs are written to console and files
- Dashboard available for performance monitoring
- Trade logging with detailed execution records

## Project Structure

```
xau_bot/
├── main.py                 # Main entry point
├── config.py              # Configuration settings
├── logger_config.py       # Logging setup
├── requirements.txt       # Python dependencies
├── trade_logger.py        # Trade logging utilities
├── dashboard.py           # Performance dashboard
├── TODO.md                # Development tasks
├── data/                  # Data handling
│   ├── connect_mt5.py     # MT5 connection
│   ├── fetch_candles.py   # Historical data
│   ├── fetch_live_data.py # Live data streaming
│   └── test_data.py       # Test data utilities
├── execution/             # Trade execution
│   └── trade_executor.py  # Order execution logic
├── indicators/            # Technical indicators
│   ├── ema.py            # Exponential Moving Average
│   ├── rsi.py            # Relative Strength Index
│   └── bollinger.py      # Bollinger Bands
├── risk/                  # Risk management
│   └── risk_manager.py    # Risk controls
├── strategies/            # Trading strategies
│   └── strategy_basic.py  # Basic trading strategy
├── tests/                 # Unit tests
│   ├── test_risk_manager.py
│   └── test_trade_executor.py
└── utils/                 # Utilities
    ├── indicators.py      # Indicator calculations
    ├── news_reader.py     # News analysis
    └── plot_utils.py      # Chart plotting
```

## Development

### Running Tests
```bash
python -m pytest tests/
```

### Adding New Indicators
1. Create indicator file in `indicators/`
2. Implement calculation function
3. Add to strategy in `strategies/strategy_basic.py`

### Customizing Risk Rules
Modify `risk/risk_manager.py` and update configurations in `config.py`

## Safety Warnings

⚠️ **Important**: This bot executes real trades. Use only with:
- Demo accounts for testing
- Small position sizes initially
- Proper risk management settings
- Understanding of automated trading risks

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is for educational and personal use. Commercial use requires proper licensing and regulatory compliance.

## Disclaimer

Trading cryptocurrencies and forex involves substantial risk of loss and is not suitable for every investor. Past performance does not guarantee future results. Use this software at your own risk.

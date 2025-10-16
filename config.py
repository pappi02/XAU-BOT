# Configuration file for XAU Bot
# Add your API keys, settings, etc. here

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Example configurations
API_KEY = os.getenv('API_KEY', 'your_api_key_here')
SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here')

# News API Key for forex news fetching
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '2287da19b4ca4f6a9d2711431ca2278b')  # Get from https://newsapi.org/

# Trading settings
TRADE_AMOUNT = 50  # in USD
LEVERAGE = 10

# Data settings
DATA_SOURCE = 'mt5'  # 'mt5' for MetaTrader 5, 'api' for other sources, 'file' for local files

# MT5 Settings
MT5_ACCOUNT = os.getenv('MT5_ACCOUNT')
if MT5_ACCOUNT in [None, '', 'None']:
    MT5_ACCOUNT = None
else:
    MT5_ACCOUNT = int(MT5_ACCOUNT) if MT5_ACCOUNT else None

MT5_PASSWORD = os.getenv('MT5_PASSWORD')
if MT5_PASSWORD in [None, '', 'None']:
    MT5_PASSWORD = None

MT5_SERVER = os.getenv('MT5_SERVER')
if MT5_SERVER in [None, '', 'None']:
    MT5_SERVER = None
MT5_TIMEOUT = 60000  # Connection timeout in milliseconds

# MT5 Path
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# Symbol settings
SYMBOL = 'XAUUSDm'  # Trading symbol (using micro lot version available in demo)
TIMEFRAME = 'M5'  # Timeframe: M1, M5, M15, H1, H4, D1, W1, MN
NUM_CANDLES = 1000  # Number of historical candles to fetch

# Strategy settings
EMA_FAST = 12
EMA_SLOW = 26
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD_DEV = 2

# Backtest settings
INITIAL_BALANCE = 50  # in USD
POSITION_SIZE_PCT = 0.5  # Position size as percentage of balance

# Logging
LOG_LEVEL = 'INFO'

# Trading / risk settings for Phase 5
TRADE_ACCOUNT_MODE = "demo"        # "demo" or "live"
SYMBOL_PHASE5 = "XAUUSDm" if TRADE_ACCOUNT_MODE == "demo" else "XAUUSDm"  # Use micro lot for demo, standard for live
CONTRACT_SIZE = 100.0              # common: 100 oz per standard lot (change to broker contract)
LEVERAGE_PHASE5 = 400               # leverage used (1:400)
RISK_PER_TRADE_PCT = 0.02          # risk 2% of account equity per trade
MAX_DAILY_LOSS_PCT = 0.30          # stop trading if daily loss > 30%
MAX_CONCURRENT_POSITIONS = 20
MIN_ACCOUNT_BALANCE = 0         # USD, minimum balance to allow trading
INITIAL_ACCOUNT_BALANCE = 50.0  # Initial account balance for emergency close calculation (set to your account's starting balance)
ATR_PERIOD = 14
TP_RISK_REWARD = 2.0               # take profit = R * stop_loss_distance
ORDER_RETRY = 3                    # times to retry order_send on failures
ORDER_DEVIATION = 20               # allowed slippage in points (depends on broker)

# Auto-close settings - Enhanced with 13 factors
AUTO_CLOSE_ENABLED = True          # Enable automatic position closing

# 1. Take Profit & Stop Loss
TP_RISK_REWARD = 2.0               # Take profit = R * stop_loss_distance

# 2. Trailing Stop
TRAILING_STOP_ENABLED = True       # Enable trailing stop loss
TRAIL_START_PIPS = 10              # Start trailing after this many pips profit
TRAIL_DISTANCE_PIPS = 5            # Distance to trail behind price

# 3. Opposite Signal
SIGNAL_REVERSAL_THRESHOLD = 60     # Minimum signal strength for reversal close (percentage)

# 4. Signal Weakening
SIGNAL_STRENGTH_DROP = 30          # Close if signal strength drops by this percentage
SIGNAL_WEAKENING_THRESHOLD = 40    # Minimum strength threshold for weakening check

# 5. News & Economic Events
NEWS_SENTIMENT_CLOSE = True        # Close positions on adverse news sentiment
HIGH_IMPACT_NEWS_CLOSE = True      # Close before high-impact news events
ECONOMIC_EVENT_CLOSE_MINUTES = 30  # Close positions this many minutes before high-impact events

# 6. Volatility Spike
VOLATILITY_SPIKE_ENABLED = True    # Enable volatility-based closing
ATR_SPIKE_MULTIPLIER = 2.0         # Close if ATR spikes above this multiplier of entry ATR

# 7. Time-Based Exit
MIN_HOLDING_TIME = 60              # Minimum seconds to hold position before auto-close
MAX_POSITION_AGE = 3600            # Maximum position age in seconds before force close
MAX_POSITION_AGE_MINUTES = 240     # Alternative: max age in minutes (4 hours)

# 8. Market Session
SESSION_END_CLOSE = True           # Close positions before session/market end
SESSION_END_BUFFER_MINUTES = 15    # Close this many minutes before session end

# 9. Break of Structure
BREAK_OF_STRUCTURE_ENABLED = True  # Enable structure break detection
FRACTAL_PERIOD = 5                 # Period for fractal detection

# 10. Risk/Reward Ratio Reversal
RR_REVERSAL_ENABLED = True         # Enable RR ratio reversal closing
RR_REVERSAL_THRESHOLD = 0.5        # Close if profit falls below this portion of max RR

# 11. Portfolio/Account Drawdown
PORTFOLIO_DRAWDOWN_CLOSE = True    # Enable portfolio-level drawdown closing
MAX_DAILY_LOSS_PCT = 0.30          # Stop trading if daily loss > 30%
EMERGENCY_CLOSE_THRESHOLD = 0.05   # Close all if account drops by this percentage

# 12. Correlation/Position Conflicts
CORRELATION_CLOSE_ENABLED = True   # Enable correlation-based closing
MAX_CORRELATED_POSITIONS = 2       # Maximum correlated positions allowed
CORRELATION_THRESHOLD = 0.7        # Correlation coefficient threshold

# 13. Trend Reversal
TREND_REVERSAL_CLOSE = True        # Close on detected trend reversals

# Dynamic Lot Sizing Configuration
DYNAMIC_LOT_SIZING_ENABLED = True  # Enable dynamic lot sizing adjustments

# Base risk settings
BASE_RISK_PERCENT = 1.0            # Base risk percentage of equity per trade

# Signal Strength Multipliers
SIGNAL_STRENGTH_HIGH_THRESHOLD = 80  # Signal strength > this = increase lot
SIGNAL_STRENGTH_LOW_THRESHOLD = 50   # Signal strength < this = decrease lot
SIGNAL_STRENGTH_HIGH_MULTIPLIER = 1.5  # Multiplier for high confidence signals
SIGNAL_STRENGTH_LOW_MULTIPLIER = 0.7   # Multiplier for low confidence signals

# Volatility (ATR) Multipliers
ATR_HIGH_THRESHOLD = 30           # ATR > this = high volatility, reduce lot
ATR_LOW_THRESHOLD = 10            # ATR < this = low volatility, increase lot
ATR_HIGH_MULTIPLIER = 0.6         # Multiplier for high volatility
ATR_LOW_MULTIPLIER = 1.2          # Multiplier for low volatility

# Market Session Multipliers
SESSION_ASIAN_MULTIPLIER = 0.8    # Asian session multiplier
SESSION_LONDON_MULTIPLIER = 1.2   # London session multiplier
SESSION_NEWYORK_MULTIPLIER = 1.2  # New York session multiplier

# Recent Performance Multipliers
WINNING_STREAK_MULTIPLIER = 1.2   # Multiplier after winning streak
LOSING_STREAK_MULTIPLIER = 0.7    # Multiplier after losing streak
WINNING_STREAK_LENGTH = 3          # Number of consecutive wins for streak

# News Impact Multipliers
NEWS_HIGH_IMPACT_MULTIPLIER = 0.5  # Multiplier during high-impact news
NEWS_MEDIUM_IMPACT_MULTIPLIER = 0.8  # Multiplier during medium-impact news

# Trade Type Multipliers
TRADE_TYPE_REVERSAL_MULTIPLIER = 0.8  # Multiplier for reversal trades
TRADE_TYPE_TREND_MULTIPLIER = 1.2     # Multiplier for trend-following trades

# Correlation Risk Multipliers
CORRELATION_RISK_MULTIPLIER = 0.7  # Multiplier when correlated positions exist
MAX_CORRELATED_POSITIONS = 2       # Max correlated positions before applying multiplier

# Risk Appetite Modes
RISK_MODE_AGGRESSIVE_MULTIPLIER = 2.0  # Aggressive mode base risk multiplier
RISK_MODE_BALANCED_MULTIPLIER = 1.0    # Balanced mode base risk multiplier
RISK_MODE_CONSERVATIVE_MULTIPLIER = 0.5  # Conservative mode base risk multiplier
DEFAULT_RISK_MODE = "balanced"      # "aggressive", "balanced", "conservative"

# Lot Size Limits
MIN_LOT_SIZE = 0.01                # Minimum allowed lot size
MAX_LOT_SIZE = 5.0                 # Maximum allowed lot size



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
TRADE_ACCOUNT_MODE = "live"        # "demo" or "live"
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

# ===== BREAK-EVEN STOP LOSS SETTINGS =====
BREAK_EVEN_ENABLED = True          # Enable break-even SL functionality
BREAK_EVEN_PROFIT_PIPS = 10        # Profit in pips before moving SL to break-even
BREAK_EVEN_BUFFER_PIPS = 2         # Buffer pips above entry for break-even SL

# ===== TRAILING STOP SETTINGS =====
TRAILING_STOP_MODIFICATION = True  # Enable trailing stop as SL modification (not close)
TRAILING_STOP_ACTIVATION_PIPS = 10 # Pips profit before trailing starts
TRAILING_STOP_DISTANCE_PIPS = 5    # Distance to trail behind price

# ===== PARTIAL CLOSE SETTINGS =====
PARTIAL_CLOSE_ENABLED = True       # Enable partial close functionality
PARTIAL_CLOSE_LEVELS = [           # Profit levels for partial closes (pips, percentage)
    {'profit_pips': 20, 'close_percentage': 0.25},  # Close 25% at 20 pips profit
    {'profit_pips': 40, 'close_percentage': 0.25},  # Close another 25% at 40 pips
    {'profit_pips': 60, 'close_percentage': 0.25},  # Close another 25% at 60 pips
]
PARTIAL_CLOSE_MIN_VOLUME = 0.01    # Minimum volume to leave after partial close

# ===== ENHANCED SIGNAL EXIT SETTINGS =====
ENHANCED_SIGNAL_EXIT = True        # Enable enhanced signal-based exits
SIGNAL_EXIT_STRENGTH_DROP = 30    # Close if signal strength drops by this percentage
SIGNAL_EXIT_OPPOSITE_THRESHOLD = 70 # Minimum strength for opposite signal exit
SIGNAL_EXIT_WEAKENING_WINDOW = 5  # Candles to check for signal weakening
TREND_REVERSAL_STRENGTH = 80      # Minimum strength for trend reversal exit

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

# ===== PHASE 7: MULTI-TIMEFRAME CONFLUENCE SETTINGS =====
MULTI_TIMEFRAME_ENABLED = True     # Enable multi-timeframe analysis

# Timeframe Configuration
ANALYSIS_TIMEFRAMES = {
    'M1': {'mt5_constant': 1, 'weight': 0.1, 'description': 'Entry timing'},
    'M5': {'mt5_constant': 5, 'weight': 0.15, 'description': 'Short-term trend'},
    'M15': {'mt5_constant': 15, 'weight': 0.2, 'description': 'Medium-term direction'},
    'M30': {'mt5_constant': 30, 'weight': 0.25, 'description': 'Volatility filter'},
    'H1': {'mt5_constant': 16385, 'weight': 0.15, 'description': 'Trend validation'},
    'H4': {'mt5_constant': 16388, 'weight': 0.15, 'description': 'Macro bias'}
}

# Confluence Thresholds
MIN_CONFLUENCE_FOR_TRADE = 0.7     # Minimum confluence score for trade entry (0-1)
STRONG_CONFLUENCE_THRESHOLD = 0.8  # Strong signal threshold
MAJORITY_AGREEMENT_RATIO = 0.6     # Minimum ratio of timeframes agreeing on direction

# Multi-Timeframe Analysis Settings
CANDLE_MULTIPLIER = {              # Multiplier for candle count per timeframe
    'M1': 1, 'M5': 1, 'M15': 2, 'M30': 3, 'H1': 4, 'H4': 6
}

# News Integration
NEWS_IMPACT_ENABLED = True         # Enable news sentiment impact on confluence
NEWS_MULTIPLIERS = {
    'bullish': 1.1,                 # Boost bullish signals
    'bearish': 0.9,                 # Dampen bearish signals
    'neutral': 1.0                  # No change
}

# Volatility Filtering
VOLATILITY_FILTER_ENABLED = True   # Enable volatility-based filtering
HIGH_VOLATILITY_THRESHOLD = 0.7    # High volatility threshold (0-1)
LOW_VOLATILITY_THRESHOLD = 0.3     # Low volatility threshold (0-1)
HIGH_VOLATILITY_MULTIPLIER = 0.9   # Reduce confidence in high volatility
LOW_VOLATILITY_MULTIPLIER = 1.1    # Increase confidence in low volatility

# Dynamic Position Sizing (Confluence-Based)
CONFLUENCE_LOT_MULTIPLIER = True   # Enable lot sizing based on confluence
BASE_LOT_SIZE = 0.01               # Base lot size
CONFLUENCE_LOT_RANGE = (0.5, 1.0)  # Lot multiplier range based on confluence (0.5-1.0)

# Risk-Reward Ratios (Confluence-Based)
STRONG_SIGNAL_RR = 3.0             # RR ratio for strong confluence (>= 0.8)
MODERATE_SIGNAL_RR = 2.0           # RR ratio for moderate confluence (0.7-0.8)
WEAK_SIGNAL_RR = 1.5               # RR ratio for weak signals (< 0.7)

# ATR-Based Stop Loss
ATR_SL_MULTIPLIER = 1.5            # ATR multiplier for stop loss distance
ATR_PERIOD_CONFLUENCE = 14         # ATR period for confluence analysis

# Signal-Driven Execution
SIGNAL_DRIVEN_TRADING = True       # Enable signal-driven vs time-triggered trading
ANALYSIS_INTERVAL_SECONDS = 60     # Analysis interval (every 60 seconds)
MAX_ANALYSIS_RETRIES = 3           # Maximum retries for failed analysis

# Confluence Dashboard Settings
CONFLUENCE_MATRIX_ENABLED = True   # Enable confluence matrix display
OVERALL_BIAS_DISPLAY = True        # Show overall market bias
TRADE_HISTORY_LENGTH = 5           # Number of recent trades to display
DYNAMIC_LOT_HISTORY = True         # Show dynamic lot adjustment history

# ===== PHASE 10: SMART EXIT MANAGEMENT & TRADE OPTIMIZATION =====
EXIT = {
    "TRAILING_ENABLED": True,
    "TRAILING_STEP_PTS": 50,         # points/price-units (adjust per symbol)
    "TRAILING_START_PTS": 30,        # start trailing after this profit
    "PARTIAL_CLOSE_ENABLED": True,
    "PARTIAL_CLOSE_AT_PTS": [30, 80], # 1st and 2nd partial close profit levels
    "PARTIAL_CLOSE_PERCENTS": [0.5, 0.5], # fractions of remaining volume to close
    "BREAKEVEN_TRIGGER_PTS": 20,     # move SL to breakeven after this profit
    "TIME_BASED_EXIT_MINUTES": 240,  # optional: max hold time
    "VOLATILITY_SPIKE_MULTIPLIER": 2.5, # if ATR > multiplier * entry_atr -> consider close
    "NEWS_CLOSE_BEFORE_MIN": 10,     # minutes before high-impact news to close positions
    "CLOSE_ON_OPPOSITE_SIGNAL": True,
    "MIN_PROFIT_TO_PARTIAL": 5,      # minimum profit to trigger partial (avoid tiny choppy closes)
    "MAX_DRAWDOWN_PERCENT_CLOSE_ALL": 0.2, # 20% daily drawdown triggers close all
}



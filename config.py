# Configuration file for XAU Bot
# Add your API keys, settings, etc. here

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
API_KEY = os.getenv('API_KEY', 'your_api_key_here')
SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here')
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '2287da19b4ca4f6a9d2711431ca2278b')  # Get from https://newsapi.org/

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
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"  # Path to MT5 terminal

# Trading Settings
TRADE_ACCOUNT_MODE = "live"  # "demo" or "live"
SYMBOL = 'XAUUSDm'  # Trading symbol (micro lot for demo)
SYMBOL_PHASE5 = 'XAUUSDm' if TRADE_ACCOUNT_MODE == "demo" else 'XAUUSDm'  # Use micro lot for demo, standard for live
CONTRACT_SIZE = 100.0  # 100 oz per standard lot (adjust for broker)
LEVERAGE = 400  # Leverage used (1:400)
LEVERAGE_PHASE5 = 400  # Leverage for Phase 5
RISK_PER_TRADE_PCT = 0.02  # Risk 2% of account equity per trade
MAX_DAILY_LOSS_PCT = 0.60  # Stop trading if daily loss > 30%
MAX_CONCURRENT_POSITIONS = 100  # Max open positions
MIN_ACCOUNT_BALANCE = 0  # Minimum balance to allow trading (USD)
INITIAL_ACCOUNT_BALANCE = 150.0  # Initial account balance for drawdown calculations
ORDER_RETRY = 3  # Times to retry order_send on failures
ORDER_DEVIATION = 20  # Allowed slippage in points

# Data Settings
DATA_SOURCE = 'mt5'  # 'mt5' for MetaTrader 5, 'api' for other sources, 'file' for local files
TIMEFRAME = 'M5'  # Timeframe: M1, M5, M15, H1, H4, D1, W1, MN
NUM_CANDLES = 1000  # Number of historical candles to fetch

# Strategy Settings
EMA_FAST = 12
EMA_SLOW = 26
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD_DEV = 2.0
ATR_PERIOD = 14
TP_RISK_REWARD = 2.5  # Take profit = R * stop_loss_distance

# Backtest Settings
POSITION_SIZE_PCT = 1.0  # Position size as percentage of balance

# Logging
LOG_LEVEL = 'INFO'

# Auto-close Settings (Enhanced for Phase 5)
AUTO_CLOSE_ENABLED = True  # Enable automatic position closing

# 1. Take Profit & Stop Loss
TP_RISK_REWARD = 2.5  # Take profit = R * stop_loss_distance

# 2. Trailing Stop
TRAILING_STOP_ENABLED = True  # Enable trailing stop loss
TRAIL_START_PIPS = 20  # Start trailing after 20 pips profit
TRAIL_DISTANCE_PIPS = 10  # Distance to trail behind price

# 3. Opposite Signal
SIGNAL_REVERSAL_THRESHOLD = 70  # Minimum signal strength for reversal close (percentage)

# 4. Signal Weakening
SIGNAL_WEAKENING_THRESHOLD = 30  # Minimum strength threshold for weakening check
SIGNAL_STRENGTH_DROP = 30  # Close if signal strength drops by this percentage (optional, not used in current TradeExecutor)

# 5. News & Economic Events
NEWS_SENTIMENT_CLOSE = True  # Close positions on adverse news sentiment (with score > 0.5)
HIGH_IMPACT_NEWS_CLOSE = True  # Close before high-impact news events
ECONOMIC_EVENT_CLOSE_MINUTES = 30  # Close positions this many minutes before high-impact events

# 6. Volatility Spike
VOLATILITY_SPIKE_ENABLED = True  # Enable volatility-based closing
ATR_SPIKE_MULTIPLIER = 2.0  # Close if ATR spikes above this multiplier of entry ATR

# 7. Time-Based Exit
MIN_HOLDING_TIME = 900  # Minimum holding time in seconds (15 minutes for M5)
MAX_POSITION_AGE = 86400  # Maximum position age in seconds (24 hours)
MAX_POSITION_AGE_MINUTES = 1440  # Alternative: max age in minutes (24 hours)

# 8. Market Session
SESSION_END_CLOSE = False  # Close positions before session/market end
SESSION_END_BUFFER_MINUTES = 15  # Close this many minutes before session end

# 9. Break of Structure
BREAK_OF_STRUCTURE_ENABLED = True  # Enable structure break detection
FRACTAL_PERIOD = 5  # Period for fractal detection

# 10. Risk/Reward Ratio Reversal
RR_REVERSAL_ENABLED = True  # Enable RR ratio reversal closing
RR_REVERSAL_THRESHOLD = 0.5  # Close if profit falls below this portion of max RR

# 11. Portfolio/Account Drawdown
PORTFOLIO_DRAWDOWN_CLOSE = True  # Enable portfolio-level drawdown closing
EMERGENCY_CLOSE_THRESHOLD = 0.35  # Close all if account drops by 35%

# 12. Correlation/Position Conflicts
CORRELATION_CLOSE_ENABLED = False  # Disable correlation-based closing (simplify for now)
MAX_CORRELATED_POSITIONS = 2  # Maximum correlated positions allowed
CORRELATION_THRESHOLD = 0.7  # Correlation coefficient threshold

# 13. Trend Reversal
TREND_REVERSAL_CLOSE = True  # Close on detected trend reversals

# Dynamic Lot Sizing Configuration
DYNAMIC_LOT_SIZING_ENABLED = True  # Enable dynamic lot sizing adjustments
BASE_RISK_PERCENT = 1.0  # Base risk percentage of equity per trade
SIGNAL_STRENGTH_HIGH_THRESHOLD = 75  # Signal strength > this = increase lot
SIGNAL_STRENGTH_LOW_THRESHOLD = 55  # Signal strength < this = decrease lot
SIGNAL_STRENGTH_HIGH_MULTIPLIER = 1.5  # Multiplier for high confidence signals
SIGNAL_STRENGTH_LOW_MULTIPLIER = 0.7  # Multiplier for low confidence signals
ATR_HIGH_THRESHOLD = 30  # ATR > this = high volatility, reduce lot
ATR_LOW_THRESHOLD = 10  # ATR < this = low volatility, increase lot
ATR_HIGH_MULTIPLIER = 0.6  # Multiplier for high volatility
ATR_LOW_MULTIPLIER = 1.2  # Multiplier for low volatility
SESSION_ASIAN_MULTIPLIER = 0.8  # Asian session multiplier
SESSION_LONDON_MULTIPLIER = 1.2  # London session multiplier
SESSION_NEWYORK_MULTIPLIER = 1.2  # New York session multiplier
WINNING_STREAK_MULTIPLIER = 1.2  # Multiplier after winning streak
LOSING_STREAK_MULTIPLIER = 0.7  # Multiplier after losing streak
WINNING_STREAK_LENGTH = 3  # Number of consecutive wins for streak
NEWS_HIGH_IMPACT_MULTIPLIER = 0.5  # Multiplier during high-impact news
NEWS_MEDIUM_IMPACT_MULTIPLIER = 0.8  # Multiplier during medium-impact news
TRADE_TYPE_REVERSAL_MULTIPLIER = 0.8  # Multiplier for reversal trades
TRADE_TYPE_TREND_MULTIPLIER = 1.2  # Multiplier for trend-following trades
CORRELATION_RISK_MULTIPLIER = 0.7  # Multiplier when correlated positions exist
RISK_MODE_AGGRESSIVE_MULTIPLIER = 2.0  # Aggressive mode base risk multiplier
RISK_MODE_BALANCED_MULTIPLIER = 1.2  # Balanced mode base risk multiplier
RISK_MODE_CONSERVATIVE_MULTIPLIER = 0.5  # Conservative mode base risk multiplier
DEFAULT_RISK_MODE = "balanced"  # "aggressive", "balanced", "conservative"
MIN_LOT_SIZE = 0.01  # Minimum allowed lot size
MAX_LOT_SIZE = 5.0  # Maximum allowed lot size
SCALING_ENABLED = True  # Enable scaling of lot sizes

#Trailing stop config
ADAPTIVE_TRAILING_STOP = True
CURRENT_ATR = 12.5
CURRENT_TREND_STRENGTH = 65
CURRENT_VOLATILITY = 1.8
CURRENT_NEWS_SENTIMENT = {'sentiment': 'bullish', 'avg_sentiment_score': 0.25}
TRAIL_START_PIPS = 25
CONTRACT_SIZE = 100000
TRAILING_STOP_MODIFICATION = True  # Enable trailing stop modification
TRAILING_STOP_ACTIVATION_PIPS = 25  # Profit threshold to start trailing (pips)
TRAILING_STOP_DISTANCE_PIPS = 10  # Distance to trail behind price (pips)

# SL Management Settings
BREAK_EVEN_ENABLED = True  # Enable break-even functionality
BREAK_EVEN_PROFIT_PIPS = 20  # Base profit threshold to trigger break-even (pips)
BREAK_EVEN_BUFFER_PIPS = 2  # Base buffer above entry price for break-even SL (pips)
BREAK_EVEN_ATR_MULTIPLIER = 0.5  # ATR multiplier for dynamic buffer (e.g., 0.5 * ATR)
BREAK_EVEN_TREND_STRENGTH_MULTIPLIER = 0.1  # Trend strength multiplier for buffer adjustment
BREAK_EVEN_NEWS_SENTIMENT_MULTIPLIER = 0.2  # News sentiment multiplier for buffer adjustment
BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER = 0.01  # Time since entry multiplier (pips per minute)
BREAK_EVEN_PROFIT_LEVEL_MULTIPLIER = 0.05  # Profit level multiplier for buffer adjustment

# Adaptive Scaling Settings
ADAPTIVE_SCALING_ENABLED = True  # Enable adaptive position scaling
SCALING_CHECK_INTERVAL = 300  # Check for scaling every 5 minutes (in seconds)
MAX_ADDITIONAL_POSITIONS = 3  # Maximum additional positions per original trade
MAX_TOTAL_EXPOSURE_MULTIPLIER = 3.0  # Maximum total exposure as multiplier of initial position
SCALING_SIGNAL_STRENGTH_THRESHOLD = 75  # Minimum signal strength to scale up (0-100)
SCALING_NEWS_FAVORABLE_THRESHOLD = 0.3  # Minimum news sentiment score to favor scaling up
SCALING_NEWS_ADVERSE_THRESHOLD = -0.3  # Maximum news sentiment score to allow scaling up
SCALING_PROFIT_THRESHOLD_PIPS = 15  # Minimum profit in pips before considering scaling up
SCALING_LOSS_THRESHOLD_PIPS = -10  # Maximum loss in pips before considering scaling down
SCALING_ATR_MULTIPLIER = 1.5  # ATR multiplier for volatility-based scaling decisions
SCALING_TREND_STRENGTH_MULTIPLIER = 1.2  # Trend strength multiplier for scaling decisions
SCALING_LOT_SIZE_MULTIPLIER = 0.5  # Multiplier for additional position lot sizes (relative to original)
SCALING_MIN_TIME_BETWEEN_ADDS = 600  # Minimum time between adding positions (seconds)
SCALING_MAX_TIME_SINCE_ENTRY = 3600  # Maximum time since entry to allow scaling up (seconds)
SCALING_CLOSE_ADVERSE_THRESHOLD = 60  # Signal strength threshold to scale down/close positions

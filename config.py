# ✅ SMART ADAPTIVE CONFIG v2.0

import os
import numpy as np
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

############################
# ✅ STATIC SYSTEM SETTINGS
############################
SYMBOL = 'XAUUSD'
TIMEFRAME = 'M5'
MIN_ACCOUNT_BALANCE = 5.0
LOG_LEVEL = "INFO"
POSITION_MODE = "hedge"

# API Keys
API_KEY = os.getenv('API_KEY', 'your_api_key_here')
SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')  # Get from https://newsapi.org/

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
MT5_PATH = os.getenv('MT5_PATH', r"C:\Program Files\MetaTrader 5\terminal64.exe")  # Path to MT5 terminal

# Data Settings
DATA_SOURCE = 'mt5'  # 'mt5' for MetaTrader 5, 'api' for other sources, 'file' for local files
NUM_CANDLES = 2000  # Increased for scalping with MTF confirmation

# Multi-Timeframe Settings for Scalping
MTF_ENABLED = True  # Enable multi-timeframe confirmation
MTF_CONFIRMATION_TFS = ['M15', 'M30', 'H1']  # Higher timeframes for confirmation

# Trading Settings
TRADE_ACCOUNT_MODE = os.getenv('TRADE_ACCOUNT_MODE', 'live')  # "demo" or "live"
ORDER_RETRY = 3  # Times to retry order_send on failures
ORDER_DEVIATION = 20  # Allowed slippage in points

############################
# ✅ RISK FRAMEWORK
############################
MIN_LOT_SIZE = 0.01
MAX_LOT_SIZE = 0.05
LOT_STEP = 0.01

# Risk per trade as percentage of account balance (env-backed, default 0.3%)
RISK_PER_TRADE_PCT = float(os.getenv('RISK_PER_TRADE_PCT', '0.3')) / 100.0  # Converted to decimal
# Validate range: 0.1% to 5%
if not (0.001 <= RISK_PER_TRADE_PCT <= 0.05):
    import warnings
    warnings.warn(f"RISK_PER_TRADE_PCT {RISK_PER_TRADE_PCT*100:.2f}% outside recommended range [0.1, 5]")

# === Dynamic Risk Control ===
# Baseline daily loss percentage (used when volatility is low)
BASE_MAX_DAILY_LOSS_PCT = 3.0

# Static max daily loss percentage (fallback when dynamic is disabled)
MAX_DAILY_LOSS_PCT = BASE_MAX_DAILY_LOSS_PCT

# Multiplier that adjusts based on volatility & recent performance
# The bot will dynamically scale the loss limit based on market conditions.
DYNAMIC_DAILY_LOSS_ENABLED = True

# Additional risk control for equity-based daily loss
LOSS_RECOVERY_FACTOR = 0.8      # Resume trading if equity recovers to 80% of limit
DYNAMIC_LOSS_TOLERANCE = True   # Enables adaptive adjustment based on performance

# Dynamic Risk Management Functions
def get_dynamic_risk_pct(account_equity: float, atr_value: float, win_streak: int, loss_streak: int) -> float:
    """Dynamic base risk percentage based on market conditions and performance"""
    base = 0.001  # start at 0.1%
    if atr_value > 2.0:
        base *= 0.6  # reduce risk in high volatility
    elif atr_value < 1.0:
        base *= 1.4  # increase slightly in calm market

    if win_streak >= 3:
        base *= 1.3
    if loss_streak >= 2:
        base *= 0.7

    # Equity scaling
    if account_equity > 1000:
        base *= 1.2  # increase risk as equity grows

    return min(max(base, 0.0005), 0.002)

def get_dynamic_max_daily_loss_pct(account_equity: float, volatility: float) -> float:
    """Dynamic max daily loss based on account size and volatility"""
    base = 0.20
    if account_equity < 100:
        base *= 0.8  # more conservative for small accounts
    if volatility > 1.5:
        base *= 0.9  # reduce in high volatility
    return base

def get_dynamic_max_total_drawdown_pct(account_equity: float, win_rate_30d: float) -> float:
    """Dynamic max drawdown based on account and recent performance"""
    base = 0.30
    if win_rate_30d < 40:
        base *= 0.8  # reduce drawdown limit if performing poorly
    if account_equity > 5000:
        base *= 1.2  # allow more drawdown for larger accounts
    return base

RISK_MODE = {
    "aggressive": 2.5,   # ✅ increased for more aggressive trading
    "balanced": 1.5,
    "conservative": 0.6
}
DEFAULT_RISK_MODE = "balanced"  # ✅ Set to Balanced Mode

############################
# ✅ DYNAMIC INDICATOR PARAMETERS
############################
def get_dynamic_ema_periods(trend_strength: float, timeframe_performance: dict) -> tuple:
    """Dynamic EMA periods based on trend strength and performance - SCALPING optimized"""
    # Shorter periods for scalping on M1/M5
    if trend_strength > 70:
        fast, slow = 8, 21  # faster response in strong trends
    elif trend_strength < 40:
        fast, slow = 5, 13   # very fast in choppy markets
    else:
        fast, slow = 8, 21  # scalping default

    # Adjust based on timeframe performance (lag detection)
    if timeframe_performance.get('ema_lag', 0) > 5:
        fast = max(3, fast - 2)
        slow = max(8, slow - 4)

    return fast, slow

def get_dynamic_rsi_period(market_regime: str, volatility: float) -> int:
    """Dynamic RSI period based on market regime - SCALPING optimized"""
    # Faster RSI for scalping
    if market_regime == 'trending':
        return 14  # moderate for trending markets
    elif market_regime == 'choppy':
        return 7   # very fast for range markets
    else:
        return 9  # scalping default (faster than standard 14)

def get_dynamic_bb_period(volatility: float, trend_strength: float) -> tuple:
    """Dynamic Bollinger Bands parameters"""
    if volatility > 1.5:
        period, std_dev = 15, 1.8  # tighter in high vol
    elif trend_strength > 60:
        period, std_dev = 25, 2.2  # wider in strong trends
    else:
        period, std_dev = 20, 2.0  # default

    return period, std_dev

def get_dynamic_atr_period(volatility: float) -> int:
    """Dynamic ATR period based on volatility"""
    if volatility > 2.0:
        return 10  # shorter for high vol
    elif volatility < 0.8:
        return 21  # longer for low vol
    else:
        return 14  # default

# SCALPING optimized constants (shorter periods for M1/M5)
EMA_FAST = 8
EMA_SLOW = 21
RSI_PERIOD = 7  # ✅ Changed from 9 to 7 for FASTER reversals (scalping)
BB_PERIOD = 15  # Shorter BB for scalping
BB_STD_DEV = 2
ATR_PERIOD = 10  # Faster ATR response for scalping

# ✅ NEW: PROFESSIONAL SCALPING INDICATOR PARAMETERS
# MACD - Fast periods for scalping
MACD_FAST = 8        # Faster than standard 12
MACD_SLOW = 17       # Slower than standard 26
MACD_SIGNAL = 9      # Signal line period (quicker reversal detection)

# VWAP - Intraday trading
VWAP_ENABLED = True
VWAP_SESSION_RESET = False  # Don't reset on daily open, use full intraday history

# Supertrend - Trend confirmation with ATR-based stops
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0
SUPERTREND_ENABLED = True

# Volume Analysis
VOLUME_SPIKE_THRESHOLD = 1.5     # 1.5x average volume = spike
VOLUME_SPIKE_PERIOD = 20         # Average volume over last 20 candles
VOLUME_ANALYSIS_ENABLED = True

# EMA Stack for scalping (8/13/21 Fibonacci-based)
EMA_STACK_PERIODS = [8, 13, 21]
EMA_STACK_ENABLED = True

# ✅ PROFESSIONAL 8-INDICATOR SCALPING SUITE PARAMETERS
# ==============================================================

# 1. RSI (Already defined above as RSI_PERIOD = 7)
RSI_OVERSOLD_LEVEL = 30       # Buy signal threshold
RSI_OVERBOUGHT_LEVEL = 70     # Sell signal threshold
RSI_EXTREME_OVERSOLD = 20     # Very strong buy signal
RSI_EXTREME_OVERBOUGHT = 80   # Very strong sell signal

# 2. Bollinger Bands (Enhanced for scalping)
BB_MIDDLE_LINE_ENABLED = True  # Use middle line for confirmation
BB_SCALPING_SQUEEZE = 1.5      # Bollinger squeeze sensitivity (lower = tighter)

# 3. Stochastic Oscillator (Enhanced for scalping - 20/80 levels per guide)
STOCHASTIC_ENABLED = True
STOCHASTIC_PERIOD = 14         # Default 14
STOCHASTIC_K_SMOOTH = 3        # Smoothing of %K
STOCHASTIC_D_SMOOTH = 3        # Smoothing of %D
STOCHASTIC_OVERSOLD = 20       # Professional scalping level (not 30)
STOCHASTIC_OVERBOUGHT = 80     # Professional scalping level (not 70)

# 4. Parabolic SAR (3-dot strategy per trading guide)
PARABOLIC_SAR_ENABLED = True
PARABOLIC_SAR_INITIAL_AF = 0.02    # Initial acceleration factor
PARABOLIC_SAR_MAX_AF = 0.2        # Maximum acceleration factor
PARABOLIC_SAR_AF_INCREMENT = 0.02 # AF increment per new extreme
PARABOLIC_SAR_MIN_DOTS = 3        # Require 3+ dots for reliable entry (per guide)

# 5. Commodity Channel Index - CCI (Extreme level detection ±200)
CCI_ENABLED = True
CCI_PERIOD = 20                    # Standard CCI period
CCI_OVERSOLD = -100               # Reversal entry threshold
CCI_OVERBOUGHT = 100              # Reversal exit threshold
CCI_EXTREME_OVERSOLD = -200       # Very high reversal probability
CCI_EXTREME_OVERBOUGHT = 200      # Very high reversal probability

# 6. MACD (Already optimized - 8/17/9)
# MACD_FAST = 8, MACD_SLOW = 17, MACD_SIGNAL = 9 (defined above)
MACD_HISTOGRAM_ENABLED = True     # Use histogram for divergence detection
MACD_DIVERGENCE_LOOKBACK = 5      # Lookback period for divergence detection

# 7. Ichimoku Cloud (Cloud breakout strategy)
ICHIMOKU_ENABLED = True
ICHIMOKU_TENKAN = 9              # Conversion line (fast)
ICHIMOKU_KIJUN = 26              # Base line (medium)
ICHIMOKU_SENKOU_B = 52           # Slow cloud line
ICHIMOKU_CHIKOU = 26             # Lagging span
ICHIMOKU_CLOUD_LOOKAHEAD = 26    # Plot cloud ahead
ICHIMOKU_BREAKOUT_ENABLED = True # Enter on cloud breakout

# 8. TRIX (Triple Exponential Average - momentum)
TRIX_ENABLED = True
TRIX_PERIOD = 15                  # Faster for scalping (standard is 15)
TRIX_ZERO_CROSS_ENABLED = True   # Trade zero-line crosses
TRIX_EXTREME_LEVEL = 1.0         # Extreme momentum threshold (±1.0)
TRIX_DIVERGENCE_ENABLED = True   # Detect divergence

############################
# ✅ PROFESSIONAL SETUP WEIGHTS
############################
# These weights are used in the master analyzer (scalping_setups_professional_8_indicators.py)
OSCILLATOR_REVERSAL_WEIGHT = 0.30        # Oscillator setup (RSI+CCI+Stochastic+BB)
CLOUD_BREAKOUT_WEIGHT = 0.35            # Cloud setup (Ichimoku+TRIX+MACD)
SAR_TREND_FOLLOWING_WEIGHT = 0.35       # SAR setup (Parabolic SAR+MACD+BB)

############################
# ✅ ADAPTIVE LOGIC SWITCHES
############################
ADAPTIVE_LOT_SIZING = True
ADAPTIVE_SL_TP = True
ADAPTIVE_SCALING = True
ADAPTIVE_SCALING_ENABLED = True
SCALING_CHECK_INTERVAL = 300  # Check for scaling opportunities every 5 minutes
ADAPTIVE_BREAK_EVEN = True

############################
# ✅ DYNAMIC SCALING & SIGNAL CONFIRMATION SETTINGS
############################
CONFIRMATION_CANDLE_WINDOW = 3      # Number of consecutive candles required for confirmation
SIGNAL_PERSISTENCE_THRESHOLD = 0.9  # 90% of signal strength must persist
SCALING_DELAY_SECONDS = 120         # Wait 2 minutes before adding next scale position
DYNAMIC_SCALING_EXPAND_LIMIT = 3    # Max additional positions per signal cluster (≤ MAX_CONCURRENT_POSITIONS)
MAX_CONCURRENT_POSITIONS = 20       # Base max concurrent positions (maximum 20 open trades allowed)

# Scaling gates: require minimum profit/margin before allowing more positions
SCALING_MIN_PROFIT_TO_ADD_POS = 50  # Require $50 floating profit before adding next position
SCALING_MIN_FREE_MARGIN_RATIO = 0.3 # Require 30% free margin before adding position
SCALING_PROFIT_MULTIPLIER = 1.5     # Each new scale position is 1.5x smaller than previous

############################
# ✅ NEWS & ECONOMIC CALENDAR GATING
############################
# Enable/disable economic calendar-based trading gating
NEWS_GATING_ENABLED = True

# High-impact event windows (e.g., FOMC, NFP, ECB decisions)
# Trading is completely blocked during these windows
HIGH_IMPACT_GATE_BEFORE_MIN = 15   # Minutes before event to start gating
HIGH_IMPACT_GATE_AFTER_MIN = 30    # Minutes after event to continue gating

# Medium-impact event windows (e.g., ISM, retail sales, inflation data)
# Signal confidence is degraded but trading is not blocked
MEDIUM_IMPACT_DEGRADE_BEFORE_MIN = 30  # Minutes before event to start degrading
MEDIUM_IMPACT_DEGRADE_AFTER_MIN = 45   # Minutes after event to continue degrading

# Optional: Economic calendar API key for real-time event data
# If not provided, falls back to manually maintained economic events list
ECONOMIC_CALENDAR_API_KEY = os.getenv('ECONOMIC_CALENDAR_API_KEY')

############################
# ✅ TRADING FEATURES
############################
AUTO_CLOSE_ENABLED = True
TRAILING_STOP_ENABLED = True
SCALING_ENABLED = True

############################
# ✅ SMART ADAPTIVE TRAILING SETTINGS
############################
SMART_TRAILING_ENABLED = True
SMART_TRAILING_CANDLE_CONFIRMATION = 2   # Wait for N candles in favor before trailing
SMART_TRAILING_COOLDOWN = 60             # Seconds before next trailing adjustment
SMART_TRAILING_BUFFER_MULTIPLIER = 0.5   # Use 50% of recent swing/ATR as safety margin
SMART_TRAILING_ATR_LOOKBACK = 14         # ATR lookback period
SMART_TRAILING_SWING_LOOKBACK = 5        # How many candles to look back for swing highs/lows
SMART_TRAILING_HOLD_ZONE = 0.3           # If retracement <30% of move, don't tighten SL

############################
# ✅ DYNAMIC SL / TP & R:R TUNING
############################
def get_dynamic_tp_rr_min_max(volatility: float, session: str, win_rate_24h: float) -> tuple:
    """Dynamic TP RR min/max based on volatility, session, and win rate - SCALPING optimized"""
    base_min, base_max = 1.2, 2.5  # Tighter for scalping (was 1.8, 4.0)

    # Adjust for volatility
    if volatility > 2.0:
        base_min *= 1.15  # slightly wider in high vol
        base_max *= 1.2
    elif volatility < 1.0:
        base_min *= 0.9  # tighter in low vol
        base_max *= 0.85

    # Session adjustments (scalping favors high-volume sessions)
    if session == "asian":
        base_min *= 0.85  # Very tight scalping in Asian session
        base_max *= 0.9
    elif session == "london":
        base_min *= 1.05  # Slightly wider in London
        base_max *= 1.1
    elif session == "newyork":
        base_min *= 1.1  # Wider in NY (more volatility)
        base_max *= 1.15

    # Win rate adjustments
    if win_rate_24h < 40:
        base_min *= 0.8  # reduce greed when losing
        base_max *= 0.85

    return base_min, base_max

def get_dynamic_atr_multiplier_sl(volatility: float, trend_strength: float) -> float:
    """Dynamic ATR multiplier for SL based on volatility and trend - SCALPING optimized"""
    base = 1.5  # Tighter SL for scalping (was 2.2)

    if volatility > 2.5:
        base *= 1.3  # wider SL in high vol
    elif volatility < 0.8:
        base *= 0.7  # very tight SL in low vol

    if trend_strength > 70:
        base *= 0.85  # tighter in strong trends

    return base

# SCALPING optimized constants (tighter TP/SL for quick profits)
TP_RR_MIN = 1.2  # Lower RR for scalping (was 1.8)
TP_RR_MAX = 2.5  # Lower max RR for scalping (was 4.0)
ATR_MULTIPLIER_SL = 1.5  # Tighter SL for scalping (was 2.2)
TP_RISK_REWARD = 1.5  # Scalping target (was 2.0)

############################
# ✅ DYNAMIC CONFIDENCE & SIGNAL STRENGTH RULES
############################
def get_dynamic_signal_strength_rules(signal_accuracy_last_trades: float, market_stability: float, active_signals: int) -> dict:
    """Dynamic signal strength rules based on recent accuracy and market conditions"""
    base_increase = 35
    base_decrease = 30

    # Adjust based on signal accuracy
    if signal_accuracy_last_trades > 70:
        base_increase *= 1.2  # increase confidence faster
        base_decrease *= 0.8  # decrease slower
    elif signal_accuracy_last_trades < 40:
        base_increase *= 0.8  # increase slower
        base_decrease *= 1.2  # decrease faster

    # Market stability adjustments
    if market_stability < 0.5:
        base_increase *= 0.9  # more cautious in unstable markets
        base_decrease *= 1.1

    # Active signals adjustments
    if active_signals > 5:
        base_increase *= 0.9  # reduce confidence with many signals

    return {
        'signal_strength_increase': base_increase,
        'signal_strength_decrease': base_decrease
    }

def get_dynamic_confluence_threshold(signal_accuracy_last_trades: float, market_stability: float) -> int:
    """Dynamic confluence threshold based on accuracy and stability"""
    base_threshold = 0

    if signal_accuracy_last_trades < 50:
        base_threshold = 1  # require at least one confluence if accuracy low
    if market_stability < 0.4:
        base_threshold = max(base_threshold, 1)  # require confluence in unstable markets

    return base_threshold

# Legacy constants for backward compatibility
SIGNAL_STRENGTH_INCREASE = 35
SIGNAL_STRENGTH_DECREASE = 30
STRATEGY_CONFLUENCE_THRESHOLD = 0

############################
# ✅ NEWS RISK MANAGEMENT
############################
NEWS_FILTER_ENABLED = True
NO_TRADE_BEFORE_NEWS_MIN = 10
NO_TRADE_AFTER_NEWS_MIN = 10
NEWS_CLOSE_STRONG_IMPACT = True

############################
# ✅ DYNAMIC SESSION-BASED TUNING
############################
def get_dynamic_session_risk_multipliers(current_session: str, real_time_atr: float, news_density: float, bot_performance_per_session: dict) -> dict:
    """Dynamic session risk multipliers based on real-time ATR, news, and performance"""
    base_multipliers = {
        "asian": 0.7,
        "london": 1.2,
        "newyork": 1.3
    }

    # Adjust for real-time ATR (volatility)
    if real_time_atr > 1.8:
        base_multipliers["newyork"] *= 1.2  # increase risk multiplier in high vol NY
        base_multipliers["london"] *= 1.1
    elif real_time_atr < 1.0:
        base_multipliers["asian"] *= 0.9  # decrease risk in low vol Asian

    # News density adjustments
    if news_density > 0.8:
        for session in base_multipliers:
            base_multipliers[session] *= 0.8  # reduce risk near high news density

    # Bot performance per session adjustments
    session_perf = bot_performance_per_session.get(current_session, {})
    win_rate = session_perf.get('win_rate', 50)
    if win_rate < 40:
        base_multipliers[current_session] *= 0.7  # reduce risk in losing sessions

    return base_multipliers

# Legacy constants for backward compatibility
SESSION_RISK_MULTIPLIERS = {
    "asian": 0.7,
    "london": 1.2,
    "newyork": 1.3
}

############################
# ✅ AUTO–OPTIMIZATION
############################
WIN_STREAK_TO_UPSHIFT = 2  # After 2 wins → increase lots
LOSS_STREAK_TO_DOWNSHIFT = 3  # After 3 losses → reduce lots temporarily
COOLDOWN_AFTER_LOSS_SEC = 90

# Bot Restart Cooldown Settings
RESTART_COOLDOWN_SECONDS = 30  # 30-second cooldown after bot restart before allowing trades

############################
# ✅ DYNAMIC SCALING LOGIC
############################
def get_dynamic_scaling_thresholds(trend_intensity: float, floating_profit_loss: float, execution_success_rate: float) -> dict:
    """Dynamic scaling thresholds based on trend, P&L, and success rate"""
    base_threshold = 70
    base_max_positions = 3

    # Trend intensity adjustments
    if trend_intensity > 80:
        base_threshold *= 0.9  # lower threshold for strong trends
        base_max_positions = 4
    elif trend_intensity < 50:
        base_threshold *= 1.1  # higher threshold for weak trends
        base_max_positions = 2

    # Execution success rate adjustments
    if execution_success_rate < 60:
        base_threshold *= 1.2  # higher threshold if scaling fails often
        base_max_positions = max(1, base_max_positions - 1)

    # Floating P&L adjustments
    if floating_profit_loss < -50:
        base_max_positions = max(1, base_max_positions - 1)  # reduce scaling in losses

    return {
        'signal_strength_threshold': base_threshold,
        'max_additional_positions': base_max_positions,
        'profit_threshold_pips': 20,
        'loss_threshold_pips': -30
    }

def get_dynamic_max_additional_positions(trend_intensity: float, execution_success_rate: float) -> int:
    """Dynamic max additional positions based on trend and success rate"""
    base = 3

    if trend_intensity > 80:
        base = 4
    elif trend_intensity < 50:
        base = 2

    if execution_success_rate < 60:
        base = max(1, base - 1)

    return base

# Legacy constants for backward compatibility
MAX_ADDITIONAL_POSITIONS = 3
SCALING_SIGNAL_STRENGTH_THRESHOLD = 70
SCALING_PROFIT_THRESHOLD_PIPS = 20
SCALING_LOSS_THRESHOLD_PIPS = -30
#TREND_STRONG_THRESHOLD = 65  # % score above which trend considered strong
#TREND_WEAK_THRESHOLD = 45



DYNAMIC_LOT_SIZING_ENABLED = True
BASE_RISK_PERCENT = 0.30

# Dynamic Lot Sizing Constants
SIGNAL_STRENGTH_HIGH_THRESHOLD = 75
SIGNAL_STRENGTH_LOW_THRESHOLD = 25
SIGNAL_STRENGTH_HIGH_MULTIPLIER = 1.5
SIGNAL_STRENGTH_LOW_MULTIPLIER = 0.7

ATR_HIGH_THRESHOLD = 2.0
ATR_LOW_THRESHOLD = 0.5
ATR_HIGH_MULTIPLIER = 0.8
ATR_LOW_MULTIPLIER = 1.2

WINNING_STREAK_MULTIPLIER = 1.3
LOSING_STREAK_MULTIPLIER = 0.6

NEWS_HIGH_IMPACT_MULTIPLIER = 0.5
NEWS_MEDIUM_IMPACT_MULTIPLIER = 0.8

TRADE_TYPE_REVERSAL_MULTIPLIER = 0.8
TRADE_TYPE_TREND_MULTIPLIER = 1.2

MAX_CORRELATED_POSITIONS = 3
CORRELATION_RISK_MULTIPLIER = 0.7

# Contract size for XAUUSD (Gold)
CONTRACT_SIZE = 100  # 1 lot = 100 oz of gold

# Symbol for risk calculations
SYMBOL_PHASE5 = SYMBOL

############################
# ✅ DYNAMIC TP_RISK_REWARD HELPER
############################
def get_dynamic_tp_rr(volatility: float, regime: str, signal_strength: float) -> float:
    """
    Dynamically compute Take-Profit to Stop-Loss ratio based on market context.

    Args:
        volatility (float): ATR or pip volatility (average true range).
        regime (str): 'trend', 'range', or 'volatile'.
        signal_strength (float): confidence of current signal (0.0–1.0).

    Returns:
        float: TP/SL ratio dynamically adjusted.
    """

    # Base ratio for calm conditions
    tp_rr = 1.5

    # Adjust for volatility
    if volatility > 10:
        tp_rr += 0.5     # Wider range, more reward needed
    elif volatility < 5:
        tp_rr -= 0.2     # Tight market, smaller TP makes sense

    # Adjust for regime
    if regime == "trend":
        tp_rr += 0.5
    elif regime == "range":
        tp_rr -= 0.2

    # Adjust for signal confidence
    tp_rr += (signal_strength - 0.5) * 1.0  # ±0.5 depending on strength

    # Clamp within reasonable range
    tp_rr = np.clip(tp_rr, 1.0, 4.0)

    return tp_rr

# ============================================================
# ✅ DYNAMIC SCALING MAX TIME SINCE ENTRY (Adaptive Function)
# ============================================================

def get_dynamic_scaling_max_time_since_entry(signal_strength: float, atr: float, trend_confidence: float) -> int:
    """
    Dynamically determine how long (in seconds) scaling should remain active after initial entry.
    Adapted to volatility, signal confidence, and market trend persistence.
    """
    # Normalize factors
    normalized_signal = min(max(signal_strength / 100.0, 0.2), 1.0)
    normalized_trend = min(max(trend_confidence / 100.0, 0.2), 1.0)
    normalized_atr = max(atr, 0.1)

    # Base scaling time (in seconds)
    base_time = 1200  # default 20 minutes for normal volatility

    # Adjust for volatility (longer duration for low ATR)
    atr_factor = 1.0 + (1.0 - min(normalized_atr / 3.0, 1.0))  # between 1.0 and 2.0

    # Adjust for strong signal persistence (extend scaling window)
    signal_factor = 1.0 + (normalized_signal * 0.6)

    # Adjust for strong trend (more time to scale)
    trend_factor = 1.0 + (normalized_trend * 0.4)

    # Final adaptive duration
    dynamic_time = base_time * atr_factor * signal_factor * trend_factor

    # Clamp between 10 min and 60 min
    dynamic_time = int(max(600, min(dynamic_time, 3600)))

    return dynamic_time

# === Adaptive Exposure Management ===
DYNAMIC_EXPOSURE_ENABLED = True

# --- Exposure management ---
BASE_MAX_TOTAL_EXPOSURE_MULTIPLIER = 2.0      # default base multiplier
EXPOSURE_SCALING_ENABLED = True               # allow dynamic adjustment
MAX_DYNAMIC_EXPOSURE_LIMIT = 3.5              # upper hard cap (safety)
MIN_DYNAMIC_EXPOSURE_LIMIT = 1.0              # lower bound

MIN_EXPOSURE_MULTIPLIER = 2.0
MAX_EXPOSURE_MULTIPLIER = 6.0

# These will guide the adaptive behavior:
EXPOSURE_BALANCE_SENSITIVITY = 0.00005     # adjusts exposure with balance
EXPOSURE_VOLATILITY_SENSITIVITY = 0.8      # adjusts exposure based on ATR or std dev
EXPOSURE_PERFORMANCE_SENSITIVITY = 0.6     # adjusts exposure based on recent performance

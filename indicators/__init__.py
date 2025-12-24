"""
Indicators Package - Professional-grade technical indicators for trading

This package consolidates all indicator implementations in separate, focused modules.
Each indicator is self-contained with core calculations and signal generation.

Available Indicators:
- EMA: Exponential Moving Average with trend signals
- RSI: Relative Strength Index with overbought/oversold detection
- Bollinger Bands: Volatility bands with breakout signals
- ATR: Average True Range for volatility measurement
- ADX: Average Directional Index for trend strength
- MACD: Moving Average Convergence Divergence
- Stochastic: Stochastic Oscillator with momentum
- VWAP: Volume Weighted Average Price (scalping)
- Supertrend: ATR-based trend following (scalping)
- Volume Analysis: Volume spikes and profile (scalping)
- Risk Utils: Dynamic position sizing and risk calculations
"""

# Import all indicator modules for convenience
from indicators.ema import (
    calculate_ema,
    add_ema_signals,
    get_ema_trend,
    get_ema_crossover_signal,
    is_bullish_ema,
    is_bearish_ema,
    calculate_ema_stack,
    is_ema_stack_bullish,
    is_ema_stack_bearish,
    get_ema_stack_alignment,
    add_ema_stack_signals
)

from indicators.rsi_clean_final import (
    calculate_rsi,
    add_rsi_signals,
    get_rsi_condition,
    get_rsi_signal,
    is_rsi_overbought,
    is_rsi_oversold,
    detect_rsi_divergence
)

from indicators.bollinger import (
    calculate_bollinger_bands,
    add_bollinger_signals,
    get_bollinger_signal,
    is_price_at_upper_band,
    is_price_at_lower_band,
    get_bollinger_squeeze_signal,
    get_bollinger_position
)

from indicators.atr import (
    calculate_atr,
    add_atr_signals,
    get_volatility_adjusted_sl,
    get_volatility_adjusted_tp,
    is_high_volatility,
    is_low_volatility
)

from indicators.adx import (
    calculate_adx,
    add_adx_signals,
    get_adx_trend_signal,
    is_strong_trend,
    is_weak_trend,
    is_very_strong_trend
)

from indicators.macd import (
    calculate_macd,
    add_macd_signals,
    get_macd_signal,
    get_macd_momentum,
    detect_macd_divergence
)

from indicators.stochastic import (
    calculate_stochastic,
    add_stochastic_signals,
    get_stochastic_signal,
    is_stoch_overbought,
    is_stoch_oversold,
    detect_stoch_divergence,
    get_stoch_momentum
)

from indicators.risk_utils import (
    calculate_dynamic_rr_ratio,
    calculate_dynamic_stop_loss,
    calculate_sl_from_atr,
    calculate_tp_from_atr,
    optimize_position_size
)

# NEW: Scalping indicators
from indicators.vwap import (
    calculate_vwap,
    calculate_vwap_bands,
    get_vwap_signal,
    get_vwap_distance,
    add_vwap_signals,
    is_price_above_vwap,
    is_price_below_vwap,
    detect_vwap_crossover
)

from indicators.supertrend import (
    calculate_supertrend,
    get_supertrend_signal,
    detect_supertrend_flip,
    calculate_supertrend_stop_loss,
    add_supertrend_signals,
    is_supertrend_bullish,
    is_supertrend_bearish,
    get_supertrend_strength
)

from indicators.volume_analysis import (
    detect_volume_spike,
    calculate_volume_profile,
    is_near_hvn,
    is_near_lvn,
    get_volume_trend,
    calculate_relative_volume,
    add_volume_analysis,
    get_volume_confirmation
)

# NEW: Professional scalping indicators (8-indicator suite)
from indicators.parabolic_sar import (
    calculate_parabolic_sar,
    count_consecutive_dots,
    get_parabolic_sar_signal,
    add_parabolic_sar_signals
)

from indicators.commodity_channel_index import (
    calculate_cci,
    get_cci_signal,
    get_cci_extremes,
    is_cci_overbought,
    is_cci_oversold,
    add_cci_signals
)

from indicators.trix import (
    calculate_trix,
    get_trix_signal,
    detect_trix_divergence,
    get_trix_strength,
    add_trix_signals
)

from indicators.ichimoku import (
    calculate_ichimoku,
    get_cloud_position,
    get_ichimoku_signal,
    detect_cloud_crossover,
    detect_chikou_signal,
    detect_tenkan_kijun_signal,
    add_ichimoku_signals
)

__all__ = [
    # EMA
    'calculate_ema',
    'add_ema_signals',
    'get_ema_trend',
    'get_ema_crossover_signal',
    'is_bullish_ema',
    'is_bearish_ema',
    'calculate_ema_stack',
    'is_ema_stack_bullish',
    'is_ema_stack_bearish',
    'get_ema_stack_alignment',
    'add_ema_stack_signals',
    
    # RSI
    'calculate_rsi',
    'add_rsi_signals',
    'get_rsi_condition',
    'get_rsi_signal',
    'is_rsi_overbought',
    'is_rsi_oversold',
    'detect_rsi_divergence',
    
    # Bollinger Bands
    'calculate_bollinger_bands',
    'add_bollinger_signals',
    'get_bollinger_signal',
    'is_price_at_upper_band',
    'is_price_at_lower_band',
    'get_bollinger_squeeze_signal',
    'get_bollinger_position',
    
    # ATR
    'calculate_atr',
    'add_atr_signals',
    'get_volatility_adjusted_sl',
    'get_volatility_adjusted_tp',
    'is_high_volatility',
    'is_low_volatility',
    
    # ADX
    'calculate_adx',
    'add_adx_signals',
    'get_adx_trend_signal',
    'is_strong_trend',
    'is_weak_trend',
    'is_very_strong_trend',
    
    # MACD
    'calculate_macd',
    'add_macd_signals',
    'get_macd_signal',
    'get_macd_momentum',
    'detect_macd_divergence',
    
    # Stochastic
    'calculate_stochastic',
    'add_stochastic_signals',
    'get_stochastic_signal',
    'is_stoch_overbought',
    'is_stoch_oversold',
    'detect_stoch_divergence',
    'get_stoch_momentum',
    
    # Risk Utils
    'calculate_dynamic_rr_ratio',
    'calculate_dynamic_stop_loss',
    'calculate_sl_from_atr',
    'calculate_tp_from_atr',
    'optimize_position_size',
    
    # VWAP (Scalping)
    'calculate_vwap',
    'calculate_vwap_bands',
    'get_vwap_signal',
    'get_vwap_distance',
    'add_vwap_signals',
    'is_price_above_vwap',
    'is_price_below_vwap',
    'detect_vwap_crossover',
    
    # Supertrend (Scalping)
    'calculate_supertrend',
    'get_supertrend_signal',
    'detect_supertrend_flip',
    'calculate_supertrend_stop_loss',
    'add_supertrend_signals',
    'is_supertrend_bullish',
    'is_supertrend_bearish',
    'get_supertrend_strength',
    
    # Volume Analysis (Scalping)
    'detect_volume_spike',
    'calculate_volume_profile',
    'is_near_hvn',
    'is_near_lvn',
    'get_volume_trend',
    'calculate_relative_volume',
    'add_volume_analysis',
    'get_volume_confirmation',
    
    # Parabolic SAR (Scalping)
    'calculate_parabolic_sar',
    'count_consecutive_dots',
    'get_parabolic_sar_signal',
    'add_parabolic_sar_signals',
    
    # CCI (Scalping)
    'calculate_cci',
    'get_cci_signal',
    'get_cci_extremes',
    'is_cci_overbought',
    'is_cci_oversold',
    'add_cci_signals',
    
    # TRIX (Scalping)
    'calculate_trix',
    'get_trix_signal',
    'detect_trix_divergence',
    'get_trix_strength',
    'add_trix_signals',
    
    # Ichimoku (Scalping)
    'calculate_ichimoku',
    'get_cloud_position',
    'get_ichimoku_signal',
    'detect_cloud_crossover',
    'detect_chikou_signal',
    'detect_tenkan_kijun_signal',
    'add_ichimoku_signals',
]

__version__ = '2.2.0'  # Updated with 8-indicator professional scalping suite
__description__ = 'Professional-grade technical indicators package for algorithmic trading'

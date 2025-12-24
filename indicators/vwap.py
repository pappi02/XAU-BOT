"""
VWAP (Volume Weighted Average Price) Indicator
Professional implementation for scalping - identifies intraday strength/weakness zones
"""

import pandas as pd
import numpy as np


def calculate_vwap(data: pd.DataFrame, use_session_reset: bool = False) -> pd.Series:
    """
    Calculate Volume Weighted Average Price (VWAP).
    
    VWAP represents the average price weighted by volume throughout the trading day.
    Formula: VWAP = Σ(Price × Volume) / Σ(Volume)
    
    Args:
        data: DataFrame with 'high', 'low', 'close', 'volume' columns
        use_session_reset: If True, reset VWAP at session start (requires 'time' index)
        
    Returns:
        pd.Series: VWAP values
    """
    if 'volume' not in data.columns:
        raise ValueError("VWAP requires 'volume' column")
    
    # Calculate typical price (average of high, low, close)
    typical_price = (data['high'] + data['low'] + data['close']) / 3.0
    
    # Calculate cumulative typical price * volume
    pv = typical_price * data['volume']
    
    if use_session_reset and isinstance(data.index, pd.DatetimeIndex):
        # Reset cumulative sum at start of each trading day
        date = data.index.date
        pv_cumsum = pv.groupby(date).cumsum()
        volume_cumsum = data['volume'].groupby(date).cumsum()
    else:
        # Simple cumulative sum (intraday VWAP)
        pv_cumsum = pv.cumsum()
        volume_cumsum = data['volume'].cumsum()
    
    # VWAP = cumulative (price * volume) / cumulative volume
    vwap = pv_cumsum / volume_cumsum
    
    return vwap


def calculate_vwap_bands(data: pd.DataFrame, std_multiplier: float = 1.0) -> tuple:
    """
    Calculate VWAP with standard deviation bands.
    
    Args:
        data: DataFrame with OHLCV data
        std_multiplier: Standard deviation multiplier for bands
        
    Returns:
        tuple: (vwap, upper_band, lower_band)
    """
    vwap = calculate_vwap(data)
    
    # Calculate standard deviation of typical price from VWAP
    typical_price = (data['high'] + data['low'] + data['close']) / 3.0
    variance = ((typical_price - vwap) ** 2 * data['volume']).cumsum() / data['volume'].cumsum()
    std_dev = np.sqrt(variance)
    
    upper_band = vwap + (std_dev * std_multiplier)
    lower_band = vwap - (std_dev * std_multiplier)
    
    return vwap, upper_band, lower_band


def get_vwap_signal(data: pd.DataFrame, sensitivity: float = 0.001) -> int:
    """
    Generate trading signal based on price position relative to VWAP.
    
    Args:
        data: DataFrame with OHLCV data
        sensitivity: Minimum distance from VWAP to trigger signal (as % of price)
        
    Returns:
        int: 1 (bullish - price above VWAP), -1 (bearish - price below VWAP), 0 (neutral)
    """
    if len(data) < 2:
        return 0
    
    vwap = calculate_vwap(data)
    current_price = float(data['close'].iloc[-1])
    current_vwap = float(vwap.iloc[-1])
    
    # Calculate distance from VWAP as percentage
    distance_pct = abs((current_price - current_vwap) / current_price)
    
    if distance_pct < sensitivity:
        return 0  # Too close to VWAP, neutral
    
    if current_price > current_vwap:
        return 1  # Bullish - price above VWAP
    elif current_price < current_vwap:
        return -1  # Bearish - price below VWAP
    else:
        return 0


def get_vwap_distance(data: pd.DataFrame, as_percentage: bool = True) -> float:
    """
    Calculate distance of current price from VWAP.
    
    Args:
        data: DataFrame with OHLCV data
        as_percentage: Return distance as percentage of price
        
    Returns:
        float: Distance from VWAP (positive if above, negative if below)
    """
    if len(data) < 1:
        return 0.0
    
    vwap = calculate_vwap(data)
    current_price = float(data['close'].iloc[-1])
    current_vwap = float(vwap.iloc[-1])
    
    distance = current_price - current_vwap
    
    if as_percentage:
        return (distance / current_price) * 100.0
    else:
        return distance


def add_vwap_signals(data: pd.DataFrame, std_multiplier: float = 1.0) -> pd.DataFrame:
    """
    Add VWAP and related signals to DataFrame.
    
    Args:
        data: DataFrame with OHLCV data
        std_multiplier: Multiplier for VWAP bands
        
    Returns:
        DataFrame with added columns: 'vwap', 'vwap_upper', 'vwap_lower', 
                                      'vwap_signal', 'vwap_distance'
    """
    data = data.copy()
    
    # Calculate VWAP and bands
    vwap, upper, lower = calculate_vwap_bands(data, std_multiplier)
    
    data['vwap'] = vwap
    data['vwap_upper'] = upper
    data['vwap_lower'] = lower
    
    # Add signal
    data['vwap_signal'] = 0
    data.loc[data['close'] > data['vwap'], 'vwap_signal'] = 1
    data.loc[data['close'] < data['vwap'], 'vwap_signal'] = -1
    
    # Add distance
    data['vwap_distance'] = ((data['close'] - data['vwap']) / data['close']) * 100.0
    
    return data


def is_price_above_vwap(data: pd.DataFrame, buffer_pct: float = 0.0) -> bool:
    """
    Check if current price is above VWAP.
    
    Args:
        data: DataFrame with OHLCV data
        buffer_pct: Buffer percentage to avoid false signals near VWAP
        
    Returns:
        bool: True if price is above VWAP + buffer
    """
    if len(data) < 1:
        return False
    
    vwap = calculate_vwap(data)
    current_price = float(data['close'].iloc[-1])
    current_vwap = float(vwap.iloc[-1])
    
    buffer = current_vwap * (buffer_pct / 100.0)
    
    return current_price > (current_vwap + buffer)


def is_price_below_vwap(data: pd.DataFrame, buffer_pct: float = 0.0) -> bool:
    """
    Check if current price is below VWAP.
    
    Args:
        data: DataFrame with OHLCV data
        buffer_pct: Buffer percentage to avoid false signals near VWAP
        
    Returns:
        bool: True if price is below VWAP - buffer
    """
    if len(data) < 1:
        return False
    
    vwap = calculate_vwap(data)
    current_price = float(data['close'].iloc[-1])
    current_vwap = float(vwap.iloc[-1])
    
    buffer = current_vwap * (buffer_pct / 100.0)
    
    return current_price < (current_vwap - buffer)


def detect_vwap_crossover(data: pd.DataFrame, lookback: int = 2) -> str:
    """
    Detect VWAP crossover in recent candles.
    
    Args:
        data: DataFrame with OHLCV data
        lookback: Number of candles to look back for crossover
        
    Returns:
        str: 'bullish_cross' (price crossed above VWAP), 
             'bearish_cross' (price crossed below VWAP), 
             'none' (no cross)
    """
    if len(data) < lookback + 1:
        return 'none'
    
    vwap = calculate_vwap(data)
    closes = data['close'].tail(lookback + 1)
    vwap_vals = vwap.tail(lookback + 1)
    
    # Check for bullish crossover (price was below, now above)
    if closes.iloc[-lookback] < vwap_vals.iloc[-lookback] and closes.iloc[-1] > vwap_vals.iloc[-1]:
        return 'bullish_cross'
    
    # Check for bearish crossover (price was above, now below)
    if closes.iloc[-lookback] > vwap_vals.iloc[-lookback] and closes.iloc[-1] < vwap_vals.iloc[-1]:
        return 'bearish_cross'
    
    return 'none'

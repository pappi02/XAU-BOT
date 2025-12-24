"""
Supertrend Indicator - Professional implementation for scalping
Provides quick buy/sell signals with ATR-based trailing stop
"""

import pandas as pd
import numpy as np
from indicators.atr import calculate_atr


def calculate_supertrend(data: pd.DataFrame, 
                         period: int = 10, 
                         multiplier: float = 3.0) -> tuple:
    """
    Calculate Supertrend indicator.
    
    Supertrend uses ATR to create a trailing stop that flips above/below price.
    - When Supertrend is below price: Uptrend (buy signal)
    - When Supertrend is above price: Downtrend (sell signal)
    
    Args:
        data: DataFrame with 'high', 'low', 'close' columns
        period: ATR period (default 10 for scalping)
        multiplier: ATR multiplier for bands (default 3.0)
        
    Returns:
        tuple: (supertrend, direction)
            - supertrend: pd.Series with Supertrend line values
            - direction: pd.Series with 1 (uptrend) or -1 (downtrend)
    """
    if len(data) < period:
        raise ValueError(f"Insufficient data for Supertrend (need {period} candles)")
    
    # Calculate ATR
    atr = calculate_atr(data, period=period)
    
    # Calculate basic bands
    hl_avg = (data['high'] + data['low']) / 2.0
    upper_band = hl_avg + (multiplier * atr)
    lower_band = hl_avg - (multiplier * atr)
    
    # Initialize arrays
    supertrend = pd.Series(index=data.index, dtype=float)
    direction = pd.Series(index=data.index, dtype=int)
    
    # First value
    supertrend.iloc[period] = lower_band.iloc[period]
    direction.iloc[period] = 1
    
    # Calculate Supertrend
    for i in range(period + 1, len(data)):
        curr_close = data['close'].iloc[i]
        prev_close = data['close'].iloc[i-1]
        curr_upper = upper_band.iloc[i]
        curr_lower = lower_band.iloc[i]
        prev_supertrend = supertrend.iloc[i-1]
        
        # Basic band calculation with persistence
        if curr_lower > prev_supertrend or prev_close < prev_supertrend:
            basic_lower = curr_lower
        else:
            basic_lower = max(curr_lower, prev_supertrend)
        
        if curr_upper < prev_supertrend or prev_close > prev_supertrend:
            basic_upper = curr_upper
        else:
            basic_upper = min(curr_upper, prev_supertrend)
        
        # Determine direction and Supertrend value
        if curr_close > basic_upper:
            # Uptrend
            supertrend.iloc[i] = basic_lower
            direction.iloc[i] = 1
        elif curr_close < basic_lower:
            # Downtrend
            supertrend.iloc[i] = basic_upper
            direction.iloc[i] = -1
        else:
            # Continue previous trend
            prev_dir = direction.iloc[i-1]
            if prev_dir == 1:
                supertrend.iloc[i] = basic_lower
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = basic_upper
                direction.iloc[i] = -1
    
    return supertrend, direction


def get_supertrend_signal(data: pd.DataFrame,
                          period: int = 10,
                          multiplier: float = 3.0) -> int:
    """
    Get current Supertrend trading signal.
    
    Args:
        data: DataFrame with OHLC data
        period: ATR period
        multiplier: ATR multiplier
        
    Returns:
        int: 1 (buy - uptrend), -1 (sell - downtrend), 0 (insufficient data)
    """
    if len(data) < period + 1:
        return 0
    
    try:
        _, direction = calculate_supertrend(data, period, multiplier)
        return int(direction.iloc[-1])
    except:
        return 0


def detect_supertrend_flip(data: pd.DataFrame,
                           period: int = 10,
                           multiplier: float = 3.0,
                           lookback: int = 2) -> str:
    """
    Detect recent Supertrend direction flip (entry signal).
    
    Args:
        data: DataFrame with OHLC data
        period: ATR period
        multiplier: ATR multiplier
        lookback: Candles to check for flip
        
    Returns:
        str: 'buy_flip' (flipped to uptrend), 'sell_flip' (flipped to downtrend), 
             'no_flip' (no change)
    """
    if len(data) < period + lookback:
        return 'no_flip'
    
    try:
        _, direction = calculate_supertrend(data, period, multiplier)
        
        # Check recent directions
        recent_dirs = direction.tail(lookback + 1)
        
        # Buy flip: was -1, now 1
        if recent_dirs.iloc[-lookback] == -1 and recent_dirs.iloc[-1] == 1:
            return 'buy_flip'
        
        # Sell flip: was 1, now -1
        if recent_dirs.iloc[-lookback] == 1 and recent_dirs.iloc[-1] == -1:
            return 'sell_flip'
        
        return 'no_flip'
    except:
        return 'no_flip'


def calculate_supertrend_stop_loss(data: pd.DataFrame,
                                   direction: int,
                                   period: int = 10,
                                   multiplier: float = 3.0,
                                   atr_multiplier: float = 1.5) -> float:
    """
    Calculate stop-loss based on Supertrend and ATR.
    
    For long positions: SL = Supertrend line or (entry - ATR * multiplier)
    For short positions: SL = Supertrend line or (entry + ATR * multiplier)
    
    Args:
        data: DataFrame with OHLC data
        direction: Trade direction (1 for long, -1 for short)
        period: ATR period
        multiplier: Supertrend multiplier
        atr_multiplier: ATR multiplier for fallback SL
        
    Returns:
        float: Stop-loss price
    """
    if len(data) < period + 1:
        return 0.0
    
    try:
        supertrend, _ = calculate_supertrend(data, period, multiplier)
        atr = calculate_atr(data, period=period)
        
        current_price = float(data['close'].iloc[-1])
        current_supertrend = float(supertrend.iloc[-1])
        current_atr = float(atr.iloc[-1])
        
        if direction == 1:
            # Long position: SL below price
            # Use Supertrend line or ATR-based SL, whichever is tighter
            atr_sl = current_price - (current_atr * atr_multiplier)
            return max(current_supertrend, atr_sl)
        else:
            # Short position: SL above price
            atr_sl = current_price + (current_atr * atr_multiplier)
            return min(current_supertrend, atr_sl)
    except:
        # Fallback to ATR-based SL
        atr = calculate_atr(data, period=period)
        current_price = float(data['close'].iloc[-1])
        current_atr = float(atr.iloc[-1])
        
        if direction == 1:
            return current_price - (current_atr * atr_multiplier)
        else:
            return current_price + (current_atr * atr_multiplier)


def add_supertrend_signals(data: pd.DataFrame,
                           period: int = 10,
                           multiplier: float = 3.0) -> pd.DataFrame:
    """
    Add Supertrend columns to DataFrame.
    
    Args:
        data: DataFrame with OHLC data
        period: ATR period
        multiplier: ATR multiplier
        
    Returns:
        DataFrame with added columns: 'supertrend', 'supertrend_direction'
    """
    data = data.copy()
    
    if len(data) < period:
        data['supertrend'] = np.nan
        data['supertrend_direction'] = 0
        return data
    
    supertrend, direction = calculate_supertrend(data, period, multiplier)
    
    data['supertrend'] = supertrend
    data['supertrend_direction'] = direction
    
    return data


def is_supertrend_bullish(data: pd.DataFrame,
                          period: int = 10,
                          multiplier: float = 3.0) -> bool:
    """
    Check if Supertrend is currently bullish (uptrend).
    
    Args:
        data: DataFrame with OHLC data
        period: ATR period
        multiplier: ATR multiplier
        
    Returns:
        bool: True if in uptrend (Supertrend below price)
    """
    signal = get_supertrend_signal(data, period, multiplier)
    return signal == 1


def is_supertrend_bearish(data: pd.DataFrame,
                          period: int = 10,
                          multiplier: float = 3.0) -> bool:
    """
    Check if Supertrend is currently bearish (downtrend).
    
    Args:
        data: DataFrame with OHLC data
        period: ATR period
        multiplier: ATR multiplier
        
    Returns:
        bool: True if in downtrend (Supertrend above price)
    """
    signal = get_supertrend_signal(data, period, multiplier)
    return signal == -1


def get_supertrend_strength(data: pd.DataFrame,
                            period: int = 10,
                            multiplier: float = 3.0,
                            lookback: int = 20) -> float:
    """
    Calculate Supertrend trend strength based on consecutive candles in same direction.
    
    Args:
        data: DataFrame with OHLC data
        period: ATR period
        multiplier: ATR multiplier
        lookback: Maximum candles to look back
        
    Returns:
        float: Strength 0-100 based on trend persistence
    """
    if len(data) < period + lookback:
        return 0.0
    
    try:
        _, direction = calculate_supertrend(data, period, multiplier)
        recent_directions = direction.tail(min(lookback, len(direction)))
        
        current_direction = recent_directions.iloc[-1]
        
        # Count consecutive candles in same direction
        consecutive = 0
        for i in range(len(recent_directions) - 1, -1, -1):
            if recent_directions.iloc[i] == current_direction:
                consecutive += 1
            else:
                break
        
        # Strength: percentage of lookback period in same direction
        strength = min(100.0, (consecutive / lookback) * 100.0)
        
        return float(strength)
    except:
        return 0.0

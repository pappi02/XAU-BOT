# adx.py - Average Directional Index (ADX) indicator

import pandas as pd
import numpy as np

def calculate_adx(data, period=14):
    """
    Calculate Average Directional Index (ADX) - measures trend strength.
    ADX > 25 indicates a strong trend, ADX < 20 indicates a weak trend.
    
    Args:
        data (pd.DataFrame): OHLC data with 'high', 'low', 'close' columns
        period (int): ADX period (default: 14)
    
    Returns:
        tuple: (ADX series, +DI series, -DI series)
    """
    if not all(col in data.columns for col in ['high', 'low', 'close']):
        raise ValueError("Data must contain 'high', 'low', 'close' columns")
    
    high = data['high'].values
    low = data['low'].values
    close = data['close'].values
    
    # Calculate True Range
    tr1 = high - low
    tr2 = np.abs(high - np.roll(close, 1))
    tr3 = np.abs(low - np.roll(close, 1))
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    tr[0] = tr1[0]
    
    # Calculate Directional Movement
    up_move = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    # Smooth the values
    plus_dm_smooth = pd.Series(plus_dm).ewm(span=period, adjust=False).mean()
    minus_dm_smooth = pd.Series(minus_dm).ewm(span=period, adjust=False).mean()
    tr_smooth = pd.Series(tr).ewm(span=period, adjust=False).mean()
    
    # Calculate DI
    plus_di = 100 * (plus_dm_smooth / tr_smooth)
    minus_di = 100 * (minus_dm_smooth / tr_smooth)
    
    # Calculate ADX
    di_diff = np.abs(plus_di - minus_di)
    di_sum = plus_di + minus_di
    di_ratio = di_diff / di_sum
    di_ratio[di_sum == 0] = 0
    adx = 100 * pd.Series(di_ratio).ewm(span=period, adjust=False).mean()
    
    return pd.Series(adx), pd.Series(plus_di), pd.Series(minus_di)

def add_adx_signals(data, period=14, strong_threshold=25, weak_threshold=20):
    """
    Add ADX and directional indicators to data.
    
    Args:
        data (pd.DataFrame): OHLC data
        period (int): ADX period
        strong_threshold (int): ADX threshold for strong trend
        weak_threshold (int): ADX threshold for weak trend
    
    Returns:
        pd.DataFrame: Data with ADX signals added
    """
    df = data.copy()
    
    adx, plus_di, minus_di = calculate_adx(df, period)
    
    df['ADX'] = adx
    df['PLUS_DI'] = plus_di
    df['MINUS_DI'] = minus_di
    
    # Trend strength classification
    df['trend_strength'] = 'weak'
    df.loc[df['ADX'] > strong_threshold, 'trend_strength'] = 'strong'
    df.loc[df['ADX'].between(weak_threshold, strong_threshold), 'trend_strength'] = 'moderate'
    
    # Trend direction
    df['adx_trend'] = 'neutral'
    df.loc[df['PLUS_DI'] > df['MINUS_DI'], 'adx_trend'] = 'bullish'
    df.loc[df['PLUS_DI'] < df['MINUS_DI'], 'adx_trend'] = 'bearish'
    
    return df

def get_adx_trend_signal(adx_value, plus_di, minus_di):
    """
    Get trend direction and strength from ADX.
    
    Args:
        adx_value (float): ADX value
        plus_di (float): +DI value
        minus_di (float): -DI value
    
    Returns:
        tuple: (trend_direction, trend_strength)
            trend_direction: 1 (bullish), -1 (bearish), 0 (neutral)
            trend_strength: 'strong', 'moderate', 'weak'
    """
    if adx_value < 20:
        return 0, 'weak'
    
    # Determine direction
    direction = 1 if plus_di > minus_di else -1
    
    # Determine strength
    if adx_value > 40:
        strength = 'very_strong'
    elif adx_value > 25:
        strength = 'strong'
    else:
        strength = 'moderate'
    
    return direction, strength

def is_strong_trend(adx_value):
    """Check if ADX indicates a strong trend."""
    return adx_value > 25

def is_weak_trend(adx_value):
    """Check if ADX indicates a weak trend (ranging)."""
    return adx_value < 20

def is_very_strong_trend(adx_value):
    """Check if ADX indicates a very strong trend."""
    return adx_value > 40

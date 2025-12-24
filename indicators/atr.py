# atr.py - Average True Range indicator

import pandas as pd
import numpy as np

def calculate_atr(data, period=14):
    """
    Calculate Average True Range (ATR) - measures volatility.
    
    Args:
        data (pd.DataFrame): OHLC data with 'high', 'low', 'close' columns
        period (int): ATR period (default: 14)
    
    Returns:
        pd.Series: ATR values
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
    tr[0] = tr1[0]  # First value is just high - low
    
    # Calculate ATR as exponential moving average
    atr = pd.Series(tr).ewm(span=period, adjust=False).mean()
    
    return atr

def add_atr_signals(data, period=14):
    """
    Add ATR to dataframe and identify volatility zones.
    
    Args:
        data (pd.DataFrame): OHLC data
        period (int): ATR period
    
    Returns:
        pd.DataFrame: Data with ATR and volatility signals added
    """
    df = data.copy()
    
    # Calculate ATR
    df['ATR'] = calculate_atr(df, period)
    
    # Calculate ATR average for volatility classification
    df['ATR_MA'] = df['ATR'].rolling(window=20).mean()
    
    # Volatility classification
    df['volatility_level'] = 'normal'
    df.loc[df['ATR'] > df['ATR_MA'] * 1.3, 'volatility_level'] = 'high'
    df.loc[df['ATR'] < df['ATR_MA'] * 0.7, 'volatility_level'] = 'low'
    
    return df

def get_volatility_adjusted_sl(atr_value, base_multiplier=1.5):
    """
    Get volatility-adjusted stop loss multiplier based on ATR.
    
    Args:
        atr_value (float): Current ATR value
        base_multiplier (float): Base SL multiplier
    
    Returns:
        float: Adjusted SL multiplier
    """
    if not atr_value or atr_value <= 0:
        return base_multiplier
    
    # Higher ATR means wider stops needed
    if atr_value > 3.0:
        return base_multiplier * 1.3  # High volatility
    elif atr_value < 1.5:
        return base_multiplier * 0.8  # Low volatility
    else:
        return base_multiplier  # Normal volatility

def get_volatility_adjusted_tp(atr_value, base_multiplier=2.0):
    """
    Get volatility-adjusted take profit multiplier based on ATR.
    
    Args:
        atr_value (float): Current ATR value
        base_multiplier (float): Base TP multiplier
    
    Returns:
        float: Adjusted TP multiplier
    """
    if not atr_value or atr_value <= 0:
        return base_multiplier
    
    # Higher ATR allows for larger TP targets
    if atr_value > 3.0:
        return base_multiplier * 1.2  # High volatility
    elif atr_value < 1.5:
        return base_multiplier * 0.9  # Low volatility
    else:
        return base_multiplier  # Normal volatility

def is_high_volatility(atr_value, atr_mean=None):
    """
    Determine if current volatility is high.
    
    Args:
        atr_value (float): Current ATR value
        atr_mean (float, optional): Mean ATR for comparison
    
    Returns:
        bool: True if high volatility
    """
    if atr_mean is None:
        atr_mean = 2.5  # Typical mean for XAUUSD M5
    
    return atr_value > atr_mean * 1.3

def is_low_volatility(atr_value, atr_mean=None):
    """
    Determine if current volatility is low.
    
    Args:
        atr_value (float): Current ATR value
        atr_mean (float, optional): Mean ATR for comparison
    
    Returns:
        bool: True if low volatility
    """
    if atr_mean is None:
        atr_mean = 2.5  # Typical mean for XAUUSD M5
    
    return atr_value < atr_mean * 0.7

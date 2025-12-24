# stochastic.py - Stochastic Oscillator indicator

import pandas as pd
import numpy as np

def calculate_stochastic(data, k_period=14, d_period=3, column='close'):
    """
    Calculate Stochastic Oscillator (%K and %D).
    
    Args:
        data (pd.DataFrame): OHLC data with 'high', 'low', 'close'
        k_period (int): Period for %K calculation (default: 14)
        d_period (int): Period for %D SMA (default: 3)
        column (str): Column to calculate on (default: 'close')
    
    Returns:
        tuple: (%K series, %D series)
    """
    if not all(col in data.columns for col in ['high', 'low', column]):
        raise ValueError(f"Data must contain 'high', 'low', '{column}' columns")
    
    # Get lowest low and highest high
    lowest_low = data['low'].rolling(window=k_period).min()
    highest_high = data['high'].rolling(window=k_period).max()
    
    # Calculate %K
    k = 100 * (data[column] - lowest_low) / (highest_high - lowest_low)
    
    # Calculate %D (SMA of %K)
    d = k.rolling(window=d_period).mean()
    
    return k, d

def add_stochastic_signals(data, k_period=14, d_period=3, column='close',
                          overbought=80, oversold=20):
    """
    Add Stochastic Oscillator signals to dataframe.
    
    Args:
        data (pd.DataFrame): OHLC data
        k_period (int): Period for %K
        d_period (int): Period for %D
        column (str): Column to calculate on
        overbought (int): Overbought threshold (default: 80)
        oversold (int): Oversold threshold (default: 20)
    
    Returns:
        pd.DataFrame: Data with Stochastic signals added
    """
    df = data.copy()
    
    k, d = calculate_stochastic(df, k_period, d_period, column)
    
    df['stoch_k'] = k
    df['stoch_d'] = d
    
    # Condition classification
    df['stoch_condition'] = 'neutral'
    df.loc[df['stoch_k'] > overbought, 'stoch_condition'] = 'overbought'
    df.loc[df['stoch_k'] < oversold, 'stoch_condition'] = 'oversold'
    
    # Crossover signals
    df['stoch_cross'] = 0
    
    # %K crosses above %D (bullish)
    df.loc[
        (df['stoch_k'].shift(1) <= df['stoch_d'].shift(1)) &
        (df['stoch_k'] > df['stoch_d']),
        'stoch_cross'
    ] = 1
    
    # %K crosses below %D (bearish)
    df.loc[
        (df['stoch_k'].shift(1) >= df['stoch_d'].shift(1)) &
        (df['stoch_k'] < df['stoch_d']),
        'stoch_cross'
    ] = -1
    
    return df

def get_stochastic_signal(k_value, d_value, overbought=80, oversold=20):
    """
    Get Stochastic trading signal.
    
    Args:
        k_value (float): %K value
        d_value (float): %D value
        overbought (int): Overbought threshold
        oversold (int): Oversold threshold
    
    Returns:
        int: 1 (bullish), -1 (bearish), 0 (neutral)
    """
    if k_value > overbought:
        return -1 if k_value > d_value else 0  # Overbought, potential reversal
    elif k_value < oversold:
        return 1 if k_value < d_value else 0  # Oversold, potential reversal
    elif k_value > d_value:
        return 1  # Bullish crossover
    elif k_value < d_value:
        return -1  # Bearish crossover
    else:
        return 0  # Neutral

def is_stoch_overbought(k_value, threshold=80):
    """Check if Stochastic is overbought."""
    return k_value > threshold

def is_stoch_oversold(k_value, threshold=20):
    """Check if Stochastic is oversold."""
    return k_value < threshold

def detect_stoch_divergence(data, lookback=20, overbought=80, oversold=20):
    """
    Detect Stochastic divergences with price.
    
    Args:
        data (pd.DataFrame): Data with 'close' and stochastic columns
        lookback (int): Number of periods to look back
        overbought (int): Overbought threshold
        oversold (int): Oversold threshold
    
    Returns:
        dict: {'bullish_div': bool, 'bearish_div': bool}
    """
    if 'stoch_k' not in data.columns or len(data) < lookback:
        return {'bullish_div': False, 'bearish_div': False}
    
    close = data['close'].values[-lookback:]
    k = data['stoch_k'].values[-lookback:]
    
    # Bullish divergence: lower lows in price, higher lows in Stochastic
    bullish_div = close[-1] < close[-lookback] and k[-1] > k[-lookback] and k[-1] < oversold
    
    # Bearish divergence: higher highs in price, lower highs in Stochastic
    bearish_div = close[-1] > close[-lookback] and k[-1] < k[-lookback] and k[-1] > overbought
    
    return {'bullish_div': bullish_div, 'bearish_div': bearish_div}

def get_stoch_momentum(k_value, prev_k_value):
    """
    Get Stochastic momentum (increasing or decreasing).
    
    Args:
        k_value (float): Current %K value
        prev_k_value (float): Previous %K value
    
    Returns:
        int: 1 (increasing), -1 (decreasing), 0 (flat)
    """
    if k_value > prev_k_value:
        return 1
    elif k_value < prev_k_value:
        return -1
    else:
        return 0

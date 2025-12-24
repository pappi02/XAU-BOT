# macd.py - MACD (Moving Average Convergence Divergence) indicator

import pandas as pd
import numpy as np

def calculate_macd(data, fast_period=12, slow_period=26, signal_period=9, column='close'):
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Args:
        data (pd.DataFrame): OHLC data
        fast_period (int): Fast EMA period (default: 12)
        slow_period (int): Slow EMA period (default: 26)
        signal_period (int): Signal line EMA period (default: 9)
        column (str): Column to calculate on (default: 'close')
    
    Returns:
        tuple: (MACD line, Signal line, Histogram)
    """
    if column not in data.columns:
        raise ValueError(f"Column '{column}' not found in data")
    
    # Calculate EMAs
    ema_fast = data[column].ewm(span=fast_period, adjust=False).mean()
    ema_slow = data[column].ewm(span=slow_period, adjust=False).mean()
    
    # MACD line
    macd_line = ema_fast - ema_slow
    
    # Signal line
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    
    # Histogram
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def add_macd_signals(data, fast_period=12, slow_period=26, signal_period=9, column='close'):
    """
    Add MACD signals to dataframe.
    
    Args:
        data (pd.DataFrame): OHLC data
        fast_period (int): Fast EMA period
        slow_period (int): Slow EMA period
        signal_period (int): Signal line EMA period
        column (str): Column to calculate on
    
    Returns:
        pd.DataFrame: Data with MACD signals added
    """
    df = data.copy()
    
    macd_line, signal_line, histogram = calculate_macd(
        df, fast_period, slow_period, signal_period, column
    )
    
    df['MACD'] = macd_line
    df['MACD_signal'] = signal_line
    df['MACD_histogram'] = histogram
    
    # Generate crossover signals
    df['MACD_signal_cross'] = 0
    
    # MACD crosses above signal line (bullish)
    df.loc[
        (df['MACD'].shift(1) <= df['MACD_signal'].shift(1)) &
        (df['MACD'] > df['MACD_signal']),
        'MACD_signal_cross'
    ] = 1
    
    # MACD crosses below signal line (bearish)
    df.loc[
        (df['MACD'].shift(1) >= df['MACD_signal'].shift(1)) &
        (df['MACD'] < df['MACD_signal']),
        'MACD_signal_cross'
    ] = -1
    
    # Histogram crossover signal (0 line)
    df['MACD_zero_cross'] = 0
    
    # Histogram crosses above 0 (bullish)
    df.loc[
        (df['MACD_histogram'].shift(1) <= 0) &
        (df['MACD_histogram'] > 0),
        'MACD_zero_cross'
    ] = 1
    
    # Histogram crosses below 0 (bearish)
    df.loc[
        (df['MACD_histogram'].shift(1) >= 0) &
        (df['MACD_histogram'] < 0),
        'MACD_zero_cross'
    ] = -1
    
    return df

def get_macd_signal(macd_value, signal_value, histogram_value):
    """
    Get MACD trading signal.
    
    Args:
        macd_value (float): MACD line value
        signal_value (float): Signal line value
        histogram_value (float): Histogram value
    
    Returns:
        int: 1 (bullish), -1 (bearish), 0 (neutral)
    """
    if histogram_value > 0 and macd_value > signal_value:
        return 1  # Bullish
    elif histogram_value < 0 and macd_value < signal_value:
        return -1  # Bearish
    else:
        return 0  # Neutral

def get_macd_momentum(histogram_value, prev_histogram_value):
    """
    Get MACD momentum direction (strengthening or weakening).
    
    Args:
        histogram_value (float): Current histogram value
        prev_histogram_value (float): Previous histogram value
    
    Returns:
        int: 1 (strengthening), -1 (weakening), 0 (unchanged)
    """
    if histogram_value > prev_histogram_value:
        return 1
    elif histogram_value < prev_histogram_value:
        return -1
    else:
        return 0

def detect_macd_divergence(data, lookback=20):
    """
    Detect bullish/bearish divergences between MACD and price.
    
    Args:
        data (pd.DataFrame): Data with 'close' and 'MACD_histogram' columns
        lookback (int): Number of periods to look back
    
    Returns:
        dict: {'bullish_div': bool, 'bearish_div': bool}
    """
    if 'MACD_histogram' not in data.columns or len(data) < lookback:
        return {'bullish_div': False, 'bearish_div': False}
    
    close = data['close'].values[-lookback:]
    histogram = data['MACD_histogram'].values[-lookback:]
    
    # Find local minima/maxima
    bullish_div = False
    bearish_div = False
    
    # Bullish divergence: lower lows in price, higher lows in MACD
    if close[-1] < close[-lookback] and histogram[-1] > histogram[-lookback]:
        bullish_div = True
    
    # Bearish divergence: higher highs in price, lower highs in MACD
    if close[-1] > close[-lookback] and histogram[-1] < histogram[-lookback]:
        bearish_div = True
    
    return {'bullish_div': bullish_div, 'bearish_div': bearish_div}

# rsi.py - Relative Strength Index indicator

import pandas as pd
import numpy as np

def calculate_rsi(data, period=14, column='close'):
    """
    Calculate Relative Strength Index (RSI).

    Args:
        data (pd.DataFrame): OHLC data
        period (int): RSI period (default: 14)
        column (str): Column to calculate RSI on (default: 'close')

    Returns:
        pd.Series: RSI values (0-100)
    """
    if column not in data.columns:
        raise ValueError(f"Column '{column}' not found in data")

    # Calculate price changes
    delta = data[column].diff()

    # Separate gains and losses
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Calculate RS and RSI
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi

def add_rsi_signals(data, period=14, overbought=70, oversold=30, column='close'):
    """
    Add RSI signals to data.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): RSI period
        overbought (int): Overbought threshold
        oversold (int): Oversold threshold
        column (str): Column to calculate RSI on

    Returns:
        pd.DataFrame: Data with RSI signals added
    """
    df = data.copy()

    # Calculate RSI
    df[f'RSI_{period}'] = calculate_rsi(df, period, column)

    # Generate signals
    df['RSI_signal'] = 0
    df.loc[df[f'RSI_{period}'] < oversold, 'RSI_signal'] = 1   # Oversold (buy signal)
    df.loc[df[f'RSI_{period}'] > overbought, 'RSI_signal'] = -1  # Overbought (sell signal)

    # Detect crossovers
    df['RSI_crossover'] = 0
    df.loc[(df[f'RSI_{period}'].shift(1) <= oversold) & (df[f'RSI_{period}'] > oversold), 'RSI_crossover'] = 1   # Bullish crossover
    df.loc[(df[f'RSI_{period}'].shift(1) >= overbought) & (df[f'RSI_{period}'] < overbought), 'RSI_crossover'] = -1  # Bearish crossover

    return df

def get_rsi_condition(data, period=14, column='close', overbought=70, oversold=30):
    """
    Get RSI condition description.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): RSI period
        column (str): Column to calculate RSI on
        overbought (int): Overbought threshold
        oversold (int): Oversold threshold

    Returns:
        str: RSI condition ('overbought', 'oversold', 'neutral')
    """
    rsi = calculate_rsi(data, period, column).iloc[-1]

    if rsi >= overbought:
        return 'overbought'
    elif rsi <= oversold:
        return 'oversold'
    else:
        return 'neutral'

def get_rsi_signal(rsi_value, overbought=70, oversold=30):
    """
    Get RSI trading signal.
    
    Args:
        rsi_value (float): Current RSI value
        overbought (int): Overbought threshold
        oversold (int): Oversold threshold
    
    Returns:
        int: 1 (bullish), -1 (bearish), 0 (neutral)
    """
    if rsi_value > overbought:
        return -1  # Overbought, potential sell
    elif rsi_value < oversold:
        return 1  # Oversold, potential buy
    else:
        return 0  # Neutral

def is_rsi_overbought(rsi_value, threshold=70):
    """Check if RSI is overbought."""
    return rsi_value > threshold

def is_rsi_oversold(rsi_value, threshold=30):
    """Check if RSI is oversold."""
    return rsi_value < threshold

def detect_rsi_divergence(data, period=14, column='close', lookback=20):
    """
    Detect RSI divergence (price vs RSI).

    Args:
        data (pd.DataFrame): OHLC data
        period (int): RSI period
        column (str): Column to calculate RSI on
        lookback (int): Number of periods to look back

    Returns:
        dict: {'bullish_div': bool, 'bearish_div': bool}
    """
    if len(data) < max(period * 2, lookback):
        return {'bullish_div': False, 'bearish_div': False}

    # Get recent data
    recent_data = data.tail(lookback)
    prices = recent_data[column].values
    rsi_values = calculate_rsi(recent_data, period, column).values

    bullish_div = False
    bearish_div = False
    
    # Bullish divergence: lower lows in price, higher lows in RSI
    if len(prices) > 1 and len(rsi_values) > 1:
        if prices[-1] < prices[0] and rsi_values[-1] > rsi_values[0]:
            bullish_div = True
        elif prices[-1] > prices[0] and rsi_values[-1] < rsi_values[0]:
            bearish_div = True
    
    return {'bullish_div': bullish_div, 'bearish_div': bearish_div}

if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data with some trend
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    prices = 1800 + np.cumsum(np.random.randn(100) * 2) + np.sin(np.arange(100) * 0.1) * 10
    sample_data = pd.DataFrame({'close': prices}, index=dates)

    # Calculate RSI
    rsi = calculate_rsi(sample_data, period=14)
    print("📊 RSI(14) calculated:")
    print(rsi.tail())

    # Add signals
    data_with_signals = add_rsi_signals(sample_data)
    print("\n📈 Data with RSI signals:")
    print(data_with_signals[['close', 'RSI_14', 'RSI_signal', 'RSI_crossover']].tail())

    # Get condition
    condition = get_rsi_condition(sample_data)
    print(f"\n📊 Current RSI condition: {condition}")

    # Check divergence
    divergence = rsi_divergence(sample_data)
    print(f"📊 RSI divergence: {divergence}")

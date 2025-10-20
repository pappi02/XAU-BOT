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
    df[f'RSI_{period}'] = calculate_rsi(df, period, column).rolling(3).mean()

    # Generate signals
    df['RSI_signal'] = 0
    df.loc[df[f'RSI_{period}'] < oversold, 'RSI_signal'] = 1   # Oversold (buy signal)
    df.loc[df[f'RSI_{period}'] > overbought, 'RSI_signal'] = -1  # Overbought (sell signal)

    # Detect crossovers
    df['RSI_crossover'] = 0
    df.loc[(df[f'RSI_{period}'].shift(1) <= oversold) & (df[f'RSI_{period}'] > oversold), 'RSI_crossover'] = 1   # Bullish crossover
    df.loc[(df[f'RSI_{period}'].shift(1) >= overbought) & (df[f'RSI_{period}'] < overbought), 'RSI_crossover'] = -1  # Bearish crossover

    return df

def get_rsi_condition(data, period=14, column='close'):
    """
    Get RSI condition description.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): RSI period
        column (str): Column to calculate RSI on

    Returns:
        str: RSI condition ('overbought', 'oversold', 'neutral')
    """
    rsi = calculate_rsi(data, period, column).iloc[-1]

    if rsi >= 70:
        return 'overbought'
    elif rsi <= 30:
        return 'oversold'
    else:
        return 'neutral'

def rsi_divergence(data, period=14, column='close'):
    """
    Detect RSI divergence (basic implementation).

    Args:
        data (pd.DataFrame): OHLC data
        period (int): RSI period
        column (str): Column to calculate RSI on

    Returns:
        str: Divergence type ('bullish', 'bearish', 'none')
    """
    if len(data) < period * 2:
        return 'none'

    # Get recent data
    recent_data = data.tail(period * 2)
    prices = recent_data[column]
    rsi_values = calculate_rsi(recent_data, period, column)

    # Simple divergence detection (price vs RSI)
    price_trend = 'up' if prices.iloc[-1] > prices.iloc[0] else 'down'
    rsi_trend = 'up' if rsi_values.iloc[-1] > rsi_values.iloc[0] else 'down'

    if price_trend == 'down' and rsi_trend == 'up':
        return 'bullish'  # Price falling, RSI rising = potential reversal up
    elif price_trend == 'up' and rsi_trend == 'down':
        return 'bearish'  # Price rising, RSI falling = potential reversal down
    else:
        return 'none'

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

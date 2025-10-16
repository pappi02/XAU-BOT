# bollinger.py - Bollinger Bands indicator

import pandas as pd
import numpy as np

def calculate_bollinger_bands(data, period=20, std_dev=2, column='close'):
    """
    Calculate Bollinger Bands.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): Moving average period (default: 20)
        std_dev (float): Standard deviation multiplier (default: 2)
        column (str): Column to calculate bands on (default: 'close')

    Returns:
        tuple: (upper_band, middle_band, lower_band)
    """
    if column not in data.columns:
        raise ValueError(f"Column '{column}' not found in data")

    # Calculate middle band (SMA)
    middle_band = data[column].rolling(window=period).mean()

    # Calculate standard deviation
    std = data[column].rolling(window=period).std()

    # Calculate upper and lower bands
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)

    return upper_band, middle_band, lower_band

def add_bollinger_signals(data, period=20, std_dev=2, column='close'):
    """
    Add Bollinger Bands signals to data.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): Moving average period
        std_dev (float): Standard deviation multiplier
        column (str): Column to calculate bands on

    Returns:
        pd.DataFrame: Data with Bollinger signals added
    """
    df = data.copy()

    # Calculate bands
    upper, middle, lower = calculate_bollinger_bands(df, period, std_dev, column)

    df[f'BB_upper_{period}'] = upper
    df[f'BB_middle_{period}'] = middle
    df[f'BB_lower_{period}'] = lower

    # Calculate %B (position within bands)
    df['BB_percent'] = (df[column] - lower) / (upper - lower)

    # Generate signals
    df['BB_signal'] = 0

    # Price touching lower band (potential buy)
    df.loc[df[column] <= lower, 'BB_signal'] = 1

    # Price touching upper band (potential sell)
    df.loc[df[column] >= upper, 'BB_signal'] = -1

    # Squeeze detection (bands narrowing)
    bandwidth = (upper - lower) / middle
    df['BB_bandwidth'] = bandwidth
    df['BB_squeeze'] = bandwidth < bandwidth.rolling(window=period).mean() * 0.8

    return df

def get_bollinger_position(data, period=20, std_dev=2, column='close'):
    """
    Get current position relative to Bollinger Bands.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): Moving average period
        std_dev (float): Standard deviation multiplier
        column (str): Column to calculate bands on

    Returns:
        str: Position ('above_upper', 'below_lower', 'within_bands')
    """
    upper, middle, lower = calculate_bollinger_bands(data, period, std_dev, column)
    current_price = data[column].iloc[-1]
    upper_val = upper.iloc[-1]
    lower_val = lower.iloc[-1]

    if current_price > upper_val:
        return 'above_upper'
    elif current_price < lower_val:
        return 'below_lower'
    else:
        return 'within_bands'

def bollinger_reversal_signal(data, period=20, std_dev=2, column='close'):
    """
    Detect potential reversal signals based on Bollinger Bands.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): Moving average period
        std_dev (float): Standard deviation multiplier
        column (str): Column to calculate bands on

    Returns:
        str: Signal type ('bullish_reversal', 'bearish_reversal', 'none')
    """
    if len(data) < period + 1:
        return 'none'

    upper, middle, lower = calculate_bollinger_bands(data, period, std_dev, column)

    # Check if price touched lower band recently and is now moving up
    recent_low = data[column].tail(period).min()
    current_price = data[column].iloc[-1]
    lower_recent = lower.tail(period).min()

    # Bullish reversal: price touched lower band and is now above middle
    if (recent_low <= lower_recent * 1.001) and (current_price > middle.iloc[-1]):
        return 'bullish_reversal'

    # Check if price touched upper band recently and is now moving down
    recent_high = data[column].tail(period).max()
    upper_recent = upper.tail(period).max()

    # Bearish reversal: price touched upper band and is now below middle
    if (recent_high >= upper_recent * 0.999) and (current_price < middle.iloc[-1]):
        return 'bearish_reversal'

    return 'none'

if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    prices = 1800 + np.cumsum(np.random.randn(100) * 3) + np.sin(np.arange(100) * 0.2) * 20
    sample_data = pd.DataFrame({'close': prices}, index=dates)

    # Calculate Bollinger Bands
    upper, middle, lower = calculate_bollinger_bands(sample_data, period=20)
    print("📊 Bollinger Bands calculated:")
    print(f"Upper: {upper.tail()}")
    print(f"Middle: {middle.tail()}")
    print(f"Lower: {lower.tail()}")

    # Add signals
    data_with_signals = add_bollinger_signals(sample_data)
    print("\n📈 Data with Bollinger signals:")
    print(data_with_signals[['close', 'BB_upper_20', 'BB_middle_20', 'BB_lower_20', 'BB_signal']].tail())

    # Get position
    position = get_bollinger_position(sample_data)
    print(f"\n📊 Current position relative to bands: {position}")

    # Check for reversal
    reversal = bollinger_reversal_signal(sample_data)
    print(f"📊 Bollinger reversal signal: {reversal}")

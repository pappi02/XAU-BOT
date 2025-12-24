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

def get_bollinger_signal(price, upper, middle, lower):
    """
    Get Bollinger Bands trading signal.
    
    Args:
        price (float): Current price
        upper (float): Upper band value
        middle (float): Middle band value
        lower (float): Lower band value
    
    Returns:
        int: 1 (bullish), -1 (bearish), 0 (neutral)
    """
    if price <= lower:
        return 1  # At/below lower band, potential buy
    elif price >= upper:
        return -1  # At/above upper band, potential sell
    else:
        return 0  # Within bands

def is_price_at_upper_band(price, upper, threshold=0.01):
    """
    Check if price is at upper band.
    
    Args:
        price (float): Current price
        upper (float): Upper band value
        threshold (float): Proximity threshold (percentage)
    
    Returns:
        bool: True if at upper band
    """
    return price >= upper * (1 - threshold)

def is_price_at_lower_band(price, lower, threshold=0.01):
    """
    Check if price is at lower band.
    
    Args:
        price (float): Current price
        lower (float): Lower band value
        threshold (float): Proximity threshold (percentage)
    
    Returns:
        bool: True if at lower band
    """
    return price <= lower * (1 + threshold)

def get_bollinger_squeeze_signal(data, period=20, std_dev=2, column='close'):
    """
    Detect Bollinger Bands squeeze (low volatility period).
    
    Args:
        data (pd.DataFrame): OHLC data
        period (int): Moving average period
        std_dev (float): Standard deviation multiplier
        column (str): Column to calculate on
    
    Returns:
        bool: True if squeeze detected
    """
    upper, middle, lower = calculate_bollinger_bands(data, period, std_dev, column)
    
    # Current bandwidth
    bandwidth = (upper - lower) / middle
    
    # Average bandwidth (using longer period for comparison)
    avg_bandwidth = bandwidth.rolling(window=period * 2).mean()
    
    # Squeeze when bandwidth is in bottom 25% of historical
    squeeze_threshold = 0.75
    
    if len(avg_bandwidth) > 1:
        return bandwidth.iloc[-1] < avg_bandwidth.iloc[-1] * squeeze_threshold
    return False


def get_bollinger_position(data, period=20, std_dev=2, column='close'):
    """Return the price position relative to the Bollinger Bands.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): Moving average period
        std_dev (float): Standard deviation multiplier
        column (str): Price column to evaluate

    Returns:
        str: 'above_upper', 'below_lower', or 'within_bands'
    """
    upper, _, lower = calculate_bollinger_bands(data, period=period, std_dev=std_dev, column=column)
    price = data[column].iloc[-1]

    if price >= upper.iloc[-1]:
        return 'above_upper'
    if price <= lower.iloc[-1]:
        return 'below_lower'
    return 'within_bands'

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

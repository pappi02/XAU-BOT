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
    Add Bollinger Bands to the frame.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): Moving average period
        std_dev (float): Standard deviation multiplier
        column (str): Column to calculate bands on

    Returns:
        pd.DataFrame: Data with ``BB_upper_{period}``, ``BB_middle_{period}``
        and ``BB_lower_{period}`` added.

    Phase 12 follow-up: also computed BB_percent, BB_signal, BB_bandwidth and
    BB_squeeze columns that no caller ever read -- strategies/signal_strength.py
    computes %B itself, independently, from the band columns kept here.
    Removed the dead ones; kept the bands themselves, which are used.
    """
    df = data.copy()

    upper, middle, lower = calculate_bollinger_bands(df, period, std_dev, column)

    df[f'BB_upper_{period}'] = upper
    df[f'BB_middle_{period}'] = middle
    df[f'BB_lower_{period}'] = lower

    return df

if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    prices = 1800 + np.cumsum(np.random.randn(100) * 3) + np.sin(np.arange(100) * 0.2) * 20
    sample_data = pd.DataFrame({'close': prices}, index=dates)

    # Add signals
    data_with_signals = add_bollinger_signals(sample_data)
    print("📊 Bollinger Bands calculated:")
    print(data_with_signals[['close', 'BB_upper_20', 'BB_middle_20', 'BB_lower_20']].tail())

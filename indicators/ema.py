# ema.py - Exponential Moving Average indicator

import pandas as pd
import numpy as np

def calculate_ema(data, period=14, column='close'):
    """
    Calculate Exponential Moving Average (EMA).

    Args:
        data (pd.DataFrame): OHLC data
        period (int): EMA period (default: 14)
        column (str): Column to calculate EMA on (default: 'close')

    Returns:
        pd.Series: EMA values
    """
    if column not in data.columns:
        raise ValueError(f"Column '{column}' not found in data")

    return data[column].ewm(span=period, adjust=False).mean()

def add_ema_signals(data, fast_period=12, slow_period=26, column='close'):
    """
    Add EMA state to the frame.

    Args:
        data (pd.DataFrame): OHLC data
        fast_period (int): Fast EMA period
        slow_period (int): Slow EMA period
        column (str): Column to calculate EMA on

    Returns:
        pd.DataFrame: Data with ``EMA_{fast_period}``, ``EMA_{slow_period}``
        and ``EMA_signal`` (+1 fast above slow, -1 below, 0 equal) added.

    Phase 12 follow-up: also computed an ``EMA_crossover`` column that no
    caller ever read -- removed.
    """
    df = data.copy()

    df[f'EMA_{fast_period}'] = calculate_ema(df, fast_period, column)
    df[f'EMA_{slow_period}'] = calculate_ema(df, slow_period, column)

    df['EMA_signal'] = 0
    df.loc[df[f'EMA_{fast_period}'] > df[f'EMA_{slow_period}'], 'EMA_signal'] = 1  # Bullish
    df.loc[df[f'EMA_{fast_period}'] < df[f'EMA_{slow_period}'], 'EMA_signal'] = -1  # Bearish

    return df

if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=200, freq='D')
    prices = 1800 + np.cumsum(np.random.randn(200) * 2) + np.sin(np.arange(200) * 0.1) * 20
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 2,
        'high': prices + abs(np.random.randn(200) * 5),
        'low': prices - abs(np.random.randn(200) * 5),
        'close': prices
    }, index=dates)

    # Add signals
    data_with_signals = add_ema_signals(sample_data)
    print("📊 EMA calculated:")
    print(data_with_signals[['close', 'EMA_12', 'EMA_26', 'EMA_signal']].tail())

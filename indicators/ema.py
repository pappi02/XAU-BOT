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
    Add EMA crossover signals to data.

    Args:
        data (pd.DataFrame): OHLC data
        fast_period (int): Fast EMA period
        slow_period (int): Slow EMA period
        column (str): Column to calculate EMA on

    Returns:
        pd.DataFrame: Data with EMA signals added
    """
    df = data.copy()

    # Calculate EMAs
    df[f'EMA_{fast_period}'] = calculate_ema(df, fast_period, column)
    df[f'EMA_{slow_period}'] = calculate_ema(df, slow_period, column)

    # Generate signals
    df['EMA_signal'] = 0
    df.loc[df[f'EMA_{fast_period}'] > df[f'EMA_{slow_period}'], 'EMA_signal'] = 1  # Bullish
    df.loc[df[f'EMA_{fast_period}'] < df[f'EMA_{slow_period}'], 'EMA_signal'] = -1  # Bearish

    # Detect crossovers
    df['EMA_crossover'] = 0
    df.loc[(df[f'EMA_{fast_period}'].shift(1) <= df[f'EMA_{slow_period}'].shift(1)) &
           (df[f'EMA_{fast_period}'] > df[f'EMA_{slow_period}']), 'EMA_crossover'] = 1  # Bullish crossover

    df.loc[(df[f'EMA_{fast_period}'].shift(1) >= df[f'EMA_{slow_period}'].shift(1)) &
           (df[f'EMA_{fast_period}'] < df[f'EMA_{slow_period}']), 'EMA_crossover'] = -1  # Bearish crossover

    return df

def get_ema_trend(data, period=14, column='close'):
    """
    Get EMA trend direction.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): EMA period
        column (str): Column to calculate EMA on

    Returns:
        str: 'up', 'down', or 'sideways'
    """
    ema = calculate_ema(data, period, column)

    # Calculate slope over last few periods
    recent_ema = ema.tail(5)
    slope = np.polyfit(range(len(recent_ema)), recent_ema.values, 1)[0]

    if slope > 0.01:  # Small threshold to avoid noise
        return 'up'
    elif slope < -0.01:
        return 'down'
    else:
        return 'sideways'

if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    prices = 1800 + np.cumsum(np.random.randn(100) * 5)
    sample_data = pd.DataFrame({'close': prices}, index=dates)

    # Calculate EMA
    ema_14 = calculate_ema(sample_data, period=14)
    print("📊 EMA(14) calculated:")
    print(ema_14.tail())

    # Add signals
    data_with_signals = add_ema_signals(sample_data)
    print("\n📈 Data with EMA signals:")
    print(data_with_signals[['close', 'EMA_12', 'EMA_26', 'EMA_signal', 'EMA_crossover']].tail())

    # Get trend
    trend = get_ema_trend(sample_data)
    print(f"\n📊 Current EMA trend: {trend}")

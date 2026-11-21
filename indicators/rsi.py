# rsi.py - Relative Strength Index indicator

import pandas as pd
import numpy as np


def calculate_rsi(data, period=14, column='close'):
    """
    Calculate Relative Strength Index (RSI), Wilder's original smoothing.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): RSI period (default: 14)
        column (str): Column to calculate RSI on (default: 'close')

    Returns:
        pd.Series: RSI values (0-100)

    Phase 12 follow-up: this used a plain rolling mean for the average
    gain/loss. That is a real, documented RSI variant, but it is not what
    Wilder defined and not what MT5's own iRSI (or any other platform's
    default RSI) computes -- so the bot's RSI disagreed with the number on the
    broker's own chart, and the 30/70 thresholds (tuned by decades of
    convention against Wilder's smoothing) were being applied to a
    differently-shaped series. Wilder's smoothing is an EMA with alpha =
    1/period, which pandas' ``ewm(alpha=..., adjust=False)`` computes exactly.
    """
    if column not in data.columns:
        raise ValueError(f"Column '{column}' not found in data")

    delta = data[column].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    # avg_loss == 0 with avg_gain > 0 divides to +inf -> rsi = 100, correct
    # (Python/pandas handle this without raising). avg_loss == avg_gain == 0
    # (a totally flat window) gives 0/0 = NaN, left as NaN rather than guessed.

    return rsi


def add_rsi_signals(data, period=14, column='close'):
    """
    Add RSI to the frame.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): RSI period
        column (str): Column to calculate RSI on

    Returns:
        pd.DataFrame: Data with an ``RSI_{period}`` column added.

    Phase 12 follow-up: this used to also smooth the RSI column with a
    further 3-bar moving average on top of Wilder's own smoothing --
    unexplained extra lag, never separately justified or tested, removed.
    It also computed RSI_signal/RSI_crossover columns that no caller ever
    read (dead weight recomputed on every bar of every backtest).
    """
    df = data.copy()
    df[f'RSI_{period}'] = calculate_rsi(df, period, column)
    return df


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

    data_with_signals = add_rsi_signals(sample_data)
    print("\n📈 Data with RSI:")
    print(data_with_signals[['close', 'RSI_14']].tail())

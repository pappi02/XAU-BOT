"""
parabolic_sar.py - Parabolic SAR (Stop and Reverse) Indicator

Parabolic SAR is a trend-following indicator that provides both entry and exit signals.
For scalping, we use the "three-dot" strategy for more reliable entries.

Formula:
- SAR(t) = SAR(t-1) + AF × (EP - SAR(t-1))
- Where AF (Acceleration Factor) starts at 0.02 and increases by 0.02 each time
  a new extreme point is reached, with a maximum of 0.2
- EP (Extreme Point) is the highest high or lowest low of the current trend

Author: Professional Scalping Suite
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict

def calculate_parabolic_sar(data: pd.DataFrame, iaf: float = 0.02, maxaf: float = 0.2) -> pd.Series:
    """
    Calculate Parabolic SAR values.
    
    Args:
        data (pd.DataFrame): OHLC data with 'high' and 'low' columns
        iaf (float): Initial Acceleration Factor (default: 0.02)
        maxaf (float): Maximum Acceleration Factor (default: 0.2)
    
    Returns:
        pd.Series: SAR values
    """
    length = len(data)
    sar = np.zeros(length)
    af = np.zeros(length)
    ep = np.zeros(length)
    trend = np.zeros(length)
    
    # Initialize with first 5 bars
    if length < 5:
        return pd.Series(sar)
    
    # Determine initial trend (uptrend or downtrend)
    if data['close'].iloc[4] > data['close'].iloc[0]:
        trend[0:5] = 1  # Uptrend
        sar[0:5] = data['low'].iloc[0:5].min()
        ep[0:5] = data['high'].iloc[0:5].max()
    else:
        trend[0:5] = -1  # Downtrend
        sar[0:5] = data['high'].iloc[0:5].max()
        ep[0:5] = data['low'].iloc[0:5].min()
    
    af[0:5] = iaf
    
    for i in range(5, length):
        # SAR calculation
        sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
        
        # Update trend and SAR based on price movement
        if trend[i-1] == 1:  # Uptrend
            trend[i] = 1
            # SAR should not be above the prior two lows
            sar[i] = min(sar[i], data['low'].iloc[i-1], data['low'].iloc[i-2] if i >= 2 else data['low'].iloc[i-1])
            
            # Check if price crosses SAR (reversal)
            if data['low'].iloc[i] < sar[i]:
                trend[i] = -1  # Switch to downtrend
                sar[i] = ep[i-1]  # SAR becomes the extreme point of previous trend
                ep[i] = data['low'].iloc[i]
                af[i] = iaf
            else:
                # Update extreme point and acceleration factor
                if data['high'].iloc[i] > ep[i-1]:
                    ep[i] = data['high'].iloc[i]
                    af[i] = min(af[i-1] + iaf, maxaf)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
        else:  # Downtrend
            trend[i] = -1
            # SAR should not be below the prior two highs
            sar[i] = max(sar[i], data['high'].iloc[i-1], data['high'].iloc[i-2] if i >= 2 else data['high'].iloc[i-1])
            
            # Check if price crosses SAR (reversal)
            if data['high'].iloc[i] > sar[i]:
                trend[i] = 1  # Switch to uptrend
                sar[i] = ep[i-1]  # SAR becomes the extreme point of previous trend
                ep[i] = data['high'].iloc[i]
                af[i] = iaf
            else:
                # Update extreme point and acceleration factor
                if data['low'].iloc[i] < ep[i-1]:
                    ep[i] = data['low'].iloc[i]
                    af[i] = min(af[i-1] + iaf, maxaf)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
    
    return pd.Series(sar, index=data.index)

def count_consecutive_dots(data: pd.DataFrame, lookback: int = 5) -> Dict:
    """
    Count consecutive SAR dots in same position (above/below price).
    For scalping: use the 3rd dot as entry signal.
    
    Args:
        data (pd.DataFrame): Data with 'sar' column added
        lookback (int): How many candles to look back
    
    Returns:
        Dict: {
            'consecutive_dots': int (0-5+),
            'dot_position': 'above' or 'below',
            'signal_ready': bool (True if 3+ dots),
            'entry_signal': int (0, 1 for buy 3rd dot below, -1 for sell 3rd dot above)
        }
    """
    if 'sar' not in data.columns or len(data) < 3:
        return {
            'consecutive_dots': 0,
            'dot_position': 'neutral',
            'signal_ready': False,
            'entry_signal': 0
        }
    
    recent = data[['close', 'sar']].iloc[-lookback:]
    
    # Determine current dot position
    current_above = recent['sar'].iloc[-1] > recent['close'].iloc[-1]
    
    # Count consecutive dots in same position
    consecutive = 0
    for i in range(len(recent) - 1, -1, -1):
        above = recent['sar'].iloc[i] > recent['close'].iloc[i]
        if above == current_above:
            consecutive += 1
        else:
            break
    
    # 3-dot entry signal (more reliable than 1st dot)
    entry_signal = 0
    if consecutive >= 3:
        if current_above:  # 3 dots above = sell signal
            entry_signal = -1
        else:  # 3 dots below = buy signal
            entry_signal = 1
    
    return {
        'consecutive_dots': consecutive,
        'dot_position': 'above' if current_above else 'below',
        'signal_ready': consecutive >= 3,
        'entry_signal': entry_signal
    }

def get_parabolic_sar_signal(data: pd.DataFrame) -> int:
    """
    Get Parabolic SAR signal (3-dot strategy for scalping).
    
    Returns:
        int: 1 (buy - 3 dots below), -1 (sell - 3 dots above), 0 (no signal)
    """
    analysis = count_consecutive_dots(data, lookback=5)
    return analysis['entry_signal']

def add_parabolic_sar_signals(data: pd.DataFrame) -> pd.DataFrame:
    """
    Add Parabolic SAR and related columns to DataFrame.
    
    Adds:
        - sar: SAR values
        - sar_dots: Consecutive dot count
        - sar_signal: 3-dot entry signal (1/-1/0)
    """
    df = data.copy()
    df['sar'] = calculate_parabolic_sar(df)
    
    sar_signals = []
    sar_dots = []
    
    for i in range(len(df)):
        if i < 3:
            sar_signals.append(0)
            sar_dots.append(0)
        else:
            analysis = count_consecutive_dots(df.iloc[:i+1], lookback=5)
            sar_signals.append(analysis['entry_signal'])
            sar_dots.append(analysis['consecutive_dots'])
    
    df['sar_dots'] = sar_dots
    df['sar_signal'] = sar_signals
    
    return df

if __name__ == "__main__":
    # Example usage
    import numpy as np
    
    dates = pd.date_range('2024-01-01', periods=100, freq='5min')
    prices = 2600 + np.cumsum(np.random.randn(100) * 2)
    
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(100) * 0.5,
        'high': prices + np.abs(np.random.randn(100)),
        'low': prices - np.abs(np.random.randn(100)),
        'close': prices
    }, index=dates)
    
    # Calculate SAR
    sar = calculate_parabolic_sar(sample_data)
    print("📊 Parabolic SAR calculated:")
    print(sar.tail())
    
    # Get 3-dot signals
    analysis = count_consecutive_dots(sample_data)
    print(f"\n🎯 3-Dot Analysis:")
    print(f"Consecutive Dots: {analysis['consecutive_dots']}")
    print(f"Position: {analysis['dot_position']}")
    print(f"Signal Ready: {analysis['signal_ready']}")
    print(f"Entry Signal: {analysis['entry_signal']}")

"""
commodity_channel_index.py - CCI (Commodity Channel Index) Indicator

CCI measures the deviation of price from its average price level.
Oscillates between -100 and +100 normally, with extremes indicating reversals.

Formula:
- CCI = (Price - SMA) / (0.015 × Mean Deviation)
- Where Price = (High + Low + Close) / 3 (Typical Price)
- SMA = Simple Moving Average of Typical Price
- Mean Deviation = Average absolute deviation from SMA

For scalping:
- Buy when CCI crosses above -100 (oversold bounce)
- Sell when CCI crosses below +100 (overbought pullback)
- Extreme levels (+200, -200) = very strong signals

Author: Professional Scalping Suite
"""

import pandas as pd
import numpy as np
from typing import Dict

def calculate_typical_price(data: pd.DataFrame) -> pd.Series:
    """Calculate typical price: (High + Low + Close) / 3"""
    return (data['high'] + data['low'] + data['close']) / 3.0

def calculate_cci(data: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Calculate Commodity Channel Index.
    
    Args:
        data (pd.DataFrame): OHLC data
        period (int): CCI period (default: 20)
    
    Returns:
        pd.Series: CCI values
    """
    typical_price = calculate_typical_price(data)
    
    # Calculate SMA of typical price
    sma = typical_price.rolling(window=period).mean()
    
    # Calculate mean deviation
    def mean_deviation(x):
        return np.abs(x - x.mean()).mean()
    
    md = typical_price.rolling(window=period).apply(mean_deviation, raw=False)
    
    # Calculate CCI
    cci = (typical_price - sma) / (0.015 * md)
    
    return cci

def get_cci_signal(data: pd.DataFrame, period: int = 20, 
                   oversold: float = -100, overbought: float = 100) -> int:
    """
    Get CCI entry signal based on extreme levels.
    
    Buy: CCI rises above -100 (from oversold)
    Sell: CCI falls below +100 (from overbought)
    
    Args:
        data (pd.DataFrame): OHLC data
        period (int): CCI period
        oversold (float): Oversold threshold (default: -100)
        overbought (float): Overbought threshold (default: 100)
    
    Returns:
        int: 1 (buy), -1 (sell), 0 (no signal)
    """
    if len(data) < period + 1:
        return 0
    
    cci = calculate_cci(data, period)
    current_cci = cci.iloc[-1]
    previous_cci = cci.iloc[-2]
    
    # Buy signal: CCI crosses above -100
    if previous_cci <= oversold and current_cci > oversold:
        return 1
    
    # Sell signal: CCI crosses below +100
    if previous_cci >= overbought and current_cci < overbought:
        return -1
    
    return 0

def get_cci_extremes(data: pd.DataFrame, period: int = 20) -> Dict:
    """
    Analyze CCI extreme levels for very strong signals.
    
    Returns:
        Dict: {
            'extreme_level': 'extreme_overbought', 'extreme_oversold', 'none',
            'signal_strength': 0-100,
            'reversal_probability': 'high', 'medium', 'low'
        }
    """
    if len(data) < period + 1:
        return {
            'extreme_level': 'none',
            'signal_strength': 0,
            'reversal_probability': 'low'
        }
    
    cci = calculate_cci(data, period)
    current_cci = cci.iloc[-1]
    
    extreme_level = 'none'
    signal_strength = 0
    reversal_probability = 'low'
    
    # Extreme overbought (CCI > 200)
    if current_cci > 200:
        extreme_level = 'extreme_overbought'
        signal_strength = min(100, (current_cci - 100) / 2)  # Scale from 100-200
        reversal_probability = 'high'
    # Extreme oversold (CCI < -200)
    elif current_cci < -200:
        extreme_level = 'extreme_oversold'
        signal_strength = min(100, (abs(current_cci) - 100) / 2)
        reversal_probability = 'high'
    # Normal overbought (100 < CCI < 200)
    elif current_cci > 100:
        extreme_level = 'overbought'
        signal_strength = (current_cci - 100) / 2
        reversal_probability = 'medium'
    # Normal oversold (-200 < CCI < -100)
    elif current_cci < -100:
        extreme_level = 'oversold'
        signal_strength = (abs(current_cci) - 100) / 2
        reversal_probability = 'medium'
    
    return {
        'extreme_level': extreme_level,
        'signal_strength': signal_strength,
        'reversal_probability': reversal_probability,
        'cci_value': current_cci
    }

def is_cci_overbought(data: pd.DataFrame, period: int = 20, threshold: float = 100) -> bool:
    """Check if CCI is overbought."""
    cci = calculate_cci(data, period)
    return cci.iloc[-1] > threshold

def is_cci_oversold(data: pd.DataFrame, period: int = 20, threshold: float = -100) -> bool:
    """Check if CCI is oversold."""
    cci = calculate_cci(data, period)
    return cci.iloc[-1] < threshold

def add_cci_signals(data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    Add CCI and signal columns to DataFrame.
    
    Adds:
        - cci: CCI values
        - cci_signal: Buy/sell signals (1/-1/0)
        - cci_extreme: Extreme level indicators
    """
    df = data.copy()
    df['cci'] = calculate_cci(df, period)
    
    cci_signals = []
    cci_extremes = []
    
    for i in range(len(df)):
        if i < period:
            cci_signals.append(0)
            cci_extremes.append('none')
        else:
            signal = get_cci_signal(df.iloc[:i+1], period)
            cci_signals.append(signal)
            
            extremes = get_cci_extremes(df.iloc[:i+1], period)
            cci_extremes.append(extremes['extreme_level'])
    
    df['cci_signal'] = cci_signals
    df['cci_extreme'] = cci_extremes
    
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
    
    # Calculate CCI
    cci = calculate_cci(sample_data, period=20)
    print("📊 CCI calculated:")
    print(cci.tail())
    
    # Get signal
    signal = get_cci_signal(sample_data)
    print(f"\n🎯 CCI Signal: {signal}")
    
    # Check extremes
    extremes = get_cci_extremes(sample_data)
    print(f"Extreme Level: {extremes['extreme_level']}")
    print(f"Signal Strength: {extremes['signal_strength']:.1f}%")
    print(f"Reversal Probability: {extremes['reversal_probability']}")

"""
trix.py - TRIX (Triple Exponential Average) Indicator

TRIX is a momentum oscillator that identifies oversold and overbought conditions.
It's a smoothed oscillator based on triple exponential moving averages.

Formula:
- TRIX = (EMA1 - EMA1_1day_ago) / EMA1_1day_ago × 10000
- Where EMA1 = EMA of price, EMA2 = EMA of EMA1, EMA3 = EMA of EMA2
- The final TRIX is the 1-day % change of EMA3

For scalping:
- Buy when TRIX crosses above 0 (bullish momentum)
- Sell when TRIX crosses below 0 (bearish momentum)
- Extreme values (+1, -1) = very strong signals
- Divergence: TRIX forms different highs/lows than price = reversal

Author: Professional Scalping Suite
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple

def calculate_trix(data: pd.DataFrame, period: int = 15, column: str = 'close') -> pd.Series:
    """
    Calculate TRIX (Triple Exponential Average).
    
    Args:
        data (pd.DataFrame): OHLC data
        period (int): EMA period (default: 15 for faster scalping signals)
        column (str): Column to calculate on (default: 'close')
    
    Returns:
        pd.Series: TRIX values (as percentage change)
    """
    if len(data) < period * 3:
        return pd.Series(np.zeros(len(data)), index=data.index)
    
    # Calculate triple exponential moving averages
    ema1 = data[column].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    
    # Calculate 1-day percentage change
    # TRIX = (EMA3 - EMA3_previous) / EMA3_previous * 10000
    trix = ema3.pct_change() * 10000
    
    return trix

def get_trix_signal(data: pd.DataFrame, period: int = 15) -> int:
    """
    Get TRIX zero-line crossover signal.
    
    Buy: TRIX crosses above 0
    Sell: TRIX crosses below 0
    
    Args:
        data (pd.DataFrame): OHLC data
        period (int): TRIX period
    
    Returns:
        int: 1 (buy), -1 (sell), 0 (no signal)
    """
    if len(data) < period * 3 + 1:
        return 0
    
    trix = calculate_trix(data, period)
    
    current_trix = trix.iloc[-1]
    previous_trix = trix.iloc[-2]
    
    # Buy signal: TRIX crosses above 0
    if previous_trix <= 0 and current_trix > 0:
        return 1
    
    # Sell signal: TRIX crosses below 0
    if previous_trix >= 0 and current_trix < 0:
        return -1
    
    return 0

def detect_trix_divergence(data: pd.DataFrame, period: int = 15, 
                          lookback: int = 20) -> Dict:
    """
    Detect TRIX divergence with price (advance reversal signal).
    
    Bullish Divergence: Price makes lower low, but TRIX makes higher low
    Bearish Divergence: Price makes higher high, but TRIX makes lower high
    
    Args:
        data (pd.DataFrame): OHLC data
        period (int): TRIX period
        lookback (int): How many candles to look back for divergence
    
    Returns:
        Dict: {
            'divergence': 'bullish', 'bearish', 'none',
            'strength': 0-100,
            'price_low': float,
            'trix_low': float (or high for bearish)
        }
    """
    if len(data) < period * 3 + lookback:
        return {
            'divergence': 'none',
            'strength': 0,
            'price_low': 0,
            'trix_low': 0
        }
    
    trix = calculate_trix(data, period)
    recent_price = data['close'].iloc[-lookback:]
    recent_trix = trix.iloc[-lookback:]
    
    # Find extremes in the lookback period
    price_low_idx = recent_price.idxmin()
    price_high_idx = recent_price.idxmax()
    trix_low_idx = recent_trix.idxmin()
    trix_high_idx = recent_trix.idxmax()
    
    divergence = 'none'
    strength = 0
    price_extreme = 0
    trix_extreme = 0
    
    # Bullish divergence: Price lower low, TRIX higher low
    price_recent_low = recent_price.iloc[-1]
    price_prev_low = recent_price.min()
    trix_recent_low = recent_trix.iloc[-1]
    
    if price_recent_low < price_prev_low:
        # Find the previous low's TRIX value
        trix_at_prev_low = recent_trix[recent_price == price_prev_low].values
        if len(trix_at_prev_low) > 0:
            if trix_recent_low > trix_at_prev_low[0]:
                divergence = 'bullish'
                strength = min(100, abs(trix_recent_low - trix_at_prev_low[0]) * 10)
                price_extreme = price_recent_low
                trix_extreme = trix_recent_low
    
    # Bearish divergence: Price higher high, TRIX lower high
    price_recent_high = recent_price.iloc[-1]
    price_prev_high = recent_price.max()
    trix_recent_high = recent_trix.iloc[-1]
    
    if price_recent_high > price_prev_high:
        # Find the previous high's TRIX value
        trix_at_prev_high = recent_trix[recent_price == price_prev_high].values
        if len(trix_at_prev_high) > 0:
            if trix_recent_high < trix_at_prev_high[0]:
                divergence = 'bearish'
                strength = min(100, abs(trix_recent_high - trix_at_prev_high[0]) * 10)
                price_extreme = price_recent_high
                trix_extreme = trix_recent_high
    
    return {
        'divergence': divergence,
        'strength': strength,
        'price_extreme': price_extreme,
        'trix_extreme': trix_extreme
    }

def get_trix_strength(data: pd.DataFrame, period: int = 15) -> Dict:
    """
    Analyze TRIX momentum strength.
    
    Returns:
        Dict: {
            'momentum_direction': 'bullish', 'bearish', 'neutral',
            'momentum_strength': 0-100,
            'is_extreme': bool,
            'is_crossing_zero': bool
        }
    """
    if len(data) < period * 3 + 1:
        return {
            'momentum_direction': 'neutral',
            'momentum_strength': 0,
            'is_extreme': False,
            'is_crossing_zero': False
        }
    
    trix = calculate_trix(data, period)
    current_trix = trix.iloc[-1]
    
    # Direction
    if current_trix > 0:
        momentum_direction = 'bullish'
        momentum_strength = min(100, abs(current_trix) * 10)
    elif current_trix < 0:
        momentum_direction = 'bearish'
        momentum_strength = min(100, abs(current_trix) * 10)
    else:
        momentum_direction = 'neutral'
        momentum_strength = 0
    
    # Check for extreme values
    is_extreme = abs(current_trix) > 1.0
    
    # Check if crossing zero
    previous_trix = trix.iloc[-2]
    is_crossing_zero = (previous_trix * current_trix) < 0  # Different signs = crossed
    
    return {
        'momentum_direction': momentum_direction,
        'momentum_strength': momentum_strength,
        'is_extreme': is_extreme,
        'is_crossing_zero': is_crossing_zero,
        'trix_value': current_trix
    }

def add_trix_signals(data: pd.DataFrame, period: int = 15) -> pd.DataFrame:
    """
    Add TRIX and signal columns to DataFrame.
    
    Adds:
        - trix: TRIX values
        - trix_signal: Zero-line crossover signals (1/-1/0)
        - trix_divergence: Divergence detection ('bullish'/'bearish'/'none')
    """
    df = data.copy()
    df['trix'] = calculate_trix(df, period)
    
    trix_signals = []
    trix_divergences = []
    
    for i in range(len(df)):
        if i < period * 3 + 1:
            trix_signals.append(0)
            trix_divergences.append('none')
        else:
            signal = get_trix_signal(df.iloc[:i+1], period)
            trix_signals.append(signal)
            
            divergence = detect_trix_divergence(df.iloc[:i+1], period, lookback=20)
            trix_divergences.append(divergence['divergence'])
    
    df['trix_signal'] = trix_signals
    df['trix_divergence'] = trix_divergences
    
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
    
    # Calculate TRIX
    trix = calculate_trix(sample_data, period=15)
    print("📊 TRIX calculated:")
    print(trix.tail())
    
    # Get signal
    signal = get_trix_signal(sample_data)
    print(f"\n🎯 TRIX Signal: {signal}")
    
    # Check strength
    strength = get_trix_strength(sample_data)
    print(f"Momentum Direction: {strength['momentum_direction']}")
    print(f"Momentum Strength: {strength['momentum_strength']:.1f}%")
    print(f"Is Extreme: {strength['is_extreme']}")
    print(f"Is Crossing Zero: {strength['is_crossing_zero']}")
    
    # Check divergence
    divergence = detect_trix_divergence(sample_data)
    print(f"\nDivergence: {divergence['divergence']}")
    print(f"Strength: {divergence['strength']:.1f}%")

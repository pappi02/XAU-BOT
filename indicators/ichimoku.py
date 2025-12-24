"""
ichimoku.py - Ichimoku Cloud Indicator

The Ichimoku Cloud (Ichimoku Kinky Hyo) is a comprehensive indicator that defines support/resistance,
identifies trend direction, gauges momentum and provides trading signals.

Key Components:
1. Tenkan-sen (Conversion Line): (9-period High + 9-period Low) / 2
2. Kijun-sen (Base Line): (26-period High + 26-period Low) / 2
3. Senkou Span A (Leading Span A): (Tenkan + Kijun) / 2, plotted 26 periods ahead
4. Senkou Span B (Leading Span B): (52-period High + 52-period Low) / 2, plotted 26 periods ahead
5. Chikou Span (Lagging Span): Close plotted 26 periods in the past

For Scalping (Per Professional Trading Guide):
- BUY: Price breaks ABOVE the cloud (especially with momentum)
- SELL: Price breaks BELOW the cloud (especially with momentum)
- Cloud crossovers = important trend changes
- Chikou crossing price = confirmation signal
- "Don't wait for confirmation, momentum is important" - Trading Guide

Author: Professional Scalping Suite
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple

def calculate_ichimoku(
    data: pd.DataFrame,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
    chikou_period: int = 26
) -> Dict[str, pd.Series]:
    """
    Calculate all Ichimoku Cloud components.
    
    Args:
        data (pd.DataFrame): OHLC data with 'high', 'low', 'close' columns
        tenkan_period (int): Tenkan-sen period (default: 9)
        kijun_period (int): Kijun-sen period (default: 26)
        senkou_b_period (int): Senkou Span B period (default: 52)
        chikou_period (int): Chikou Span period (default: 26)
    
    Returns:
        Dict with keys: 'tenkan', 'kijun', 'senkou_a', 'senkou_b', 'chikou'
    """
    # Tenkan-sen (Conversion Line)
    tenkan_high = data['high'].rolling(window=tenkan_period).max()
    tenkan_low = data['low'].rolling(window=tenkan_period).min()
    tenkan = (tenkan_high + tenkan_low) / 2
    
    # Kijun-sen (Base Line)
    kijun_high = data['high'].rolling(window=kijun_period).max()
    kijun_low = data['low'].rolling(window=kijun_period).min()
    kijun = (kijun_high + kijun_low) / 2
    
    # Senkou Span A (Leading Span A) - plotted 26 periods ahead
    senkou_a = (tenkan + kijun) / 2
    senkou_a = senkou_a.shift(chikou_period)
    
    # Senkou Span B (Leading Span B) - plotted 26 periods ahead
    senkou_b_high = data['high'].rolling(window=senkou_b_period).max()
    senkou_b_low = data['low'].rolling(window=senkou_b_period).min()
    senkou_b = (senkou_b_high + senkou_b_low) / 2
    senkou_b = senkou_b.shift(chikou_period)
    
    # Chikou Span (Lagging Span) - close plotted 26 periods in the past
    chikou = data['close'].shift(-chikou_period)
    
    return {
        'tenkan': tenkan,
        'kijun': kijun,
        'senkou_a': senkou_a,
        'senkou_b': senkou_b,
        'chikou': chikou
    }

def get_cloud_position(data: pd.DataFrame, ichimoku: Dict[str, pd.Series]) -> str:
    """
    Determine price position relative to cloud.
    
    Returns:
        'above_cloud', 'below_cloud', 'in_cloud'
    """
    current_close = data['close'].iloc[-1]
    current_senkou_a = ichimoku['senkou_a'].iloc[-1]
    current_senkou_b = ichimoku['senkou_b'].iloc[-1]
    
    cloud_top = max(current_senkou_a, current_senkou_b)
    cloud_bottom = min(current_senkou_a, current_senkou_b)
    
    if current_close > cloud_top:
        return 'above_cloud'
    elif current_close < cloud_bottom:
        return 'below_cloud'
    else:
        return 'in_cloud'

def get_ichimoku_signal(data: pd.DataFrame, 
                       tenkan_period: int = 9,
                       kijun_period: int = 26,
                       senkou_b_period: int = 52,
                       chikou_period: int = 26) -> int:
    """
    Get Ichimoku cloud breakout signal.
    
    Per Professional Trading Guide:
    - BUY: Price breaks ABOVE the cloud (bullish momentum)
    - SELL: Price breaks BELOW the cloud (bearish momentum)
    - No confirmation needed, momentum is important
    
    Args:
        data (pd.DataFrame): OHLC data
    
    Returns:
        int: 1 (buy - price above cloud), -1 (sell - price below cloud), 0 (no signal)
    """
    if len(data) < senkou_b_period + 1:
        return 0
    
    ichimoku = calculate_ichimoku(data, tenkan_period, kijun_period, 
                                  senkou_b_period, chikou_period)
    
    current_position = get_cloud_position(data, ichimoku)
    
    if len(data) >= 2:
        # Get previous position
        prev_data = data.iloc[:-1]
        prev_ichimoku = calculate_ichimoku(prev_data, tenkan_period, kijun_period,
                                          senkou_b_period, chikou_period)
        previous_position = get_cloud_position(prev_data, prev_ichimoku)
    else:
        previous_position = current_position
    
    # Buy signal: Price breaks above cloud (from in_cloud or below_cloud to above_cloud)
    if previous_position != 'above_cloud' and current_position == 'above_cloud':
        return 1
    
    # Sell signal: Price breaks below cloud (from in_cloud or above_cloud to below_cloud)
    if previous_position != 'below_cloud' and current_position == 'below_cloud':
        return -1
    
    return 0

def detect_cloud_crossover(data: pd.DataFrame,
                          tenkan_period: int = 9,
                          kijun_period: int = 26,
                          senkou_b_period: int = 52,
                          chikou_period: int = 26) -> Dict:
    """
    Detect Senkou Span crossovers (Span A > Span B = bullish).
    
    Returns:
        Dict: {
            'crossover': 'bullish', 'bearish', 'none',
            'span_a': float,
            'span_b': float,
            'distance': float
        }
    """
    ichimoku = calculate_ichimoku(data, tenkan_period, kijun_period,
                                  senkou_b_period, chikou_period)
    
    current_a = ichimoku['senkou_a'].iloc[-1]
    current_b = ichimoku['senkou_b'].iloc[-1]
    
    if len(data) >= 2:
        prev_a = ichimoku['senkou_a'].iloc[-2]
        prev_b = ichimoku['senkou_b'].iloc[-2]
    else:
        prev_a = current_a
        prev_b = current_b
    
    crossover = 'none'
    
    # Bullish crossover: Span A crosses above Span B
    if prev_a <= prev_b and current_a > current_b:
        crossover = 'bullish'
    
    # Bearish crossover: Span A crosses below Span B
    if prev_a >= prev_b and current_a < current_b:
        crossover = 'bearish'
    
    distance = abs(current_a - current_b)
    
    return {
        'crossover': crossover,
        'span_a': current_a,
        'span_b': current_b,
        'distance': distance
    }

def detect_chikou_signal(data: pd.DataFrame, chikou_period: int = 26) -> Dict:
    """
    Detect Chikou Span signals.
    
    Chikou crossing price = confirmation of trend change.
    
    Returns:
        Dict: {
            'signal': 'above_price', 'below_price', 'crossing_price',
            'chikou_value': float,
            'strength': 0-100
        }
    """
    ichimoku = calculate_ichimoku(data, chikou_period=chikou_period)
    
    current_chikou = ichimoku['chikou'].iloc[-1]
    current_close = data['close'].iloc[-1]
    
    if pd.isna(current_chikou):
        return {
            'signal': 'none',
            'chikou_value': 0,
            'strength': 0
        }
    
    signal = 'none'
    strength = 0
    
    if len(data) >= 2:
        prev_chikou = ichimoku['chikou'].iloc[-2]
        prev_close = data['close'].iloc[-2]
        
        # Check if chikou is crossing price
        if (prev_chikou <= prev_close and current_chikou > current_close):
            signal = 'crossing_above'
            strength = min(100, abs(current_chikou - current_close) * 100)
        elif (prev_chikou >= prev_close and current_chikou < current_close):
            signal = 'crossing_below'
            strength = min(100, abs(current_chikou - current_close) * 100)
        elif current_chikou > current_close:
            signal = 'above_price'
            strength = min(100, (current_chikou - current_close) * 100)
        else:
            signal = 'below_price'
            strength = min(100, (current_close - current_chikou) * 100)
    else:
        if current_chikou > current_close:
            signal = 'above_price'
        else:
            signal = 'below_price'
    
    return {
        'signal': signal,
        'chikou_value': current_chikou,
        'strength': strength
    }

def detect_tenkan_kijun_signal(data: pd.DataFrame,
                              tenkan_period: int = 9,
                              kijun_period: int = 26) -> Dict:
    """
    Detect Tenkan-sen and Kijun-sen crossovers.
    
    Tenkan crossing above Kijun = bullish momentum
    Tenkan crossing below Kijun = bearish momentum
    
    Returns:
        Dict: {
            'crossover': 'bullish', 'bearish', 'none',
            'tenkan_kijun_distance': float
        }
    """
    ichimoku = calculate_ichimoku(data, tenkan_period=tenkan_period,
                                  kijun_period=kijun_period)
    
    current_tenkan = ichimoku['tenkan'].iloc[-1]
    current_kijun = ichimoku['kijun'].iloc[-1]
    
    crossover = 'none'
    
    if len(data) >= 2:
        prev_tenkan = ichimoku['tenkan'].iloc[-2]
        prev_kijun = ichimoku['kijun'].iloc[-2]
        
        # Bullish: Tenkan crosses above Kijun
        if prev_tenkan <= prev_kijun and current_tenkan > current_kijun:
            crossover = 'bullish'
        
        # Bearish: Tenkan crosses below Kijun
        if prev_tenkan >= prev_kijun and current_tenkan < current_kijun:
            crossover = 'bearish'
    
    distance = abs(current_tenkan - current_kijun)
    
    return {
        'crossover': crossover,
        'tenkan_value': current_tenkan,
        'kijun_value': current_kijun,
        'distance': distance
    }

def add_ichimoku_signals(data: pd.DataFrame,
                        tenkan_period: int = 9,
                        kijun_period: int = 26,
                        senkou_b_period: int = 52,
                        chikou_period: int = 26) -> pd.DataFrame:
    """
    Add Ichimoku components and signals to DataFrame.
    
    Adds columns:
        - tenkan, kijun, senkou_a, senkou_b, chikou
        - ichimoku_signal: Cloud breakout signals (1/-1/0)
        - cloud_position: above_cloud / below_cloud / in_cloud
    """
    df = data.copy()
    
    ichimoku = calculate_ichimoku(df, tenkan_period, kijun_period,
                                 senkou_b_period, chikou_period)
    
    df['tenkan'] = ichimoku['tenkan']
    df['kijun'] = ichimoku['kijun']
    df['senkou_a'] = ichimoku['senkou_a']
    df['senkou_b'] = ichimoku['senkou_b']
    df['chikou'] = ichimoku['chikou']
    
    signals = []
    positions = []
    
    for i in range(len(df)):
        if i < senkou_b_period:
            signals.append(0)
            positions.append('unknown')
        else:
            signal = get_ichimoku_signal(
                df.iloc[:i+1], tenkan_period, kijun_period,
                senkou_b_period, chikou_period
            )
            signals.append(signal)
            
            position = get_cloud_position(df.iloc[:i+1], ichimoku)
            positions.append(position)
    
    df['ichimoku_signal'] = signals
    df['cloud_position'] = positions
    
    return df

if __name__ == "__main__":
    # Example usage
    dates = pd.date_range('2024-01-01', periods=100, freq='5min')
    prices = 2600 + np.cumsum(np.random.randn(100) * 2)
    
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(100) * 0.5,
        'high': prices + np.abs(np.random.randn(100)),
        'low': prices - np.abs(np.random.randn(100)),
        'close': prices
    }, index=dates)
    
    # Calculate Ichimoku
    ichimoku = calculate_ichimoku(sample_data)
    print("📊 Ichimoku Cloud calculated:")
    print(f"Tenkan: {ichimoku['tenkan'].iloc[-1]:.2f}")
    print(f"Kijun: {ichimoku['kijun'].iloc[-1]:.2f}")
    print(f"Senkou A: {ichimoku['senkou_a'].iloc[-1]:.2f}")
    print(f"Senkou B: {ichimoku['senkou_b'].iloc[-1]:.2f}")
    
    # Get cloud position
    position = get_cloud_position(sample_data, ichimoku)
    print(f"\n☁️  Price Position: {position}")
    
    # Get signal
    signal = get_ichimoku_signal(sample_data)
    print(f"🎯 Cloud Breakout Signal: {signal}")
    
    # Check cloud crossover
    crossover = detect_cloud_crossover(sample_data)
    print(f"\nCloud Crossover: {crossover['crossover']}")
    print(f"Distance: {crossover['distance']:.2f}")
    
    # Check Chikou
    chikou = detect_chikou_signal(sample_data)
    print(f"\nChikou Signal: {chikou['signal']}")
    print(f"Strength: {chikou['strength']:.1f}%")
    
    # Check Tenkan-Kijun
    tk = detect_tenkan_kijun_signal(sample_data)
    print(f"\nTenkan-Kijun Crossover: {tk['crossover']}")
    print(f"Distance: {tk['distance']:.2f}")

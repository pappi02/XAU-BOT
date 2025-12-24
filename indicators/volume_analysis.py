"""
Volume Analysis - Volume Profile and Volume Spike Detection
Professional implementation for scalping - identifies high-volume nodes and volume surges
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


def detect_volume_spike(data: pd.DataFrame,
                       period: int = 20,
                       threshold: float = 1.5,
                       require_price_move: bool = True,
                       min_price_move_pct: float = 0.1) -> Dict:
    """
    Detect volume spikes that may indicate strong momentum or reversals.
    
    Args:
        data: DataFrame with 'volume', 'close' columns
        period: Lookback period for average volume
        threshold: Multiplier for average volume (e.g., 1.5 = 150% of avg)
        require_price_move: If True, require significant price movement with volume
        min_price_move_pct: Minimum price move % to confirm spike
        
    Returns:
        Dict: {'spike_detected': bool, 'spike_ratio': float, 'direction': int}
    """
    if len(data) < period + 1:
        return {'spike_detected': False, 'spike_ratio': 0.0, 'direction': 0}
    
    # Calculate average volume
    avg_volume = data['volume'].rolling(window=period).mean()
    
    current_volume = float(data['volume'].iloc[-1])
    current_avg = float(avg_volume.iloc[-1])
    
    if current_avg == 0:
        return {'spike_detected': False, 'spike_ratio': 0.0, 'direction': 0}
    
    # Calculate spike ratio
    spike_ratio = current_volume / current_avg
    
    spike_detected = spike_ratio >= threshold
    
    # Check price movement if required
    direction = 0
    if spike_detected and require_price_move:
        current_close = float(data['close'].iloc[-1])
        prev_close = float(data['close'].iloc[-2])
        price_change_pct = abs((current_close - prev_close) / prev_close) * 100.0
        
        if price_change_pct >= min_price_move_pct:
            direction = 1 if current_close > prev_close else -1
        else:
            # Volume spike without significant price move - ignore
            spike_detected = False
    
    return {
        'spike_detected': spike_detected,
        'spike_ratio': float(spike_ratio),
        'direction': direction
    }


def calculate_volume_profile(data: pd.DataFrame,
                             num_bins: int = 20,
                             lookback: int = 100) -> Dict:
    """
    Calculate Volume Profile to identify high-volume nodes (HVNs) and low-volume nodes (LVNs).
    
    HVNs act as support/resistance; LVNs are areas of fast price movement.
    
    Args:
        data: DataFrame with 'high', 'low', 'volume' columns
        num_bins: Number of price bins to divide the range
        lookback: Number of candles to analyze
        
    Returns:
        Dict: {'hvns': list, 'lvns': list, 'poc': float, 'value_area': tuple}
    """
    if len(data) < lookback:
        lookback = len(data)
    
    recent_data = data.tail(lookback)
    
    # Get price range
    high_price = float(recent_data['high'].max())
    low_price = float(recent_data['low'].min())
    price_range = high_price - low_price
    
    if price_range == 0:
        return {'hvns': [], 'lvns': [], 'poc': float(recent_data['close'].iloc[-1]), 'value_area': (low_price, high_price)}
    
    # Create price bins
    bin_size = price_range / num_bins
    bins = []
    for i in range(num_bins):
        bin_low = low_price + (i * bin_size)
        bin_high = bin_low + bin_size
        bins.append({'low': bin_low, 'high': bin_high, 'volume': 0.0})
    
    # Distribute volume across bins
    for idx, row in recent_data.iterrows():
        candle_high = row['high']
        candle_low = row['low']
        candle_volume = row['volume']
        
        # Find bins that overlap with this candle
        for bin_data in bins:
            if candle_low <= bin_data['high'] and candle_high >= bin_data['low']:
                # Simple allocation: distribute volume evenly to overlapping bins
                bins[bins.index(bin_data)]['volume'] += candle_volume
    
    # Sort bins by volume
    volumes = [b['volume'] for b in bins]
    avg_volume = np.mean(volumes)
    std_volume = np.std(volumes)
    
    # Identify HVNs (High Volume Nodes) - support/resistance
    hvns = []
    for bin_data in bins:
        if bin_data['volume'] > avg_volume + (0.5 * std_volume):
            price_level = (bin_data['low'] + bin_data['high']) / 2.0
            hvns.append(price_level)
    
    # Identify LVNs (Low Volume Nodes) - breakout zones
    lvns = []
    for bin_data in bins:
        if bin_data['volume'] < avg_volume - (0.5 * std_volume):
            price_level = (bin_data['low'] + bin_data['high']) / 2.0
            lvns.append(price_level)
    
    # Point of Control (POC) - price level with highest volume
    max_volume_bin = max(bins, key=lambda x: x['volume'])
    poc = (max_volume_bin['low'] + max_volume_bin['high']) / 2.0
    
    # Value Area (70% of volume)
    sorted_bins = sorted(bins, key=lambda x: x['volume'], reverse=True)
    total_volume = sum(b['volume'] for b in bins)
    value_area_volume = 0.0
    value_area_bins = []
    
    for bin_data in sorted_bins:
        value_area_bins.append(bin_data)
        value_area_volume += bin_data['volume']
        if value_area_volume >= total_volume * 0.70:
            break
    
    va_high = max(b['high'] for b in value_area_bins)
    va_low = min(b['low'] for b in value_area_bins)
    
    return {
        'hvns': hvns,
        'lvns': lvns,
        'poc': float(poc),
        'value_area': (float(va_low), float(va_high))
    }


def is_near_hvn(current_price: float, hvns: List[float], tolerance_pct: float = 0.5) -> bool:
    """
    Check if current price is near a High Volume Node (support/resistance).
    
    Args:
        current_price: Current market price
        hvns: List of HVN price levels
        tolerance_pct: Percentage tolerance for "near" (default 0.5%)
        
    Returns:
        bool: True if price is near an HVN
    """
    if not hvns:
        return False
    
    for hvn in hvns:
        distance_pct = abs((current_price - hvn) / current_price) * 100.0
        if distance_pct <= tolerance_pct:
            return True
    
    return False


def is_near_lvn(current_price: float, lvns: List[float], tolerance_pct: float = 0.5) -> bool:
    """
    Check if current price is near a Low Volume Node (breakout zone).
    
    Args:
        current_price: Current market price
        lvns: List of LVN price levels
        tolerance_pct: Percentage tolerance for "near" (default 0.5%)
        
    Returns:
        bool: True if price is near an LVN
    """
    if not lvns:
        return False
    
    for lvn in lvns:
        distance_pct = abs((current_price - lvn) / current_price) * 100.0
        if distance_pct <= tolerance_pct:
            return True
    
    return False


def get_volume_trend(data: pd.DataFrame, period: int = 10) -> str:
    """
    Determine if volume is increasing, decreasing, or stable.
    
    Args:
        data: DataFrame with 'volume' column
        period: Lookback period
        
    Returns:
        str: 'increasing', 'decreasing', or 'stable'
    """
    if len(data) < period:
        return 'stable'
    
    recent_volume = data['volume'].tail(period)
    
    # Linear regression to determine trend
    x = np.arange(len(recent_volume))
    y = recent_volume.values
    
    slope, _ = np.polyfit(x, y, 1)
    
    # Normalize slope by average volume
    avg_volume = np.mean(y)
    if avg_volume == 0:
        return 'stable'
    
    normalized_slope = slope / avg_volume
    
    # Thresholds
    if normalized_slope > 0.05:
        return 'increasing'
    elif normalized_slope < -0.05:
        return 'decreasing'
    else:
        return 'stable'


def calculate_relative_volume(data: pd.DataFrame, period: int = 20) -> float:
    """
    Calculate relative volume (current volume vs average).
    
    Args:
        data: DataFrame with 'volume' column
        period: Period for average volume
        
    Returns:
        float: Relative volume ratio (e.g., 1.5 = 150% of average)
    """
    if len(data) < period + 1:
        return 1.0
    
    avg_volume = data['volume'].rolling(window=period).mean()
    current_volume = float(data['volume'].iloc[-1])
    current_avg = float(avg_volume.iloc[-1])
    
    if current_avg == 0:
        return 1.0
    
    return current_volume / current_avg


def add_volume_analysis(data: pd.DataFrame,
                       spike_period: int = 20,
                       spike_threshold: float = 1.5,
                       profile_bins: int = 20) -> pd.DataFrame:
    """
    Add volume analysis columns to DataFrame.
    
    Args:
        data: DataFrame with OHLCV data
        spike_period: Period for volume spike detection
        spike_threshold: Threshold for spike detection
        profile_bins: Number of bins for volume profile
        
    Returns:
        DataFrame with added volume analysis columns
    """
    data = data.copy()
    
    # Relative volume
    data['relative_volume'] = data['volume'] / data['volume'].rolling(window=spike_period).mean()
    
    # Volume spike detection
    spikes = []
    for i in range(len(data)):
        if i < spike_period:
            spikes.append(False)
        else:
            window_data = data.iloc[:i+1]
            spike_result = detect_volume_spike(window_data, spike_period, spike_threshold)
            spikes.append(spike_result['spike_detected'])
    
    data['volume_spike'] = spikes
    
    # Volume trend
    trends = []
    for i in range(len(data)):
        if i < 10:
            trends.append('stable')
        else:
            window_data = data.iloc[:i+1]
            trends.append(get_volume_trend(window_data, period=10))
    
    data['volume_trend'] = trends
    
    return data


def get_volume_confirmation(data: pd.DataFrame,
                           direction: int,
                           spike_threshold: float = 1.3,
                           min_relative_volume: float = 1.1) -> bool:
    """
    Check if volume confirms the price direction (for scalping setups).
    
    Args:
        data: DataFrame with OHLCV data
        direction: Price direction (1 = up, -1 = down)
        spike_threshold: Volume spike threshold
        min_relative_volume: Minimum relative volume ratio
        
    Returns:
        bool: True if volume confirms the move
    """
    if len(data) < 2:
        return False
    
    # Check for volume spike
    spike_result = detect_volume_spike(data, period=20, threshold=spike_threshold)
    
    if spike_result['spike_detected'] and spike_result['direction'] == direction:
        return True
    
    # Check relative volume
    rel_volume = calculate_relative_volume(data, period=20)
    if rel_volume >= min_relative_volume:
        # Check price direction matches
        current_close = float(data['close'].iloc[-1])
        prev_close = float(data['close'].iloc[-2])
        price_direction = 1 if current_close > prev_close else -1
        
        if price_direction == direction:
            return True
    
    return False

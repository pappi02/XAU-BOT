"""
scalping_setups.py - Professional Scalping Setup Analyzers

This module implements three professional scalping strategies:
1. EMA + VWAP Setup: Fast EMA stack alignment with VWAP confirmation
2. MACD + RSI Reversal: Quick momentum reversal detection
3. Supertrend + ATR Setup: Trend following with automatic stop-loss

Each setup returns high-confidence scalping signals with entry zones,
stop-loss levels, and confidence scores.

Author: XAU-BOT Development Team
Version: 1.0.0
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging

# Import indicators
from indicators.ema import (
    is_ema_stack_bullish, 
    is_ema_stack_bearish, 
    get_ema_stack_alignment,
    calculate_ema_stack
)
from indicators.vwap import (
    calculate_vwap,
    is_price_above_vwap,
    is_price_below_vwap,
    get_vwap_distance,
    get_vwap_signal
)
from indicators.supertrend import (
    calculate_supertrend,
    get_supertrend_signal,
    detect_supertrend_flip,
    calculate_supertrend_stop_loss,
    is_supertrend_bullish,
    is_supertrend_bearish
)
from indicators.volume_analysis import (
    detect_volume_spike,
    get_volume_confirmation,
    calculate_relative_volume
)
from indicators.macd import calculate_macd, get_macd_signal
from indicators.rsi_clean_final import calculate_rsi
from indicators.atr import calculate_atr

logger = logging.getLogger(__name__)


class EmaVwapSetup:
    """
    EMA + VWAP Scalping Setup
    
    Strategy:
    - Uses 8/13/21 EMA stack for trend direction
    - VWAP for institutional support/resistance
    - Volume spike for confirmation
    
    Entry Rules:
    LONG:
      1. EMA stack bullish (8 > 13 > 21)
      2. Price above VWAP (institutional buying)
      3. Volume spike on recent candles
      4. Entry: On pullback to EMA(8) or VWAP
    
    SHORT:
      1. EMA stack bearish (8 < 13 < 21)
      2. Price below VWAP (institutional selling)
      3. Volume spike on recent candles
      4. Entry: On retracement to EMA(8) or VWAP
    
    Confidence Factors:
    - EMA stack alignment strength (0-100)
    - Distance from VWAP (closer = higher confidence)
    - Volume confirmation (spike = +20%)
    - Price position (at entry zone = +15%)
    """
    
    def __init__(self, ema_periods: list = None, vwap_distance_threshold: float = 0.5):
        """
        Initialize EMA + VWAP setup analyzer.
        
        Args:
            ema_periods (list): EMA periods for stack (default: [8, 13, 21])
            vwap_distance_threshold (float): Max distance from VWAP in % (default: 0.5%)
        """
        self.ema_periods = ema_periods or [8, 13, 21]
        self.vwap_distance_threshold = vwap_distance_threshold
        self.name = "EMA_VWAP_Setup"
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Analyze EMA + VWAP setup for scalping opportunity.
        
        Args:
            data (pd.DataFrame): OHLC data with volume
        
        Returns:
            dict: {
                'signal': int (1=long, -1=short, 0=no trade),
                'confidence': float (0-100),
                'condition': str (description),
                'entry_zone': float (suggested entry price),
                'stop_loss': float (suggested SL),
                'take_profit': float (suggested TP),
                'setup_type': str ('EMA_VWAP'),
                'details': dict (additional info)
            }
        """
        try:
            # Get current price
            current_price = data['close'].iloc[-1]
            
            # Calculate EMA stack
            ema_stack = calculate_ema_stack(data, self.ema_periods)
            ema_alignment = get_ema_stack_alignment(data, self.ema_periods)
            
            # Calculate VWAP
            data_with_vwap = data.copy()
            data_with_vwap['vwap'] = calculate_vwap(data)
            vwap_value = data_with_vwap['vwap'].iloc[-1]
            vwap_distance = get_vwap_distance(data_with_vwap, as_percentage=True)
            
            # Volume analysis
            volume_spike = detect_volume_spike(data)
            relative_volume = calculate_relative_volume(data)
            
            # Initialize result
            result = {
                'signal': 0,
                'confidence': 0.0,
                'condition': 'No setup detected',
                'entry_zone': current_price,
                'stop_loss': 0.0,
                'take_profit': 0.0,
                'setup_type': 'EMA_VWAP',
                'details': {}
            }
            
            # Check for bullish setup
            if (ema_alignment['alignment'] == 'bullish' and 
                is_price_above_vwap(data_with_vwap, buffer_pct=0.1)):
                
                signal = 1
                condition = "Bullish EMA+VWAP: Stack aligned, price above VWAP"
                
                # Base confidence from EMA alignment
                confidence = ema_alignment['strength']
                
                # Adjust for VWAP distance (closer = better)
                if abs(vwap_distance) < self.vwap_distance_threshold:
                    confidence += 10
                    condition += ", near VWAP support"
                
                # Adjust for volume
                if volume_spike['spike_detected']:
                    confidence += 15
                    condition += ", volume spike"
                elif relative_volume > 1.2:
                    confidence += 8
                    condition += ", above-average volume"
                
                # Entry zone: EMA(8) or VWAP, whichever is higher
                ema_8 = ema_stack[8].iloc[-1]
                entry_zone = max(ema_8, vwap_value)
                
                # Stop loss: Below EMA(21) or VWAP - 0.2%
                ema_21 = ema_stack[21].iloc[-1]
                stop_loss = min(ema_21, vwap_value * 0.998)
                
                # Take profit: 1.5:1 risk-reward
                risk = entry_zone - stop_loss
                take_profit = entry_zone + (risk * 1.5)
                
                # Update result
                result.update({
                    'signal': signal,
                    'confidence': min(100, confidence),
                    'condition': condition,
                    'entry_zone': entry_zone,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'details': {
                        'ema_8': ema_8,
                        'ema_13': ema_stack[13].iloc[-1],
                        'ema_21': ema_21,
                        'vwap': vwap_value,
                        'vwap_distance_pct': vwap_distance,
                        'volume_spike': volume_spike['spike_detected'],
                        'relative_volume': relative_volume,
                        'ema_strength': ema_alignment['strength']
                    }
                })
            
            # Check for bearish setup
            elif (ema_alignment['alignment'] == 'bearish' and 
                  is_price_below_vwap(data_with_vwap, buffer_pct=0.1)):
                
                signal = -1
                condition = "Bearish EMA+VWAP: Stack aligned, price below VWAP"
                
                # Base confidence from EMA alignment
                confidence = ema_alignment['strength']
                
                # Adjust for VWAP distance (closer = better)
                if abs(vwap_distance) < self.vwap_distance_threshold:
                    confidence += 10
                    condition += ", near VWAP resistance"
                
                # Adjust for volume
                if volume_spike['spike_detected']:
                    confidence += 15
                    condition += ", volume spike"
                elif relative_volume > 1.2:
                    confidence += 8
                    condition += ", above-average volume"
                
                # Entry zone: EMA(8) or VWAP, whichever is lower
                ema_8 = ema_stack[8].iloc[-1]
                entry_zone = min(ema_8, vwap_value)
                
                # Stop loss: Above EMA(21) or VWAP + 0.2%
                ema_21 = ema_stack[21].iloc[-1]
                stop_loss = max(ema_21, vwap_value * 1.002)
                
                # Take profit: 1.5:1 risk-reward
                risk = stop_loss - entry_zone
                take_profit = entry_zone - (risk * 1.5)
                
                # Update result
                result.update({
                    'signal': signal,
                    'confidence': min(100, confidence),
                    'condition': condition,
                    'entry_zone': entry_zone,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'details': {
                        'ema_8': ema_8,
                        'ema_13': ema_stack[13].iloc[-1],
                        'ema_21': ema_21,
                        'vwap': vwap_value,
                        'vwap_distance_pct': vwap_distance,
                        'volume_spike': volume_spike['spike_detected'],
                        'relative_volume': relative_volume,
                        'ema_strength': ema_alignment['strength']
                    }
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in EMA+VWAP setup analysis: {e}")
            return {
                'signal': 0,
                'confidence': 0.0,
                'condition': f'Error: {str(e)}',
                'entry_zone': 0.0,
                'stop_loss': 0.0,
                'take_profit': 0.0,
                'setup_type': 'EMA_VWAP',
                'details': {}
            }


class MacdRsiReversalSetup:
    """
    MACD + RSI Reversal Scalping Setup
    
    Strategy:
    - Fast MACD (8/17/9) for momentum shifts
    - Fast RSI (7-9) for overbought/oversold
    - Volume confirmation for reversal validity
    
    Entry Rules:
    LONG (Bullish Reversal):
      1. RSI < 30 (oversold) or bullish divergence
      2. MACD histogram turning up or bullish crossover
      3. Volume spike confirming reversal
      4. Entry: On first green candle after setup
    
    SHORT (Bearish Reversal):
      1. RSI > 70 (overbought) or bearish divergence
      2. MACD histogram turning down or bearish crossover
      3. Volume spike confirming reversal
      4. Entry: On first red candle after setup
    
    Confidence Factors:
    - RSI extremes (>80 or <20 = +20%)
    - MACD signal strength (histogram size)
    - Volume confirmation (+15%)
    - Divergence detected (+25%)
    """
    
    def __init__(self, rsi_period: int = 7, macd_fast: int = 8, 
                 macd_slow: int = 17, macd_signal: int = 9,
                 rsi_oversold: float = 30, rsi_overbought: float = 70):
        """
        Initialize MACD + RSI reversal setup analyzer.
        
        Args:
            rsi_period (int): RSI period (default: 7 for scalping)
            macd_fast (int): MACD fast period (default: 8)
            macd_slow (int): MACD slow period (default: 17)
            macd_signal (int): MACD signal period (default: 9)
            rsi_oversold (float): RSI oversold level (default: 30)
            rsi_overbought (float): RSI overbought level (default: 70)
        """
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.name = "MACD_RSI_Reversal"
    
    def detect_rsi_divergence(self, data: pd.DataFrame, rsi: pd.Series, 
                             lookback: int = 10) -> Tuple[bool, str]:
        """
        Detect RSI divergence (price makes new high/low but RSI doesn't).
        
        Returns:
            tuple: (divergence_detected: bool, divergence_type: str)
                   divergence_type can be 'bullish', 'bearish', or 'none'
        """
        if len(data) < lookback + 5:
            return False, 'none'
        
        recent_data = data.iloc[-lookback:]
        recent_rsi = rsi.iloc[-lookback:]
        
        # Find price and RSI extremes
        price_low_idx = recent_data['low'].idxmin()
        price_high_idx = recent_data['high'].idxmax()
        rsi_low_idx = recent_rsi.idxmin()
        rsi_high_idx = recent_rsi.idxmax()
        
        # Bullish divergence: Price makes lower low, RSI makes higher low
        if price_low_idx != rsi_low_idx:
            price_current_low = recent_data['low'].iloc[-1]
            price_prev_low = recent_data['low'].min()
            rsi_current = recent_rsi.iloc[-1]
            rsi_at_price_low = recent_rsi.loc[price_low_idx]
            
            if price_current_low < price_prev_low and rsi_current > rsi_at_price_low:
                return True, 'bullish'
        
        # Bearish divergence: Price makes higher high, RSI makes lower high
        if price_high_idx != rsi_high_idx:
            price_current_high = recent_data['high'].iloc[-1]
            price_prev_high = recent_data['high'].max()
            rsi_current = recent_rsi.iloc[-1]
            rsi_at_price_high = recent_rsi.loc[price_high_idx]
            
            if price_current_high > price_prev_high and rsi_current < rsi_at_price_high:
                return True, 'bearish'
        
        return False, 'none'
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Analyze MACD + RSI reversal setup for scalping opportunity.
        
        Args:
            data (pd.DataFrame): OHLC data with volume
        
        Returns:
            dict: Setup analysis results
        """
        try:
            # Get current price
            current_price = data['close'].iloc[-1]
            
            # Calculate RSI
            rsi = calculate_rsi(data, period=self.rsi_period)
            current_rsi = rsi.iloc[-1]
            
            # Calculate MACD
            macd_line, signal_line, histogram = calculate_macd(
                data, 
                fast_period=self.macd_fast,
                slow_period=self.macd_slow,
                signal_period=self.macd_signal
            )
            current_macd = macd_line.iloc[-1]
            current_signal = signal_line.iloc[-1]
            current_histogram = histogram.iloc[-1]
            prev_histogram = histogram.iloc[-2] if len(histogram) > 1 else 0
            
            # Get MACD signal
            macd_signal_val = get_macd_signal(macd_line, signal_line)
            
            # Detect RSI divergence
            divergence_detected, divergence_type = self.detect_rsi_divergence(data, rsi)
            
            # Volume analysis
            volume_spike = detect_volume_spike(data)
            relative_volume = calculate_relative_volume(data)
            
            # Calculate ATR for stop-loss
            atr = calculate_atr(data)
            current_atr = atr.iloc[-1]
            
            # Initialize result
            result = {
                'signal': 0,
                'confidence': 0.0,
                'condition': 'No reversal setup detected',
                'entry_zone': current_price,
                'stop_loss': 0.0,
                'take_profit': 0.0,
                'setup_type': 'MACD_RSI_Reversal',
                'details': {}
            }
            
            # Check for bullish reversal
            if (current_rsi < self.rsi_oversold or divergence_type == 'bullish'):
                # Check if MACD is turning up
                macd_turning_up = (
                    current_histogram > prev_histogram or  # Histogram increasing
                    (macd_signal_val == 1 and current_histogram > 0)  # Bullish crossover
                )
                
                if macd_turning_up:
                    signal = 1
                    confidence = 50  # Base confidence
                    condition = "Bullish Reversal: RSI oversold + MACD turning up"
                    
                    # Extreme RSI bonus
                    if current_rsi < 20:
                        confidence += 20
                        condition += ", extreme oversold"
                    
                    # Divergence bonus
                    if divergence_detected and divergence_type == 'bullish':
                        confidence += 25
                        condition = "Bullish Divergence: " + condition
                    
                    # Volume confirmation
                    if volume_spike['spike_detected']:
                        confidence += 15
                        condition += ", volume spike"
                    elif relative_volume > 1.2:
                        confidence += 8
                    
                    # MACD strength bonus
                    if abs(current_histogram) > abs(prev_histogram) * 1.5:
                        confidence += 10
                        condition += ", strong momentum shift"
                    
                    # Entry, SL, TP
                    entry_zone = current_price
                    stop_loss = current_price - (current_atr * 1.5)
                    risk = entry_zone - stop_loss
                    take_profit = entry_zone + (risk * 2.0)  # 2:1 RR for reversals
                    
                    result.update({
                        'signal': signal,
                        'confidence': min(100, confidence),
                        'condition': condition,
                        'entry_zone': entry_zone,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'details': {
                            'rsi': current_rsi,
                            'macd': current_macd,
                            'macd_signal': current_signal,
                            'macd_histogram': current_histogram,
                            'divergence': divergence_type,
                            'volume_spike': volume_spike['spike_detected'],
                            'relative_volume': relative_volume,
                            'atr': current_atr
                        }
                    })
            
            # Check for bearish reversal
            elif (current_rsi > self.rsi_overbought or divergence_type == 'bearish'):
                # Check if MACD is turning down
                macd_turning_down = (
                    current_histogram < prev_histogram or  # Histogram decreasing
                    (macd_signal_val == -1 and current_histogram < 0)  # Bearish crossover
                )
                
                if macd_turning_down:
                    signal = -1
                    confidence = 50  # Base confidence
                    condition = "Bearish Reversal: RSI overbought + MACD turning down"
                    
                    # Extreme RSI bonus
                    if current_rsi > 80:
                        confidence += 20
                        condition += ", extreme overbought"
                    
                    # Divergence bonus
                    if divergence_detected and divergence_type == 'bearish':
                        confidence += 25
                        condition = "Bearish Divergence: " + condition
                    
                    # Volume confirmation
                    if volume_spike['spike_detected']:
                        confidence += 15
                        condition += ", volume spike"
                    elif relative_volume > 1.2:
                        confidence += 8
                    
                    # MACD strength bonus
                    if abs(current_histogram) > abs(prev_histogram) * 1.5:
                        confidence += 10
                        condition += ", strong momentum shift"
                    
                    # Entry, SL, TP
                    entry_zone = current_price
                    stop_loss = current_price + (current_atr * 1.5)
                    risk = stop_loss - entry_zone
                    take_profit = entry_zone - (risk * 2.0)  # 2:1 RR for reversals
                    
                    result.update({
                        'signal': signal,
                        'confidence': min(100, confidence),
                        'condition': condition,
                        'entry_zone': entry_zone,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'details': {
                            'rsi': current_rsi,
                            'macd': current_macd,
                            'macd_signal': current_signal,
                            'macd_histogram': current_histogram,
                            'divergence': divergence_type,
                            'volume_spike': volume_spike['spike_detected'],
                            'relative_volume': relative_volume,
                            'atr': current_atr
                        }
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in MACD+RSI reversal analysis: {e}")
            return {
                'signal': 0,
                'confidence': 0.0,
                'condition': f'Error: {str(e)}',
                'entry_zone': 0.0,
                'stop_loss': 0.0,
                'take_profit': 0.0,
                'setup_type': 'MACD_RSI_Reversal',
                'details': {}
            }


class SupertrendAtrSetup:
    """
    Supertrend + ATR Scalping Setup
    
    Strategy:
    - Supertrend (10, 3.0) for clear trend direction
    - ATR for dynamic stop-loss placement
    - Automated trailing stop using Supertrend line
    
    Entry Rules:
    LONG:
      1. Supertrend flips to bullish (buy signal)
      2. Price closes above Supertrend line
      3. Volume confirmation (optional but preferred)
      4. Entry: Current price or pullback to Supertrend line
      5. Stop: Supertrend line or ATR-based
    
    SHORT:
      1. Supertrend flips to bearish (sell signal)
      2. Price closes below Supertrend line
      3. Volume confirmation (optional but preferred)
      4. Entry: Current price or retest of Supertrend line
      5. Stop: Supertrend line or ATR-based
    
    Confidence Factors:
    - Fresh Supertrend flip (+20%)
    - Strong trend strength (>70 = +15%)
    - Volume spike (+15%)
    - Distance from Supertrend line (closer = better)
    """
    
    def __init__(self, supertrend_period: int = 10, supertrend_multiplier: float = 3.0,
                 atr_multiplier: float = 1.5):
        """
        Initialize Supertrend + ATR setup analyzer.
        
        Args:
            supertrend_period (int): Supertrend ATR period (default: 10)
            supertrend_multiplier (float): Supertrend multiplier (default: 3.0)
            atr_multiplier (float): ATR multiplier for stop-loss (default: 1.5)
        """
        self.supertrend_period = supertrend_period
        self.supertrend_multiplier = supertrend_multiplier
        self.atr_multiplier = atr_multiplier
        self.name = "Supertrend_ATR_Setup"
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Analyze Supertrend + ATR setup for scalping opportunity.
        
        Args:
            data (pd.DataFrame): OHLC data with volume
        
        Returns:
            dict: Setup analysis results
        """
        try:
            # Get current price
            current_price = data['close'].iloc[-1]
            
            # Calculate Supertrend
            supertrend_line, supertrend_direction = calculate_supertrend(
                data,
                period=self.supertrend_period,
                multiplier=self.supertrend_multiplier
            )
            current_supertrend = supertrend_line.iloc[-1]
            current_direction = supertrend_direction.iloc[-1]
            
            # Detect Supertrend flip
            flip_type = detect_supertrend_flip(data, lookback=2)
            
            # Calculate Supertrend strength
            from indicators.supertrend import get_supertrend_strength
            trend_strength = get_supertrend_strength(data, lookback=20)
            
            # Calculate ATR
            atr = calculate_atr(data, period=self.supertrend_period)
            current_atr = atr.iloc[-1]
            
            # Volume analysis
            volume_spike = detect_volume_spike(data)
            relative_volume = calculate_relative_volume(data)
            
            # Initialize result
            result = {
                'signal': 0,
                'confidence': 0.0,
                'condition': 'No Supertrend setup detected',
                'entry_zone': current_price,
                'stop_loss': 0.0,
                'take_profit': 0.0,
                'setup_type': 'Supertrend_ATR',
                'details': {}
            }
            
            # Check for bullish setup
            if is_supertrend_bullish(data):
                signal = 1
                confidence = 55  # Base confidence for trend following
                condition = "Bullish Supertrend: Uptrend confirmed"
                
                # Fresh flip bonus
                if flip_type == 'buy_flip':
                    confidence += 20
                    condition = "Fresh Bullish Flip: " + condition
                
                # Trend strength bonus
                if trend_strength > 70:
                    confidence += 15
                    condition += ", strong trend"
                elif trend_strength > 50:
                    confidence += 8
                
                # Volume confirmation
                if volume_spike['spike_detected']:
                    confidence += 15
                    condition += ", volume spike"
                elif relative_volume > 1.2:
                    confidence += 7
                
                # Distance from Supertrend (closer = better for entry)
                distance_pct = ((current_price - current_supertrend) / current_price) * 100
                if distance_pct < 0.2:  # Within 0.2% of Supertrend
                    confidence += 10
                    condition += ", near support line"
                
                # Entry zone: Current price or Supertrend line
                entry_zone = max(current_price, current_supertrend)
                
                # Stop loss: Supertrend line - ATR buffer
                stop_loss = calculate_supertrend_stop_loss(
                    data,
                    direction=1,
                    atr_multiplier=self.atr_multiplier
                )
                
                # Take profit: 1.5:1 RR for trend following
                risk = entry_zone - stop_loss
                take_profit = entry_zone + (risk * 1.5)
                
                result.update({
                    'signal': signal,
                    'confidence': min(100, confidence),
                    'condition': condition,
                    'entry_zone': entry_zone,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'details': {
                        'supertrend_line': current_supertrend,
                        'supertrend_direction': current_direction,
                        'flip_type': flip_type,
                        'trend_strength': trend_strength,
                        'atr': current_atr,
                        'distance_from_supertrend_pct': distance_pct,
                        'volume_spike': volume_spike['spike_detected'],
                        'relative_volume': relative_volume
                    }
                })
            
            # Check for bearish setup
            elif is_supertrend_bearish(data):
                signal = -1
                confidence = 55  # Base confidence for trend following
                condition = "Bearish Supertrend: Downtrend confirmed"
                
                # Fresh flip bonus
                if flip_type == 'sell_flip':
                    confidence += 20
                    condition = "Fresh Bearish Flip: " + condition
                
                # Trend strength bonus
                if trend_strength > 70:
                    confidence += 15
                    condition += ", strong trend"
                elif trend_strength > 50:
                    confidence += 8
                
                # Volume confirmation
                if volume_spike['spike_detected']:
                    confidence += 15
                    condition += ", volume spike"
                elif relative_volume > 1.2:
                    confidence += 7
                
                # Distance from Supertrend (closer = better for entry)
                distance_pct = ((current_supertrend - current_price) / current_price) * 100
                if distance_pct < 0.2:  # Within 0.2% of Supertrend
                    confidence += 10
                    condition += ", near resistance line"
                
                # Entry zone: Current price or Supertrend line
                entry_zone = min(current_price, current_supertrend)
                
                # Stop loss: Supertrend line + ATR buffer
                stop_loss = calculate_supertrend_stop_loss(
                    data,
                    direction=-1,
                    atr_multiplier=self.atr_multiplier
                )
                
                # Take profit: 1.5:1 RR for trend following
                risk = stop_loss - entry_zone
                take_profit = entry_zone - (risk * 1.5)
                
                result.update({
                    'signal': signal,
                    'confidence': min(100, confidence),
                    'condition': condition,
                    'entry_zone': entry_zone,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'details': {
                        'supertrend_line': current_supertrend,
                        'supertrend_direction': current_direction,
                        'flip_type': flip_type,
                        'trend_strength': trend_strength,
                        'atr': current_atr,
                        'distance_from_supertrend_pct': distance_pct,
                        'volume_spike': volume_spike['spike_detected'],
                        'relative_volume': relative_volume
                    }
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in Supertrend+ATR setup analysis: {e}")
            return {
                'signal': 0,
                'confidence': 0.0,
                'condition': f'Error: {str(e)}',
                'entry_zone': 0.0,
                'stop_loss': 0.0,
                'take_profit': 0.0,
                'setup_type': 'Supertrend_ATR',
                'details': {}
            }


class ScalpingSetupsAnalyzer:
    """
    Master Analyzer for All Scalping Setups
    
    Coordinates all three scalping strategies and combines their signals
    into a unified recommendation with weighted confidence.
    
    Weights (default):
    - EMA+VWAP: 35% (trend-following bias)
    - MACD+RSI: 30% (reversal opportunities)
    - Supertrend: 35% (strong trend confirmation)
    """
    
    def __init__(self, weights: Dict[str, float] = None):
        """
        Initialize master scalping setups analyzer.
        
        Args:
            weights (dict): Weight for each setup (default: equal)
                Example: {'ema_vwap': 0.35, 'macd_rsi': 0.30, 'supertrend': 0.35}
        """
        self.ema_vwap = EmaVwapSetup()
        self.macd_rsi = MacdRsiReversalSetup()
        self.supertrend = SupertrendAtrSetup()
        
        self.weights = weights or {
            'ema_vwap': 0.35,
            'macd_rsi': 0.30,
            'supertrend': 0.35
        }
        
        # Normalize weights to sum to 1.0
        total_weight = sum(self.weights.values())
        self.weights = {k: v / total_weight for k, v in self.weights.items()}
    
    def analyze_all(self, data: pd.DataFrame) -> Dict:
        """
        Analyze all scalping setups and combine results.
        
        Args:
            data (pd.DataFrame): OHLC data with volume
        
        Returns:
            dict: Combined analysis with weighted confidence
        """
        # Analyze each setup
        ema_vwap_result = self.ema_vwap.analyze(data)
        macd_rsi_result = self.macd_rsi.analyze(data)
        supertrend_result = self.supertrend.analyze(data)
        
        # Store individual results
        setups = {
            'ema_vwap': ema_vwap_result,
            'macd_rsi': macd_rsi_result,
            'supertrend': supertrend_result
        }
        
        # Calculate weighted signal
        weighted_signal = (
            ema_vwap_result['signal'] * ema_vwap_result['confidence'] * self.weights['ema_vwap'] +
            macd_rsi_result['signal'] * macd_rsi_result['confidence'] * self.weights['macd_rsi'] +
            supertrend_result['signal'] * supertrend_result['confidence'] * self.weights['supertrend']
        ) / 100.0  # Normalize by confidence scaling
        
        # Calculate weighted confidence
        weighted_confidence = (
            ema_vwap_result['confidence'] * self.weights['ema_vwap'] +
            macd_rsi_result['confidence'] * self.weights['macd_rsi'] +
            supertrend_result['confidence'] * self.weights['supertrend']
        )
        
        # Determine final signal
        if weighted_signal > 0.3:
            final_signal = 1
        elif weighted_signal < -0.3:
            final_signal = -1
        else:
            final_signal = 0
        
        # Build condition summary
        conditions = []
        if ema_vwap_result['signal'] != 0:
            conditions.append(f"EMA+VWAP: {ema_vwap_result['condition']}")
        if macd_rsi_result['signal'] != 0:
            conditions.append(f"MACD+RSI: {macd_rsi_result['condition']}")
        if supertrend_result['signal'] != 0:
            conditions.append(f"Supertrend: {supertrend_result['condition']}")
        
        condition_summary = " | ".join(conditions) if conditions else "No strong setups"
        
        # Determine best entry/SL/TP (use highest confidence setup)
        best_setup = max(
            [ema_vwap_result, macd_rsi_result, supertrend_result],
            key=lambda x: x['confidence']
        )
        
        return {
            'signal': final_signal,
            'confidence': weighted_confidence,
            'condition': condition_summary,
            'entry_zone': best_setup['entry_zone'],
            'stop_loss': best_setup['stop_loss'],
            'take_profit': best_setup['take_profit'],
            'weighted_signal': weighted_signal,
            'individual_setups': setups,
            'best_setup': best_setup['setup_type']
        }


# Example usage
if __name__ == "__main__":
    import sys
    sys.path.append('..')
    
    # Create sample data
    dates = pd.date_range('2024-01-01', periods=200, freq='5min')
    np.random.seed(42)
    prices = 2600 + np.cumsum(np.random.randn(200) * 5)
    volumes = np.random.randint(1000, 5000, 200)
    
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200),
        'high': prices + np.abs(np.random.randn(200) * 2),
        'low': prices - np.abs(np.random.randn(200) * 2),
        'close': prices,
        'volume': volumes
    }, index=dates)
    
    # Test individual setups
    print("=" * 80)
    print("SCALPING SETUPS ANALYSIS")
    print("=" * 80)
    
    ema_vwap = EmaVwapSetup()
    result1 = ema_vwap.analyze(sample_data)
    print(f"\n1️⃣ EMA+VWAP Setup:")
    print(f"   Signal: {result1['signal']} | Confidence: {result1['confidence']:.1f}%")
    print(f"   Condition: {result1['condition']}")
    print(f"   Entry: {result1['entry_zone']:.2f} | SL: {result1['stop_loss']:.2f} | TP: {result1['take_profit']:.2f}")
    
    macd_rsi = MacdRsiReversalSetup()
    result2 = macd_rsi.analyze(sample_data)
    print(f"\n2️⃣ MACD+RSI Reversal Setup:")
    print(f"   Signal: {result2['signal']} | Confidence: {result2['confidence']:.1f}%")
    print(f"   Condition: {result2['condition']}")
    print(f"   Entry: {result2['entry_zone']:.2f} | SL: {result2['stop_loss']:.2f} | TP: {result2['take_profit']:.2f}")
    
    supertrend_atr = SupertrendAtrSetup()
    result3 = supertrend_atr.analyze(sample_data)
    print(f"\n3️⃣ Supertrend+ATR Setup:")
    print(f"   Signal: {result3['signal']} | Confidence: {result3['confidence']:.1f}%")
    print(f"   Condition: {result3['condition']}")
    print(f"   Entry: {result3['entry_zone']:.2f} | SL: {result3['stop_loss']:.2f} | TP: {result3['take_profit']:.2f}")
    
    # Test combined analyzer
    print("\n" + "=" * 80)
    print("COMBINED SCALPING ANALYSIS")
    print("=" * 80)
    
    analyzer = ScalpingSetupsAnalyzer()
    combined = analyzer.analyze_all(sample_data)
    print(f"\n📊 Final Signal: {combined['signal']}")
    print(f"📈 Weighted Confidence: {combined['confidence']:.1f}%")
    print(f"📋 Conditions: {combined['condition']}")
    print(f"🎯 Entry: {combined['entry_zone']:.2f}")
    print(f"🛑 Stop Loss: {combined['stop_loss']:.2f}")
    print(f"💰 Take Profit: {combined['take_profit']:.2f}")
    print(f"🏆 Best Setup: {combined['best_setup']}")

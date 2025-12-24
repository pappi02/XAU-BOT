"""
Range Scalping Strategy

Professional range scalping strategy that capitalizes on price oscillations within
established support and resistance levels during consolidation periods. Buys at
support, sells at resistance.

Timeframes: 1-5 minute charts (M1, M3, M5)
Risk-Reward: 1:1.5 to 1:2
Stop Loss: Beyond range boundary (support for longs, resistance for shorts)
Take Profit: Opposite range boundary

Entry Criteria:
BUY at Support:
- Price at or near support level
- RSI oversold (< 40)
- Stochastic oversold (K < 30)
- Bollinger Bands lower band touched
- Volume confirms (not declining)

SELL at Resistance:
- Price at or near resistance level
- RSI overbought (> 60)
- Stochastic overbought (K > 70)
- Bollinger Bands upper band touched
- Volume confirms

Exit Criteria:
- Take profit at opposite range boundary
- Stop loss if range breaks (below support or above resistance)
- Exit immediately if range shows breakout signs
- Exit if volume drops significantly (range ending)

Best Market Conditions:
- Low volatility sideways markets
- Clear defined ranges (support/resistance)
- Consolidation after trends
- Avoid during breakout attempts
"""

import pandas as pd
import numpy as np
from typing import Dict, List

from indicators import (
    calculate_rsi,
    calculate_stochastic,
    calculate_bollinger_bands,
    calculate_relative_volume
)


class RangeScalping:
    """Professional Range Scalping Strategy - Trade bounces between support/resistance"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.range_lookback = self.config.get('range_lookback', 50)
        self.range_touch_proximity = self.config.get('range_proximity', 0.003)  # 0.3%
        self.rsi_period = self.config.get('rsi_period', 14)
        self.rsi_oversold = self.config.get('rsi_oversold', 40)
        self.rsi_overbought = self.config.get('rsi_overbought', 60)
        self.stoch_oversold = self.config.get('stoch_oversold', 30)
        self.stoch_overbought = self.config.get('stoch_overbought', 70)
        self.min_range_width = self.config.get('min_range_width', 0.005)  # 0.5% minimum
    
    def identify_range(self, data: pd.DataFrame) -> Dict:
        """Identify support/resistance range"""
        recent = data.tail(self.range_lookback)
        resistance = recent['high'].max()
        support = recent['low'].min()
        range_width = (resistance - support) / support
        
        if range_width < self.min_range_width:
            return {'valid': False, 'reason': 'Range too narrow'}
        
        # Check if price is oscillating (not trending)
        closes = recent['close']
        above_support = (closes > support * 1.01).sum()
        below_resistance = (closes < resistance * 0.99).sum()
        oscillating = above_support > len(closes) * 0.3 and below_resistance > len(closes) * 0.3
        
        if not oscillating:
            return {'valid': False, 'reason': 'Not oscillating, likely trending'}
        
        return {
            'valid': True,
            'support': support,
            'resistance': resistance,
            'width': range_width,
            'middle': (support + resistance) / 2
        }
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        if len(data) < 100:
            return {'signal': 0, 'confidence': 0, 'entry': None, 'sl': None, 'tp': None,
                   'confluences': [], 'reason': 'Insufficient data'}
        
        # Identify range
        range_info = self.identify_range(data)
        if not range_info['valid']:
            return {'signal': 0, 'confidence': 0, 'entry': None, 'sl': None, 'tp': None,
                   'confluences': [], 'reason': range_info.get('reason', 'No valid range')}
        
        support = range_info['support']
        resistance = range_info['resistance']
        
        # Calculate indicators
        rsi = calculate_rsi(data, self.rsi_period)
        stoch_k, stoch_d = calculate_stochastic(data, k_period=14, d_period=3)
        stoch = {'K': stoch_k, 'D': stoch_d}
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(data, period=20, std_dev=2)
        bb = {'upper': bb_upper, 'middle': bb_middle, 'lower': bb_lower}
        vol_ratio = calculate_relative_volume(data, period=20)
        
        current_close = data['close'].iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_stoch_k = stoch['K'].iloc[-1]
        current_vol_ratio = vol_ratio.iloc[-1]
        
        # Check proximity to support/resistance
        dist_to_support = abs(current_close - support) / support
        dist_to_resistance = abs(current_close - resistance) / resistance
        
        at_support = dist_to_support <= self.range_touch_proximity
        at_resistance = dist_to_resistance <= self.range_touch_proximity
        
        if not (at_support or at_resistance):
            return {'signal': 0, 'confidence': 0, 'entry': None, 'sl': None, 'tp': None,
                   'confluences': [], 'reason': 'Price not at range boundary'}
        
        confluences = []
        confidence = 0
        signal = 0
        
        # BUY at Support
        if at_support:
            confluences.append('Price_at_support')
            confidence += 30
            signal = 1
            
            if current_rsi < self.rsi_oversold:
                confluences.append('RSI_oversold')
                confidence += 20
            if current_stoch_k < self.stoch_oversold:
                confluences.append('Stochastic_oversold')
                confidence += 15
            if current_close <= bb['lower'].iloc[-1]:
                confluences.append('BB_lower_band')
                confidence += 10
            if current_vol_ratio >= 1.0:
                confluences.append('Volume_adequate')
                confidence += 5
        
        # SELL at Resistance
        elif at_resistance:
            confluences.append('Price_at_resistance')
            confidence += 30
            signal = -1
            
            if current_rsi > self.rsi_overbought:
                confluences.append('RSI_overbought')
                confidence += 20
            if current_stoch_k > self.stoch_overbought:
                confluences.append('Stochastic_overbought')
                confidence += 15
            if current_close >= bb['upper'].iloc[-1]:
                confluences.append('BB_upper_band')
                confidence += 10
            if current_vol_ratio >= 1.0:
                confluences.append('Volume_adequate')
                confidence += 5
        
        if len(confluences) < 2:
            return {'signal': 0, 'confidence': confidence, 'entry': None, 'sl': None, 'tp': None,
                   'confluences': confluences, 'reason': 'Insufficient range confluence'}
        
        # Calculate SL/TP
        if signal == 1:  # Buy at support
            entry = current_close
            sl = support * 0.998  # Just below support
            tp = resistance * 0.998  # Just below resistance
        else:  # Sell at resistance
            entry = current_close
            sl = resistance * 1.002  # Just above resistance
            tp = support * 1.002  # Just above support
        
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = reward / risk if risk > 0 else 0
        
        return {
            'signal': signal,
            'confidence': min(100, confidence),
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'confluences': confluences,
            'range_support': support,
            'range_resistance': resistance,
            'range_width_pct': range_info['width'] * 100,
            'rsi': current_rsi,
            'stoch_k': current_stoch_k,
            'risk_reward': f"1:{rr:.2f}",
            'reason': 'Range boundary with confluence'
        }

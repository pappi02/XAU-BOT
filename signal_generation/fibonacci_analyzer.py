"""
Fibonacci Analyzer - Detects Fibonacci retracement levels and trend-aligned entries
Inspired by Cabbage FX strategy: uses SMA trend filter + Fib level crossovers
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class FibonacciAnalyzer:
    """
    Fibonacci retracement analyzer with trend filtering.
    
    Strategy:
    - Finds recent high/low over lookback period
    - Calculates 38.2% and 61.8% Fibonacci retracement levels
    - Filters entries via SMA trend (200-bar default)
    - Signals when price crosses Fib levels in trend direction
    """
    
    def __init__(self, fib_lookback: int = 50, sma_trend_length: int = 200):
        """
        Initialize Fibonacci analyzer.
        
        Args:
            fib_lookback: Number of bars for recent high/low (default 50)
            sma_trend_length: SMA period for trend filter (default 200)
        """
        self.fib_lookback = fib_lookback
        self.sma_trend_length = sma_trend_length
        self.last_fib618 = None
        self.last_fib382 = None
        self.last_trend = 0
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Analyze price action against Fibonacci levels with trend filter.
        
        Args:
            data: OHLC DataFrame with columns: open, high, low, close, volume
            
        Returns:
            Dict: Signal analysis with Fib-based entry signals
        """
        try:
            if len(data) < max(self.fib_lookback, self.sma_trend_length) + 5:
                return self._neutral_signal("Insufficient data for Fibonacci analysis")
            
            # 1. Calculate trend filter (SMA 200)
            sma_trend = data['close'].rolling(window=self.sma_trend_length).mean()
            current_price = float(data['close'].iloc[-1])
            sma_trend_val = float(sma_trend.iloc[-1])
            
            # Determine trend direction
            if current_price > sma_trend_val:
                trend = 1  # Uptrend
                trend_name = "Uptrend"
            elif current_price < sma_trend_val:
                trend = -1  # Downtrend
                trend_name = "Downtrend"
            else:
                trend = 0  # At SMA (neutral)
                trend_name = "At SMA"
            
            # 2. Calculate recent high & low (last N bars)
            lookback_data = data.iloc[-self.fib_lookback:]
            recent_high = float(lookback_data['high'].max())
            recent_low = float(lookback_data['low'].min())
            fib_range = recent_high - recent_low
            
            # Guard against zero range
            if fib_range < 0.001:
                return self._neutral_signal("Fibonacci range too small")
            
            # 3. Calculate Fibonacci retracement levels
            fib618 = recent_high - (fib_range * 0.618)  # 61.8% retracement
            fib382 = recent_high - (fib_range * 0.382)  # 38.2% retracement
            
            # Store for crossover detection
            self.last_fib618 = fib618
            self.last_fib382 = fib382
            self.last_trend = trend
            
            # 4. Detect crossovers (using last 2 bars for price movement)
            if len(data) >= 2:
                prev_close = float(data['close'].iloc[-2])
                prev_high = float(data['high'].iloc[-2])
                prev_low = float(data['low'].iloc[-2])
            else:
                prev_close = current_price
                prev_high = current_price
                prev_low = current_price
            
            signal = 0
            confidence = 0
            condition = "No Signal"
            
            # Long signal: price in uptrend + crosses above Fib level
            if trend == 1:
                # Check for crossover above 38.2% or 61.8%
                if (prev_close <= fib382 and current_price > fib382) or \
                   (prev_close <= fib618 and current_price > fib618):
                    signal = 1
                    # Stronger signal if crossing 61.8% (deeper retracement)
                    if prev_close <= fib618 and current_price > fib618:
                        confidence = 85  # Strong: bouncing from deep retracement (boosted from 75)
                    else:
                        confidence = 70  # Moderate: bouncing from shallower level (boosted from 60)
                    condition = f"Long: Uptrend + Fib Crossover (price={current_price:.2f}, fib382={fib382:.2f}, fib618={fib618:.2f})"
            
            # Short signal: price in downtrend + crosses below Fib level
            elif trend == -1:
                # Check for crossunder below 38.2% or 61.8%
                if (prev_close >= fib382 and current_price < fib382) or \
                   (prev_close >= fib618 and current_price < fib618):
                    signal = -1
                    # Stronger signal if crossing 61.8%
                    if prev_close >= fib618 and current_price < fib618:
                        confidence = 85  # Strong: breaking through deep level (boosted from 75)
                    else:
                        confidence = 70  # Moderate: breaking through shallower level (boosted from 60)
                    condition = f"Short: Downtrend + Fib Crossover (price={current_price:.2f}, fib382={fib382:.2f}, fib618={fib618:.2f})"
            
            return {
                'signal': signal,
                'confidence': confidence,
                'condition': condition,
                'trend': trend_name,
                'price': current_price,
                'sma_trend': sma_trend_val,
                'fib_high': recent_high,
                'fib_low': recent_low,
                'fib_618': fib618,
                'fib_382': fib382,
                'fib_range': fib_range,
                'detected_patterns': self._get_pattern_description(signal, trend, current_price, fib618, fib382)
            }
        
        except Exception as e:
            logger.error(f"Error in Fibonacci analysis: {e}")
            return self._neutral_signal(str(e))
    
    def _get_pattern_description(self, signal: int, trend: int, price: float, fib618: float, fib382: float) -> list:
        """Describe the detected Fibonacci pattern"""
        patterns = []
        
        if signal == 1:
            if price > fib618:
                patterns.append("Fibonacci Bullish Bounce (Deep)")
            elif price > fib382:
                patterns.append("Fibonacci Bullish Bounce (Shallow)")
        elif signal == -1:
            if price < fib618:
                patterns.append("Fibonacci Bearish Breakdown (Deep)")
            elif price < fib382:
                patterns.append("Fibonacci Bearish Breakdown (Shallow)")
        
        if signal == 0:
            patterns.append("Fibonacci Pattern: No Crossover")
        
        return patterns
    
    def _neutral_signal(self, reason: str = "") -> Dict:
        """Return neutral signal"""
        return {
            'signal': 0,
            'confidence': 0,
            'condition': f"Neutral: {reason}",
            'trend': "Unknown",
            'price': 0.0,
            'sma_trend': 0.0,
            'fib_high': 0.0,
            'fib_low': 0.0,
            'fib_618': 0.0,
            'fib_382': 0.0,
            'fib_range': 0.0,
            'detected_patterns': []
        }

"""
Technical Indicator Analyzer - Analyzes and combines technical indicators
Consolidates EMA, RSI, Bollinger Bands, ATR, ADX, MACD, Stochastic signals
"""

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass
from typing import Dict, Tuple, Optional

# Import all indicators
from indicators import (
    calculate_ema, add_ema_signals, get_ema_trend, is_bullish_ema, is_bearish_ema,
    calculate_rsi, add_rsi_signals, get_rsi_condition, get_rsi_signal, is_rsi_oversold, is_rsi_overbought,
    calculate_bollinger_bands, add_bollinger_signals, get_bollinger_signal, is_price_at_upper_band, is_price_at_lower_band,
    calculate_atr, add_atr_signals, is_high_volatility, is_low_volatility,
    calculate_adx, add_adx_signals, get_adx_trend_signal, is_strong_trend,
    calculate_macd, add_macd_signals, get_macd_signal,
    calculate_stochastic, add_stochastic_signals, get_stochastic_signal
)

logger = logging.getLogger(__name__)

@dataclass
class IndicatorSignal:
    """Container for indicator analysis results"""
    indicator: str
    signal: int  # 1 (bullish), -1 (bearish), 0 (neutral)
    strength: float  # 0-100
    condition: str  # describes the condition
    details: Dict = None

class TechnicalIndicatorAnalyzer:
    """
    Professional-grade technical indicator analyzer.
    Combines multiple indicators with weighted voting for robust signals.
    """
    
    def __init__(self):
        """Initialize the analyzer with default weights"""
        self.ema_weight = 0.25
        self.rsi_weight = 0.20
        self.bollinger_weight = 0.15
        self.atr_weight = 0.10
        self.adx_weight = 0.15
        self.macd_weight = 0.10
        self.stochastic_weight = 0.05
        
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Comprehensive technical analysis of price data.
        
        Args:
            data (pd.DataFrame): OHLC data with columns: open, high, low, close, volume
            
        Returns:
            Dict: Combined analysis with signal, strength, and detailed breakdown
        """
        if len(data) < 30:
            return self._neutral_signal("Insufficient data")
        
        try:
            # Analyze each indicator
            ema_signal = self._analyze_ema(data)
            rsi_signal = self._analyze_rsi(data)
            bollinger_signal = self._analyze_bollinger(data)
            atr_signal = self._analyze_atr(data)
            adx_signal = self._analyze_adx(data)
            macd_signal = self._analyze_macd(data)
            stochastic_signal = self._analyze_stochastic(data)
            
            # Combine signals with weighted voting
            combined_signal, combined_strength = self._combine_signals([
                (ema_signal, self.ema_weight),
                (rsi_signal, self.rsi_weight),
                (bollinger_signal, self.bollinger_weight),
                (atr_signal, self.atr_weight),
                (adx_signal, self.adx_weight),
                (macd_signal, self.macd_weight),
                (stochastic_signal, self.stochastic_weight)
            ])
            
            return {
                'signal': combined_signal,
                'strength': combined_strength,
                'condition': self._get_condition_description(combined_signal, combined_strength),
                'indicators': {
                    'ema': ema_signal,
                    'rsi': rsi_signal,
                    'bollinger': bollinger_signal,
                    'atr': atr_signal,
                    'adx': adx_signal,
                    'macd': macd_signal,
                    'stochastic': stochastic_signal
                },
                'volatility_level': self._assess_volatility(data),
                'trend_strength': self._assess_trend_strength(data)
            }
        except Exception as e:
            logger.error(f"Error in technical analysis: {e}")
            return self._neutral_signal(str(e))
    
    def _analyze_ema(self, data: pd.DataFrame) -> IndicatorSignal:
        """Analyze EMA signals"""
        try:
            fast_ema = calculate_ema(data, period=12)
            slow_ema = calculate_ema(data, period=26)
            
            signal = 1 if fast_ema.iloc[-1] > slow_ema.iloc[-1] else -1
            
            # Calculate EMA distance strength (0-100)
            distance_pct = abs(fast_ema.iloc[-1] - slow_ema.iloc[-1]) / slow_ema.iloc[-1]
            strength = min(100, distance_pct * 1000)  # Scale to 0-100
            
            condition = "Bullish EMA" if signal == 1 else "Bearish EMA"
            
            return IndicatorSignal(
                indicator='EMA',
                signal=signal,
                strength=strength,
                condition=condition,
                details={
                    'fast_ema': fast_ema.iloc[-1],
                    'slow_ema': slow_ema.iloc[-1],
                    'distance': fast_ema.iloc[-1] - slow_ema.iloc[-1]
                }
            )
        except Exception as e:
            logger.warning(f"EMA analysis error: {e}")
            return IndicatorSignal('EMA', 0, 0, f"Error: {str(e)}")
    
    def _analyze_rsi(self, data: pd.DataFrame) -> IndicatorSignal:
        """Analyze RSI signals"""
        try:
            rsi = calculate_rsi(data, period=14)
            rsi_value = rsi.iloc[-1]
            
            # Determine signal
            if rsi_value < 30:
                signal = 1
                condition = f"Oversold ({rsi_value:.1f})"
                strength = (30 - rsi_value) * 3.33  # 0-100
            elif rsi_value > 70:
                signal = -1
                condition = f"Overbought ({rsi_value:.1f})"
                strength = (rsi_value - 70) * 3.33  # 0-100
            else:
                signal = 1 if rsi_value > 50 else -1
                condition = f"Neutral ({rsi_value:.1f})"
                strength = abs(rsi_value - 50) * 2  # 0-100
            
            return IndicatorSignal(
                indicator='RSI',
                signal=signal,
                strength=min(100, strength),
                condition=condition,
                details={'rsi_value': rsi_value}
            )
        except Exception as e:
            logger.warning(f"RSI analysis error: {e}")
            return IndicatorSignal('RSI', 0, 0, f"Error: {str(e)}")
    
    def _analyze_bollinger(self, data: pd.DataFrame) -> IndicatorSignal:
        """Analyze Bollinger Bands signals"""
        try:
            upper, middle, lower = calculate_bollinger_bands(data, period=20)
            price = data['close'].iloc[-1]
            
            # Determine signal
            if price <= lower.iloc[-1]:
                signal = 1
                condition = "Price at Lower Band"
                strength = 80
            elif price >= upper.iloc[-1]:
                signal = -1
                condition = "Price at Upper Band"
                strength = 80
            else:
                # Measure position within bands (0-100)
                band_width = upper.iloc[-1] - lower.iloc[-1]
                position = (price - lower.iloc[-1]) / band_width if band_width > 0 else 0.5
                signal = 1 if position < 0.33 else (-1 if position > 0.67 else 0)
                condition = f"Within Bands ({position*100:.1f}%)"
                strength = 50
            
            return IndicatorSignal(
                indicator='Bollinger',
                signal=signal,
                strength=strength,
                condition=condition,
                details={
                    'upper': upper.iloc[-1],
                    'middle': middle.iloc[-1],
                    'lower': lower.iloc[-1],
                    'price': price
                }
            )
        except Exception as e:
            logger.warning(f"Bollinger analysis error: {e}")
            return IndicatorSignal('Bollinger', 0, 0, f"Error: {str(e)}")
    
    def _analyze_atr(self, data: pd.DataFrame) -> IndicatorSignal:
        """Analyze ATR for volatility context"""
        try:
            atr = calculate_atr(data, period=14)
            atr_value = atr.iloc[-1]
            atr_mean = atr.rolling(window=20).mean().iloc[-1]
            
            # ATR is context indicator, not directional
            if is_high_volatility(atr_value, atr_mean):
                signal = 0  # High vol doesn't indicate direction
                condition = f"High Volatility (ATR: {atr_value:.2f})"
                strength = 60
            elif is_low_volatility(atr_value, atr_mean):
                signal = 0
                condition = f"Low Volatility (ATR: {atr_value:.2f})"
                strength = 40
            else:
                signal = 0
                condition = f"Normal Volatility (ATR: {atr_value:.2f})"
                strength = 50
            
            return IndicatorSignal(
                indicator='ATR',
                signal=signal,
                strength=strength,
                condition=condition,
                details={'atr': atr_value, 'atr_mean': atr_mean}
            )
        except Exception as e:
            logger.warning(f"ATR analysis error: {e}")
            return IndicatorSignal('ATR', 0, 50, f"Error: {str(e)}")
    
    def _analyze_adx(self, data: pd.DataFrame) -> IndicatorSignal:
        """Analyze ADX for trend strength confirmation"""
        try:
            adx, plus_di, minus_di = calculate_adx(data, period=14)
            adx_value = adx.iloc[-1]
            
            # Determine trend direction from DI
            if plus_di.iloc[-1] > minus_di.iloc[-1]:
                signal = 1 if is_strong_trend(adx_value) else 0
                trend = "Bullish"
            else:
                signal = -1 if is_strong_trend(adx_value) else 0
                trend = "Bearish"
            
            # Strength based on ADX value
            if adx_value > 40:
                strength = 100
                trend_strength = "Very Strong"
            elif adx_value > 25:
                strength = 75
                trend_strength = "Strong"
            elif adx_value > 20:
                strength = 50
                trend_strength = "Moderate"
            else:
                strength = 25
                trend_strength = "Weak"
            
            condition = f"{trend} {trend_strength} (ADX: {adx_value:.1f})"
            
            return IndicatorSignal(
                indicator='ADX',
                signal=signal,
                strength=strength,
                condition=condition,
                details={'adx': adx_value, 'plus_di': plus_di.iloc[-1], 'minus_di': minus_di.iloc[-1]}
            )
        except Exception as e:
            logger.warning(f"ADX analysis error: {e}")
            return IndicatorSignal('ADX', 0, 0, f"Error: {str(e)}")
    
    def _analyze_macd(self, data: pd.DataFrame) -> IndicatorSignal:
        """Analyze MACD signals"""
        try:
            macd_line, signal_line, histogram = calculate_macd(data)
            
            # Signal is based on histogram position
            if histogram.iloc[-1] > 0:
                signal = 1
                condition = f"Bullish (Hist: +{histogram.iloc[-1]:.4f})"
            elif histogram.iloc[-1] < 0:
                signal = -1
                condition = f"Bearish (Hist: {histogram.iloc[-1]:.4f})"
            else:
                signal = 0
                condition = "Neutral (Zero Line)"
            
            # Strength based on histogram magnitude
            strength = min(100, abs(histogram.iloc[-1]) * 10000)
            
            return IndicatorSignal(
                indicator='MACD',
                signal=signal,
                strength=strength,
                condition=condition,
                details={
                    'macd': macd_line.iloc[-1],
                    'signal': signal_line.iloc[-1],
                    'histogram': histogram.iloc[-1]
                }
            )
        except Exception as e:
            logger.warning(f"MACD analysis error: {e}")
            return IndicatorSignal('MACD', 0, 0, f"Error: {str(e)}")
    
    def _analyze_stochastic(self, data: pd.DataFrame) -> IndicatorSignal:
        """Analyze Stochastic Oscillator signals"""
        try:
            k, d = calculate_stochastic(data, k_period=14, d_period=3)
            k_value = k.iloc[-1]
            
            # Determine signal
            if k_value < 20:
                signal = 1
                condition = f"Oversold ({k_value:.1f})"
                strength = (20 - k_value) * 5
            elif k_value > 80:
                signal = -1
                condition = f"Overbought ({k_value:.1f})"
                strength = (k_value - 80) * 5
            else:
                signal = 1 if k_value > 50 else -1
                condition = f"Neutral ({k_value:.1f})"
                strength = abs(k_value - 50) * 2
            
            return IndicatorSignal(
                indicator='Stochastic',
                signal=signal,
                strength=min(100, strength),
                condition=condition,
                details={'k': k_value, 'd': d.iloc[-1]}
            )
        except Exception as e:
            logger.warning(f"Stochastic analysis error: {e}")
            return IndicatorSignal('Stochastic', 0, 0, f"Error: {str(e)}")
    
    def _combine_signals(self, signals_with_weights: list) -> Tuple[int, float]:
        """
        Combine signals using weighted voting.
        
        Args:
            signals_with_weights: List of (IndicatorSignal, weight) tuples
            
        Returns:
            Tuple: (combined_signal, combined_strength)
        """
        total_weight = sum(w for _, w in signals_with_weights)
        weighted_signal = 0
        weighted_strength = 0
        
        for signal_obj, weight in signals_with_weights:
            weighted_signal += signal_obj.signal * weight
            weighted_strength += signal_obj.strength * weight
        
        # Normalize
        combined_strength = weighted_strength / total_weight if total_weight > 0 else 0
        
        # Final signal based on weighted majority (slightly more permissive)
        if weighted_signal / total_weight > 0.1:
            combined_signal = 1
        elif weighted_signal / total_weight < -0.1:
            combined_signal = -1
        else:
            combined_signal = 0
        
        return combined_signal, combined_strength
    
    def _assess_volatility(self, data: pd.DataFrame) -> str:
        """Assess current market volatility level"""
        try:
            atr = calculate_atr(data, period=14)
            atr_mean = atr.rolling(window=20).mean()
            
            if is_high_volatility(atr.iloc[-1], atr_mean.iloc[-1]):
                return "HIGH"
            elif is_low_volatility(atr.iloc[-1], atr_mean.iloc[-1]):
                return "LOW"
            else:
                return "NORMAL"
        except:
            return "UNKNOWN"
    
    def _assess_trend_strength(self, data: pd.DataFrame) -> str:
        """Assess current trend strength"""
        try:
            adx, _, _ = calculate_adx(data, period=14)
            adx_value = adx.iloc[-1]
            
            if adx_value > 40:
                return "VERY_STRONG"
            elif adx_value > 25:
                return "STRONG"
            elif adx_value > 20:
                return "MODERATE"
            else:
                return "WEAK"
        except:
            return "UNKNOWN"
    
    def _neutral_signal(self, reason: str = "") -> Dict:
        """Return neutral signal with reason"""
        return {
            'signal': 0,
            'strength': 0,
            'condition': f'Neutral/Error: {reason}',
            'indicators': {},
            'volatility_level': 'UNKNOWN',
            'trend_strength': 'UNKNOWN'
        }
    
    def _get_condition_description(self, signal: int, strength: float) -> str:
        """Get human-readable condition description"""
        if signal == 1:
            return f"Bullish ({strength:.1f}% confidence)"
        elif signal == -1:
            return f"Bearish ({strength:.1f}% confidence)"
        else:
            return "Neutral/Mixed Signals"

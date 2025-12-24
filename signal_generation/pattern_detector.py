"""
Pattern Detector - Detects and analyzes chart patterns
Combines candlestick patterns, price action, and technical formations
"""

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from patterns import (
    detect_triple_top, detect_triple_bottom,
    RisingWedge, FallingWedge,
    detect_double_top, detect_double_bottom,
    detect_head_and_shoulders,
    detect_bullish_channel, detect_bearish_channel
)

logger = logging.getLogger(__name__)

@dataclass
class PatternSignal:
    """Container for pattern detection results"""
    pattern_name: str
    signal: int  # 1 (bullish), -1 (bearish), 0 (neutral)
    confidence: float  # 0-100
    entry_level: float
    stop_loss_level: float
    take_profit_level: float
    details: Dict = None

class PatternDetector:
    """
    Professional-grade chart pattern detector.
    Detects continuation patterns, reversal patterns, and price action formations.
    """
    
    def __init__(self):
        """Initialize pattern detector"""
        self.min_pattern_confidence = 0.50
        self.detected_patterns = []
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Comprehensive pattern analysis of price data.
        
        Args:
            data (pd.DataFrame): OHLC data with columns: open, high, low, close
            
        Returns:
            Dict: Detected patterns with signals and confidence levels
        """
        if len(data) < 50:
            return self._no_patterns("Insufficient data")
        
        try:
            patterns = []
            
            # Reversal patterns
            try:
                triple_top = detect_triple_top(data)
                if triple_top['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Triple Top',
                        signal=-1,
                        confidence=triple_top.get('confidence', 60),
                        entry_level=triple_top.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=triple_top.get('stop_loss', data['high'].tail(20).max()),
                        take_profit_level=triple_top.get('take_profit', data['close'].iloc[-1] * 0.98),
                        details=triple_top
                    ))
            except Exception as e:
                logger.debug(f"Triple top detection error: {e}")
            
            try:
                triple_bottom = detect_triple_bottom(data)
                if triple_bottom['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Triple Bottom',
                        signal=1,
                        confidence=triple_bottom.get('confidence', 60),
                        entry_level=triple_bottom.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=triple_bottom.get('stop_loss', data['low'].tail(20).min()),
                        take_profit_level=triple_bottom.get('take_profit', data['close'].iloc[-1] * 1.02),
                        details=triple_bottom
                    ))
            except Exception as e:
                logger.debug(f"Triple bottom detection error: {e}")
            
            try:
                double_top = detect_double_top(data)
                if double_top['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Double Top',
                        signal=-1,
                        confidence=double_top.get('confidence', 65),
                        entry_level=double_top.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=double_top.get('stop_loss', data['high'].tail(20).max()),
                        take_profit_level=double_top.get('take_profit', data['close'].iloc[-1] * 0.98),
                        details=double_top
                    ))
            except Exception as e:
                logger.debug(f"Double top detection error: {e}")
            
            try:
                double_bottom = detect_double_bottom(data)
                if double_bottom['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Double Bottom',
                        signal=1,
                        confidence=double_bottom.get('confidence', 65),
                        entry_level=double_bottom.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=double_bottom.get('stop_loss', data['low'].tail(20).min()),
                        take_profit_level=double_bottom.get('take_profit', data['close'].iloc[-1] * 1.02),
                        details=double_bottom
                    ))
            except Exception as e:
                logger.debug(f"Double bottom detection error: {e}")
            
            try:
                h_s = detect_head_and_shoulders(data)
                if h_s['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Head & Shoulders',
                        signal=-1,
                        confidence=h_s.get('confidence', 70),
                        entry_level=h_s.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=h_s.get('stop_loss', data['high'].tail(30).max()),
                        take_profit_level=h_s.get('take_profit', data['close'].iloc[-1] * 0.97),
                        details=h_s
                    ))
            except Exception as e:
                logger.debug(f"Head & Shoulders detection error: {e}")
            
            # Continuation patterns
            try:
                rising_wedge = RisingWedge().detect(data)
                if rising_wedge['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Rising Wedge',
                        signal=-1,
                        confidence=rising_wedge.get('confidence', 55),
                        entry_level=rising_wedge.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=rising_wedge.get('stop_loss', data['high'].tail(20).max()),
                        take_profit_level=rising_wedge.get('take_profit', data['close'].iloc[-1] * 0.99),
                        details=rising_wedge
                    ))
            except Exception as e:
                logger.debug(f"Rising Wedge detection error: {e}")
            
            try:
                falling_wedge = FallingWedge().detect(data)
                if falling_wedge['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Falling Wedge',
                        signal=1,
                        confidence=falling_wedge.get('confidence', 55),
                        entry_level=falling_wedge.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=falling_wedge.get('stop_loss', data['low'].tail(20).min()),
                        take_profit_level=falling_wedge.get('take_profit', data['close'].iloc[-1] * 1.01),
                        details=falling_wedge
                    ))
            except Exception as e:
                logger.debug(f"Falling Wedge detection error: {e}")
            
            # Channel patterns
            try:
                bull_channel = detect_bullish_channel(data)
                if bull_channel['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Bullish Channel',
                        signal=1,
                        confidence=bull_channel.get('confidence', 60),
                        entry_level=bull_channel.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=bull_channel.get('stop_loss', data['low'].tail(20).min()),
                        take_profit_level=bull_channel.get('take_profit', data['close'].iloc[-1] * 1.02),
                        details=bull_channel
                    ))
            except Exception as e:
                logger.debug(f"Bullish channel detection error: {e}")
            
            try:
                bear_channel = detect_bearish_channel(data)
                if bear_channel['detected']:
                    patterns.append(PatternSignal(
                        pattern_name='Bearish Channel',
                        signal=-1,
                        confidence=bear_channel.get('confidence', 60),
                        entry_level=bear_channel.get('entry_level', data['close'].iloc[-1]),
                        stop_loss_level=bear_channel.get('stop_loss', data['high'].tail(20).max()),
                        take_profit_level=bear_channel.get('take_profit', data['close'].iloc[-1] * 0.98),
                        details=bear_channel
                    ))
            except Exception as e:
                logger.debug(f"Bearish channel detection error: {e}")
            
            # Combine pattern signals
            if patterns:
                return self._combine_patterns(patterns)
            else:
                return self._no_patterns("No patterns detected")
        
        except Exception as e:
            logger.error(f"Error in pattern analysis: {e}")
            return self._no_patterns(str(e))
    
    def _combine_patterns(self, patterns: List[PatternSignal]) -> Dict:
        """
        Combine multiple pattern signals.
        
        Args:
            patterns: List of detected patterns
            
        Returns:
            Dict: Combined pattern analysis
        """
        # Separate bullish and bearish patterns
        bullish_patterns = [p for p in patterns if p.signal == 1]
        bearish_patterns = [p for p in patterns if p.signal == -1]
        
        # Calculate weighted signals
        bullish_strength = sum(p.confidence for p in bullish_patterns) / len(bullish_patterns) if bullish_patterns else 0
        bearish_strength = sum(p.confidence for p in bearish_patterns) / len(bearish_patterns) if bearish_patterns else 0
        
        # Determine combined signal
        if bullish_strength > bearish_strength + 10:
            combined_signal = 1
            confidence = bullish_strength
        elif bearish_strength > bullish_strength + 10:
            combined_signal = -1
            confidence = bearish_strength
        else:
            combined_signal = 0
            confidence = max(bullish_strength, bearish_strength)
        
        return {
            'signal': combined_signal,
            'confidence': confidence,
            'condition': self._get_pattern_condition(combined_signal, confidence),
            'detected_patterns': [
                {
                    'name': p.pattern_name,
                    'signal': p.signal,
                    'confidence': p.confidence,
                    'entry': p.entry_level,
                    'stop_loss': p.stop_loss_level,
                    'take_profit': p.take_profit_level
                }
                for p in patterns
            ],
            'bullish_count': len(bullish_patterns),
            'bearish_count': len(bearish_patterns),
            'total_patterns': len(patterns)
        }
    
    def _no_patterns(self, reason: str = "") -> Dict:
        """Return no patterns detected"""
        return {
            'signal': 0,
            'confidence': 0,
            'condition': f'No patterns: {reason}',
            'detected_patterns': [],
            'bullish_count': 0,
            'bearish_count': 0,
            'total_patterns': 0
        }
    
    def _get_pattern_condition(self, signal: int, confidence: float) -> str:
        """Get human-readable pattern condition"""
        if signal == 1:
            return f"Bullish Patterns ({confidence:.1f}% confidence)"
        elif signal == -1:
            return f"Bearish Patterns ({confidence:.1f}% confidence)"
        else:
            return "Mixed/No Clear Patterns"

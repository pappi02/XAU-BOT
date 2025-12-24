"""
Adaptive Signal Analyzer - Handles adaptive engine, signal smoothing, and quality control
Implements signal validation, persistence checking, and conflict resolution
"""

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from collections import deque

from utils.signal_smoothing_pro import evaluate_enhanced_signal, smooth_signal
from adaptive_engine import AdaptiveEngine, MarketData
import config as _config

logger = logging.getLogger(__name__)

@dataclass
class AdaptiveSignalResult:
    """Container for adaptive signal analysis"""
    original_signal: int
    final_signal: int
    confidence: float
    reason: str
    smoothed: bool
    persistence_check: bool
    details: Dict = None

class AdaptiveSignalAnalyzer:
    """
    Professional-grade adaptive signal analyzer.
    Implements signal smoothing, persistence checking, conflict resolution, and quality control.
    """
    
    def __init__(self, lookback_periods: int = 10, min_persistence: int = 2, sensitivity: str = 'balanced'):
        """
        Initialize adaptive analyzer.
        
        Args:
            lookback_periods: Number of periods to track signal history
            min_persistence: Minimum consecutive periods for signal confirmation
        """
        self.lookback_periods = lookback_periods
        # Configure thresholds based on sensitivity preset
        sensitivity = (sensitivity or 'balanced').lower()
        preset_map = {
            'conservative': {'min_strength': 45, 'min_persistence': 2},
            'balanced': {'min_strength': 25, 'min_persistence': 1},
            'aggressive': {'min_strength': 10, 'min_persistence': 0},
        }
        preset = preset_map.get(sensitivity, preset_map['balanced'])
        self.min_persistence = min_persistence if min_persistence is not None else preset['min_persistence']
        self.min_strength_threshold = preset['min_strength']
        self.sensitivity = sensitivity
        self.signal_history = deque(maxlen=lookback_periods)
        # Initialize adaptive engine with default config to avoid missing-arg errors
        self.adaptive_engine = AdaptiveEngine(_config)
        self.last_signal = 0
        self.last_signal_strength = 0
    
    def analyze(self, 
                original_signal: int,
                signal_strength: float,
                data: pd.DataFrame,
                market_conditions: Dict,
                **kwargs) -> Dict:
        """
        Apply adaptive analysis and quality control to raw signal.
        
        Args:
            original_signal: Raw signal from indicators/patterns/news (-1, 0, 1)
            signal_strength: Strength of the signal (0-100)
            data: OHLC data for context
            market_conditions: Current market conditions (volatility, trend, etc.)
            **kwargs: Additional parameters (price, volatility, etc.)
            
        Returns:
            Dict: Adaptively processed signal with validation
        """
        try:
            # Step 1: Evaluate signal quality using professional smoothing
            tech_signal = {
                'signal': 'BUY' if original_signal == 1 else ('SELL' if original_signal == -1 else 'HOLD'),
                'strength': float(signal_strength)
            }
            patterns_list = []
            if kwargs.get('pattern_signal', 0) == 1:
                patterns_list = [{'detected': True, 'type': 'bullish', 'confidence': 0.6}]
            elif kwargs.get('pattern_signal', 0) == -1:
                patterns_list = [{'detected': True, 'type': 'bearish', 'confidence': 0.6}]

            news_data = {
                'sentiment': 'bullish' if kwargs.get('news_signal', 0) == 1 else ('bearish' if kwargs.get('news_signal', 0) == -1 else 'neutral')
            }

            vol = market_conditions.get('volatility', 'NORMAL')
            trend = market_conditions.get('trend', 'MODERATE')
            trend_intensity = 0.6
            if trend == 'STRONG':
                trend_intensity = 0.8
            elif trend == 'WEAK':
                trend_intensity = 0.4
            volatility_num = 1.0
            if vol == 'HIGH':
                volatility_num = 1.8
            elif vol == 'LOW':
                volatility_num = 0.8

            market_context = {
                'trend_intensity': trend_intensity,
                'volatility': volatility_num
            }

            quality_result = evaluate_enhanced_signal(
                tech_signal=tech_signal,
                patterns=patterns_list,
                news_data=news_data,
                market_context=market_context
            )

            # Map quality result back to unified numeric signal
            qr_signal_str = quality_result.get('signal', 'HOLD')
            final_signal = 1 if qr_signal_str == 'BUY' else (-1 if qr_signal_str == 'SELL' else 0)
            # Use raw strength when result is HOLD to avoid misleading 0.0% strength
            quality_conf = float(quality_result.get('confidence', 0.0))
            quality_strength = float(quality_result.get('strength', 0.0))
            final_strength = (quality_strength if qr_signal_str == 'HOLD' else quality_conf) * 100.0
            smoothed = final_signal != original_signal
            
            # Step 2: Check signal persistence
            persistence_check = self._check_signal_persistence(final_signal)
            
            # Step 3: Apply adaptive engine for market-aware adjustments
            market_adapted_signal = self._apply_adaptive_engine(
                final_signal,
                final_strength,
                data,
                market_conditions
            )
            
            # Step 4: Resolve conflicts if present
            conflict_resolved_signal = self._resolve_signal_conflicts(
                combined_signal=final_signal,
                combined_strength=final_strength,
                indicator_signal=kwargs.get('indicator_signal', 0),
                pattern_signal=kwargs.get('pattern_signal', 0),
                fib_signal=kwargs.get('fib_signal', 0),
                strategy_signal=kwargs.get('strategy_signal', 0),
                news_signal=kwargs.get('news_signal', 0),
                news_confidence=kwargs.get('news_confidence', 0.0)
            )
            
            # Step 5: Final validation
            validated_signal = self._validate_signal(
                conflict_resolved_signal,
                final_strength,
                persistence_check
            )
            
            # Update signal history
            self.signal_history.append(validated_signal)
            self.last_signal = validated_signal
            self.last_signal_strength = final_strength
            
            return {
                'signal': validated_signal,
                'strength': final_strength,
                'condition': self._get_adaptive_condition(validated_signal, final_strength),
                'smoothed': smoothed,
                'persistence_confirmed': persistence_check,
                'adaptive_adjustments': {
                    'original': original_signal,
                    'after_smoothing': final_signal,
                    'after_adaptive': market_adapted_signal,
                    'after_conflict_resolution': conflict_resolved_signal,
                    'final': validated_signal
                },
                'quality_metrics': {
                    'signal_consistency': self._get_signal_consistency(),
                    'recent_history': list(self.signal_history),
                    'stability_score': self._calculate_stability_score()
                },
                'recommendation': self._get_signal_recommendation(validated_signal, final_strength, persistence_check),
                'timestamp': pd.Timestamp.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error in adaptive signal analysis: {e}")
            return self._neutral_adaptive_signal(str(e))
    
    def _check_signal_persistence(self, signal: int) -> bool:
        """
        Check if signal has sufficient persistence.
        
        Args:
            signal: Current signal
            
        Returns:
            bool: True if signal persists for minimum periods
        """
        if signal == 0:
            return True  # Neutral signals don't require persistence
        
        # Count consecutive same signals at end of history
        consecutive = 0
        for s in reversed(self.signal_history):
            if s == signal:
                consecutive += 1
            else:
                break
        
        return consecutive >= self.min_persistence
    
    def _apply_adaptive_engine(self,
                              signal: int,
                              strength: float,
                              data: pd.DataFrame,
                              market_conditions: Dict) -> int:
        """
        Apply adaptive engine adjustments based on market conditions.
        
        Args:
            signal: Current signal
            strength: Signal strength
            data: OHLC data
            market_conditions: Market context
            
        Returns:
            int: Adaptively adjusted signal
        """
        try:
            # Create market data for adaptive engine
            market_data = MarketData(
                price=data['close'].iloc[-1],
                volatility=market_conditions.get('volatility', 0.5),
                trend=market_conditions.get('trend', 0),
                adr=market_conditions.get('adr', 1.0),
                volume=data['volume'].iloc[-1] if 'volume' in data.columns else 1000
            )
            
            # Update market data in adaptive engine
            self.adaptive_engine.update_market_data(market_data)
            
            # Process signal through adaptive engine
            adjusted_signal = self.adaptive_engine.process_signals({
                'signal': signal,
                'strength': strength,
                'type': 'unified'
            })
            
            return adjusted_signal if isinstance(adjusted_signal, int) else signal
        
        except Exception as e:
            logger.debug(f"Adaptive engine adjustment error: {e}")
            return signal
    
    def _resolve_signal_conflicts(self,
                                 combined_signal: int,
                                 combined_strength: float,
                                 indicator_signal: int,
                                 pattern_signal: int,
                                 fib_signal: int,
                                 strategy_signal: int,
                                 news_signal: int,
                                 news_confidence: float) -> int:
        """
        Resolve conflicts between different signal sources.
        
        Args:
            combined_signal: Already combined signal
            combined_strength: Strength of combined signal
            indicator_signal: Technical indicator signal
            pattern_signal: Chart pattern signal
            fib_signal: Fibonacci signal
            strategy_signal: Strategy signal
            news_signal: News sentiment signal
            news_confidence: News confidence (0 if unavailable)
            
        Returns:
            int: Conflict-resolved signal
        """
        # Only consider news if we have confidence
        news_available = news_confidence and news_confidence > 0

        # Core signals: indicators, fibonacci (highest priority), patterns, strategies
        core_signals = [indicator_signal, fib_signal, pattern_signal, strategy_signal]
        bullish_core = sum(1 for sig in core_signals if sig == 1)
        bearish_core = sum(1 for sig in core_signals if sig == -1)

        # If combined signal is already decisive and strong enough, prefer it unless core opposes strongly
        min_strength = getattr(self, 'min_strength_threshold', 30)
        if combined_signal != 0 and combined_strength >= min_strength:
            if (combined_signal == 1 and bearish_core >= 3) or (combined_signal == -1 and bullish_core >= 3):
                return 0  # strong opposition -> neutralize
            return combined_signal

        # 2-of-4 rule on core signals (indicators, fibonacci, patterns, strategies)
        if bullish_core >= 2:
            return 1
        if bearish_core >= 2:
            return -1

        # If no core consensus, let news tilt only when available and confident
        if news_available and news_signal in (1, -1) and combined_signal == 0:
            return news_signal

        # Default neutral when mixed and weak
        return 0
    
    def _validate_signal(self, signal: int, strength: float, persistence: bool) -> int:
        """
        Final signal validation using multiple criteria.
        
        Args:
            signal: Signal to validate
            strength: Signal strength (0-100)
            persistence: Whether signal has persistence
            
        Returns:
            int: Validated signal
        """
        if signal == 0:
            return 0

        # Drastically reduce thresholds for aggressive mode to emulate human trader
        sensitivity = getattr(self, 'sensitivity', 'balanced')
        
        if sensitivity == 'aggressive':
            # Aggressive: Accept ANY non-zero signal with strength >= 8%
            # Human traders act on partial confirmations and don't require all factors
            min_strength = 8
            if strength >= min_strength:
                return signal  # Accept immediately, no persistence requirement
            return 0
        
        # Balanced mode
        if sensitivity == 'balanced':
            min_strength = 25
            if strength >= 50:
                return signal  # Strong signal bypasses persistence
            if strength < min_strength:
                return 0
            if not persistence:
                return 0
            return signal
        
        # Conservative mode
        min_strength = getattr(self, 'min_strength_threshold', 40)
        if strength >= 50:
            return signal
        if strength < min_strength:
            return 0
        if not persistence:
            return 0
        return signal
    
    def _get_signal_consistency(self) -> float:
        """
        Calculate signal consistency score (0-100).
        Measures how consistent signals are over recent history.
        
        Returns:
            float: Consistency score
        """
        if len(self.signal_history) < 2:
            return 50.0
        
        # Count transitions (changes) in signal
        transitions = 0
        for i in range(1, len(self.signal_history)):
            if self.signal_history[i] != self.signal_history[i-1]:
                transitions += 1
        
        # Fewer transitions = more consistency
        consistency = ((len(self.signal_history) - 1 - transitions) / (len(self.signal_history) - 1)) * 100
        return consistency
    
    def _calculate_stability_score(self) -> float:
        """
        Calculate signal stability score (0-100).
        Measures how stable the signal has been.
        
        Returns:
            float: Stability score
        """
        if not self.signal_history:
            return 50.0
        
        # Count how long current signal has held
        current_signal = self.signal_history[-1] if self.signal_history else 0
        hold_periods = 0
        
        for s in reversed(self.signal_history):
            if s == current_signal:
                hold_periods += 1
            else:
                break
        
        # Longer hold = higher stability
        stability = (hold_periods / len(self.signal_history)) * 100
        return stability
    
    def _neutral_adaptive_signal(self, reason: str = "") -> Dict:
        """Return neutral adaptive signal"""
        return {
            'signal': 0,
            'strength': 0,
            'condition': f'Adaptive Analysis Error: {reason}',
            'smoothed': False,
            'persistence_confirmed': False,
            'adaptive_adjustments': {},
            'quality_metrics': {
                'signal_consistency': 0,
                'recent_history': list(self.signal_history),
                'stability_score': 0
            },
            'recommendation': 'HOLD',
            'timestamp': pd.Timestamp.now().isoformat()
        }
    
    def _get_adaptive_condition(self, signal: int, strength: float) -> str:
        """Get human-readable adaptive condition"""
        if signal == 1:
            return f"Bullish (Adaptive, {strength:.1f}% confidence)"
        elif signal == -1:
            return f"Bearish (Adaptive, {strength:.1f}% confidence)"
        else:
            return "Neutral/Insufficient Signals"
    
    def _get_signal_recommendation(self, signal: int, strength: float, persistence: bool) -> str:
        """Get final trading recommendation"""
        if signal == 0:
            return "HOLD"
        elif signal == 1:
            if persistence and strength > 60:
                return "BUY_STRONG"
            else:
                return "BUY"
        elif signal == -1:
            if persistence and strength > 60:
                return "SELL_STRONG"
            else:
                return "SELL"
        else:
            return "HOLD"

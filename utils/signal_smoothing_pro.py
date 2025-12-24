"""
Professional Signal Smoothing and Conflict Resolution Engine.
Reduces false rejections and enables more profitable trades through intelligent weighting.
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class WeightedSignalVoter:
    """Combines technical, pattern, and news signals with professional weighting."""
    
    def __init__(self):
        # Professional trading weights: prioritize technical > patterns > news
        self.WEIGHTS = {
            'technical': 0.55,      # Technical indicators are most reliable
            'patterns': 0.30,       # Chart patterns add confirmation
            'news': 0.15            # News provides context but not primary
        }
    
    def calculate_weighted_signal(self, tech_signal: Dict, patterns: List[Dict], 
                                 news_data: Dict) -> Tuple[str, float, str]:
        """
        Calculate final signal using weighted voting.
        Returns: (signal, confidence, reason)
        """
        signals_weighted = {}
        reasons = []
        
        # Technical signal: -1 (SELL) to +1 (BUY)
        tech_strength = tech_signal.get('strength', 50) / 100.0  # Normalize to 0-1
        if tech_signal.get('signal') == 'SELL':
            tech_strength = -tech_strength
        elif tech_signal.get('signal') != 'BUY':
            tech_strength = 0.0
        signals_weighted['technical'] = tech_strength
        
        # Pattern signals: consensus from valid patterns
        if patterns:
            pattern_signal = 0.0
            for p in patterns:
                if p.get('detected'):
                    conf = p.get('confidence', 0.5)
                    if p.get('type', '').lower() in ['double_bottom', 'bullish', 'long']:
                        pattern_signal += conf
                    else:
                        pattern_signal -= conf
            # Normalize to roughly -1 to +1
            pattern_signal = np.tanh(pattern_signal / max(len(patterns), 1))
            signals_weighted['patterns'] = pattern_signal
            if pattern_signal > 0.3:
                reasons.append(f"Bullish patterns ({len([p for p in patterns if p.get('detected') and 'bull' in p.get('type', '').lower()])})")
            elif pattern_signal < -0.3:
                reasons.append(f"Bearish patterns ({len([p for p in patterns if p.get('detected') and 'bear' in p.get('type', '').lower()])})")
        else:
            signals_weighted['patterns'] = 0.0
        
        # News sentiment: -1 (bearish) to +1 (bullish)
        news_sent = news_data.get('sentiment', 'neutral')
        if news_sent == 'bullish':
            signals_weighted['news'] = 0.5
            reasons.append("Bullish news bias")
        elif news_sent == 'bearish':
            signals_weighted['news'] = -0.5
            reasons.append("Bearish news bias")
        else:
            signals_weighted['news'] = 0.0
        
        # Weighted combination
        total = (
            signals_weighted['technical'] * self.WEIGHTS['technical'] +
            signals_weighted['patterns'] * self.WEIGHTS['patterns'] +
            signals_weighted['news'] * self.WEIGHTS['news']
        )
        
        # Convert to signal string and confidence (slightly lower threshold)
        if total > 0.10:
            signal = 'BUY'
            confidence = abs(total)
        elif total < -0.10:
            signal = 'SELL'
            confidence = abs(total)
        else:
            signal = 'HOLD'
            confidence = 0.0
        
        if signal != 'HOLD':
            reasons.insert(0, f"Weighted vote: {signal} ({confidence:.1%})")
        
        return signal, min(confidence, 1.0), "; ".join(reasons)


class ConflictAwareValidator:
    """Intelligently resolves signal conflicts instead of rejecting."""
    
    @staticmethod
    def resolve_conflicting_patterns(patterns: List[Dict]) -> Tuple[List[Dict], str]:
        """
        When patterns conflict (bullish vs bearish), use strength and context.
        Returns: (filtered_patterns, action)
        """
        if not patterns:
            return [], "no patterns"
        
        bullish_patterns = [p for p in patterns if p.get('detected') and 'bull' in p.get('type', '').lower()]
        bearish_patterns = [p for p in patterns if p.get('detected') and 'bear' in p.get('type', '').lower()]
        
        # No conflict
        if not bullish_patterns or not bearish_patterns:
            return [p for p in patterns if p.get('detected')], "no conflict"
        
        # Get strongest from each side
        bull_strength = sum(p.get('confidence', 0) for p in bullish_patterns) / len(bullish_patterns)
        bear_strength = sum(p.get('confidence', 0) for p in bearish_patterns) / len(bearish_patterns)
        
        # Conflict: pick the stronger side
        if abs(bull_strength - bear_strength) < 0.15:
            # Similar strength → use both (ambiguous market)
            action = f"ambiguous ({bull_strength:.1%} vs {bear_strength:.1%})"
            return [p for p in patterns if p.get('detected')], action
        elif bull_strength > bear_strength:
            action = f"bullish favored ({bull_strength:.1%} > {bear_strength:.1%})"
            return bullish_patterns, action
        else:
            action = f"bearish favored ({bear_strength:.1%} > {bull_strength:.1%})"
            return bearish_patterns, action
    
    @staticmethod
    def relax_confidence_threshold(signal: str, strength: float, context: Dict) -> Tuple[bool, str]:
        """
        Professional traders accept lower confidence in trending markets.
        Returns: (accept, reason)
        """
        if strength >= 0.50:
            return True, "strong signal"
        
        # Relaxed thresholds in favorable conditions
        trend_intensity = context.get('trend_intensity', 0)
        volatility = context.get('volatility', 0.5)
        
        if trend_intensity > 0.6 and strength >= 0.35:
            return True, f"trending market ({trend_intensity:.0%}), relaxed threshold"
        
        if volatility > 1.5 and strength >= 0.40:
            return True, f"high volatility ({volatility:.1f}x), relaxed threshold"
        
        if strength >= 0.45:
            return True, "near threshold, acceptable"
        
        return False, f"insufficient confidence ({strength:.0%})"


class SignalSmoothingFilter:
    """Smooths out noisy signals via temporal filtering and persistence."""
    
    def __init__(self, history_window: int = 5):
        self.history = []
        self.window = history_window
    
    def add_signal(self, signal: str, strength: float):
        """Record signal in history."""
        self.history.append({'signal': signal, 'strength': strength})
        self.history = self.history[-self.window:]
    
    def get_smoothed_signal(self) -> Tuple[str, float]:
        """Get consensus signal from history (persistence filter)."""
        if not self.history:
            return 'HOLD', 0.0
        
        # Count signal occurrences
        buy_count = sum(1 for h in self.history if h['signal'] == 'BUY')
        sell_count = sum(1 for h in self.history if h['signal'] == 'SELL')
        
        # Require 2+ consecutive same signals or 60%+ consensus
        if buy_count >= len(self.history) * 0.6:
            avg_strength = np.mean([h['strength'] for h in self.history if h['signal'] == 'BUY'])
            return 'BUY', avg_strength
        elif sell_count >= len(self.history) * 0.6:
            avg_strength = np.mean([h['strength'] for h in self.history if h['signal'] == 'SELL'])
            return 'SELL', avg_strength
        else:
            return 'HOLD', 0.0
    
    def is_signal_persistent(self) -> bool:
        """Check if current signal has persisted (reduces whipsaws)."""
        if len(self.history) < 2:
            return False
        # Signal is persistent if last 2 signals agree
        return self.history[-1]['signal'] == self.history[-2]['signal']


class EnhancedSignalQuality:
    """
    Professional-grade signal quality check that enables more trades
    while maintaining win rate.
    """
    
    def __init__(self):
        self.voter = WeightedSignalVoter()
        self.conflict_resolver = ConflictAwareValidator()
        self.smoother = SignalSmoothingFilter(history_window=3)
    
    def evaluate_signal(self, 
                       tech_signal: Dict,
                       patterns: List[Dict],
                       news_data: Dict,
                       market_context: Dict) -> Dict:
        """
        Evaluate signal quality using professional standards.
        
        Returns:
        {
            'signal': 'BUY'|'SELL'|'HOLD',
            'strength': float (0-1),
            'confidence': float (0-1),
            'quality': 'high'|'medium'|'low',
            'reasons': str,
            'accept': bool
        }
        """
        
        # Step 1: Resolve pattern conflicts
        valid_patterns, conflict_note = self.conflict_resolver.resolve_conflicting_patterns(patterns)
        
        # Step 2: Weighted voting across all signal types
        signal, raw_strength, voting_reasons = self.voter.calculate_weighted_signal(
            tech_signal, valid_patterns, news_data
        )
        
        # Step 3: Check against relaxed professional thresholds
        accept, threshold_reason = self.conflict_resolver.relax_confidence_threshold(
            signal, raw_strength, market_context
        )
        
        # Step 4: Smooth via history (persistence filter)
        self.smoother.add_signal(signal, raw_strength)
        is_persistent = False
        if signal != 'HOLD':
            is_persistent = self.smoother.is_signal_persistent()
            if not is_persistent and raw_strength < 0.35:
                signal = 'HOLD'
                accept = False
                threshold_reason = "signal not persistent"
        
        # Quality rating
        if raw_strength >= 0.60 and is_persistent:
            quality = 'high'
        elif raw_strength >= 0.45:
            quality = 'medium'
        else:
            quality = 'low'
        
        # Combine reasons
        reasons_list = [voting_reasons, threshold_reason, conflict_note]
        reasons = " | ".join([r for r in reasons_list if r])
        
        return {
            'signal': signal,
            'strength': float(raw_strength),
            'confidence': float(raw_strength) if accept else 0.0,
            'quality': quality,
            'reasons': reasons,
            'accept': accept
        }


# Singleton instance for use across signal_generator.py
_smoother_instance = SignalSmoothingFilter(history_window=3)
_quality_checker = EnhancedSignalQuality()


def evaluate_enhanced_signal(tech_signal: Dict, patterns: List[Dict], 
                            news_data: Dict, market_context: Dict) -> Dict:
    """Entry point for enhanced signal quality evaluation."""
    return _quality_checker.evaluate_signal(tech_signal, patterns, news_data, market_context)


def smooth_signal(signal: str, strength: float) -> Tuple[str, float]:
    """Add signal to history and get smoothed consensus."""
    _smoother_instance.add_signal(signal, strength)
    return _smoother_instance.get_smoothed_signal()

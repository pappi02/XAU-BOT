"""
Pattern quality control system for improved pattern detection reliability.
Tightens thresholds, adds secondary confirmations, and penalizes conflicting patterns.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class PatternQualityController:
    """
    Enhances pattern detection quality by:
    1. Tightening confidence thresholds (avoid overconfident 1.0 scores)
    2. Adding secondary confirmations (volume, RSI divergence, etc.)
    3. Penalizing patterns that conflict with market regime or trend
    """
    
    def __init__(self, min_pattern_confidence: float = 0.65,
                 max_pattern_confidence: float = 0.95,
                 require_volume_confirmation: bool = False):
        """
        Initialize pattern quality controller.
        
        Args:
            min_pattern_confidence: Minimum confidence to accept pattern (default 0.65)
            max_pattern_confidence: Maximum confidence to assign (default 0.95, avoid 1.0)
            require_volume_confirmation: Require volume spike for breakout patterns
        """
        self.min_confidence = min_pattern_confidence
        self.max_confidence = max_pattern_confidence
        self.require_volume_confirmation = require_volume_confirmation
        
        # Pattern type categorization
        self.reversal_patterns = [
            'double_top', 'double_bottom', 'triple_top', 'triple_bottom',
            'head_shoulders', 'inverse_head_shoulders'
        ]
        self.continuation_patterns = [
            'rising_wedge', 'falling_wedge', 'bullish_flag', 'bearish_flag',
            'bullish_channel', 'bearish_channel', 'symmetrical_triangle'
        ]
    
    def validate_pattern_confidence(self, pattern_dict: Dict) -> Dict:
        """
        Adjust pattern confidence to avoid overconfidence.
        
        Args:
            pattern_dict: Pattern detection result with 'confidence' key
        
        Returns:
            Modified pattern_dict with adjusted confidence
        """
        original_confidence = pattern_dict.get('confidence', 0.0)
        
        # Clamp confidence to max threshold (avoid 1.0)
        if original_confidence > self.max_confidence:
            pattern_dict['confidence'] = self.max_confidence
            pattern_dict['confidence_clamped'] = True
            logger.debug(
                f"Pattern confidence clamped: {original_confidence:.2f} → "
                f"{self.max_confidence:.2f}"
            )
        
        # Reject patterns below minimum threshold
        if pattern_dict['confidence'] < self.min_confidence:
            pattern_dict['rejected'] = True
            pattern_dict['rejection_reason'] = f"Confidence {pattern_dict['confidence']:.2f} < {self.min_confidence:.2f}"
            logger.debug(f"Pattern rejected: {pattern_dict['rejection_reason']}")
        
        return pattern_dict
    
    def add_volume_confirmation(self, pattern_dict: Dict, data: pd.DataFrame) -> Dict:
        """
        Add volume confirmation for breakout patterns.
        
        Args:
            pattern_dict: Pattern detection result
            data: OHLC data with 'tick_volume' or 'volume' column
        
        Returns:
            Modified pattern_dict with volume_confirmed flag
        """
        pattern_type = pattern_dict.get('type', '')
        
        # Only check volume for breakout/continuation patterns
        if pattern_type not in self.continuation_patterns:
            pattern_dict['volume_confirmed'] = True  # Not applicable
            return pattern_dict
        
        if 'tick_volume' not in data.columns and 'volume' not in data.columns:
            logger.debug("No volume data available for confirmation")
            pattern_dict['volume_confirmed'] = False
            return pattern_dict
        
        volume_col = 'tick_volume' if 'tick_volume' in data.columns else 'volume'
        
        # Check for volume spike in recent candles
        if len(data) < 20:
            pattern_dict['volume_confirmed'] = False
            return pattern_dict
        
        recent_volume = data[volume_col].iloc[-5:].mean()
        baseline_volume = data[volume_col].iloc[-20:-5].mean()
        
        # Require at least 30% increase in volume
        volume_ratio = recent_volume / baseline_volume if baseline_volume > 0 else 0
        
        pattern_dict['volume_ratio'] = volume_ratio
        pattern_dict['volume_confirmed'] = volume_ratio >= 1.3
        
        if not pattern_dict['volume_confirmed']:
            # Reduce confidence if no volume confirmation
            pattern_dict['confidence'] *= 0.85
            logger.debug(
                f"Pattern volume unconfirmed: ratio={volume_ratio:.2f}, "
                f"confidence reduced to {pattern_dict['confidence']:.2f}"
            )
        
        return pattern_dict
    
    def add_rsi_divergence_confirmation(self, pattern_dict: Dict, data: pd.DataFrame) -> Dict:
        """
        Check for RSI divergence to confirm reversal patterns.
        
        Args:
            pattern_dict: Pattern detection result
            data: OHLC data with 'rsi' column
        
        Returns:
            Modified pattern_dict with rsi_divergence flag
        """
        pattern_type = pattern_dict.get('type', '')
        
        # Only check divergence for reversal patterns
        if pattern_type not in self.reversal_patterns:
            pattern_dict['rsi_divergence'] = None  # Not applicable
            return pattern_dict
        
        if 'rsi' not in data.columns or len(data) < 20:
            pattern_dict['rsi_divergence'] = None
            return pattern_dict
        
        # Get recent price and RSI trends
        recent_prices = data['close'].iloc[-10:]
        recent_rsi = data['rsi'].iloc[-10:]
        
        price_trend = recent_prices.iloc[-1] - recent_prices.iloc[0]
        rsi_trend = recent_rsi.iloc[-1] - recent_rsi.iloc[0]
        
        # Detect divergence
        # Bullish divergence: price down, RSI up (for double bottom)
        # Bearish divergence: price up, RSI down (for double top)
        
        has_divergence = False
        
        if pattern_type in ['double_bottom', 'triple_bottom', 'inverse_head_shoulders']:
            # Expect bullish divergence
            has_divergence = (price_trend < 0 and rsi_trend > 0)
        elif pattern_type in ['double_top', 'triple_top', 'head_shoulders']:
            # Expect bearish divergence
            has_divergence = (price_trend > 0 and rsi_trend < 0)
        
        pattern_dict['rsi_divergence'] = has_divergence
        
        if has_divergence:
            # Boost confidence with divergence confirmation
            pattern_dict['confidence'] = min(pattern_dict['confidence'] * 1.15, self.max_confidence)
            logger.debug(f"RSI divergence confirmed, confidence boosted to {pattern_dict['confidence']:.2f}")
        else:
            # Reduce confidence without divergence
            pattern_dict['confidence'] *= 0.9
            logger.debug(f"No RSI divergence, confidence reduced to {pattern_dict['confidence']:.2f}")
        
        return pattern_dict
    
    def check_pattern_regime_alignment(self, pattern_dict: Dict, market_regime: str,
                                      ema_trend: str) -> Dict:
        """
        Penalize patterns that conflict with detected market regime or trend.
        
        Args:
            pattern_dict: Pattern detection result
            market_regime: Current regime ('trending', 'ranging', 'volatile')
            ema_trend: Current EMA trend ('bullish', 'bearish', 'neutral')
        
        Returns:
            Modified pattern_dict with regime_aligned flag
        """
        pattern_type = pattern_dict.get('type', '')
        pattern_signal = pattern_dict.get('signal', 0)
        
        conflicts = []
        
        # Check regime conflicts
        if market_regime == 'ranging':
            # In ranging market, continuation patterns are less reliable
            if pattern_type in self.continuation_patterns:
                conflicts.append("Continuation pattern in ranging market")
        elif market_regime == 'trending':
            # In trending market, reversal patterns are less reliable
            if pattern_type in self.reversal_patterns:
                conflicts.append("Reversal pattern in strong trending market")
        
        # Check trend conflicts
        if ema_trend == 'bullish' and pattern_signal < 0:
            conflicts.append("Bearish pattern against bullish trend")
        elif ema_trend == 'bearish' and pattern_signal > 0:
            conflicts.append("Bullish pattern against bearish trend")
        
        pattern_dict['regime_conflicts'] = conflicts
        pattern_dict['regime_aligned'] = len(conflicts) == 0
        
        if conflicts:
            # Apply penalty for each conflict
            penalty = 0.85 ** len(conflicts)  # Compound penalty
            pattern_dict['confidence'] *= penalty
            logger.warning(
                f"Pattern-regime conflicts: {', '.join(conflicts)}; "
                f"confidence reduced to {pattern_dict['confidence']:.2f}"
            )
        
        return pattern_dict
    
    def detect_conflicting_patterns(self, patterns: List[Dict]) -> List[Dict]:
        """
        Detect and penalize conflicting patterns in the same detection window.
        
        Args:
            patterns: List of detected patterns
        
        Returns:
            Modified list with conflicting patterns penalized
        """
        if len(patterns) <= 1:
            return patterns
        
        # Group by signal direction
        bullish = [p for p in patterns if p.get('signal', 0) > 0]
        bearish = [p for p in patterns if p.get('signal', 0) < 0]
        
        # If both bullish and bearish patterns detected, it's a conflict
        if bullish and bearish:
            logger.warning(
                f"Conflicting patterns detected: {len(bullish)} bullish, {len(bearish)} bearish"
            )
            
            # Penalize all patterns in this window
            for p in patterns:
                p['confidence'] *= 0.7
                p['conflicting_patterns'] = True
                if 'rejection_reason' not in p:
                    p['rejection_reason'] = "Conflicting patterns in detection window"
        
        return patterns
    
    def apply_quality_controls(self, patterns: List[Dict], data: pd.DataFrame,
                              market_regime: str = 'unknown',
                              ema_trend: str = 'neutral') -> List[Dict]:
        """
        Apply all quality controls to detected patterns.
        
        Args:
            patterns: List of detected patterns
            data: OHLC data for confirmations
            market_regime: Current market regime
            ema_trend: Current EMA trend direction
        
        Returns:
            List of validated and adjusted patterns
        """
        if not patterns:
            return []
        
        validated = []
        
        for pattern in patterns:
            # 1. Validate confidence thresholds
            pattern = self.validate_pattern_confidence(pattern)
            
            # Skip rejected patterns
            if pattern.get('rejected', False):
                continue
            
            # 2. Add volume confirmation
            pattern = self.add_volume_confirmation(pattern, data)
            
            # 3. Add RSI divergence confirmation
            pattern = self.add_rsi_divergence_confirmation(pattern, data)
            
            # 4. Check regime alignment
            pattern = self.check_pattern_regime_alignment(pattern, market_regime, ema_trend)
            
            # Final threshold check after adjustments
            if pattern['confidence'] >= self.min_confidence:
                validated.append(pattern)
            else:
                logger.debug(
                    f"Pattern rejected after adjustments: {pattern['type']} "
                    f"confidence={pattern['confidence']:.2f}"
                )
        
        # 5. Detect conflicting patterns
        validated = self.detect_conflicting_patterns(validated)
        
        # Final filter: remove patterns below threshold after conflict detection
        validated = [p for p in validated if p['confidence'] >= self.min_confidence]
        
        return validated
    
    def get_quality_report(self, original_patterns: List[Dict],
                          validated_patterns: List[Dict]) -> Dict:
        """
        Generate quality control report.
        
        Args:
            original_patterns: Patterns before quality control
            validated_patterns: Patterns after quality control
        
        Returns:
            Dict with quality metrics
        """
        original_count = len(original_patterns)
        validated_count = len(validated_patterns)
        rejected_count = original_count - validated_count
        
        rejection_reasons = {}
        for p in original_patterns:
            if p not in validated_patterns:
                reason = p.get('rejection_reason', 'Unknown')
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        
        return {
            'original_count': original_count,
            'validated_count': validated_count,
            'rejected_count': rejected_count,
            'rejection_rate': rejected_count / original_count if original_count > 0 else 0,
            'rejection_reasons': rejection_reasons,
            'avg_confidence_before': np.mean([p.get('confidence', 0) for p in original_patterns]) if original_patterns else 0,
            'avg_confidence_after': np.mean([p.get('confidence', 0) for p in validated_patterns]) if validated_patterns else 0
        }


def create_pattern_quality_controller(
    min_confidence: float = 0.65,
    max_confidence: float = 0.95,
    require_volume: bool = False
) -> PatternQualityController:
    """
    Factory function to create pattern quality controller with configuration.
    
    Args:
        min_confidence: Minimum pattern confidence to accept (default 0.65)
        max_confidence: Maximum confidence to assign (default 0.95)
        require_volume: Require volume confirmation for breakouts (default False)
    
    Returns:
        PatternQualityController instance
    """
    return PatternQualityController(
        min_pattern_confidence=min_confidence,
        max_pattern_confidence=max_confidence,
        require_volume_confirmation=require_volume
    )

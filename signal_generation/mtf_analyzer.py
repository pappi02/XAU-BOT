"""
Multi-Timeframe Analyzer for Scalping Strategy
Confirms lower timeframe signals (M1, M5) with higher timeframes (M15, M30, H1)
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MTFSignal:
    """Multi-timeframe signal container"""
    direction: int  # 1 = bullish, -1 = bearish, 0 = neutral
    confidence: float  # 0-100
    timeframe_agreement: Dict[str, int]  # Agreement across timeframes
    trend_alignment: bool  # Whether HTF trend aligns
    condition: str


class MultiTimeframeAnalyzer:
    """
    Multi-timeframe confirmation for scalping trades.
    Analyzes higher timeframes to confirm lower timeframe signals.
    """
    
    # Timeframe hierarchy for scalping
    TF_HIERARCHY = {
        'M1': ['M5', 'M15', 'M30'],
        'M3': ['M15', 'M30', 'H1'],
        'M5': ['M15', 'M30', 'H1'],
        'M15': ['M30', 'H1', 'H4'],
        'M30': ['H1', 'H4', 'D1']
    }
    
    def __init__(self, primary_timeframe: str = 'M5'):
        """
        Initialize MTF analyzer.
        
        Args:
            primary_timeframe: The trading timeframe (M1, M5, etc.)
        """
        self.primary_tf = primary_timeframe
        self.confirmation_tfs = self.TF_HIERARCHY.get(primary_timeframe, ['M15', 'M30', 'H1'])
        
    def analyze(self, 
                primary_data: pd.DataFrame,
                htf_data: Optional[Dict[str, pd.DataFrame]] = None) -> Dict:
        """
        Analyze multiple timeframes for trend confirmation.
        
        Args:
            primary_data: OHLC data for primary (trading) timeframe
            htf_data: Dict of higher timeframe data {timeframe: dataframe}
            
        Returns:
            Dict with MTF analysis results
        """
        try:
            if len(primary_data) < 50:
                return self._neutral_signal("Insufficient primary data")
            
            # Analyze primary timeframe
            primary_trend = self._detect_trend(primary_data)
            primary_strength = self._calculate_trend_strength(primary_data)
            
            # If no HTF data provided, analyze only primary TF
            if htf_data is None or len(htf_data) == 0:
                logger.debug("No HTF data provided, using primary timeframe only")
                return {
                    'signal': primary_trend,
                    'confidence': primary_strength,
                    'condition': f'Primary TF ({self.primary_tf}) trend: {self._trend_name(primary_trend)}',
                    'htf_confirmation': False,
                    'timeframe_agreement': {self.primary_tf: primary_trend}
                }
            
            # Analyze higher timeframes
            htf_trends = {}
            htf_strengths = {}
            
            for tf_name in self.confirmation_tfs:
                if tf_name in htf_data and htf_data[tf_name] is not None:
                    tf_data = htf_data[tf_name]
                    if len(tf_data) >= 30:
                        htf_trends[tf_name] = self._detect_trend(tf_data)
                        htf_strengths[tf_name] = self._calculate_trend_strength(tf_data)
            
            # Calculate confirmation
            htf_confirmation = self._check_htf_confirmation(primary_trend, htf_trends)
            combined_confidence = self._calculate_mtf_confidence(
                primary_strength, 
                htf_strengths, 
                htf_confirmation
            )
            
            # Determine final signal
            if htf_confirmation and combined_confidence >= 50:
                final_signal = primary_trend
            elif htf_confirmation and combined_confidence >= 30:
                final_signal = primary_trend  # Weak confirmation
            else:
                final_signal = 0  # No confirmation
            
            all_trends = {self.primary_tf: primary_trend}
            all_trends.update(htf_trends)
            
            return {
                'signal': final_signal,
                'confidence': combined_confidence,
                'condition': self._build_condition_string(primary_trend, htf_trends, htf_confirmation),
                'htf_confirmation': htf_confirmation,
                'timeframe_agreement': all_trends,
                'primary_trend': primary_trend,
                'primary_strength': primary_strength,
                'htf_trends': htf_trends
            }
            
        except Exception as e:
            logger.error(f"MTF analysis error: {e}", exc_info=True)
            return self._neutral_signal(f"Error: {str(e)}")
    
    def _detect_trend(self, data: pd.DataFrame) -> int:
        """
        Detect trend direction using multiple methods.
        
        Returns:
            1 = bullish, -1 = bearish, 0 = neutral/ranging
        """
        if len(data) < 20:
            return 0
        
        close = data['close'].values
        
        # Method 1: EMA crossover (fast vs slow)
        ema_fast = pd.Series(close).ewm(span=8, adjust=False).mean()
        ema_slow = pd.Series(close).ewm(span=21, adjust=False).mean()
        ema_signal = 1 if ema_fast.iloc[-1] > ema_slow.iloc[-1] else -1
        
        # Method 2: Price vs SMA
        sma_50 = pd.Series(close).rolling(window=min(50, len(close))).mean()
        price_vs_sma = 1 if close[-1] > sma_50.iloc[-1] else -1
        
        # Method 3: Higher highs / Lower lows
        recent_high = max(data['high'].tail(10))
        recent_low = min(data['low'].tail(10))
        prev_high = max(data['high'].iloc[-20:-10])
        prev_low = min(data['low'].iloc[-20:-10])
        
        hh_ll_signal = 0
        if recent_high > prev_high and recent_low > prev_low:
            hh_ll_signal = 1  # Uptrend
        elif recent_high < prev_high and recent_low < prev_low:
            hh_ll_signal = -1  # Downtrend
        
        # Combine methods (majority vote)
        votes = [ema_signal, price_vs_sma, hh_ll_signal]
        bullish = sum(1 for v in votes if v == 1)
        bearish = sum(1 for v in votes if v == -1)
        
        if bullish >= 2:
            return 1
        elif bearish >= 2:
            return -1
        else:
            return 0
    
    def _calculate_trend_strength(self, data: pd.DataFrame) -> float:
        """
        Calculate trend strength (0-100).
        
        Returns:
            Strength percentage
        """
        if len(data) < 14:
            return 0.0
        
        close = data['close'].values
        high = data['high'].values
        low = data['low'].values
        
        # ADX-like calculation (simplified)
        tr_values = []
        for i in range(1, len(close)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
            tr_values.append(tr)
        
        atr = np.mean(tr_values[-14:]) if len(tr_values) >= 14 else np.mean(tr_values)
        
        # Price momentum
        momentum = abs((close[-1] - close[-14]) / close[-14]) * 100 if len(close) >= 14 else 0
        
        # Combine ATR and momentum for strength
        strength = min(100, (momentum * 5 + atr / close[-1] * 1000))
        
        return float(strength)
    
    def _check_htf_confirmation(self, primary_trend: int, htf_trends: Dict[str, int]) -> bool:
        """
        Check if higher timeframes confirm the primary trend.
        
        Returns:
            True if at least 2 HTFs agree with primary trend
        """
        if not htf_trends:
            return False
        
        if primary_trend == 0:
            return False
        
        agreement_count = sum(1 for trend in htf_trends.values() if trend == primary_trend)
        
        # Require at least 1 HTF agreement (or 2 if 3+ HTFs available)
        required = 2 if len(htf_trends) >= 3 else 1
        
        return agreement_count >= required
    
    def _calculate_mtf_confidence(self,
                                   primary_strength: float,
                                   htf_strengths: Dict[str, float],
                                   htf_confirmation: bool) -> float:
        """
        Calculate combined confidence from all timeframes.
        
        Returns:
            Confidence score 0-100
        """
        if not htf_confirmation:
            # Without HTF confirmation, reduce confidence
            return min(primary_strength * 0.6, 40.0)
        
        # With HTF confirmation, boost confidence
        base_confidence = primary_strength
        
        if htf_strengths:
            htf_avg_strength = np.mean(list(htf_strengths.values()))
            # Weight: 60% primary + 40% HTF average
            combined = base_confidence * 0.6 + htf_avg_strength * 0.4
        else:
            combined = base_confidence
        
        # Bonus for confirmation
        combined = min(100, combined * 1.2)
        
        return float(combined)
    
    def _build_condition_string(self, 
                                primary_trend: int,
                                htf_trends: Dict[str, int],
                                htf_confirmation: bool) -> str:
        """Build descriptive condition string"""
        primary_name = self._trend_name(primary_trend)
        
        if not htf_trends:
            return f"{self.primary_tf}: {primary_name} (no HTF data)"
        
        if htf_confirmation:
            agreeing_tfs = [tf for tf, trend in htf_trends.items() if trend == primary_trend]
            return f"{self.primary_tf}: {primary_name} ✓ HTF Confirmed ({', '.join(agreeing_tfs)})"
        else:
            return f"{self.primary_tf}: {primary_name} ✗ HTF Conflict"
    
    def _trend_name(self, signal: int) -> str:
        """Convert signal to name"""
        if signal == 1:
            return "Bullish"
        elif signal == -1:
            return "Bearish"
        else:
            return "Neutral"
    
    def _neutral_signal(self, reason: str) -> Dict:
        """Return neutral signal"""
        return {
            'signal': 0,
            'confidence': 0,
            'condition': reason,
            'htf_confirmation': False,
            'timeframe_agreement': {}
        }

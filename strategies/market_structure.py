"""
Market Structure Analyzer - Expert Trader's Edge

Analyzes market structure to identify:
- Trend direction and strength
- Support and resistance levels
- Price action context
- High-probability zones

Expert traders never trade in a vacuum - they trade with context.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from logger_config import setup_logger

logger = setup_logger()


class MarketStructureAnalyzer:
    """
    Analyzes market structure for expert-level trading decisions.
    """
    
    def __init__(self, config=None):
        """Initialize market structure analyzer."""
        self.config = config or {}
        
        # Structure detection parameters
        self.swing_lookback = 20  # Bars to look back for swing points
        self.sr_tolerance = 0.0003  # 30 pips tolerance for S/R zones
        self.trend_strength_threshold = 0.6  # 60% strength to confirm trend
        
        # Cache for performance
        self.cache = {}
        self.cache_max_age = 5  # bars
        
        logger.info("MarketStructureAnalyzer initialized | Expert context analysis enabled")
    
    def analyze_structure(self, df: pd.DataFrame, current_idx: int = -1) -> Dict:
        """
        Analyze complete market structure at current position.
        
        Args:
            df: DataFrame with OHLCV data
            current_idx: Index to analyze (-1 for latest)
            
        Returns:
            dict: Complete market structure analysis
        """
        if len(df) < 50:
            return self._default_structure()
        
        try:
            # Detect trend
            trend_info = self.detect_trend(df, current_idx)
            
            # Find support/resistance
            sr_levels = self.find_support_resistance(df, current_idx)
            
            # Analyze price action
            price_action = self.analyze_price_action(df, current_idx)
            
            # Calculate structure quality score
            structure_quality = self._calculate_structure_quality(
                trend_info, sr_levels, price_action
            )
            
            return {
                'trend': trend_info,
                'support_resistance': sr_levels,
                'price_action': price_action,
                'structure_quality': structure_quality,
                'timestamp': df.index[current_idx] if current_idx != -1 else df.index[-1]
            }
        
        except Exception as e:
            logger.error(f"Error analyzing structure: {e}")
            return self._default_structure()
    
    def detect_trend(self, df: pd.DataFrame, current_idx: int = -1) -> Dict:
        """
        Detect trend direction and strength using multiple methods.
        
        Returns:
            dict: {
                'direction': 'up' | 'down' | 'sideways',
                'strength': 0.0-1.0,
                'ema_aligned': bool,
                'higher_highs': bool,
                'higher_lows': bool
            }
        """
        if current_idx == -1:
            current_idx = len(df) - 1
        
        # Ensure we have enough data
        if current_idx < 50:
            return {'direction': 'sideways', 'strength': 0.0, 'ema_aligned': False,
                    'higher_highs': False, 'higher_lows': False}
        
        # Get recent data
        lookback = 50
        start_idx = max(0, current_idx - lookback)
        recent_df = df.iloc[start_idx:current_idx + 1]
        
        # Method 1: EMA alignment (8, 21, 50)
        ema_8 = recent_df['close'].ewm(span=8, adjust=False).mean().iloc[-1]
        ema_21 = recent_df['close'].ewm(span=21, adjust=False).mean().iloc[-1]
        ema_50 = recent_df['close'].ewm(span=50, adjust=False).mean().iloc[-1] if len(recent_df) >= 50 else ema_21
        
        ema_bullish = (ema_8 > ema_21 > ema_50)
        ema_bearish = (ema_8 < ema_21 < ema_50)
        
        # Method 2: Higher highs / Lower lows
        swing_period = 10
        highs = recent_df['high'].rolling(window=swing_period, center=True).max()
        lows = recent_df['low'].rolling(window=swing_period, center=True).min()
        
        # Count swing points
        recent_highs = highs.dropna().tail(5)
        recent_lows = lows.dropna().tail(5)
        
        higher_highs = (recent_highs.iloc[-1] > recent_highs.iloc[0]) if len(recent_highs) >= 2 else False
        higher_lows = (recent_lows.iloc[-1] > recent_lows.iloc[0]) if len(recent_lows) >= 2 else False
        lower_highs = (recent_highs.iloc[-1] < recent_highs.iloc[0]) if len(recent_highs) >= 2 else False
        lower_lows = (recent_lows.iloc[-1] < recent_lows.iloc[0]) if len(recent_lows) >= 2 else False
        
        # Method 3: Price vs EMA slope
        current_price = recent_df['close'].iloc[-1]
        price_above_ema21 = current_price > ema_21
        ema_slope = (ema_21 - recent_df['close'].ewm(span=21, adjust=False).mean().iloc[-10]) / ema_21
        
        # Combine signals
        bullish_signals = sum([
            ema_bullish,
            higher_highs and higher_lows,
            price_above_ema21,
            ema_slope > 0.0001
        ])
        
        bearish_signals = sum([
            ema_bearish,
            lower_highs and lower_lows,
            not price_above_ema21,
            ema_slope < -0.0001
        ])
        
        # Determine trend
        if bullish_signals >= 3:
            direction = 'up'
            strength = bullish_signals / 4.0
        elif bearish_signals >= 3:
            direction = 'down'
            strength = bearish_signals / 4.0
        else:
            direction = 'sideways'
            strength = 0.3  # Low strength in sideways
        
        return {
            'direction': direction,
            'strength': round(strength, 2),
            'ema_aligned': ema_bullish or ema_bearish,
            'higher_highs': higher_highs,
            'higher_lows': higher_lows,
            'price_vs_ema21': 'above' if price_above_ema21 else 'below'
        }
    
    def find_support_resistance(self, df: pd.DataFrame, current_idx: int = -1) -> Dict:
        """
        Find key support and resistance levels.
        
        Returns:
            dict: {
                'resistances': [prices],
                'supports': [prices],
                'nearest_resistance': price,
                'nearest_support': price,
                'distance_to_resistance_pips': float,
                'distance_to_support_pips': float
            }
        """
        if current_idx == -1:
            current_idx = len(df) - 1
        
        lookback = min(200, current_idx)
        if lookback < 50:
            return {'resistances': [], 'supports': [], 'nearest_resistance': None,
                    'nearest_support': None, 'distance_to_resistance_pips': 999,
                    'distance_to_support_pips': 999}
        
        start_idx = current_idx - lookback
        recent_df = df.iloc[start_idx:current_idx + 1]
        current_price = recent_df['close'].iloc[-1]
        
        # Find swing highs and lows
        swing_period = 10
        resistances = []
        supports = []
        
        for i in range(swing_period, len(recent_df) - swing_period):
            # Resistance (swing high)
            if recent_df['high'].iloc[i] == recent_df['high'].iloc[i-swing_period:i+swing_period+1].max():
                resistances.append(recent_df['high'].iloc[i])
            
            # Support (swing low)
            if recent_df['low'].iloc[i] == recent_df['low'].iloc[i-swing_period:i+swing_period+1].min():
                supports.append(recent_df['low'].iloc[i])
        
        # Cluster nearby levels (within tolerance)
        resistances = self._cluster_levels(resistances, current_price, self.sr_tolerance)
        supports = self._cluster_levels(supports, current_price, self.sr_tolerance)
        
        # Sort and get nearest levels
        resistances = sorted([r for r in resistances if r > current_price])[:3]  # Top 3 above
        supports = sorted([s for s in supports if s < current_price], reverse=True)[:3]  # Top 3 below
        
        nearest_resistance = resistances[0] if resistances else None
        nearest_support = supports[0] if supports else None
        
        # Calculate distances in pips (1 pip = 0.01 for XAUUSD)
        pip_value = 0.1  # Gold pip value
        dist_to_resistance = (nearest_resistance - current_price) / pip_value if nearest_resistance else 999
        dist_to_support = (current_price - nearest_support) / pip_value if nearest_support else 999
        
        return {
            'resistances': resistances,
            'supports': supports,
            'nearest_resistance': nearest_resistance,
            'nearest_support': nearest_support,
            'distance_to_resistance_pips': round(dist_to_resistance, 1),
            'distance_to_support_pips': round(dist_to_support, 1)
        }
    
    def analyze_price_action(self, df: pd.DataFrame, current_idx: int = -1) -> Dict:
        """
        Analyze recent price action patterns.
        
        Returns:
            dict: {
                'last_candle': 'bullish' | 'bearish' | 'doji',
                'momentum': 'strong' | 'weak',
                'volatility': 'high' | 'normal' | 'low',
                'consolidation': bool
            }
        """
        if current_idx == -1:
            current_idx = len(df) - 1
        
        if current_idx < 20:
            return {'last_candle': 'doji', 'momentum': 'weak', 
                    'volatility': 'normal', 'consolidation': False}
        
        # Analyze last candle
        last = df.iloc[current_idx]
        candle_body = abs(last['close'] - last['open'])
        candle_range = last['high'] - last['low']
        
        if candle_body / candle_range < 0.3:
            last_candle = 'doji'
        elif last['close'] > last['open']:
            last_candle = 'bullish'
        else:
            last_candle = 'bearish'
        
        # Analyze momentum (last 10 bars)
        recent = df.iloc[current_idx-9:current_idx+1]
        price_change = (recent['close'].iloc[-1] - recent['close'].iloc[0]) / recent['close'].iloc[0]
        momentum = 'strong' if abs(price_change) > 0.005 else 'weak'  # 0.5% threshold
        
        # Analyze volatility (ATR comparison)
        atr_period = 14
        if current_idx >= atr_period:
            recent_atr = df.iloc[current_idx-atr_period+1:current_idx+1]
            high_low = recent_atr['high'] - recent_atr['low']
            atr = high_low.mean()
            current_range = last['high'] - last['low']
            
            if current_range > atr * 1.5:
                volatility = 'high'
            elif current_range < atr * 0.5:
                volatility = 'low'
            else:
                volatility = 'normal'
        else:
            volatility = 'normal'
        
        # Check for consolidation (narrow range over 20 bars) - RELAXED for scalping
        if current_idx >= 20:
            recent_20 = df.iloc[current_idx-19:current_idx+1]
            price_range = (recent_20['high'].max() - recent_20['low'].min()) / recent_20['close'].mean()
            # RELAXED: Increased threshold from 0.01 to 0.015 (1.5% range)
            consolidation = price_range < 0.015
        else:
            consolidation = False
        
        return {
            'last_candle': last_candle,
            'momentum': momentum,
            'volatility': volatility,
            'consolidation': consolidation
        }
    
    def should_trade_long(self, structure: Dict) -> Tuple[bool, str]:
        """
        Determine if long trade is aligned with market structure.
        RELAXED for scalping: Only block obviously bad setups.
        
        Returns:
            (bool, reason): Whether to trade and why
        """
        trend = structure['trend']
        sr = structure['support_resistance']
        pa = structure['price_action']
        
        # RELAXED Rule 1: Only block STRONG opposing trends
        if trend['direction'] == 'down' and trend['strength'] > 0.75:
            return False, "Very strong downtrend (avoid longs)"
        
        # Allow all other trend situations (weak trends, sideways, up)
        
        # RELAXED Rule 2: Only block if VERY close to resistance
        if sr['distance_to_resistance_pips'] < 1.5:
            return False, f"Too close to resistance ({sr['distance_to_resistance_pips']:.1f} pips)"
        
        # Rule 3: Price action alignment is now OPTIONAL for scalping
        # (Removed strict requirement)
        
        # All checks passed
        return True, f"Allowed: {trend['direction']} trend (str:{trend['strength']:.2f}), {sr['distance_to_resistance_pips']:.1f}p to R"
    
    def should_trade_short(self, structure: Dict) -> Tuple[bool, str]:
        """
        Determine if short trade is aligned with market structure.
        RELAXED for scalping: Only block obviously bad setups.
        
        Returns:
            (bool, reason): Whether to trade and why
        """
        trend = structure['trend']
        sr = structure['support_resistance']
        pa = structure['price_action']
        
        # RELAXED Rule 1: Only block STRONG opposing trends
        if trend['direction'] == 'up' and trend['strength'] > 0.75:
            return False, "Very strong uptrend (avoid shorts)"
        
        # Allow all other trend situations (weak trends, sideways, down)
        
        # RELAXED Rule 2: Only block if VERY close to support
        if sr['distance_to_support_pips'] < 1.5:
            return False, f"Too close to support ({sr['distance_to_support_pips']:.1f} pips)"
        
        # Rule 3: Price action alignment is now OPTIONAL for scalping
        # (Removed strict requirement)
        
        return True, f"Allowed: {trend['direction']} trend (str:{trend['strength']:.2f}), {sr['distance_to_support_pips']:.1f}p to R"
    
    def _cluster_levels(self, levels: List[float], current_price: float, tolerance: float) -> List[float]:
        """Cluster nearby S/R levels together."""
        if not levels:
            return []
        
        clustered = []
        sorted_levels = sorted(levels)
        
        i = 0
        while i < len(sorted_levels):
            cluster = [sorted_levels[i]]
            j = i + 1
            
            # Group nearby levels
            while j < len(sorted_levels):
                if abs(sorted_levels[j] - sorted_levels[i]) / current_price < tolerance:
                    cluster.append(sorted_levels[j])
                    j += 1
                else:
                    break
            
            # Average the cluster
            clustered.append(sum(cluster) / len(cluster))
            i = j
        
        return clustered
    
    def _calculate_structure_quality(self, trend: Dict, sr: Dict, pa: Dict) -> float:
        """
        Calculate overall structure quality score (0-1).
        Higher score = clearer structure = better trading conditions.
        """
        score = 0.0
        
        # Trend quality (40% weight)
        if trend['direction'] in ['up', 'down']:
            score += 0.4 * trend['strength']
        else:
            score += 0.1  # Sideways gets low score
        
        # S/R clarity (30% weight)
        if sr['nearest_resistance'] and sr['nearest_support']:
            # Clear levels exist
            score += 0.3
        elif sr['nearest_resistance'] or sr['nearest_support']:
            score += 0.15
        
        # Price action quality (30% weight)
        if pa['momentum'] == 'strong' and pa['volatility'] in ['normal', 'high']:
            score += 0.3
        elif pa['momentum'] == 'strong' or pa['volatility'] == 'normal':
            score += 0.15
        
        # Penalty for consolidation
        if pa['consolidation']:
            score *= 0.5
        
        return round(min(1.0, score), 2)
    
    def _default_structure(self) -> Dict:
        """Return default structure when analysis fails."""
        return {
            'trend': {
                'direction': 'sideways',
                'strength': 0.0,
                'ema_aligned': False,
                'higher_highs': False,
                'higher_lows': False
            },
            'support_resistance': {
                'resistances': [],
                'supports': [],
                'nearest_resistance': None,
                'nearest_support': None,
                'distance_to_resistance_pips': 999,
                'distance_to_support_pips': 999
            },
            'price_action': {
                'last_candle': 'doji',
                'momentum': 'weak',
                'volatility': 'normal',
                'consolidation': False
            },
            'structure_quality': 0.0,
            'timestamp': None
        }


if __name__ == "__main__":
    print("=" * 80)
    print("MARKET STRUCTURE ANALYZER - EXPERT TRADER'S EDGE")
    print("=" * 80)
    print("\n✅ MarketStructureAnalyzer initialized")
    print("   Features: Trend detection | S/R levels | Price action analysis")
    print("   Purpose: Trade only high-probability setups aligned with structure")

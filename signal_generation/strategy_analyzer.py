"""
Strategy Analyzer - Evaluates trading strategies and regime-based signals
Implements multiple trading strategies and strategy selection logic
"""

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass
from typing import Dict, Optional

# Note: Avoid importing strategies here to prevent circular imports.
# The analyzer implements its own logic and does not require the scalping module.

logger = logging.getLogger(__name__)

@dataclass
class StrategySignal:
    """Container for strategy analysis results"""
    strategy_name: str
    signal: int  # 1 (bullish), -1 (bearish), 0 (neutral)
    confidence: float  # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    details: Dict = None

class StrategyAnalyzer:
    """
    Professional-grade strategy analyzer.
    Evaluates multiple trading strategies and selects appropriate regime.
    """
    
    def __init__(self):
        """Initialize strategy analyzer"""
        self.selected_strategy = 'scalping'
        self.strategy_weights = {
            'scalping': 0.4,
            'swing': 0.3,
            'breakout': 0.3
        }
    
    def analyze(self, data: pd.DataFrame, market_regime: str = 'trending') -> Dict:
        """
        Comprehensive strategy analysis.
        
        Args:
            data (pd.DataFrame): OHLC data
            market_regime (str): Current market regime ('ranging', 'trending', 'volatile')
            
        Returns:
            Dict: Strategy signals and recommendations
        """
        if len(data) < 50:
            return self._no_strategy("Insufficient data")
        
        try:
            strategy_signals = []
            
            # Scalping strategy for short-term intraday
            try:
                scalp_signal = self._analyze_scalping_strategy(data)
                if scalp_signal:
                    strategy_signals.append(scalp_signal)
            except Exception as e:
                logger.debug(f"Scalping strategy error: {e}")
            
            # Swing strategy for medium-term trends
            try:
                swing_signal = self._analyze_swing_strategy(data)
                if swing_signal:
                    strategy_signals.append(swing_signal)
            except Exception as e:
                logger.debug(f"Swing strategy error: {e}")
            
            # Breakout strategy for momentum
            try:
                breakout_signal = self._analyze_breakout_strategy(data)
                if breakout_signal:
                    strategy_signals.append(breakout_signal)
            except Exception as e:
                logger.debug(f"Breakout strategy error: {e}")
            
            # Combine strategy signals
            if strategy_signals:
                return self._combine_strategies(strategy_signals, market_regime)
            else:
                return self._no_strategy("No strategies generated signals")
        
        except Exception as e:
            logger.error(f"Error in strategy analysis: {e}")
            return self._no_strategy(str(e))
    
    def _analyze_scalping_strategy(self, data: pd.DataFrame) -> Optional[StrategySignal]:
        """
        Analyze scalping strategy (short timeframe, quick trades).
        
        Args:
            data (pd.DataFrame): OHLC data
            
        Returns:
            StrategySignal: Scalping strategy signal
        """
        try:
            # Scalping uses very short-term technical indicators
            close = data['close'].values
            
            # Quick EMA crossover (fast period)
            ema_5 = pd.Series(close).ewm(span=5).mean()
            ema_10 = pd.Series(close).ewm(span=10).mean()
            
            signal = 1 if ema_5.iloc[-1] > ema_10.iloc[-1] else -1
            
            # Calculate confidence based on how strong the signal is
            distance = abs(ema_5.iloc[-1] - ema_10.iloc[-1])
            confidence = min(100, distance * 1000)
            
            # Risk/reward for scalping
            atr = data['high'].values[-14:] - data['low'].values[-14:]
            avg_atr = np.mean(atr)
            
            entry = close[-1]
            if signal == 1:
                stop_loss = entry - (avg_atr * 1.0)
                take_profit = entry + (avg_atr * 2.0)
            else:
                stop_loss = entry + (avg_atr * 1.0)
                take_profit = entry - (avg_atr * 2.0)
            
            return StrategySignal(
                strategy_name='Scalping',
                signal=signal,
                confidence=confidence,
                entry_price=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                details={
                    'ema_5': ema_5.iloc[-1],
                    'ema_10': ema_10.iloc[-1],
                    'timeframe': 'M5-M15'
                }
            )
        except Exception as e:
            logger.debug(f"Scalping analysis error: {e}")
            return None
    
    def _analyze_swing_strategy(self, data: pd.DataFrame) -> Optional[StrategySignal]:
        """
        Analyze swing strategy (medium-term trades).
        
        Args:
            data (pd.DataFrame): OHLC data
            
        Returns:
            StrategySignal: Swing strategy signal
        """
        try:
            # Swing trading uses medium-term indicators
            close = data['close'].values
            
            # Medium-term EMA crossover
            ema_20 = pd.Series(close).ewm(span=20).mean()
            ema_50 = pd.Series(close).ewm(span=50).mean()
            
            signal = 1 if ema_20.iloc[-1] > ema_50.iloc[-1] else -1
            
            # Confidence based on alignment
            distance = abs(ema_20.iloc[-1] - ema_50.iloc[-1])
            confidence = min(100, distance * 500)
            
            # Risk/reward for swing trading
            atr = data['high'].values[-20:] - data['low'].values[-20:]
            avg_atr = np.mean(atr)
            
            entry = close[-1]
            if signal == 1:
                stop_loss = entry - (avg_atr * 1.5)
                take_profit = entry + (avg_atr * 3.0)
            else:
                stop_loss = entry + (avg_atr * 1.5)
                take_profit = entry - (avg_atr * 3.0)
            
            return StrategySignal(
                strategy_name='Swing Trading',
                signal=signal,
                confidence=confidence,
                entry_price=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                details={
                    'ema_20': ema_20.iloc[-1],
                    'ema_50': ema_50.iloc[-1],
                    'timeframe': 'H1-H4'
                }
            )
        except Exception as e:
            logger.debug(f"Swing strategy error: {e}")
            return None
    
    def _analyze_breakout_strategy(self, data: pd.DataFrame) -> Optional[StrategySignal]:
        """
        Analyze breakout strategy (momentum trades).
        
        Args:
            data (pd.DataFrame): OHLC data
            
        Returns:
            StrategySignal: Breakout strategy signal
        """
        try:
            # Breakout strategy looks for price breaking key levels
            close = data['close'].values
            high = data['high'].values
            low = data['low'].values
            
            # Calculate 20-period highs and lows for breakout levels
            lookback = 20
            resistance = np.max(high[-lookback:])
            support = np.min(low[-lookback:])
            current_price = close[-1]
            
            # Check for breakout
            breakout_threshold = (resistance - support) * 0.02  # 2% threshold
            
            if current_price > resistance - breakout_threshold:
                signal = 1
                confidence = 70
                entry = current_price
                stop_loss = support
                take_profit = current_price + (resistance - support) * 1.5
            elif current_price < support + breakout_threshold:
                signal = -1
                confidence = 70
                entry = current_price
                stop_loss = resistance
                take_profit = current_price - (resistance - support) * 1.5
            else:
                return None  # No breakout signal
            
            return StrategySignal(
                strategy_name='Breakout',
                signal=signal,
                confidence=confidence,
                entry_price=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                details={
                    'resistance': resistance,
                    'support': support,
                    'breakout_range': resistance - support
                }
            )
        except Exception as e:
            logger.debug(f"Breakout strategy error: {e}")
            return None
    
    def _combine_strategies(self, signals: list, market_regime: str) -> Dict:
        """
        Combine strategy signals with regime weighting.
        
        Args:
            signals: List of strategy signals
            market_regime: Current market regime
            
        Returns:
            Dict: Combined strategy analysis
        """
        # Adjust weights based on market regime
        if market_regime == 'ranging':
            weights = {'Scalping': 0.5, 'Swing Trading': 0.3, 'Breakout': 0.2}
        elif market_regime == 'volatile':
            weights = {'Scalping': 0.3, 'Swing Trading': 0.2, 'Breakout': 0.5}
        else:  # trending
            weights = {'Swing Trading': 0.5, 'Scalping': 0.3, 'Breakout': 0.2}
        
        # Calculate weighted signal
        total_weight = 0
        weighted_signal = 0
        weighted_confidence = 0
        
        for sig in signals:
            weight = weights.get(sig.strategy_name, 0.33)
            weighted_signal += sig.signal * weight
            weighted_confidence += sig.confidence * weight
            total_weight += weight
        
        # Normalize
        if total_weight > 0:
            final_signal = 1 if weighted_signal / total_weight > 0.1 else (-1 if weighted_signal / total_weight < -0.1 else 0)
            final_confidence = weighted_confidence / total_weight
        else:
            final_signal = 0
            final_confidence = 0
        
        return {
            'signal': final_signal,
            'confidence': final_confidence,
            'condition': self._get_strategy_condition(final_signal, final_confidence),
            'market_regime': market_regime,
            'selected_strategies': [
                {
                    'name': s.strategy_name,
                    'signal': s.signal,
                    'confidence': s.confidence,
                    'entry': s.entry_price,
                    'stop_loss': s.stop_loss,
                    'take_profit': s.take_profit
                }
                for s in signals
            ],
            'recommendation': self._get_strategy_recommendation(final_signal)
        }
    
    def _no_strategy(self, reason: str = "") -> Dict:
        """Return no strategy signal"""
        return {
            'signal': 0,
            'confidence': 0,
            'condition': f'No Strategy: {reason}',
            'market_regime': 'unknown',
            'selected_strategies': [],
            'recommendation': 'HOLD'
        }
    
    def _get_strategy_condition(self, signal: int, confidence: float) -> str:
        """Get human-readable strategy condition"""
        if signal == 1:
            return f"Bullish Setup ({confidence:.1f}% confidence)"
        elif signal == -1:
            return f"Bearish Setup ({confidence:.1f}% confidence)"
        else:
            return "Mixed/Unclear Setup"
    
    def _get_strategy_recommendation(self, signal: int) -> str:
        """Get trading recommendation"""
        if signal == 1:
            return "BUY"
        elif signal == -1:
            return "SELL"
        else:
            return "HOLD"

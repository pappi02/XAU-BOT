"""
Signal Master - Master signal generator that coordinates all analysis components
Integrates indicators, patterns, news, strategies, MTF confirmation, and adaptive processing
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, Optional
from datetime import datetime

from signal_generation.indicator_analyzer import TechnicalIndicatorAnalyzer
from signal_generation.pattern_detector import PatternDetector
from signal_generation.news_sentiment_analyzer import NewsSentimentAnalyzer
from signal_generation.strategy_analyzer import StrategyAnalyzer
from signal_generation.fibonacci_analyzer import FibonacciAnalyzer
from signal_generation.mtf_analyzer import MultiTimeframeAnalyzer
from signal_generation.adaptive_signal_analyzer import AdaptiveSignalAnalyzer
from signal_generation.scalping_setups import ScalpingSetupsAnalyzer

logger = logging.getLogger(__name__)

class SignalMaster:
    """
    Master signal generator - Professional-grade SCALPING signal generation system.
    
    Coordinates analysis from:
    - Technical Indicators (EMA, RSI, Bollinger, ATR, ADX, MACD, Stochastic) - SCALPING optimized
    - Chart Patterns (reversals, continuations, channels)
    - Multi-Timeframe Confirmation (HTF trend alignment for scalping)
    - News & Sentiment (fundamental analysis)
    - Trading Strategies (scalping, swing, breakout)
    - Fibonacci retracements + SMA trend filter
    - Adaptive Processing (smoothing, persistence, conflict resolution)
    """
    
    # Weights for component analysis (SCALPING optimized)
    COMPONENT_WEIGHTS = {
        'indicators': 0.20,        # Technical indicators
        'patterns': 0.08,          # Chart patterns
        'fibonacci': 0.17,         # Fibonacci + SMA trend
        'mtf': 0.17,               # Multi-timeframe confirmation
        'news': 0.03,              # Fundamental sentiment
        'strategies': 0.08,        # Strategy-based analysis
        'scalping_setups': 0.27    # Professional scalping setups (NEW - highest weight for scalping)
    }
    
    def __init__(self, sensitivity: str = 'balanced', primary_timeframe: str = 'M5', mtf_enabled: bool = True):
        """Initialize the signal master with all analyzers"""
        self.sensitivity = (sensitivity or 'balanced').lower()
        self.primary_timeframe = primary_timeframe
        self.mtf_enabled = mtf_enabled
        
        self.indicator_analyzer = TechnicalIndicatorAnalyzer()
        self.pattern_detector = PatternDetector()
        self.fibonacci_analyzer = FibonacciAnalyzer(fib_lookback=50, sma_trend_length=200)
        self.news_analyzer = NewsSentimentAnalyzer()
        self.strategy_analyzer = StrategyAnalyzer()
        self.mtf_analyzer = MultiTimeframeAnalyzer(primary_timeframe=primary_timeframe) if mtf_enabled else None
        self.scalping_setups_analyzer = ScalpingSetupsAnalyzer()  # NEW: Professional scalping setups
        # Pass sensitivity preset into adaptive analyzer
        self.adaptive_analyzer = AdaptiveSignalAnalyzer(lookback_periods=10, min_persistence=2, sensitivity=self.sensitivity)
        
        logger.info(f"Signal Master initialized for SCALPING ({primary_timeframe}) with MTF={'ON' if mtf_enabled else 'OFF'} | Scalping Setups=ON")
    
    def generate_signal(self, 
                       data: pd.DataFrame, 
                       market_regime: str = 'trending',
                       htf_data: Optional[Dict[str, pd.DataFrame]] = None) -> Dict:
        """
        Generate comprehensive SCALPING signal by analyzing all factors + MTF confirmation.
        
        Args:
            data (pd.DataFrame): OHLC data for primary timeframe (M1/M5)
            market_regime (str): Current market regime ('ranging', 'trending', 'volatile')
            htf_data (Dict): Optional higher timeframe data {timeframe: dataframe} for MTF confirmation
            
        Returns:
            Dict: Complete signal analysis with recommendation
        """
        if len(data) < 50:
            return self._insufficient_data()
        
        try:
            # Get current market conditions
            market_conditions = self._assess_market_conditions(data)
            
            # 1. Technical Indicator Analysis
            logger.info("Analyzing technical indicators...")
            indicator_result = self.indicator_analyzer.analyze(data)
            indicator_signal = indicator_result.get('signal', 0)
            indicator_strength = indicator_result.get('strength', 0)
            
            # 2. Pattern Detection
            logger.info("Detecting chart patterns...")
            pattern_result = self.pattern_detector.analyze(data)
            pattern_signal = pattern_result.get('signal', 0)
            pattern_confidence = pattern_result.get('confidence', 0)
            
            # 2b. Fibonacci Analysis (Trend + Level Crossovers)
            logger.info("Analyzing Fibonacci levels...")
            fib_result = self.fibonacci_analyzer.analyze(data)
            fib_signal = fib_result.get('signal', 0)
            fib_confidence = fib_result.get('confidence', 0)
            
            # 2c. Multi-Timeframe Confirmation (SCALPING KEY)
            mtf_signal = 0
            mtf_confidence = 0
            if self.mtf_enabled and self.mtf_analyzer:
                logger.info("Analyzing multi-timeframe confirmation...")
                mtf_result = self.mtf_analyzer.analyze(data, htf_data)
                mtf_signal = mtf_result.get('signal', 0)
                mtf_confidence = mtf_result.get('confidence', 0)
                logger.info(f"MTF: {mtf_result.get('condition', 'N/A')}")
            
            # 2d. Professional Scalping Setups (NEW - EMA+VWAP, MACD+RSI, Supertrend+ATR)
            logger.info("Analyzing professional scalping setups...")
            scalping_result = self.scalping_setups_analyzer.analyze_all(data)
            scalping_signal = scalping_result.get('signal', 0)
            scalping_confidence = scalping_result.get('confidence', 0)
            scalping_setup = scalping_result.get('best_setup', 'None')
            logger.info(f"Scalping: {scalping_result.get('condition', 'N/A')} | Setup: {scalping_setup}")
            
            # 3. News & Sentiment Analysis
            logger.info("Analyzing news sentiment...")
            news_result = self.news_analyzer.analyze()
            news_signal = news_result.get('signal', 0)
            news_confidence = news_result.get('confidence', 0)
            
            # 4. Strategy Selection
            logger.info("Evaluating strategies...")
            strategy_result = self.strategy_analyzer.analyze(data, market_regime)
            strategy_signal = strategy_result.get('signal', 0)
            strategy_confidence = strategy_result.get('confidence', 0)
            
            # 5. Combine all signals using weighted voting (INCLUDING SCALPING SETUPS)
            logger.info("Combining signals...")
            combined_signal, combined_strength = self._combine_all_signals(
                indicator_signal, indicator_strength,
                pattern_signal, pattern_confidence,
                fib_signal, fib_confidence,
                mtf_signal, mtf_confidence,
                news_signal, news_confidence,
                strategy_signal, strategy_confidence,
                scalping_signal, scalping_confidence  # NEW: Add scalping setups signal
            )
            
            # 6. Apply adaptive processing
            logger.info("Applying adaptive analysis...")
            adaptive_result = self.adaptive_analyzer.analyze(
                original_signal=combined_signal,
                signal_strength=combined_strength,
                data=data,
                market_conditions=market_conditions,
                indicator_signal=indicator_signal,
                pattern_signal=pattern_signal,
                strategy_signal=strategy_signal,
                news_signal=news_signal,
                news_confidence=news_confidence,
                fib_signal=fib_signal,
                fib_confidence=fib_confidence,
                mtf_signal=mtf_signal,
                mtf_confidence=mtf_confidence
            )
            
            final_signal = adaptive_result['signal']
            final_strength = adaptive_result['strength']
            
            # Compile comprehensive report
            return {
                'signal': final_signal,
                'strength': final_strength,
                'recommendation': self._get_recommendation(final_signal, final_strength, adaptive_result),
                'timestamp': datetime.now().isoformat(),
                
                # Component analysis breakdown
                'components': {
                    'indicators': {
                        'signal': indicator_signal,
                        'strength': indicator_strength,
                        'condition': indicator_result.get('condition', ''),
                        'volatility': indicator_result.get('volatility_level', 'UNKNOWN'),
                        'trend': indicator_result.get('trend_strength', 'UNKNOWN')
                    },
                    'fibonacci': {
                        'signal': fib_signal,
                        'confidence': fib_confidence,
                        'condition': fib_result.get('condition', ''),
                        'trend': fib_result.get('trend', 'Unknown'),
                        'detected_patterns': fib_result.get('detected_patterns', [])
                    },
                    'patterns': {
                        'signal': pattern_signal,
                        'confidence': pattern_confidence,
                        'condition': pattern_result.get('condition', ''),
                        'detected_patterns': pattern_result.get('detected_patterns', [])
                    },
                    'news': {
                        'signal': news_signal,
                        'confidence': news_confidence,
                        'condition': news_result.get('condition', ''),
                        'impact': news_result.get('impact_assessment', 'NONE')
                    },
                    'strategy': {
                        'signal': strategy_signal,
                        'confidence': strategy_confidence,
                        'condition': strategy_result.get('condition', ''),
                        'regime': strategy_result.get('market_regime', 'unknown')
                    },
                    'scalping_setups': {  # NEW: Professional scalping setups
                        'signal': scalping_signal,
                        'confidence': scalping_confidence,
                        'condition': scalping_result.get('condition', ''),
                        'best_setup': scalping_setup,
                        'entry_zone': scalping_result.get('entry_zone', 0),
                        'stop_loss': scalping_result.get('stop_loss', 0),
                        'take_profit': scalping_result.get('take_profit', 0),
                        'individual_setups': {
                            'ema_vwap': scalping_result.get('individual_setups', {}).get('ema_vwap', {}),
                            'macd_rsi': scalping_result.get('individual_setups', {}).get('macd_rsi', {}),
                            'supertrend': scalping_result.get('individual_setups', {}).get('supertrend', {})
                        }
                    }
                },
                
                # Adaptive processing details
                'adaptive': {
                    'smoothed': adaptive_result.get('smoothed', False),
                    'persistence_confirmed': adaptive_result.get('persistence_confirmed', False),
                    'quality_metrics': adaptive_result.get('quality_metrics', {}),
                    'adjustments': adaptive_result.get('adaptive_adjustments', {})
                },
                
                # Market context
                'market_conditions': market_conditions,
                
                # Risk and position sizing guidance
                'risk_management': self._calculate_risk_parameters(data, final_signal, final_strength),
                
                # Summary
                'summary': self._generate_summary(final_signal, final_strength, market_conditions)
            }
        
        except Exception as e:
            logger.error(f"Error in signal generation: {e}", exc_info=True)
            return self._error_signal(str(e))
    
    def _combine_all_signals(self,
                           ind_signal: int, ind_strength: float,
                           pat_signal: int, pat_conf: float,
                           fib_signal: int, fib_conf: float,
                           mtf_signal: int, mtf_conf: float,
                           news_signal: int, news_conf: float,
                           strat_signal: int, strat_conf: float,
                           scalp_signal: int = 0, scalp_conf: float = 0.0) -> Tuple[int, float]:  # NEW: scalping params
        """
        Combine all component signals with weighted voting (SCALPING + MTF + PROFESSIONAL SCALPING SETUPS).
        
        Returns:
            Tuple: (combined_signal, combined_strength)
        """
        # Dynamically adjust weights: ignore components with no confidence/strength
        weights = dict(self.COMPONENT_WEIGHTS)
        if news_conf <= 0:
            weights['news'] = 0.0
        if pat_conf <= 0:
            weights['patterns'] = 0.0
        if fib_conf <= 0:
            weights['fibonacci'] = 0.0
        if mtf_conf <= 0:
            weights['mtf'] = 0.0
        if strat_conf <= 0:
            weights['strategies'] = 0.0
        if ind_strength <= 0:
            weights['indicators'] = 0.0
        if scalp_conf <= 0:  # NEW: Ignore scalping if no confidence
            weights['scalping_setups'] = 0.0
        total_weight = sum(weights.values()) or 1.0

        # Create weighted sum with dynamic weights (INCLUDE SCALPING SETUPS)
        weighted_signal = (
            ind_signal * weights['indicators'] * (ind_strength / 100) +
            pat_signal * weights['patterns'] * (pat_conf / 100) +
            fib_signal * weights['fibonacci'] * (fib_conf / 100) +
            mtf_signal * weights['mtf'] * (mtf_conf / 100) +
            news_signal * weights['news'] * (news_conf / 100) +
            strat_signal * weights['strategies'] * (strat_conf / 100) +
            scalp_signal * weights['scalping_setups'] * (scalp_conf / 100)  # NEW: scalping setups
        )

        weighted_strength = (
            ind_strength * weights['indicators'] +
            pat_conf * weights['patterns'] +
            fib_conf * weights['fibonacci'] +
            mtf_conf * weights['mtf'] +
            news_conf * weights['news'] +
            strat_conf * weights['strategies'] +
            scalp_conf * weights['scalping_setups']  # NEW: Add scalping confidence
        ) / total_weight

        # Determine final signal from weighted score (sensitivity-aware threshold)
        signal_value = weighted_signal / total_weight
        sens = getattr(self, 'sensitivity', 'balanced')
        thr_map = {'conservative': 0.12, 'balanced': 0.10, 'aggressive': 0.07}
        decision_thr = thr_map.get(sens, 0.10)

        if signal_value > decision_thr:
            final_signal = 1
        elif signal_value < -decision_thr:
            final_signal = -1
        else:
            final_signal = 0

        # Fallback: if neutral but at least two of (indicators, patterns, strategies) align with ANY confidence
        # Also boost strength when multiple factors agree (human trader behavior)
        if final_signal == 0:
            votes = []
            confs = []
            # Accept ANY non-zero signal from indicators/patterns/strategies (lowered threshold massively)
            for sig, conf in ((ind_signal, ind_strength), (pat_signal, pat_conf), (strat_signal, strat_conf)):
                if sig != 0 and conf > 0:  # Just require non-zero signal and some confidence
                    votes.append(sig)
                    confs.append(conf)
            bull = sum(1 for v in votes if v == 1)
            bear = sum(1 for v in votes if v == -1)
            if bull >= 2:
                final_signal = 1
                # boost strength from agreeing sources
                weighted_strength = max(weighted_strength, float(np.mean([c for v,c in zip(votes, confs) if v == 1])) if confs else weighted_strength)
            elif bear >= 2:
                final_signal = -1
                weighted_strength = max(weighted_strength, float(np.mean([c for v,c in zip(votes, confs) if v == -1])) if confs else weighted_strength)
            else:
                # AGGRESSIVE MODE FALLBACK: Accept single strong factor (Fibonacci, indicators, strategies, patterns)
                # if in aggressive sensitivity
                if sens == 'aggressive':
                    # Fibonacci has priority (Cabbage FX strategy)
                    if fib_signal != 0 and fib_conf >= 60:
                        final_signal = fib_signal
                        weighted_strength = max(weighted_strength, fib_conf)
                    # Then check strategies (high quality)
                    elif strat_signal != 0 and strat_conf >= 50:
                        final_signal = strat_signal
                        weighted_strength = max(weighted_strength, strat_conf)
                    # Then indicators
                    elif ind_signal != 0 and ind_strength >= 40:
                        final_signal = ind_signal
                        weighted_strength = max(weighted_strength, ind_strength)
                    # Patterns as fallback
                    elif pat_signal != 0 and pat_conf >= 35:
                        final_signal = pat_signal
                        weighted_strength = max(weighted_strength, pat_conf)
        else:
            # Boost strength when multiple factors agree with the final signal (human trader effect)
            agreeing_factors = 0
            agreeing_strengths = []
            
            if (final_signal == 1 and ind_signal == 1 and ind_strength > 0) or \
               (final_signal == -1 and ind_signal == -1 and ind_strength > 0):
                agreeing_factors += 1
                agreeing_strengths.append(ind_strength)
            
            if (final_signal == 1 and pat_signal == 1 and pat_conf > 0) or \
               (final_signal == -1 and pat_signal == -1 and pat_conf > 0):
                agreeing_factors += 1
                agreeing_strengths.append(pat_conf)
            
            if (final_signal == 1 and fib_signal == 1 and fib_conf > 0) or \
               (final_signal == -1 and fib_signal == -1 and fib_conf > 0):
                agreeing_factors += 1
                agreeing_strengths.append(fib_conf)
            
            if (final_signal == 1 and strat_signal == 1 and strat_conf > 0) or \
               (final_signal == -1 and strat_signal == -1 and strat_conf > 0):
                agreeing_factors += 1
                agreeing_strengths.append(strat_conf)
            
            # Boost by 5-20 points when 2+ factors align
            if agreeing_factors >= 2:
                boost = min(20.0, 5.0 * (agreeing_factors - 1))
                weighted_strength = min(100.0, weighted_strength + boost)

        return final_signal, float(weighted_strength)
    
    def _assess_market_conditions(self, data: pd.DataFrame) -> Dict:
        """Assess current market conditions for context"""
        try:
            from indicators import calculate_atr, calculate_adx
            
            atr = calculate_atr(data)
            adx, _, _ = calculate_adx(data)
            
            atr_val = atr.iloc[-1]
            adx_val = adx.iloc[-1]
            atr_ma = atr.rolling(20).mean().iloc[-1]
            
            return {
                'volatility': 'HIGH' if atr_val > atr_ma * 1.2 else ('LOW' if atr_val < atr_ma * 0.8 else 'NORMAL'),
                'trend': 'STRONG' if adx_val > 25 else ('WEAK' if adx_val < 20 else 'MODERATE'),
                'atr': atr_val,
                'adx': adx_val
            }
        except Exception as e:
            logger.debug(f"Market condition assessment error: {e}")
            return {'volatility': 'UNKNOWN', 'trend': 'UNKNOWN'}
    
    def _calculate_risk_parameters(self, data: pd.DataFrame, signal: int, strength: float) -> Dict:
        """Calculate risk management parameters"""
        try:
            from indicators import calculate_atr
            
            atr = calculate_atr(data)
            atr_val = atr.iloc[-1]
            price = data['close'].iloc[-1]
            
            if signal != 0:
                sl_distance = atr_val * 1.5
                tp_distance = atr_val * (3.0 if strength > 70 else 2.0)
                
                if signal == 1:
                    sl_price = price - sl_distance
                    tp_price = price + tp_distance
                else:
                    sl_price = price + sl_distance
                    tp_price = price - tp_distance
                
                return {
                    'entry_price': price,
                    'stop_loss': sl_price,
                    'take_profit': tp_price,
                    'risk_reward_ratio': tp_distance / sl_distance if sl_distance > 0 else 0,
                    'position_type': 'LONG' if signal == 1 else 'SHORT'
                }
            else:
                return {
                    'entry_price': price,
                    'stop_loss': None,
                    'take_profit': None,
                    'risk_reward_ratio': 0,
                    'position_type': 'NONE'
                }
        except Exception as e:
            logger.debug(f"Risk parameter calculation error: {e}")
            return {}
    
    def _get_recommendation(self, signal: int, strength: float, adaptive_result: Dict) -> str:
        """Get final trading recommendation"""
        if signal == 0:
            return "HOLD"
        
        persistence = adaptive_result.get('persistence_confirmed', False)
        
        if signal == 1:
            if persistence and strength > 70:
                return "STRONG_BUY"
            elif strength > 60:
                return "BUY"
            else:
                return "WEAK_BUY"
        elif signal == -1:
            if persistence and strength > 70:
                return "STRONG_SELL"
            elif strength > 60:
                return "SELL"
            else:
                return "WEAK_SELL"
        else:
            return "HOLD"
    
    def _generate_summary(self, signal: int, strength: float, market_conditions: Dict) -> str:
        """Generate human-readable signal summary"""
        signal_desc = {
            1: "Bullish",
            -1: "Bearish",
            0: "Neutral"
        }
        
        strength_desc = "Strong" if strength > 70 else ("Moderate" if strength > 50 else "Weak")
        
        return f"{strength_desc} {signal_desc.get(signal, 'Unknown')} signal in {market_conditions.get('trend', 'unknown')} trend"
    
    def _insufficient_data(self) -> Dict:
        """Return error when data is insufficient"""
        return {
            'signal': 0,
            'strength': 0,
            'recommendation': 'HOLD',
            'error': 'Insufficient data (minimum 50 candles required)',
            'timestamp': datetime.now().isoformat()
        }
    
    def _error_signal(self, error: str) -> Dict:
        """Return error signal"""
        logger.error(f"Signal generation error: {error}")
        return {
            'signal': 0,
            'strength': 0,
            'recommendation': 'HOLD',
            'error': error,
            'timestamp': datetime.now().isoformat()
        }

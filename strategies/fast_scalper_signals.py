"""
Fast Technical Indicator Scalping Signal Generator

Optimized for M1/M3 high-frequency scalping with heavy reliance on technical indicators:
- RSI (7-period for fast scalping)
- EMA (3, 8, 21 for micro trends)
- MACD (8, 17, 9 for scalping)
- Stochastic (5, 3, 3 for fast momentum)
- Bollinger Bands (10, 1.5 for tight ranges)

Generates signals in < 200ms for rapid execution.
"""

import pandas as pd
import numpy as np
import time
from datetime import datetime
from typing import Dict, Optional
from logger_config import setup_logger

# Import indicators
from indicators import (
    calculate_rsi,
    calculate_ema,
    calculate_macd,
    calculate_stochastic,
    calculate_bollinger_bands,
    calculate_atr
)

# Import market structure analyzer
from strategies.market_structure import MarketStructureAnalyzer

logger = setup_logger()


class FastScalperSignals:
    """
    Ultra-fast technical indicator-based signal generator for M1/M3 scalping.
    
    Design Philosophy:
    - Speed > Accuracy (sub-200ms signal generation)
    - Technical indicators > Patterns (scalping relies on math, not patterns)
    - Simple > Complex (fewer calculations = faster signals)
    - Aggressive > Conservative (more signals, smaller profits)
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize fast scalper signal generator.
        
        Args:
            config: Configuration with scalping parameters
        """
        self.config = config or {}
        
        # Fast indicator periods for M1/M3 scalping
        self.rsi_period = 7  # Fast RSI for scalping
        self.ema_ultra_fast = 3  # Ultra-fast EMA
        self.ema_fast = 8  # Fast EMA
        self.ema_slow = 21  # Slow EMA for trend
        self.macd_fast = 8  # Fast MACD
        self.macd_slow = 17
        self.macd_signal = 9
        self.stoch_k = 5  # Fast stochastic
        self.stoch_d = 3
        self.bb_period = 10  # Tight Bollinger Bands
        self.bb_std = 1.5
        
        # Scalping thresholds (BALANCED: Quality with reasonable frequency)
        self.rsi_oversold = 35  # Balanced (not too extreme)
        self.rsi_overbought = 65
        self.rsi_momentum_bull = 53  # Moderate momentum
        self.rsi_momentum_bear = 47  # Moderate momentum
        self.stoch_oversold = 25  # Balanced
        self.stoch_overbought = 75
        
        # Confluence requirements (BALANCED: Quality with volume)
        self.min_confluences = 2  # Minimum 2 (was 3, too strict)
        self.strong_signal_confluences = 3  # 3+ = high confidence
        self.expert_signal_confluences = 4  # 4+ = expert quality
        
        # Market structure analyzer for trend alignment
        self.market_structure = MarketStructureAnalyzer(config)
        # Allow disabling strict consolidation filter during backtests
        self.disable_consolidation_filter = bool(
            (self.config.get('disable_consolidation_filter') is True) or
            (self.config.get('backtest_mode') is True)
        )
        # Quality mode: 'balanced' (default) or 'strict' (target 65–75% WR)
        self.quality_mode = self.config.get('quality_mode', 'balanced')
        # Strict TP multiplier can be customized; default to 1.0 ATR for better R:R than 0.8
        self.tp_atr_multiplier_strict = self.config.get('strict_tp_atr_multiplier', 1.0)
        if self.quality_mode == 'strict':
            # Tighten for quality but stay tradeable (loosened to recover volume and profit)
            self.min_confluences = max(self.config.get('strict_min_confluences', 2), self.min_confluences)
            self.required_confidence = self.config.get('strict_min_confidence', 60)
            self.min_trend_strength_strict = self.config.get('strict_min_trend_strength', 0.55)
            self.sr_proximity_pips_strict = self.config.get('strict_sr_proximity_pips', 2.0)
        else:
            self.required_confidence = self.config.get('min_confidence', 55)
        
        logger.info("FastScalperSignals initialized for M1/M3 timeframes")
        logger.info(f"  Indicators: RSI({self.rsi_period}), EMA({self.ema_ultra_fast}/{self.ema_fast}/{self.ema_slow}), "
                   f"MACD({self.macd_fast}/{self.macd_slow}/{self.macd_signal})")
    
    def generate_signal(self, data: pd.DataFrame, timeframe: str = 'M1') -> Dict:
        """
        Generate scalping signal based on technical indicators.
        
        Args:
            data: OHLCV DataFrame (minimum 50 candles)
            timeframe: 'M1', 'M3', or 'M5'
            
        Returns:
            dict: Signal with direction, confidence, entry, SL, TP, confluences
        """
        import time
        start_time = time.perf_counter()
        
        # Validate data
        if len(data) < 50:
            return self._no_signal("Insufficient data", start_time)
        
        try:
            # EXPERT FILTER 1: Analyze market structure first
            structure = self.market_structure.analyze_structure(data)
            
            # BALANCED FILTER: Warn on low volatility but don't block
            if structure['price_action']['volatility'] == 'low':
                pass  # Allow but log warning
            
            # EXPERT FILTER 3: Avoid consolidation
            if structure['price_action']['consolidation'] and not self.disable_consolidation_filter:
                return self._no_signal("Market consolidating - wait for breakout", start_time)
            
            # Calculate all indicators quickly
            indicators = self._calculate_indicators_fast(data)
            
            # Analyze each indicator
            rsi_signal = self._analyze_rsi(indicators['rsi'])
            ema_signal = self._analyze_ema(indicators)
            macd_signal = self._analyze_macd(indicators)
            stoch_signal = self._analyze_stochastic(indicators)
            bb_signal = self._analyze_bollinger(indicators, data)
            
            # Aggregate signals
            bullish_signals = [s for s in [rsi_signal, ema_signal, macd_signal, stoch_signal, bb_signal] 
                              if s == 1]
            bearish_signals = [s for s in [rsi_signal, ema_signal, macd_signal, stoch_signal, bb_signal] 
                              if s == -1]
            
            # Build confluences list
            confluences = []
            if rsi_signal == 1:
                confluences.append('RSI_bullish')
            elif rsi_signal == -1:
                confluences.append('RSI_bearish')
            
            if ema_signal == 1:
                confluences.append('EMA_uptrend')
            elif ema_signal == -1:
                confluences.append('EMA_downtrend')
            
            if macd_signal == 1:
                confluences.append('MACD_bullish')
            elif macd_signal == -1:
                confluences.append('MACD_bearish')
            
            if stoch_signal == 1:
                confluences.append('Stoch_oversold')
            elif stoch_signal == -1:
                confluences.append('Stoch_overbought')
            
            if bb_signal == 1:
                confluences.append('BB_lower_bounce')
            elif bb_signal == -1:
                confluences.append('BB_upper_bounce')
            
            # Determine signal direction with EXPERT CONFLUENCE requirements
            if len(bullish_signals) >= self.min_confluences and len(bullish_signals) > len(bearish_signals):
                signal_direction = 1
                confluence_ratio = len(bullish_signals) / 5  # 5 total indicators
                
                # EXPERT FILTER 4: Check trend alignment for LONG
                can_trade, reason = self.market_structure.should_trade_long(structure)
                if not can_trade:
                    return self._no_signal(f"Long rejected: {reason}", start_time, confluences)
                
                # STRICT MODE: Enforce stronger trend and S/R distance
                if self.quality_mode == 'strict':
                    if structure['trend']['strength'] < self.min_trend_strength_strict or structure['trend']['direction'] == 'down':
                        return self._no_signal("Trend not strong enough for long", start_time, confluences)
                    if structure['support_resistance']['distance_to_resistance_pips'] < self.sr_proximity_pips_strict:
                        return self._no_signal(
                            f"Too close to resistance ({structure['support_resistance']['distance_to_resistance_pips']:.1f} pips)",
                            start_time,
                            confluences
                        )
                
                # Base confidence from indicators
                confidence = confluence_ratio * 100
                
            elif len(bearish_signals) >= self.min_confluences and len(bearish_signals) > len(bullish_signals):
                signal_direction = -1
                confluence_ratio = len(bearish_signals) / 5
                
                # EXPERT FILTER 4: Check trend alignment for SHORT
                can_trade, reason = self.market_structure.should_trade_short(structure)
                if not can_trade:
                    return self._no_signal(f"Short rejected: {reason}", start_time, confluences)
                
                # STRICT MODE: Enforce stronger trend and S/R distance
                if self.quality_mode == 'strict':
                    if structure['trend']['strength'] < self.min_trend_strength_strict or structure['trend']['direction'] == 'up':
                        return self._no_signal("Trend not strong enough for short", start_time, confluences)
                    if structure['support_resistance']['distance_to_support_pips'] < self.sr_proximity_pips_strict:
                        return self._no_signal(
                            f"Too close to support ({structure['support_resistance']['distance_to_support_pips']:.1f} pips)",
                            start_time,
                            confluences
                        )
                
                # Base confidence from indicators
                confidence = confluence_ratio * 100
                
            else:
                return self._no_signal("Insufficient confluence", start_time, confluences)
            
            # Calculate entry, SL, TP based on ATR
            current_close = data['close'].iloc[-1]
            atr = indicators['atr']
            
            # SL/TP tuning: Strict mode keeps tighter SL but slightly larger TP to recover P/L
            if self.quality_mode == 'strict':
                sl_distance = atr * 0.6
                tp_distance = atr * self.tp_atr_multiplier_strict
            else:
                # Scalping defaults
                sl_distance = atr * 0.6
                tp_distance = atr * 1.2  # quicker profit
            
            if signal_direction == 1:  # BUY
                entry = current_close
                sl = entry - sl_distance
                tp = entry + tp_distance
            else:  # SELL
                entry = current_close
                sl = entry + sl_distance
                tp = entry - tp_distance
            
            # Calculate execution time
            execution_time = (time.perf_counter() - start_time) * 1000
            
            # EXPERT CONFIDENCE BOOSTING
            if len(confluences) >= self.expert_signal_confluences:
                confidence = min(92, confidence * 1.25)  # Expert quality
                logger.info(f"⭐ EXPERT SIGNAL detected (5 confluences)")
            elif len(confluences) >= self.strong_signal_confluences:
                confidence = min(85, confidence * 1.15)  # Strong quality
            
            # Additional boost for strong trend alignment
            if structure['trend']['strength'] >= 0.7:
                confidence = min(92, confidence * 1.1)
                logger.info(f"📈 Strong {structure['trend']['direction']} trend (strength: {structure['trend']['strength']})")
            
            # Confidence threshold: Higher in strict mode
            min_conf_threshold = 45 if self.quality_mode != 'strict' else self.required_confidence
            if confidence < min_conf_threshold:
                return self._no_signal(f"Confidence too low: {confidence:.1f}%", start_time, confluences)
            
            logger.info(f"✅ Signal generated in {execution_time:.1f}ms | "
                       f"{'BUY' if signal_direction == 1 else 'SELL'} | "
                       f"Confidence: {confidence:.0f}% | "
                       f"Confluences: {len(confluences)} | "
                       f"Trend: {structure['trend']['direction']} ({structure['trend']['strength']})")
            
            return {
                'signal': signal_direction,
                'confidence': round(confidence, 1),
                'entry': round(entry, 2),
                'sl': round(sl, 2),
                'tp': round(tp, 2),
                'confluences': confluences,
                'timeframe': timeframe,
                'generation_time_ms': round(execution_time, 1),
                'indicators': {
                    'rsi': round(indicators['rsi'], 1),
                    'ema_fast': round(indicators['ema_fast'], 2),
                    'ema_slow': round(indicators['ema_slow'], 2),
                    'macd_histogram': round(indicators['macd_histogram'], 3),
                    'stoch_k': round(indicators['stoch_k'], 1),
                    'atr': round(atr, 2)
                },
                'reason': f"Technical indicator confluence ({len(confluences)})"
            }
        
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return self._no_signal(f"Error: {str(e)}", start_time)
    
    def _calculate_indicators_fast(self, data: pd.DataFrame) -> Dict:
        """Calculate all indicators quickly (optimized for speed)."""
        # RSI
        rsi = calculate_rsi(data, period=self.rsi_period)
        current_rsi = rsi.iloc[-1]
        
        # EMAs
        ema_ultra = calculate_ema(data, period=self.ema_ultra_fast)
        ema_fast = calculate_ema(data, period=self.ema_fast)
        ema_slow = calculate_ema(data, period=self.ema_slow)
        
        # MACD
        macd_line, signal_line, macd_hist = calculate_macd(
            data, 
            fast_period=self.macd_fast,
            slow_period=self.macd_slow,
            signal_period=self.macd_signal
        )
        
        # Stochastic
        stoch_k, stoch_d = calculate_stochastic(
            data,
            k_period=self.stoch_k,
            d_period=self.stoch_d
        )
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(
            data,
            period=self.bb_period,
            std_dev=self.bb_std
        )
        
        # ATR for stop loss calculation
        atr = calculate_atr(data, period=14).iloc[-1]
        
        return {
            'rsi': current_rsi,
            'ema_ultra': ema_ultra.iloc[-1],
            'ema_fast': ema_fast.iloc[-1],
            'ema_slow': ema_slow.iloc[-1],
            'macd_line': macd_line.iloc[-1],
            'signal_line': signal_line.iloc[-1],
            'macd_histogram': macd_hist.iloc[-1],
            'stoch_k': stoch_k.iloc[-1],
            'stoch_d': stoch_d.iloc[-1],
            'bb_upper': bb_upper.iloc[-1],
            'bb_middle': bb_middle.iloc[-1],
            'bb_lower': bb_lower.iloc[-1],
            'atr': atr,
            'current_close': data['close'].iloc[-1]
        }
    
    def _analyze_rsi(self, rsi: float) -> int:
        """
        Analyze RSI for scalping signals.
        
        Returns: 1 (bullish), -1 (bearish), 0 (neutral)
        """
        # Oversold/overbought
        if rsi < self.rsi_oversold:
            return 1  # Bullish (oversold bounce)
        elif rsi > self.rsi_overbought:
            return -1  # Bearish (overbought rejection)
        
        # Momentum (crossing 50)
        elif self.rsi_momentum_bull <= rsi < self.rsi_overbought:
            return 1  # Bullish momentum
        elif self.rsi_oversold < rsi <= self.rsi_momentum_bear:
            return -1  # Bearish momentum
        
        return 0
    
    def _analyze_ema(self, indicators: Dict) -> int:
        """
        Analyze EMA alignment for trend.
        
        Returns: 1 (uptrend), -1 (downtrend), 0 (neutral)
        """
        ema_ultra = indicators['ema_ultra']
        ema_fast = indicators['ema_fast']
        ema_slow = indicators['ema_slow']
        current_close = indicators['current_close']
        
        # Perfect uptrend: Price > EMA3 > EMA8 > EMA21
        if current_close > ema_ultra > ema_fast > ema_slow:
            return 1
        
        # Perfect downtrend: Price < EMA3 < EMA8 < EMA21
        elif current_close < ema_ultra < ema_fast < ema_slow:
            return -1
        
        # Partial trends (faster entries)
        elif current_close > ema_fast > ema_slow:
            return 1  # Uptrend (less strict)
        elif current_close < ema_fast < ema_slow:
            return -1  # Downtrend (less strict)
        
        return 0
    
    def _analyze_macd(self, indicators: Dict) -> int:
        """
        Analyze MACD for momentum.
        
        Returns: 1 (bullish), -1 (bearish), 0 (neutral)
        """
        macd_hist = indicators['macd_histogram']
        macd_line = indicators['macd_line']
        signal_line = indicators['signal_line']
        
        # Histogram direction (most important for scalping)
        if macd_hist > 0 and macd_line > signal_line:
            return 1  # Bullish
        elif macd_hist < 0 and macd_line < signal_line:
            return -1  # Bearish
        
        return 0
    
    def _analyze_stochastic(self, indicators: Dict) -> int:
        """
        Analyze Stochastic for oversold/overbought.
        
        Returns: 1 (oversold), -1 (overbought), 0 (neutral)
        """
        stoch_k = indicators['stoch_k']
        stoch_d = indicators['stoch_d']
        
        # Oversold with bullish cross
        if stoch_k < self.stoch_oversold and stoch_k > stoch_d:
            return 1
        
        # Overbought with bearish cross
        elif stoch_k > self.stoch_overbought and stoch_k < stoch_d:
            return -1
        
        # Just oversold/overbought (weaker signal)
        elif stoch_k < self.stoch_oversold:
            return 1
        elif stoch_k > self.stoch_overbought:
            return -1
        
        return 0
    
    def _analyze_bollinger(self, indicators: Dict, data: pd.DataFrame) -> int:
        """
        Analyze Bollinger Bands for mean reversion.
        
        Returns: 1 (lower band bounce), -1 (upper band rejection), 0 (neutral)
        """
        current_close = indicators['current_close']
        bb_upper = indicators['bb_upper']
        bb_lower = indicators['bb_lower']
        bb_middle = indicators['bb_middle']
        
        # Price at lower band = bullish bounce
        if current_close <= bb_lower:
            return 1
        
        # Price at upper band = bearish rejection
        elif current_close >= bb_upper:
            return -1
        
        # Price below middle = potential bullish
        elif current_close < bb_middle:
            return 1
        
        # Price above middle = potential bearish
        elif current_close > bb_middle:
            return -1
        
        return 0
    
    def _no_signal(self, reason: str, start_time: float, confluences: list = None) -> Dict:
        """Return no-signal result."""
        execution_time = (time.perf_counter() - start_time) * 1000
        
        return {
            'signal': 0,
            'confidence': 0,
            'entry': None,
            'sl': None,
            'tp': None,
            'confluences': confluences or [],
            'generation_time_ms': round(execution_time, 1),
            'reason': reason
        }


if __name__ == "__main__":
    import time
    
    print("=" * 80)
    print("FAST SCALPER SIGNALS TEST")
    print("=" * 80)
    
    # Create test data
    dates = pd.date_range('2024-01-01', periods=100, freq='1min')
    prices = 2050 + np.cumsum(np.random.randn(100) * 0.5)
    
    test_data = pd.DataFrame({
        'open': prices + np.random.randn(100) * 0.2,
        'high': prices + abs(np.random.randn(100) * 0.5),
        'low': prices - abs(np.random.randn(100) * 0.5),
        'close': prices,
        'volume': np.random.randint(1000, 5000, 100)
    }, index=dates)
    
    # Initialize generator
    generator = FastScalperSignals()
    
    # Generate signal
    signal = generator.generate_signal(test_data, timeframe='M1')
    
    print(f"\nSignal Result:")
    print(f"  Direction: {'BUY' if signal['signal'] == 1 else 'SELL' if signal['signal'] == -1 else 'HOLD'}")
    print(f"  Confidence: {signal['confidence']}%")
    print(f"  Entry: {signal.get('entry')}")
    print(f"  SL: {signal.get('sl')}")
    print(f"  TP: {signal.get('tp')}")
    print(f"  Confluences: {signal.get('confluences', [])}")
    print(f"  Generation Time: {signal['generation_time_ms']}ms")
    
    if signal['generation_time_ms'] < 200:
        print("\n✅ Target met: Signal generated in < 200ms")
    else:
        print(f"\n⚠️ Target missed: {signal['generation_time_ms']}ms > 200ms")

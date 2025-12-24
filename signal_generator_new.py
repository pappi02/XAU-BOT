"""
Unified Signal Generator - Main entry point for signal generation
Uses the modular signal_generation package for professional signal analysis
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Import the modular signal generation system
from signal_generation import SignalMaster

logger = logging.getLogger(__name__)

class UnifiedSignalGenerator:
    """
    Unified Signal Generator - Professional modular signal generation system.
    
    This class serves as the main entry point and maintains backward compatibility
    while using the new modular signal_generation package internally.
    
    Architecture:
    - TechnicalIndicatorAnalyzer: Analyzes 7+ technical indicators
    - PatternDetector: Detects chart patterns and formations
    - NewsSentimentAnalyzer: Analyzes news and fundamental sentiment
    - StrategyAnalyzer: Evaluates trading strategies
    - AdaptiveSignalAnalyzer: Applies adaptive processing and smoothing
    - SignalMaster: Coordinates all components
    """
    
    def __init__(self,
                 ema_fast=12,
                 ema_slow=26,
                 rsi_period=14,
                 bb_period=20,
                 bb_std=2,
                 pattern_min_strength=65,
                 news_weight=0.2,
                 indicator_weight=0.5,
                 pattern_weight=0.3,
                 config=None,
                 enable_news_gating=True,
                 enable_strategy_refinements=True,
                 enable_pattern_quality_controls=True,
                 mt5_connection=None,
                 professional_mode=True,
                 sensitivity: str = 'balanced'):
        """
        Initialize the Unified Signal Generator with modular architecture.
        
        Args:
            ema_fast/slow (int): EMA periods for technical analysis
            rsi_period (int): RSI period
            bb_period/std: Bollinger Bands parameters
            pattern_min_strength (int): Pattern confidence threshold
            news_weight (float): Weight for news in final signal
            indicator_weight (float): Weight for technical indicators
            pattern_weight (float): Weight for patterns
            config: Configuration object
            enable_news_gating (bool): Enable news-aware filtering
            enable_strategy_refinements (bool): Enable strategy analysis
            enable_pattern_quality_controls (bool): Enable pattern validation
            mt5_connection: MT5 connection for multi-timeframe analysis
            professional_mode (bool): Enable professional features
        """
        # Store original parameters for backward compatibility
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.pattern_min_strength = pattern_min_strength
        
        self.news_weight = news_weight
        self.indicator_weight = indicator_weight
        self.pattern_weight = pattern_weight
        
        self.config = config
        self.enable_news_gating = enable_news_gating
        self.enable_strategy_refinements = enable_strategy_refinements
        self.enable_pattern_quality_controls = enable_pattern_quality_controls
        self.mt5_connection = mt5_connection
        self.professional_mode = professional_mode
        self.sensitivity = sensitivity
        
        # Initialize the modular Signal Master
        self.signal_master = SignalMaster(sensitivity=self.sensitivity)
        
        # Load professional config if available and professional mode enabled
        self.professional_config = None
        if professional_mode:
            try:
                import professional_config as pc
                self.professional_config = {
                    'signal_min_confidence': pc.PROFESSIONAL_SIGNAL_MIN_CONFIDENCE,
                    'pattern_min_confidence': pc.PROFESSIONAL_PATTERN_MIN_CONFIDENCE,
                    'risk_per_trade': pc.PROFESSIONAL_RISK_PER_TRADE_PCT,
                    'trailing_stop_enabled': pc.PROFESSIONAL_TRAILING_STOP_ENABLED,
                    'conflict_penalty': pc.PROFESSIONAL_CONFLICT_PENALTY,
                    'trail_activation_rr': pc.PROFESSIONAL_TRAIL_ACTIVATION_RR
                }
                logger.info("Professional configuration loaded")
            except ImportError:
                logger.info("Professional config not available, using defaults")
        
        logger.info(f"UnifiedSignalGenerator initialized (Professional Mode: {professional_mode}, Sensitivity: {self.sensitivity})")
        logger.info("Using modular signal_generation package with 5 specialized analyzers")
    
    def generate_signal(self, df, market_regime='trending'):
        """
        Generate comprehensive trading signal using modular architecture.
        
        Args:
            df (pd.DataFrame): OHLC data
            market_regime (str): Market regime ('ranging', 'trending', 'volatile')
            
        Returns:
            dict: Comprehensive signal analysis from SignalMaster
        """
        try:
            if len(df) < 50:
                return {
                    'signal': 0,
                    'strength': 0,
                    'recommendation': 'HOLD',
                    'error': 'Insufficient data'
                }
            
            # Use the modular Signal Master for analysis
            result = self.signal_master.generate_signal(df, market_regime)
            
            # Add backward compatibility fields
            result['signal_type'] = self._get_signal_type(result)
            result['confidence'] = result.get('strength', 0)
            result['direction'] = 'BUY' if result.get('signal') == 1 else ('SELL' if result.get('signal') == -1 else 'HOLD')
            
            logger.info(f"Signal generated: {result['recommendation']} (Strength: {result['strength']:.1f}%)")
            
            return result
        
        except Exception as e:
            logger.error(f"Error in signal generation: {e}", exc_info=True)
            return {
                'signal': 0,
                'strength': 0,
                'recommendation': 'HOLD',
                'error': str(e)
            }
    
    def get_latest_signal(self, symbol='XAUUSD', timeframe='M5', limit=100):
        """
        Get the latest signal for a symbol (backward compatibility).
        
        Args:
            symbol (str): Trading symbol
            timeframe (str): Timeframe
            limit (int): Number of candles to fetch
            
        Returns:
            dict: Latest signal
        """
        try:
            # This would typically fetch live data - for now return placeholder
            logger.warning("get_latest_signal: Using placeholder data")
            
            # Create dummy data for demonstration
            dates = pd.date_range(end=datetime.now(), periods=limit, freq='5min')
            prices = np.random.randn(limit).cumsum() + 2000
            df = pd.DataFrame({
                'open': prices,
                'high': prices + np.abs(np.random.randn(limit)),
                'low': prices - np.abs(np.random.randn(limit)),
                'close': prices,
                'volume': np.random.randint(1000, 10000, limit)
            }, index=dates)
            
            return self.generate_signal(df)
        
        except Exception as e:
            logger.error(f"Error getting latest signal: {e}")
            return {'signal': 0, 'strength': 0, 'error': str(e)}
    
    def _get_signal_type(self, result: dict) -> str:
        """Get signal type description"""
        signal = result.get('signal', 0)
        strength = result.get('strength', 0)
        
        if signal == 1:
            return "BULLISH" if strength > 60 else "WEAK_BULLISH"
        elif signal == -1:
            return "BEARISH" if strength > 60 else "WEAK_BEARISH"
        else:
            return "NEUTRAL"
    
    def analyze_multiple_timeframes(self, symbol, timeframes=['M5', 'M15', 'H1']):
        """
        Analyze multiple timeframes (placeholder for future implementation).
        
        Args:
            symbol (str): Trading symbol
            timeframes (list): List of timeframes to analyze
            
        Returns:
            dict: Multi-timeframe analysis
        """
        logger.warning("Multi-timeframe analysis: Not yet implemented in modular version")
        return {
            'timeframes': {},
            'consensus': 0,
            'recommendation': 'HOLD'
        }

# Backward compatibility function
def create_signal_generator(config=None, **kwargs):
    """
    Factory function to create signal generator.
    Maintains backward compatibility with existing code.
    """
    return UnifiedSignalGenerator(config=config, **kwargs)

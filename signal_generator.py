"""
Unified Signal Generator - Consolidates all signal generation logic
Combines indicators, patterns, news sentiment, and chart analysis for intelligent trading decisions
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Import indicators
from indicators.ema import calculate_ema, add_ema_signals, get_ema_trend
from indicators.rsi_clean_final import calculate_rsi, add_rsi_signals, get_rsi_condition
from indicators.bollinger import calculate_bollinger_bands, add_bollinger_signals, get_bollinger_position

# Import patterns
from patterns import (
    detect_triple_top, detect_triple_bottom,
    RisingWedge, FallingWedge,
    detect_double_top, detect_double_bottom,
    detect_head_and_shoulders,
    detect_bullish_channel, detect_bearish_channel
)

# Import news sentiment
from utils.news_reader import get_latest_forex_news

# Import adaptive engine components
from adaptive_engine import AdaptiveEngine, MarketData

logger = logging.getLogger(__name__)

class UnifiedSignalGenerator:
    """
    Unified signal generator that considers all market factors:
    - Technical indicators (EMA, RSI, Bollinger Bands)
    - Chart patterns (triple extrema, wedges, channels, head & shoulders)
    - News sentiment analysis
    - Market regime and volatility
    """

    def __init__(self,
                 ema_fast=12, ema_slow=26,
                 rsi_period=14,
                 bb_period=20, bb_std=2,
                 pattern_min_strength=65,
                 news_weight=0.2,
                 indicator_weight=0.5,
                 pattern_weight=0.3,
                 config=None):
        """
        Initialize signal generator parameters.

        Args:
            ema_fast/slow (int): EMA periods
            rsi_period (int): RSI period
            bb_period/std (int/float): Bollinger Bands parameters
            pattern_min_strength (int): Minimum pattern strength threshold
            news_weight (float): Weight for news sentiment in final score
            indicator_weight (float): Weight for technical indicators
            pattern_weight (float): Weight for chart patterns
        """
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.pattern_min_strength = pattern_min_strength

        # Weights for different signal components
        self.news_weight = news_weight
        self.indicator_weight = indicator_weight
        self.pattern_weight = pattern_weight

        # Ensure weights sum to 1.0
        total_weight = news_weight + indicator_weight + pattern_weight
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"Signal weights don't sum to 1.0: {total_weight}, normalizing...")
            self.news_weight /= total_weight
            self.indicator_weight /= total_weight
            self.pattern_weight /= total_weight

        # Store config for adaptive engine
        self.config = config

        # Initialize adaptive engine if config is provided
        self.adaptive_engine = AdaptiveEngine(config) if config else None

    def prepare_data(self, data):
        """
        Prepare data with all technical indicators.

        Args:
            data (pd.DataFrame): OHLC data

        Returns:
            pd.DataFrame: Data with all indicators added
        """
        df = data.copy()

        # Add EMA signals
        df = add_ema_signals(df, self.ema_fast, self.ema_slow)

        # Add RSI signals
        df = add_rsi_signals(df, self.rsi_period)

        # Add Bollinger signals
        df = add_bollinger_signals(df, self.bb_period, self.bb_std)

        # Add volatility measures
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std() * np.sqrt(252)  # Annualized

        # Add ATR approximation
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(window=14).mean()

        return df

    def _analyze_technical_indicators(self, data):
        """
        Analyze technical indicators and return weighted scores.

        Args:
            data (pd.DataFrame): Data with indicators

        Returns:
            dict: Technical analysis results
        """
        latest = data.iloc[-1]

        # EMA analysis
        ema_fast = latest.get(f'EMA_{self.ema_fast}', latest['close'])
        ema_slow = latest.get(f'EMA_{self.ema_slow}', latest['close'])
        ema_signal = 1 if ema_fast > ema_slow else (-1 if ema_fast < ema_slow else 0)

        # RSI analysis
        rsi_val = latest.get(f'RSI_{self.rsi_period}', 50)
        if rsi_val < 30:
            rsi_signal = 1  # Oversold - bullish
        elif rsi_val > 70:
            rsi_signal = -1  # Overbought - bearish
        else:
            rsi_signal = 0  # Neutral

        # Bollinger Bands analysis
        close = latest['close']
        bb_upper = latest.get(f'BB_upper_{self.bb_period}', close)
        bb_lower = latest.get(f'BB_lower_{self.bb_period}', close)
        bb_middle = latest.get(f'BB_middle_{self.bb_period}', close)

        if close <= bb_lower:
            bb_signal = 1  # Below lower band - bullish bounce potential
        elif close >= bb_upper:
            bb_signal = -1  # Above upper band - bearish bounce potential
        else:
            bb_signal = 0  # Within bands - neutral

        # Calculate confidence scores
        ema_confidence = min(abs(ema_fast - ema_slow) / ema_slow * 100, 100)
        rsi_confidence = min(abs(50 - rsi_val) * 2, 100)  # Max confidence at extremes
        bb_confidence = min(abs(close - bb_middle) / (bb_upper - bb_middle) * 100, 100)

        # Weighted technical score
        tech_score = (
            ema_signal * ema_confidence * 0.4 +
            rsi_signal * rsi_confidence * 0.35 +
            bb_signal * bb_confidence * 0.25
        )

        return {
            'ema_signal': ema_signal,
            'rsi_signal': rsi_signal,
            'bb_signal': bb_signal,
            'tech_score': tech_score,
            'confidence': (ema_confidence + rsi_confidence + bb_confidence) / 3,
            'components': {
                'ema_trend': 'bullish' if ema_signal == 1 else 'bearish' if ema_signal == -1 else 'neutral',
                'rsi_condition': 'oversold' if rsi_val < 30 else 'overbought' if rsi_val > 70 else 'neutral',
                'bb_position': 'below_lower' if close <= bb_lower else 'above_upper' if close >= bb_upper else 'within_bands'
            }
        }

    def _analyze_chart_patterns(self, data):
        """
        Analyze chart patterns for signals.

        Args:
            data (pd.DataFrame): OHLC data

        Returns:
            dict: Pattern analysis results
        """
        if len(data) < 100:  # Need sufficient data for pattern analysis
            return {
                'pattern_signal': 0,
                'pattern_strength': 0,
                'detected_patterns': [],
                'confidence': 0
            }

        window_df = data.reset_index(drop=True).tail(400).copy()
        patterns_found = []

        # Double Top/Bottom patterns
        double_top = detect_double_top(window_df)
        double_bottom = detect_double_bottom(window_df)

        if double_top and double_top.get('detected', False) and double_top.get('confidence', 0) >= 0.4:
            patterns_found.append({
                'type': 'double_top',
                'signal': -1,  # Bearish
                'strength': double_top['confidence'] * 100,
                'confidence': double_top['confidence']
            })

        if double_bottom and double_bottom.get('detected', False) and double_bottom.get('confidence', 0) >= 0.4:
            patterns_found.append({
                'type': 'double_bottom',
                'signal': 1,  # Bullish
                'strength': double_bottom['confidence'] * 100,
                'confidence': double_bottom['confidence']
            })

        # Triple patterns
        triple_top = detect_triple_top(window_df,
                                       lookback=3,
                                       tolerance=0.004,
                                       min_separation=6,
                                       max_span=120,
                                       confirmation_lookforward=4)

        triple_bot = detect_triple_bottom(window_df,
                                          lookback=3,
                                          tolerance=0.004,
                                          min_separation=6,
                                          max_span=120,
                                          confirmation_lookforward=4)

        if triple_top and triple_top['strength'] >= self.pattern_min_strength:
            patterns_found.append({
                'type': 'triple_top',
                'signal': -1,  # Bearish
                'strength': triple_top['strength'],
                'confidence': triple_top['strength'] / 100
            })

        if triple_bot and triple_bot['strength'] >= self.pattern_min_strength:
            patterns_found.append({
                'type': 'triple_bottom',
                'signal': 1,  # Bullish
                'strength': triple_bot['strength'],
                'confidence': triple_bot['strength'] / 100
            })

        # Wedge patterns
        wedge_candles = [{'high': row['high'], 'low': row['low'], 'close': row['close'], 'open': row['open']}
                         for _, row in window_df.tail(50).iterrows()]

        rising_wedge = RisingWedge(wedge_candles, timeframe="M5")
        falling_wedge = FallingWedge(wedge_candles, timeframe="M5")
        rising_result = rising_wedge.detect()
        falling_result = falling_wedge.detect()

        if rising_result['detected'] and rising_result['confidence'] >= 0.7:
            patterns_found.append({
                'type': 'rising_wedge',
                'signal': -1,  # Bearish breakout
                'strength': rising_result['confidence'] * 100,
                'confidence': rising_result['confidence'],
                'breakout_price': rising_result.get('breakout_price')
            })

        if falling_result['detected'] and falling_result['confidence'] >= 0.7:
            patterns_found.append({
                'type': 'falling_wedge',
                'signal': 1,  # Bullish breakout
                'strength': falling_result['confidence'] * 100,
                'confidence': falling_result['confidence'],
                'breakout_price': falling_result.get('breakout_price')
            })

        # Head and shoulders
        head_shoulders = detect_head_and_shoulders(window_df)
        if head_shoulders and head_shoulders.get('strength', 0) >= self.pattern_min_strength:
            patterns_found.append({
                'type': 'head_shoulders',
                'signal': -1,  # Bearish
                'strength': head_shoulders['strength'],
                'confidence': head_shoulders['strength'] / 100
            })

        # Determine overall pattern signal
        if not patterns_found:
            return {
                'pattern_signal': 0,
                'pattern_strength': 0,
                'detected_patterns': [],
                'confidence': 0
            }

        # Weight patterns by strength and recency
        total_weight = sum(p['confidence'] for p in patterns_found)
        weighted_signal = sum(p['signal'] * p['confidence'] for p in patterns_found) / total_weight
        avg_strength = sum(p['strength'] for p in patterns_found) / len(patterns_found)
        avg_confidence = sum(p['confidence'] for p in patterns_found) / len(patterns_found)

        return {
            'pattern_signal': 1 if weighted_signal > 0.3 else (-1 if weighted_signal < -0.3 else 0),
            'pattern_strength': avg_strength,
            'detected_patterns': patterns_found,
            'confidence': avg_confidence
        }

    def _analyze_news_sentiment(self):
        """
        Analyze news sentiment for market bias.

        Returns:
            dict: News sentiment analysis
        """
        try:
            news_data = get_latest_forex_news()

            sentiment_map = {
                'bullish': 1,
                'bearish': -1,
                'neutral': 0
            }

            sentiment_signal = sentiment_map.get(news_data['sentiment'], 0)
            confidence = min(abs(news_data['avg_sentiment_score']) * 2, 1.0)  # Scale to 0-1

            # Determine news impact level
            article_count = news_data.get('article_count', 0)
            if article_count > 10 or confidence > 0.8:
                news_impact = 'high'
            elif article_count > 5 or confidence > 0.5:
                news_impact = 'medium'
            else:
                news_impact = 'low'

            return {
                'news_signal': sentiment_signal,
                'news_sentiment': news_data['sentiment'],
                'news_confidence': confidence,
                'news_impact': news_impact,
                'article_count': news_data['article_count'],
                'available': news_data['available']
            }

        except Exception as e:
            logger.warning(f"News sentiment analysis failed: {e}")
            return {
                'news_signal': 0,
                'news_sentiment': 'neutral',
                'news_confidence': 0,
                'news_impact': 'low',
                'article_count': 0,
                'available': False
            }

    def _calculate_market_regime(self, data):
        """
        Determine current market regime (trending vs ranging).

        Args:
            data (pd.DataFrame): OHLC data

        Returns:
            dict: Market regime analysis
        """
        if len(data) < 20:
            return {'regime': 'unknown', 'strength': 0}

        # Calculate trend strength using ADX approximation
        high_low = data['high'] - data['low']
        high_close = abs(data['high'] - data['close'].shift(1))
        low_close = abs(data['low'] - data['close'].shift(1))

        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()

        # Directional movement
        dm_plus = data['high'] - data['high'].shift(1)
        dm_minus = data['low'].shift(1) - data['low']

        dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0)
        dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0)

        di_plus = 100 * (dm_plus.rolling(window=14).mean() / atr)
        di_minus = 100 * (dm_minus.rolling(window=14).mean() / atr)
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
        adx = dx.rolling(window=14).mean()

        adx_current = adx.iloc[-1] if not adx.empty else 0

        if adx_current > 25:
            regime = 'trending'
        elif adx_current < 20:
            regime = 'ranging'
        else:
            regime = 'transitional'

        return {
            'regime': regime,
            'adx': adx_current,
            'di_plus': di_plus.iloc[-1] if not di_plus.empty else 0,
            'di_minus': di_minus.iloc[-1] if not di_minus.empty else 0
        }

    def generate_signal(self, data, strategy_type='unified'):
        """
        Generate unified trading signal considering all factors.

        Args:
            data (pd.DataFrame): OHLC data
            strategy_type (str): Strategy type for signal weighting

        Returns:
            dict: Comprehensive signal information
        """
        if len(data) < max(self.ema_slow, self.rsi_period, self.bb_period, 20):
            return {
                'signal': 'HOLD',
                'strength': 0,
                'confidence': 0,
                'reasons': ['Insufficient data for analysis'],
                'components': {
                    'technical': {'score': 0, 'confidence': 0},
                    'patterns': {'signal': 0, 'strength': 0},
                    'news': {'signal': 0, 'sentiment': 'neutral'},
                    'regime': {'regime': 'unknown'}
                }
            }

        # Prepare data with indicators
        prepared_data = self.prepare_data(data)

        # Analyze each component
        technical = self._analyze_technical_indicators(prepared_data)
        patterns = self._analyze_chart_patterns(prepared_data)
        news = self._analyze_news_sentiment()
        regime = self._calculate_market_regime(prepared_data)

        # Calculate weighted final signal
        tech_weighted = technical['tech_score'] * self.indicator_weight
        pattern_weighted = patterns['pattern_signal'] * patterns['confidence'] * 100 * self.pattern_weight
        news_weighted = news['news_signal'] * news['news_confidence'] * 100 * self.news_weight

        total_score = tech_weighted + pattern_weighted + news_weighted

        # Determine signal direction and strength
        if abs(total_score) < 10:  # Low conviction threshold
            signal = 'HOLD'
            strength = 0
        elif total_score > 0:
            signal = 'BUY'
            strength = min(abs(total_score), 100)
        else:
            signal = 'SELL'
            strength = min(abs(total_score), 100)

        # Overall confidence
        confidence_components = [
            technical['confidence'] * self.indicator_weight,
            patterns['confidence'] * self.pattern_weight,
            news['news_confidence'] * self.news_weight
        ]
        overall_confidence = sum(confidence_components)

        # Build reasons
        reasons = []

        if technical['tech_score'] != 0:
            direction = "bullish" if technical['tech_score'] > 0 else "bearish"
            reasons.append(f"Technical indicators show {direction} bias ({technical['confidence']:.1f}% confidence)")

        if patterns['pattern_signal'] != 0:
            pattern_types = [p['type'] for p in patterns['detected_patterns']]
            direction = "bullish" if patterns['pattern_signal'] > 0 else "bearish"
            reasons.append(f"Chart patterns suggest {direction} continuation ({', '.join(pattern_types)})")

        if news['news_signal'] != 0:
            reasons.append(f"News sentiment is {news['news_sentiment']} ({news['article_count']} articles)")

        if regime['regime'] != 'unknown':
            reasons.append(f"Market regime: {regime['regime']} (ADX: {regime['adx']:.1f})")

        if not reasons:
            reasons.append("No significant signals detected")

        # Calculate position sizing factors
        volatility = prepared_data['volatility'].iloc[-1] if 'volatility' in prepared_data.columns else 0.02
        atr = prepared_data['atr'].iloc[-1] if 'atr' in prepared_data.columns else prepared_data['close'].iloc[-1] * 0.01

        size_factor = self._calculate_size_factor(strength, volatility, regime, news)

        # Apply adaptive engine processing if available
        adaptive_result = None
        if self.adaptive_engine:
            try:
                # Create signals dict from components
                signals_dict = {
                    'technical': technical['tech_score'] / 100.0,  # Normalize to -1 to 1
                    'patterns': patterns['pattern_signal'] * patterns['confidence'],
                    'news': news['news_signal'] * news['news_confidence']
                }

                # Create market data object
                market_data = MarketData(
                    atr=atr,
                    trend_strength=regime['adx'] / 100.0,  # Normalize to 0-1
                    volatility=volatility,
                    news_impact=news['news_impact']
                )

                # Process signals through adaptive engine
                adaptive_result = self.adaptive_engine.process_signals(signals_dict, market_data)

                # Check if adaptive engine allows trading
                if not adaptive_result.get('should_trade', True):
                    # Override signal to HOLD if adaptive engine rejects
                    signal = 'HOLD'
                    strength = 0
                    reasons.append("Adaptive engine rejected the signal")
                    logger.info("Signal overridden to HOLD by adaptive engine")

                # Get entry parameters from adaptive engine
                entry_params = self.adaptive_engine.calculate_entry_parameters(
                    signal, strength, prepared_data['close'].iloc[-1], atr
                )

                # Update size factor with adaptive calculations
                if entry_params and 'position_size' in entry_params:
                    size_factor = entry_params['position_size']

            except Exception as e:
                logger.warning(f"Adaptive engine processing failed: {e}")
                adaptive_result = {'error': str(e)}

        return {
            'signal': signal,
            'strength': round(strength, 2),
            'confidence': round(overall_confidence, 2),
            'entry_price': float(prepared_data['close'].iloc[-1]),
            'size_factor': size_factor,
            'reasons': reasons,
            'components': {
                'technical': technical,
                'patterns': patterns,
                'news': news,
                'regime': regime
            },
            'market_data': {
                'volatility': volatility,
                'atr': atr,
                'regime_strength': regime['adx']
            },
            'adaptive_result': adaptive_result
        }

    def _calculate_size_factor(self, signal_strength, volatility, regime, news):
        """
        Calculate position sizing factor based on market conditions.

        Args:
            signal_strength (float): Signal strength (0-100)
            volatility (float): Current volatility
            regime (dict): Market regime info
            news (dict): News sentiment info

        Returns:
            float: Size factor (0.1 to 2.0)
        """
        base_factor = 1.0

        # Signal strength adjustment
        if signal_strength > 80:
            base_factor *= 1.5
        elif signal_strength > 60:
            base_factor *= 1.2
        elif signal_strength < 30:
            base_factor *= 0.7

        # Volatility adjustment
        if volatility > 0.03:  # High volatility
            base_factor *= 0.8
        elif volatility < 0.01:  # Low volatility
            base_factor *= 1.2

        # Regime adjustment
        if regime['regime'] == 'trending':
            base_factor *= 1.1  # Slightly larger in trends
        elif regime['regime'] == 'ranging':
            base_factor *= 0.9  # Smaller in ranges

        # News impact adjustment
        news_impact = news.get('news_impact', 'low')
        if news_impact == 'high':
            base_factor *= 0.7
        elif news_impact == 'low':
            base_factor *= 1.1

        return round(max(0.1, min(base_factor, 2.0)), 2)

    def get_market_analysis(self, data):
        """
        Get comprehensive market analysis without generating a signal.

        Args:
            data (pd.DataFrame): OHLC data

        Returns:
            dict: Market analysis
        """
        prepared_data = self.prepare_data(data)

        return {
            'technical': self._analyze_technical_indicators(prepared_data),
            'patterns': self._analyze_chart_patterns(prepared_data),
            'news': self._analyze_news_sentiment(),
            'regime': self._calculate_market_regime(prepared_data),
            'timestamp': datetime.now()
        }


if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=200, freq='h')
    base_trend = np.cumsum(np.random.randn(200) * 0.5)
    micro_noise = np.sin(np.arange(200) * 0.5) * 2
    prices = 1800 + base_trend + micro_noise

    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 0.5,
        'high': prices + abs(np.random.randn(200) * 1),
        'low': prices - abs(np.random.randn(200) * 1),
        'close': prices
    }, index=dates)

    # Create signal generator
    generator = UnifiedSignalGenerator()

    # Generate signal
    signal = generator.generate_signal(sample_data)
    print("📊 Unified Signal Analysis:")
    print(f"Signal: {signal['signal']} (Strength: {signal['strength']}%, Confidence: {signal['confidence']}%)")
    print(f"Reasons: {signal['reasons']}")
    print(f"Size Factor: {signal['size_factor']}")

    print("\n📈 Component Analysis:")
    print(f"Technical: {signal['components']['technical']['components']}")
    print(f"Patterns: {len(signal['components']['patterns']['detected_patterns'])} detected")
    print(f"News: {signal['components']['news']['news_sentiment']} ({signal['components']['news']['article_count']} articles)")
    print(f"Regime: {signal['components']['regime']['regime']} (ADX: {signal['components']['regime']['adx']:.1f})")

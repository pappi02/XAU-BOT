"""
Multi-Timeframe Analyzer for XAU/USD Trading Bot
Phase 7 - Signal-Based Trade Execution with Multi-Timeframe Confluence

This module analyzes multiple timeframes simultaneously to generate confluence-based trading signals.
Only executes trades when multi-timeframe conditions align with high confidence.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import time
from typing import Dict, List, Optional, Tuple

# Import project modules
from logger_config import setup_logger
from data.fetch_candles import get_candles
from strategies.strategy_basic import BasicTradingStrategy
from utils.news_reader import get_latest_forex_news
from utils.indicators import atr
from analysis.decision_engine import analyze_and_decide
import config

logger = setup_logger()

# Define factor weights (tune later based on performance)
WEIGHTS = {
    "signal_strength": 0.30,
    "ema_alignment": 0.20,
    "rsi_condition": 0.15,
    "volatility": 0.15,
    "news_sentiment": 0.10,
    "trend_strength": 0.10
}

CONFIDENCE_THRESHOLD = 0.70   # 70% minimum confidence for trade execution
TRADE_COOLDOWN = 300          # 5 min cooldown between trades

last_trade_time = 0

class MultiTimeframeAnalyzer:
    """
    Analyzes multiple timeframes for confluence-based trading signals.
    """

    def __init__(self):
        """
        Initialize the multi-timeframe analyzer.
        """
        # Define timeframes and their MT5 constants
        self.timeframes = {
            'M1': 1,      # 1 minute
            'M5': 5,      # 5 minutes
            'M15': 15,    # 15 minutes
            'M30': 30,    # 30 minutes
            'H1': 16385,  # 1 hour
            'H4': 16388   # 4 hours
        }

        # Define timeframe weights for confluence scoring
        # Higher weights for longer timeframes (more significant)
        self.timeframe_weights = {
            'M1': 0.1,   # Entry timing
            'M5': 0.15,  # Short-term trend
            'M15': 0.2,  # Medium-term direction
            'M30': 0.25, # Volatility filter
            'H1': 0.15,  # Trend validation
            'H4': 0.15   # Macro bias
        }

        # Initialize strategy for each timeframe
        self.strategies = {}
        for tf_name in self.timeframes.keys():
            self.strategies[tf_name] = BasicTradingStrategy(
                ema_fast=config.EMA_FAST,
                ema_slow=config.EMA_SLOW,
                rsi_period=config.RSI_PERIOD,
                bb_period=config.BB_PERIOD,
                bb_std=config.BB_STD_DEV
            )

        # Confluence thresholds
        self.min_confluence_for_trade = 0.7  # Minimum 70% confluence for trade entry
        self.strong_confluence_threshold = 0.8  # Strong signal threshold

        logger.info("MultiTimeframeAnalyzer initialized with timeframes: %s", list(self.timeframes.keys()))

    def analyze_market(self, symbol: str = "XAUUSDm") -> Dict:
        """
        Perform comprehensive multi-timeframe analysis with Phase 9 enhancements.
        """

    logger.info("Starting Phase 9 multi-timeframe analysis for %s", symbol)

    # Define timeframes as per Phase 9
    phase9_timeframes = {
        'M1': 1,
        'M5': 5,
        'M15': 15,
        'M30': 30,
        'H1': 16385,
        'H4': 16388
    }

    # Fetch data for all timeframes (count=200 as per Phase 9)
    timeframe_data = {}
    for tf_name, tf_constant in phase9_timeframes.items():
        try:
            df = get_candles(symbol, tf_constant, 200)
            if df is not None and not df.empty:
                timeframe_data[tf_name] = df
                logger.debug("✅ Successfully fetched %d candles for %s timeframe", len(df), tf_name)
            else:
                logger.warning("⚠️ No candle data returned for %s timeframe.", tf_name)
        except Exception as e:
            logger.error("❌ Error fetching %s data: %s", tf_name, e)

    # Handle missing data gracefully
    if not timeframe_data:
        logger.warning("⚠️ No timeframe data fetched at all. Skipping this cycle.")
        return self._create_empty_analysis()

    # Analyze each timeframe safely
    analysis = {}
    for tf, df in timeframe_data.items():
        try:
            rsi_val = self.get_rsi(df)
            atr_val = self.get_atr(df)
            signal_strength_val = self.get_signal_strength(df)
            ema_trend_val = self.check_ema_trend(df)

            analysis[tf] = {
                "ema_trend": ema_trend_val or "neutral",
                "rsi": float(rsi_val) if not np.isnan(rsi_val) else 50.0,
                "atr": float(atr_val) if not np.isnan(atr_val) else 0.5,
                "signal_strength": float(signal_strength_val) if signal_strength_val else 0.0
            }

            logger.debug("🧭 %s -> Trend=%s | RSI=%.2f | ATR=%.3f | SignalStrength=%.2f",
                         tf, ema_trend_val, rsi_val, atr_val, signal_strength_val)

        except Exception as e:
            logger.error("❌ Error analyzing %s timeframe: %s", tf, e)

    # Re-check if valid analysis data exists
    valid_signals = [a for a in analysis.values() if a["signal_strength"] > 0]
    if not valid_signals:
        logger.warning("⚠️ No valid timeframe signals detected after analysis.")
        return self._create_empty_analysis()

    # Determine overall alignment
    alignment_result = self.multi_tf_alignment(analysis)

    # Get news data (optional)
    news_data = get_latest_forex_news()
    news_sentiment = "neutral"
    if news_data and news_data.get('available', False):
        news_sentiment = news_data.get('sentiment', 'neutral')
    else:
        logger.info("📰 No relevant news at this time — proceeding without news impact.")

    # Calculate volatility score
    volatility_score = self._calculate_volatility_score(timeframe_data)

    # Calculate confidence score
    confidence_score = self.calculate_confidence(analysis, news_data, volatility_score)

    # Build factor inputs for decision engine
    factor_inputs = {
        "multi_tf": self._map_alignment_to_score(alignment_result),
        "ema_alignment": self._calculate_ema_alignment_score(analysis),
        "rsi": self._calculate_rsi_score(analysis),
        "momentum": self._calculate_momentum_score(timeframe_data),
        "atr_volatility": -volatility_score if volatility_score else 0,
        "price_action": self._calculate_price_action_score(timeframe_data),
        "news": self._map_news_to_score(news_sentiment),
        "recent_perf": self._calculate_recent_performance_score()
    }

    recent_trend = 1 if analysis.get('H1', {}).get('ema_trend') == 'bullish' else \
                   -1 if analysis.get('H1', {}).get('ema_trend') == 'bearish' else 0
    current_atr = analysis.get('H1', {}).get('atr', 0.5)

    # Get decision
    decision_result = analyze_and_decide(
        factor_inputs,
        symbol=symbol,
        bias_preference="ema_alignment",
        recent_trend=recent_trend,
        atr=current_atr
    )

    # Extract results
    action = decision_result['decision']['action']
    confluence_score = decision_result['confluence']['confluence_score']
    direction_score = decision_result['confluence']['direction_score']
    factor_scores = decision_result['confluence']['factor_scores']
    rationale = decision_result['decision']['rationale']

    # Dynamic position parameters
    position_params = self._calculate_position_parameters_phase9(
        alignment_result, timeframe_data, action, confidence_score
    )

    # Should trade logic
    should_trade = confidence_score >= CONFIDENCE_THRESHOLD

    # Construct full result
    analysis_result = {
        'timestamp': datetime.now(),
        'symbol': symbol,
        'alignment': alignment_result,
        'action': action,
        'news_sentiment': news_sentiment,
        'volatility_score': volatility_score,
        'confidence_score': confidence_score,
        'confluence_score': confluence_score,
        'direction_score': direction_score,
        'factor_scores': factor_scores,
        'rationale': rationale,
        'timeframe_analysis': analysis,
        'position_params': position_params,
        'should_trade': should_trade
    }

    # Final log
    rsi_avg = np.mean([tf_data['rsi'] for tf_data in analysis.values()])
    atr_avg = np.mean([tf_data['atr'] for tf_data in analysis.values()])
    logger.info("✅ Phase 9 Analysis complete: Alignment=%s | Action=%s | ShouldTrade=%s | Confidence=%.2f | Confluence=%.2f | RSI=%.1f | ATR=%.3f",
                alignment_result, action, should_trade, confidence_score, confluence_score, rsi_avg, atr_avg)

    logger.info("🧩 Signal Log: Action=%s | Confluence=%.2f | Factors=%s",
                action, confluence_score, factor_scores)

    return analysis_result


    def _signal_to_score(self, signal: str) -> float:
        """
        Convert signal string to numerical score.

        Args:
            signal: 'BUY', 'SELL', or 'HOLD'

        Returns:
            float: -1 (SELL), 0 (HOLD), 1 (BUY)
        """
        if signal == 'BUY':
            return 1.0
        elif signal == 'SELL':
            return -1.0
        else:
            return 0.0

    def _get_news_multiplier(self, news_sentiment: str) -> float:
        """
        Get news impact multiplier.

        Args:
            news_sentiment: News sentiment string

        Returns:
            float: Multiplier for confluence score
        """
        multipliers = {
            'bullish': 1.1,    # Boost bullish signals
            'bearish': 0.9,    # Dampen bearish signals
            'neutral': 1.0     # No change
        }
        return multipliers.get(news_sentiment.lower(), 1.0)

    def _calculate_volatility_score(self, timeframe_data: Dict) -> float:
        """
        Calculate volatility score across timeframes.

        Args:
            timeframe_data: Dictionary of timeframe DataFrames

        Returns:
            float: Volatility score (0-1, higher = more volatile)
        """
        try:
            # Use H1 timeframe for volatility assessment
            if 'H1' in timeframe_data:
                df = timeframe_data['H1']
                atr_values = atr(df, period=config.ATR_PERIOD)
                if len(atr_values) > 0:
                    current_atr = atr_values.iloc[-1]
                    # Normalize ATR (assuming typical range 0.1-2.0 for XAU)
                    normalized_atr = min(max(current_atr / 2.0, 0), 1)
                    return normalized_atr
        except Exception as e:
            logger.error("Error calculating volatility score: %s", e)

        return 0.5  # Default neutral volatility

    def _evaluate_recent_bias(self, timeframe_data: Dict, news_sentiment: str) -> str:
        """
        Evaluate recent price bias when alignment is neutral but confidence is high.
        
        Args:
            timeframe_data: Dictionary of timeframe data
            news_sentiment: Current news sentiment
            
        Returns:
            str: 'BUY', 'SELL', or 'WAIT'
        """
        try:
            # Use M5 and M15 for recent bias evaluation
            bias_signals = []
            
            for tf_name in ['M5', 'M15']:
                if tf_name in timeframe_data:
                    df = timeframe_data[tf_name]
                    if len(df) >= 10:
                        # Look at recent price movement
                        recent_prices = df['close'].tail(10)
                        price_trend = recent_prices.iloc[-1] - recent_prices.iloc[0]
                        
                        # Look at recent highs/lows
                        recent_high = df['high'].tail(10).max()
                        recent_low = df['low'].tail(10).min()
                        current_price = df['close'].iloc[-1]
                        
                        # Determine bias based on price position and trend
                        if current_price > (recent_high + recent_low) / 2 and price_trend > 0:
                            bias_signals.append('BUY')
                        elif current_price < (recent_high + recent_low) / 2 and price_trend < 0:
                            bias_signals.append('SELL')
                        else:
                            bias_signals.append('NEUTRAL')
            
            # Combine bias signals with news sentiment
            if bias_signals:
                buy_count = bias_signals.count('BUY')
                sell_count = bias_signals.count('SELL')
                
                # If bias is clear, use it
                if buy_count > sell_count:
                    if news_sentiment in ['bullish', 'neutral']:
                        return 'BUY'
                elif sell_count > buy_count:
                    if news_sentiment in ['bearish', 'neutral']:
                        return 'SELL'
                
                # If bias is unclear, use news sentiment as tiebreaker
                if news_sentiment == 'bullish':
                    return 'BUY'
                elif news_sentiment == 'bearish':
                    return 'SELL'
            
            return 'WAIT'
            
        except Exception as e:
            logger.error(f"Error evaluating recent bias: {e}")
            return 'WAIT'

    def _apply_additional_factors(self, base_confluence: float,
                                news_multiplier: float,
                                volatility_score: float) -> float:
        """
        Apply additional market factors to confluence score.

        Args:
            base_confluence: Base confluence score (0-1)
            news_multiplier: News impact multiplier
            volatility_score: Volatility score (0-1)

        Returns:
            float: Adjusted confluence score
        """
        # Apply news sentiment
        adjusted_score = base_confluence * news_multiplier

        # Apply volatility filter (reduce confidence in high volatility)
        if volatility_score > 0.7:  # High volatility
            adjusted_score *= 0.9
        elif volatility_score < 0.3:  # Low volatility
            adjusted_score *= 1.1

        # Ensure score stays within 0-1 range
        return max(0, min(1, adjusted_score))

    def _determine_overall_signal(self, confluence_score: float,
                                timeframe_signals: Dict) -> Tuple[str, float]:
        """
        Determine overall trading signal based on confluence.

        Args:
            confluence_score: Final confluence score (0-1)
            timeframe_signals: Individual timeframe signals

        Returns:
            tuple: (signal, confidence)
        """
        if confluence_score >= self.strong_confluence_threshold:
            # Strong confluence - check direction
            buy_votes = sum(1 for tf in timeframe_signals.values()
                          if tf['signal'] == 'BUY')
            sell_votes = sum(1 for tf in timeframe_signals.values()
                           if tf['signal'] == 'SELL')

            if buy_votes > sell_votes:
                return 'BUY', confluence_score
            elif sell_votes > buy_votes:
                return 'SELL', confluence_score

        elif confluence_score >= self.min_confluence_for_trade:
            # Moderate confluence - require majority agreement
            buy_votes = sum(1 for tf in timeframe_signals.values()
                          if tf['signal'] == 'BUY')
            sell_votes = sum(1 for tf in timeframe_signals.values()
                           if tf['signal'] == 'SELL')

            total_signals = len(timeframe_signals)
            if buy_votes >= total_signals * 0.6:  # 60% agreement
                return 'BUY', confluence_score * 0.9  # Slight confidence reduction
            elif sell_votes >= total_signals * 0.6:
                return 'SELL', confluence_score * 0.9

        return 'HOLD', 0.0

    def _calculate_position_parameters(self, confluence_score: float,
                                    timeframe_data: Dict,
                                    signal: str) -> Dict:
        """
        Calculate recommended position parameters.

        Args:
            confluence_score: Confluence score (0-1)
            timeframe_data: Timeframe data dictionary
            signal: Trading signal

        Returns:
            dict: Position parameters
        """
        try:
            # Get current price from M1 data
            if 'M1' in timeframe_data:
                current_price = timeframe_data['M1']['close'].iloc[-1]
            else:
                current_price = 1800  # Fallback

            # Calculate dynamic stop loss based on ATR
            if 'H1' in timeframe_data:
                df_h1 = timeframe_data['H1']
                atr_values = atr(df_h1, period=config.ATR_PERIOD_CONFLUENCE)
                if len(atr_values) > 0:
                    current_atr = atr_values.iloc[-1]
                    # ATR-based SL distance
                    atr_sl_distance = current_atr * config.ATR_SL_MULTIPLIER
                else:
                    atr_sl_distance = current_price * 0.005  # 0.5% fallback
            else:
                atr_sl_distance = current_price * 0.005

            # Dynamic risk-reward based on confluence
            if confluence_score >= self.strong_confluence_threshold:
                rr_ratio = 3.0  # Higher RR for strong signals
            elif confluence_score >= self.min_confluence_for_trade:
                rr_ratio = 2.0  # Standard RR
            else:
                rr_ratio = 1.5  # Conservative RR

            # Calculate SL and TP
            if signal == 'BUY':
                stop_loss = current_price - atr_sl_distance
                take_profit = current_price + (atr_sl_distance * rr_ratio)
            elif signal == 'SELL':
                stop_loss = current_price + atr_sl_distance
                take_profit = current_price - (atr_sl_distance * rr_ratio)
            else:
                stop_loss = take_profit = current_price

            # Dynamic lot size based on confluence
            base_lot = 0.01
            confluence_multiplier = 0.5 + (confluence_score * 0.5)  # 0.5 to 1.0
            dynamic_lot = base_lot * confluence_multiplier

            # Ensure lot size limits
            dynamic_lot = max(config.MIN_LOT_SIZE, min(config.MAX_LOT_SIZE, dynamic_lot))

            return {
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'lot_size': dynamic_lot,
                'rr_ratio': rr_ratio,
                'atr_value': current_atr if 'current_atr' in locals() else 0,
                'sl_distance': atr_sl_distance
            }

        except Exception as e:
            logger.error("Error calculating position parameters: %s", e)
            return {
                'entry_price': 1800,
                'stop_loss': 1790,
                'take_profit': 1820,
                'lot_size': 0.01,
                'rr_ratio': 2.0,
                'atr_value': 0,
                'sl_distance': 10
            }

    def calculate_confidence(self, analysis: Dict, news_data: Dict, volatility_score: float) -> float:
        """
        Calculate confidence score using weighted factors, with optional news impact.

        Args:
            analysis: Timeframe analysis results
            news_data: News data dict with availability status
            volatility_score: Volatility score (0-1)

        Returns:
            float: Confidence score (0-1)
        """
        # If analysis is empty or all signal_strength are zero, return 0
        if not analysis or all(tf_data.get('signal_strength', 0) == 0 for tf_data in analysis.values()):
            logger.warning("⚠️ Confidence calculation: No valid signals present. Returning confidence=0.0.")
            return 0.0
        try:
            # Factor 1: Signal strength (average across timeframes)
            signal_strengths = [tf_data['signal_strength'] for tf_data in analysis.values()]
            avg_signal_strength = np.mean(signal_strengths) / 100.0  # Normalize to 0-1

            # Factor 2: EMA alignment (percentage of bullish/bearish alignment)
            ema_trends = [tf_data['ema_trend'] for tf_data in analysis.values()]
            bullish_count = sum(1 for trend in ema_trends if trend == 'bullish')
            bearish_count = sum(1 for trend in ema_trends if trend == 'bearish')
            alignment_score = max(bullish_count, bearish_count) / len(ema_trends)

            # Factor 3: RSI condition (average RSI deviation from neutral)
            rsi_values = [tf_data['rsi'] for tf_data in analysis.values()]
            avg_rsi = np.mean(rsi_values)
            rsi_condition = 1.0 - abs(avg_rsi - 50.0) / 50.0  # Higher when RSI is more extreme

            # Factor 4: Volatility (inverse relationship - lower volatility = higher confidence)
            volatility_factor = 1.0 - volatility_score

            # Factor 5: News sentiment (optional - only apply if news is available)
            news_available = news_data.get('available', False)
            if news_available:
                news_sentiment = news_data.get('sentiment', 'neutral')
                news_factor = 1.0
                if news_sentiment == 'bullish':
                    news_factor = 1.1
                elif news_sentiment == 'bearish':
                    news_factor = 0.9
                logger.debug(f"News factor applied: sentiment={news_sentiment}, factor={news_factor:.3f}")
            else:
                # No news available - skip news factor and redistribute weight
                news_factor = 1.0  # Neutral multiplier
                logger.debug(f"News factor skipped: {news_data.get('reason', 'No news available')}")

            # Factor 6: Trend strength (based on alignment consistency)
            trend_strength = alignment_score

            # Calculate weighted confidence score
            # If news is not available, the news_sentiment weight is effectively neutral (1.0)
            confidence = (
                WEIGHTS["signal_strength"] * avg_signal_strength +
                WEIGHTS["ema_alignment"] * alignment_score +
                WEIGHTS["rsi_condition"] * rsi_condition +
                WEIGHTS["volatility"] * volatility_factor +
                WEIGHTS["news_sentiment"] * news_factor +
                WEIGHTS["trend_strength"] * trend_strength
            )

            # Ensure score is within 0-1 range
            confidence = max(0.0, min(1.0, confidence))

            logger.debug(f"Confidence calculation: signal={avg_signal_strength:.3f}, ema={alignment_score:.3f}, rsi={rsi_condition:.3f}, vol={volatility_factor:.3f}, news={news_factor:.3f} ({'applied' if news_available else 'skipped'}), trend={trend_strength:.3f} -> confidence={confidence:.3f}")

            return confidence

        except Exception as e:
            logger.error(f"Error calculating confidence score: {e}")
            return 0.0

    def should_execute_trade(self, analysis_result: Dict, open_positions: List, trade_direction: str = None) -> Tuple[bool, str]:
        """
        Determine if trade should be executed based on confidence, cooldown, and position checks.

        Args:
            analysis_result: Analysis result from analyze_market
            open_positions: List of current open positions
            trade_direction: Override trade direction (BUY/SELL) for confidence-based trading

        Returns:
            tuple: (should_execute, reason)
        """
        global last_trade_time

        try:
            confidence = analysis_result.get('confidence_score', 0.0)
            action = analysis_result.get('action', 'WAIT')

            # Check confidence threshold (0.7 = 70%)
            if confidence < 0.7:
                return False, f"Confidence {confidence:.3f} below threshold 0.7"

            # Use trade_direction if provided (for confidence-based trading), otherwise use action
            effective_direction = trade_direction if trade_direction else action
            
            # Check if we have a valid direction
            if effective_direction not in ['BUY', 'SELL']:
                return False, f"No valid trade direction: action={action}, trade_direction={trade_direction}"

            # Check cooldown period
            current_time = time.time()
            time_since_last_trade = current_time - last_trade_time

            # Adaptive cooldown based on confidence and volatility
            volatility = analysis_result.get('volatility_score', 0.5)
            news_sentiment = analysis_result.get('news_sentiment', 'neutral')

            # Base cooldown
            if confidence >= 0.85:
                cooldown = 180  # 3 min for high confidence
            elif confidence >= 0.65:
                cooldown = 300  # 5 min for medium confidence
            else:
                cooldown = 600  # 10 min for low confidence

            # Adjust for volatility
            if volatility > 0.7:  # High volatility
                cooldown *= 1.5
            elif volatility < 0.3:  # Low volatility
                cooldown *= 0.8

            # Adjust for news impact
            if news_sentiment in ['bullish', 'bearish']:
                cooldown *= 1.2  # Increase cooldown during news events

            if time_since_last_trade < cooldown:
                remaining_time = int(cooldown - time_since_last_trade)
                return False, f"Cooldown active: {remaining_time}s remaining"

            # Check for conflicting positions
            existing_directions = []
            for pos in open_positions:
                if hasattr(pos, 'type'):
                    if pos.type == 0:  # BUY position
                        existing_directions.append('BUY')
                    elif pos.type == 1:  # SELL position
                        existing_directions.append('SELL')

            if action in existing_directions:
                return False, f"Position already exists in {action} direction"

            # All checks passed
            return True, f"Trade approved: confidence={confidence:.3f}, action={action}"

        except Exception as e:
            logger.error(f"Error in should_execute_trade: {e}")
            return False, f"Error: {str(e)}"

    def _create_empty_analysis(self) -> Dict:
        """
        Create empty analysis result when data fetching fails.

        Returns:
            dict: Empty analysis structure
        """
        logger.info("No valid signal - skipping this round.")
        return {
            'timestamp': datetime.now(),
            'symbol': 'XAUUSDm',
            'confluence_score': 0.0,
            'overall_signal': 'HOLD',
            'confidence': 0.0,
            'confidence_score': 0.0,
            'timeframe_signals': {},
            'news_sentiment': 'neutral',
            'volatility_score': 0.5,
            'position_params': {
                'entry_price': 1800,
                'stop_loss': 1790,
                'take_profit': 1820,
                'lot_size': 0.01,
                'rr_ratio': 2.0,
                'atr_value': 0,
                'sl_distance': 10
            },
            'should_trade': False,
            'analysis_details': {
                'raw_confluence': 0,
                'normalized_confluence': 0,
                'news_multiplier': 1.0,
                'volatility_multiplier': 0.5,
                'total_weight': 0
            }
        }

    def get_confluence_matrix(self, analysis_result: Dict) -> pd.DataFrame:
        """
        Generate confluence matrix for dashboard visualization.

        Args:
            analysis_result: Analysis result dictionary

        Returns:
            pd.DataFrame: Confluence matrix
        """
        matrix_data = []
        for tf_name, tf_signal in analysis_result['timeframe_signals'].items():
            matrix_data.append({
                'Timeframe': tf_name,
                'Signal': tf_signal['signal'],
                'Strength': tf_signal['strength'],
                'Score': tf_signal['score'],
                'Weight': tf_signal['weight']
            })

        return pd.DataFrame(matrix_data)

    def check_ema_trend(self, df: pd.DataFrame) -> str:
        """
        Check EMA trend direction.

        Args:
            df: DataFrame with OHLC data

        Returns:
            str: "bullish", "bearish", or "neutral"
        """
        try:
            # Prepare data with EMAs
            df_with_ema = self.strategies['M1'].prepare_data(df)  # Use any strategy for EMA calc

            if len(df_with_ema) < 2:
                return "neutral"

            # Check if fast EMA > slow EMA for bullish trend
            fast_ema_col = f'EMA_{config.EMA_FAST}'
            slow_ema_col = f'EMA_{config.EMA_SLOW}'

            if fast_ema_col in df_with_ema.columns and slow_ema_col in df_with_ema.columns:
                fast_ema = df_with_ema[fast_ema_col].iloc[-1]
                slow_ema = df_with_ema[slow_ema_col].iloc[-1]

                if fast_ema > slow_ema:
                    return "bullish"
                elif fast_ema < slow_ema:
                    return "bearish"

        except Exception as e:
            logger.error("Error checking EMA trend: %s", e)

        return "neutral"

    def get_rsi(self, df: pd.DataFrame) -> float:
        """
        Get current RSI value.

        Args:
            df: DataFrame with OHLC data

        Returns:
            float: RSI value (0-100)
        """
        try:
            # Prepare data with RSI
            df_with_rsi = self.strategies['M1'].prepare_data(df)

            rsi_col = f'RSI_{config.RSI_PERIOD}'
            if rsi_col in df_with_rsi.columns and len(df_with_rsi) > 0:
                return df_with_rsi[rsi_col].iloc[-1]

        except Exception as e:
            logger.error("Error getting RSI: %s", e)

        return 50.0  # Neutral RSI

    def get_atr(self, df: pd.DataFrame) -> float:
        """
        Get current ATR value.

        Args:
            df: DataFrame with OHLC data

        Returns:
            float: ATR value
        """
        try:
            atr_values = atr(df, period=config.ATR_PERIOD)
            if len(atr_values) > 0:
                return atr_values.iloc[-1]

        except Exception as e:
            logger.error("Error getting ATR: %s", e)

        return 0.0

    def get_signal_strength(self, df: pd.DataFrame) -> float:
        """
        Get signal strength from strategy analysis.

        Args:
            df: DataFrame with OHLC data

        Returns:
            float: Signal strength (0-100)
        """
        try:
            # Use M1 strategy for signal strength
            df_with_indicators = self.strategies['M1'].prepare_data(df)
            signal_info = self.strategies['M1'].generate_signal(df_with_indicators)
            return signal_info['strength']

        except Exception as e:
            logger.error("Error getting signal strength: %s", e)

        return 0.0

    def multi_tf_alignment(self, analysis: Dict) -> str:
        """
        Determine multi-timeframe alignment as per Phase 9 logic.

        Args:
            analysis: Dictionary with timeframe analysis results

        Returns:
            str: "strong_buy", "strong_sell", or "neutral"
        """
        bullish = sum(1 for tf in analysis if analysis[tf]["ema_trend"] == "bullish")
        bearish = sum(1 for tf in analysis if analysis[tf]["ema_trend"] == "bearish")

        if bullish >= 4 and bearish <= 1:
            return "strong_buy"
        elif bearish >= 4 and bullish <= 1:
            return "strong_sell"
        else:
            return "neutral"

    def _calculate_position_parameters_phase9(self, alignment_result: str,
                                           timeframe_data: Dict,
                                           action: str,
                                           confidence_score: float) -> Dict:
        """
        Calculate position parameters for Phase 9 with dynamic RR based on confidence.

        Args:
            alignment_result: Alignment result ("strong_buy", "strong_sell", "neutral")
            timeframe_data: Timeframe data dictionary
            action: Trading action ("BUY", "SELL", "WAIT")
            confidence_score: Confidence score (0-1) for dynamic RR calculation
        """
        try:
            # Get current price from 1m data
            if '1m' in timeframe_data:
                current_price = timeframe_data['1m']['close'].iloc[-1]
            else:
                current_price = 1800  # Fallback

            # Calculate dynamic stop loss based on ATR from 1h
            if '1h' in timeframe_data:
                df_h1 = timeframe_data['1h']
                atr_values = atr(df_h1, period=config.ATR_PERIOD_CONFLUENCE)
                if len(atr_values) > 0:
                    current_atr = atr_values.iloc[-1]
                    # ATR-based SL distance
                    atr_sl_distance = current_atr * config.ATR_SL_MULTIPLIER
                else:
                    atr_sl_distance = current_price * 0.005  # 0.5% fallback
            else:
                atr_sl_distance = current_price * 0.005

            # Dynamic risk-reward based on confidence score
            if confidence_score >= 0.85:
                rr_ratio = 3.0  # High confidence - aggressive RR
            elif confidence_score >= 0.75:
                rr_ratio = 2.5  # Good confidence
            elif confidence_score >= 0.70:
                rr_ratio = 2.0  # Standard RR for minimum threshold
            else:
                rr_ratio = 1.5  # Conservative RR

            # Calculate SL and TP based on action
            if action == 'BUY':
                stop_loss = current_price - atr_sl_distance
                take_profit = current_price + (atr_sl_distance * rr_ratio)
            elif action == 'SELL':
                stop_loss = current_price + atr_sl_distance
                take_profit = current_price - (atr_sl_distance * rr_ratio)
            else:
                # WAIT action - no position
                stop_loss = take_profit = current_price

            # Dynamic lot size based on confidence score
            base_lot = 0.01
            confidence_multiplier = 0.5 + (confidence_score * 0.5)  # 0.5 to 1.0 range
            dynamic_lot = base_lot * confidence_multiplier

            # Ensure lot size within configured limits
            dynamic_lot = max(config.MIN_LOT_SIZE, min(config.MAX_LOT_SIZE, dynamic_lot))

            return {
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'lot_size': dynamic_lot,
                'rr_ratio': rr_ratio,
                'atr_value': current_atr if 'current_atr' in locals() else 0,
                'sl_distance': atr_sl_distance
            }

        except Exception as e:
            logger.error("Error calculating position parameters for Phase 9: %s", e)
            return {
                'entry_price': 1800,
                'stop_loss': 1790,
                'take_profit': 1820,
                'lot_size': 0.01,
                'rr_ratio': 2.0,
                'atr_value': 0,
                'sl_distance': 10
            }

    def _map_alignment_to_score(self, alignment_result: str) -> float:
        """
        Map alignment result to numerical score for decision engine.

        Args:
            alignment_result: "strong_buy", "strong_sell", or "neutral"

        Returns:
            float: Score between -1 and 1
        """
        if alignment_result == "strong_buy":
            return 1.0
        elif alignment_result == "strong_sell":
            return -1.0
        else:
            return 0.0

    def _calculate_ema_alignment_score(self, analysis: Dict) -> float:
        """
        Calculate EMA alignment score across timeframes.

        Args:
            analysis: Timeframe analysis results

        Returns:
            float: Score between -1 and 1
        """
        try:
            bullish_count = sum(1 for tf_data in analysis.values() if tf_data['ema_trend'] == 'bullish')
            bearish_count = sum(1 for tf_data in analysis.values() if tf_data['ema_trend'] == 'bearish')
            total = len(analysis)

            if total == 0:
                return 0.0

            # Return net alignment (bullish - bearish) normalized
            net_alignment = (bullish_count - bearish_count) / total
            return max(-1.0, min(1.0, net_alignment))

        except Exception as e:
            logger.error(f"Error calculating EMA alignment score: {e}")
            return 0.0

    def _calculate_rsi_score(self, analysis: Dict) -> float:
        """
        Calculate RSI score across timeframes.

        Args:
            analysis: Timeframe analysis results

        Returns:
            float: Score between -1 and 1 (negative = oversold, positive = overbought)
        """
        try:
            rsi_values = [tf_data['rsi'] for tf_data in analysis.values() if tf_data['rsi'] > 0]
            if not rsi_values:
                return 0.0

            avg_rsi = np.mean(rsi_values)
            # Convert RSI to score: 50 = 0, 70+ = 1, 30- = -1
            if avg_rsi >= 70:
                return 1.0
            elif avg_rsi <= 30:
                return -1.0
            else:
                # Linear interpolation between 30-70
                return (avg_rsi - 50) / 20.0

        except Exception as e:
            logger.error(f"Error calculating RSI score: {e}")
            return 0.0

    def _calculate_momentum_score(self, timeframe_data: Dict) -> float:
        """
        Calculate momentum score based on recent price movement.

        Args:
            timeframe_data: Dictionary of timeframe DataFrames

        Returns:
            float: Score between -1 and 1
        """
        try:
            # Use M5 timeframe for momentum
            if 'M5' in timeframe_data:
                df = timeframe_data['M5']
                if len(df) >= 10:
                    recent_prices = df['close'].tail(10)
                    # Calculate momentum as percentage change over last 10 bars
                    momentum = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]
                    # Normalize to -1 to 1 (assuming max 2% change = full score)
                    return max(-1.0, min(1.0, momentum / 0.02))
            return 0.0

        except Exception as e:
            logger.error(f"Error calculating momentum score: {e}")
            return 0.0

    def _calculate_price_action_score(self, timeframe_data: Dict) -> float:
        """
        Calculate price action score based on recent highs/lows.

        Args:
            timeframe_data: Dictionary of timeframe DataFrames

        Returns:
            float: Score between -1 and 1
        """
        try:
            # Use M15 timeframe for price action
            if 'M15' in timeframe_data:
                df = timeframe_data['M15']
                if len(df) >= 20:
                    recent_data = df.tail(20)
                    current_price = recent_data['close'].iloc[-1]
                    recent_high = recent_data['high'].max()
                    recent_low = recent_data['low'].min()

                    # Calculate position within recent range
                    if recent_high != recent_low:
                        position = (current_price - recent_low) / (recent_high - recent_low)
                        # Convert to score: 0.5 = 0, 1.0 = 1, 0.0 = -1
                        return max(-1.0, min(1.0, (position - 0.5) * 2))
            return 0.0

        except Exception as e:
            logger.error(f"Error calculating price action score: {e}")
            return 0.0

    def _map_news_to_score(self, news_sentiment: str) -> float:
        """
        Map news sentiment to numerical score.

        Args:
            news_sentiment: 'bullish', 'bearish', or 'neutral'

        Returns:
            float: Score between -1 and 1
        """
        if news_sentiment == 'bullish':
            return 1.0
        elif news_sentiment == 'bearish':
            return -1.0
        else:
            return 0.0

    def _calculate_recent_performance_score(self) -> float:
        """
        Calculate recent performance score (placeholder for now).

        Returns:
            float: Score between -1 and 1
        """
        # This would integrate with trade logger to get recent performance
        # For now, return neutral
        return 0.0


# Convenience function for external use
def analyze_market_confluence(symbol: str = "XAUUSDm") -> Dict:
    """
    Convenience function to analyze market confluence.

    Args:
        symbol: Trading symbol

    Returns:
        dict: Analysis results
    """
    analyzer = MultiTimeframeAnalyzer()
    return analyzer.analyze_market(symbol)


if __name__ == "__main__":
    # Test the analyzer
    print("Testing MultiTimeframeAnalyzer...")

    analyzer = MultiTimeframeAnalyzer()
    result = analyzer.analyze_market("XAUUSDm")

    print("\nAnalysis Result:")
    print(f"Confluence Score: {result['confluence_score']:.3f}")
    print(f"Overall Signal: {result['overall_signal']}")
    print(f"Should Trade: {result['should_trade']}")
    print(f"News Sentiment: {result['news_sentiment']}")

    print("\nTimeframe Signals:")
    for tf, signal in result['timeframe_signals'].items():
        print(f"  {tf}: {signal['signal']} ({signal['strength']:.1f}%)")

    print("\nPosition Parameters:")
    params = result['position_params']
    print(f"  Entry: ${params['entry_price']:.2f}")
    print(f"  SL: ${params['stop_loss']:.2f}")
    print(f"  TP: ${params['take_profit']:.2f}")
    print(f"  Lot Size: {params['lot_size']}")
    print(f"  RR Ratio: {params['rr_ratio']:.1f}")

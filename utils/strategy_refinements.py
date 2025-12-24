"""
Advanced strategy refinements for improved signal quality.
Includes regime-specific indicator calibration, multi-timeframe confirmation,
and indicator smoothing to reduce noise and false signals.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
import logging

logger = logging.getLogger(__name__)


class RegimeCalibrator:
    """
    Calibrates indicator parameters based on detected market regime.
    Different market conditions (trending/ranging/volatile) require different thresholds.
    """
    
    def __init__(self):
        # Regime-specific RSI thresholds
        self.rsi_thresholds = {
            'trending_bullish': {'oversold': 35, 'overbought': 80, 'neutral_low': 45, 'neutral_high': 70},
            'trending_bearish': {'oversold': 20, 'overbought': 65, 'neutral_low': 30, 'neutral_high': 55},
            'ranging': {'oversold': 25, 'overbought': 75, 'neutral_low': 40, 'neutral_high': 60},
            'volatile': {'oversold': 20, 'overbought': 80, 'neutral_low': 35, 'neutral_high': 65},
            'default': {'oversold': 30, 'overbought': 70, 'neutral_low': 40, 'neutral_high': 60}
        }
        
        # Regime-specific EMA separation thresholds (in pips for XAUUSD)
        self.ema_separation_thresholds = {
            'trending_bullish': 8.0,   # Strong trend: require good separation
            'trending_bearish': 8.0,
            'ranging': 3.0,            # Range: accept smaller separation
            'volatile': 5.0,           # Volatile: moderate separation
            'default': 5.0
        }
        
        # Regime-specific Bollinger Band squeeze thresholds
        self.bb_squeeze_thresholds = {
            'trending_bullish': 0.0015,   # Wider bands in trend
            'trending_bearish': 0.0015,
            'ranging': 0.0008,            # Tighter bands in range
            'volatile': 0.0025,           # Very wide bands in volatility
            'default': 0.0012
        }
    
    def detect_regime(self, data: pd.DataFrame, adx_threshold_trending: float = 25,
                     adx_threshold_ranging: float = 20, volatility_threshold: float = 0.02) -> str:
        """
        Detect current market regime from OHLC data.
        
        Args:
            data: DataFrame with OHLC and indicators
            adx_threshold_trending: ADX value above which market is trending
            adx_threshold_ranging: ADX value below which market is ranging
            volatility_threshold: Volatility above which market is volatile
        
        Returns:
            str: Regime name (trending_bullish, trending_bearish, ranging, volatile)
        """
        if len(data) < 20:
            return 'default'
        
        # Get ADX if available
        adx = data.get('adx', pd.Series([0] * len(data))).iloc[-1]
        
        # Get volatility (ATR/Price)
        if 'atr' in data.columns and 'close' in data.columns:
            volatility = data['atr'].iloc[-1] / data['close'].iloc[-1]
        else:
            volatility = data['close'].pct_change().std() if 'close' in data.columns else 0.01
        
        # Get trend direction
        if 'ema_fast' in data.columns and 'ema_slow' in data.columns:
            ema_fast = data['ema_fast'].iloc[-1]
            ema_slow = data['ema_slow'].iloc[-1]
            trend_bullish = ema_fast > ema_slow
        else:
            # Fallback: use simple price trend
            trend_bullish = data['close'].iloc[-1] > data['close'].iloc[-10] if len(data) >= 10 else True
        
        # Classify regime
        if volatility > volatility_threshold:
            return 'volatile'
        elif adx > adx_threshold_trending:
            return 'trending_bullish' if trend_bullish else 'trending_bearish'
        elif adx < adx_threshold_ranging:
            return 'ranging'
        else:
            return 'default'
    
    def get_rsi_thresholds(self, regime: str) -> Dict[str, float]:
        """Get RSI thresholds for the given regime."""
        return self.rsi_thresholds.get(regime, self.rsi_thresholds['default'])
    
    def get_ema_separation_threshold(self, regime: str) -> float:
        """Get EMA separation threshold (in pips) for the given regime."""
        return self.ema_separation_thresholds.get(regime, self.ema_separation_thresholds['default'])
    
    def get_bb_squeeze_threshold(self, regime: str) -> float:
        """Get Bollinger Band squeeze threshold for the given regime."""
        return self.bb_squeeze_thresholds.get(regime, self.bb_squeeze_thresholds['default'])
    
    def calibrate_indicator_params(self, regime: str, base_params: Dict) -> Dict:
        """
        Adjust indicator parameters based on regime.
        
        Args:
            regime: Current market regime
            base_params: Base indicator parameters (ema_fast, ema_slow, rsi_period, etc.)
        
        Returns:
            Dict with calibrated parameters
        """
        calibrated = base_params.copy()
        
        # Adjust EMA periods
        if regime == 'trending_bullish' or regime == 'trending_bearish':
            # Use longer EMAs in trends for stability
            calibrated['ema_fast'] = max(12, base_params.get('ema_fast', 12))
            calibrated['ema_slow'] = max(26, base_params.get('ema_slow', 26))
        elif regime == 'ranging':
            # Use shorter EMAs in ranges for responsiveness
            calibrated['ema_fast'] = min(8, base_params.get('ema_fast', 12))
            calibrated['ema_slow'] = min(18, base_params.get('ema_slow', 26))
        elif regime == 'volatile':
            # Use moderate EMAs in volatility
            calibrated['ema_fast'] = 10
            calibrated['ema_slow'] = 21
        
        # Adjust RSI period
        if regime == 'trending_bullish' or regime == 'trending_bearish':
            calibrated['rsi_period'] = 21  # Longer in trends
        elif regime == 'ranging':
            calibrated['rsi_period'] = 9   # Shorter in ranges
        else:
            calibrated['rsi_period'] = 14  # Default
        
        # Adjust Bollinger Band parameters
        if regime == 'volatile':
            calibrated['bb_period'] = 15
            calibrated['bb_std'] = 1.8  # Tighter bands
        elif regime.startswith('trending'):
            calibrated['bb_period'] = 25
            calibrated['bb_std'] = 2.2  # Wider bands
        else:
            calibrated['bb_period'] = 20
            calibrated['bb_std'] = 2.0  # Default
        
        return calibrated


class MultiTimeframeConfirmation:
    """
    Validates signals across multiple timeframes to reduce false signals.
    Ensures lower timeframe signals align with higher timeframe trends.
    """
    
    def __init__(self, mt5_connection=None):
        """
        Initialize multi-timeframe confirmation.
        
        Args:
            mt5_connection: MetaTrader5 connection for fetching additional timeframes
        """
        self.mt5 = mt5_connection
        
        # Timeframe hierarchy (base → higher)
        # For M5 trading: M5 → M15 → H1
        self.timeframe_map = {
            'M5': ['M15', 'H1'],
            'M15': ['H1', 'H4'],
            'H1': ['H4', 'D1']
        }
    
    def fetch_higher_timeframe_data(self, symbol: str, base_timeframe: str,
                                   num_candles: int = 100) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for higher timeframes.
        
        Args:
            symbol: Trading symbol
            base_timeframe: Base timeframe (e.g., 'M5')
            num_candles: Number of candles to fetch
        
        Returns:
            Dict mapping timeframe names to DataFrames
        """
        if not self.mt5:
            logger.warning("No MT5 connection; multi-timeframe confirmation unavailable")
            return {}
        
        higher_timeframes = self.timeframe_map.get(base_timeframe, [])
        data = {}
        
        for tf in higher_timeframes:
            try:
                # Convert timeframe string to MT5 constant
                import MetaTrader5 as mt5
                tf_constant = getattr(mt5, f'TIMEFRAME_{tf}', None)
                
                if tf_constant:
                    rates = mt5.copy_rates_from_pos(symbol, tf_constant, 0, num_candles)
                    if rates is not None and len(rates) > 0:
                        df = pd.DataFrame(rates)
                        df['time'] = pd.to_datetime(df['time'], unit='s')
                        data[tf] = df
                        logger.debug(f"Fetched {len(df)} candles for {tf}")
            except Exception as e:
                logger.warning(f"Failed to fetch {tf} data: {e}")
        
        return data
    
    def get_trend_direction(self, data: pd.DataFrame, ema_fast_period: int = 12,
                           ema_slow_period: int = 26) -> Optional[str]:
        """
        Determine trend direction from data.
        
        Args:
            data: OHLC DataFrame
            ema_fast_period: Fast EMA period
            ema_slow_period: Slow EMA period
        
        Returns:
            'bullish', 'bearish', or None if unclear
        """
        if len(data) < max(ema_fast_period, ema_slow_period):
            return None
        
        # Calculate EMAs if not present
        if 'ema_fast' not in data.columns:
            data['ema_fast'] = data['close'].ewm(span=ema_fast_period, adjust=False).mean()
        if 'ema_slow' not in data.columns:
            data['ema_slow'] = data['close'].ewm(span=ema_slow_period, adjust=False).mean()
        
        ema_fast = data['ema_fast'].iloc[-1]
        ema_slow = data['ema_slow'].iloc[-1]
        
        # Require clear separation (at least 0.1%)
        separation_pct = abs(ema_fast - ema_slow) / ema_slow
        
        if separation_pct < 0.001:  # Too close, unclear trend
            return None
        
        return 'bullish' if ema_fast > ema_slow else 'bearish'
    
    def confirm_signal(self, base_signal: str, base_data: pd.DataFrame,
                      higher_tf_data: Dict[str, pd.DataFrame],
                      require_all: bool = False) -> Tuple[bool, List[str]]:
        """
        Confirm base timeframe signal against higher timeframes.
        
        Args:
            base_signal: Base signal ('BUY', 'SELL', 'HOLD')
            base_data: Base timeframe OHLC data
            higher_tf_data: Dict of higher timeframe data
            require_all: If True, require all higher TFs to confirm; if False, require majority
        
        Returns:
            Tuple: (is_confirmed, list_of_reasons)
        """
        if base_signal == 'HOLD':
            return True, ["No signal to confirm"]
        
        if not higher_tf_data:
            logger.debug("No higher timeframe data; skipping MTF confirmation")
            return True, ["MTF data unavailable"]
        
        expected_direction = 'bullish' if base_signal == 'BUY' else 'bearish'
        confirmations = []
        conflicts = []
        
        for tf_name, tf_data in higher_tf_data.items():
            trend = self.get_trend_direction(tf_data)
            
            if trend == expected_direction:
                confirmations.append(tf_name)
            elif trend is not None:  # Clear opposite trend
                conflicts.append(tf_name)
        
        total_checked = len(confirmations) + len(conflicts)
        
        if total_checked == 0:
            return True, ["Higher timeframe trends unclear"]
        
        # Determine confirmation
        if require_all:
            is_confirmed = len(conflicts) == 0 and len(confirmations) > 0
        else:
            # Majority rule: at least 50% confirmation, no strong conflicts
            is_confirmed = (len(confirmations) >= total_checked / 2) and (len(conflicts) <= 1)
        
        reasons = []
        if confirmations:
            reasons.append(f"Confirmed by {', '.join(confirmations)}")
        if conflicts:
            reasons.append(f"Conflicts with {', '.join(conflicts)}")
        
        return is_confirmed, reasons


class IndicatorSmoother:
    """
    Applies smoothing techniques to reduce indicator noise and false signals.
    """
    
    @staticmethod
    def smooth_ema(data: pd.DataFrame, column: str = 'ema_fast',
                   smooth_period: int = 3) -> pd.Series:
        """
        Apply additional smoothing to EMA.
        
        Args:
            data: DataFrame with EMA column
            column: Name of EMA column to smooth
            smooth_period: Smoothing window
        
        Returns:
            Smoothed series
        """
        if column not in data.columns:
            return data.get(column, pd.Series(dtype=float))
        
        return data[column].rolling(window=smooth_period, min_periods=1).mean()
    
    @staticmethod
    def smooth_rsi(data: pd.DataFrame, column: str = 'rsi',
                  smooth_period: int = 3) -> pd.Series:
        """
        Apply smoothing to RSI to reduce whipsaws.
        
        Args:
            data: DataFrame with RSI column
            column: Name of RSI column
            smooth_period: Smoothing window
        
        Returns:
            Smoothed RSI
        """
        if column not in data.columns:
            return data.get(column, pd.Series(dtype=float))
        
        return data[column].rolling(window=smooth_period, min_periods=1).mean()
    
    @staticmethod
    def remove_conflicting_signals(technical_score: float, pattern_signal: int,
                                  news_signal: int, threshold: float = 0.5) -> Tuple[bool, str]:
        """
        Detect and remove conflicting signals between components.
        
        Args:
            technical_score: Technical indicator score (-100 to 100)
            pattern_signal: Pattern signal (-1, 0, 1)
            news_signal: News sentiment signal (-1, 0, 1)
            threshold: Threshold for considering signals conflicting
        
        Returns:
            Tuple: (has_conflict, conflict_description)
        """
        conflicts = []
        
        # Normalize technical score to -1, 0, 1
        tech_direction = 1 if technical_score > 10 else (-1 if technical_score < -10 else 0)
        
        # Check technical vs pattern conflict
        if tech_direction != 0 and pattern_signal != 0 and tech_direction != pattern_signal:
            conflicts.append("Technical indicators conflict with chart patterns")
        
        # Check technical vs news conflict
        if tech_direction != 0 and news_signal != 0 and tech_direction != news_signal:
            conflicts.append("Technical indicators conflict with news sentiment")
        
        # Check pattern vs news conflict
        if pattern_signal != 0 and news_signal != 0 and pattern_signal != news_signal:
            conflicts.append("Chart patterns conflict with news sentiment")
        
        has_conflict = len(conflicts) > 0
        conflict_desc = "; ".join(conflicts) if conflicts else "No conflicts"
        
        return has_conflict, conflict_desc
    
    @staticmethod
    def apply_signal_persistence_filter(signal_history: List[str],
                                       current_signal: str,
                                       min_persistence: int = 2) -> Tuple[bool, str]:
        """
        Require signal to persist for N candles before accepting.
        
        Args:
            signal_history: List of recent signals (e.g., ['BUY', 'BUY', 'HOLD'])
            current_signal: Current signal
            min_persistence: Minimum consecutive occurrences required
        
        Returns:
            Tuple: (is_persistent, reason)
        """
        if current_signal == 'HOLD':
            return True, "HOLD signal always accepted"
        
        if len(signal_history) < min_persistence - 1:
            return False, f"Need {min_persistence} consecutive signals (have {len(signal_history) + 1})"
        
        # Check if last N-1 signals match current
        recent = signal_history[-(min_persistence - 1):]
        persistent = all(s == current_signal for s in recent)
        
        if persistent:
            return True, f"Signal persisted for {min_persistence} candles"
        else:
            return False, f"Signal not persistent (recent: {recent})"


def create_strategy_refinement_suite(mt5_connection=None) -> Dict:
    """
    Factory function to create all strategy refinement components.
    
    Args:
        mt5_connection: Optional MT5 connection for multi-timeframe
    
    Returns:
        Dict with 'calibrator', 'mtf_confirmation', 'smoother' components
    """
    return {
        'calibrator': RegimeCalibrator(),
        'mtf_confirmation': MultiTimeframeConfirmation(mt5_connection),
        'smoother': IndicatorSmoother()
    }

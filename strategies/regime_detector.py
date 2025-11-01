# regime_detector.py - Market Regime Detection for Strategy Selection

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import indicators
from indicators.ema import calculate_ema
from indicators.rsi_clean_final import calculate_rsi
from indicators.bollinger import calculate_bollinger_bands

class RegimeDetector:
    """
    Detects market regime to select appropriate trading strategy.
    """

    def __init__(self, fast_ema=20, slow_ema=50, bb_period=20, atr_period=14):
        """
        Initialize regime detector parameters.

        Args:
            fast_ema (int): Fast EMA period
            slow_ema (int): Slow EMA period
            bb_period (int): Bollinger Bands period
            atr_period (int): ATR period
        """
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.bb_period = bb_period
        self.atr_period = atr_period

    def prepare_data(self, data):
        """
        Prepare data with regime detection indicators.

        Args:
            data (pd.DataFrame): OHLC data

        Returns:
            pd.DataFrame: Data with regime indicators
        """
        df = data.copy()

        # EMAs for trend detection
        df[f'EMA_{self.fast_ema}'] = calculate_ema(df, self.fast_ema, 'close')
        df[f'EMA_{self.slow_ema}'] = calculate_ema(df, self.slow_ema, 'close')

        # RSI for momentum
        df['RSI_14'] = calculate_rsi(df, 14, 'close')

        # Bollinger Bands for volatility/consolidation
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df, self.bb_period, 2, 'close')
        df['BB_upper'] = bb_upper
        df['BB_middle'] = bb_middle
        df['BB_lower'] = bb_lower
        df['BB_width'] = (bb_upper - bb_lower) / bb_middle

        # ATR for volatility
        df['ATR'] = self._calculate_atr(df, self.atr_period)

        # Recent price action for breakout detection
        df['recent_high'] = df['high'].rolling(window=20).max()
        df['recent_low'] = df['low'].rolling(window=20).min()

        return df

    def _calculate_atr(self, df, period=14):
        """
        Calculate Average True Range.

        Args:
            df (pd.DataFrame): OHLC data
            period (int): ATR period

        Returns:
            pd.Series: ATR values
        """
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def detect_regime(self, data):
        """
        Detect current market regime.

        Args:
            data (pd.DataFrame): Data with regime indicators

        Returns:
            dict: Regime information with confidence scores
        """
        if len(data) < max(self.slow_ema, self.bb_period, self.atr_period):
            return {
                'regime': 'unknown',
                'confidence': 0.0,
                'components': {}
            }

        latest = data.iloc[-1]
        close = latest['close']

        # Trend strength (EMA separation)
        ema_fast = latest[f'EMA_{self.fast_ema}']
        ema_slow = latest[f'EMA_{self.slow_ema}']
        ema_diff_pct = abs((ema_fast - ema_slow) / ema_slow) * 100

        # Trend direction and strength
        trend_up = ema_fast > ema_slow
        trend_down = ema_fast < ema_slow
        trend_strength = min(ema_diff_pct / 2, 100)  # Scale to 0-100

        # Volatility assessment
        atr_val = latest['ATR']
        atr_relative = atr_val / close
        volatility_score = min(atr_relative * 1000, 100)  # Scale ATR% to 0-100

        # Consolidation detection (tight Bollinger Bands)
        bb_width = latest['BB_width']
        consolidation_score = max(0, (0.02 - bb_width) / 0.02 * 100)  # Lower width = higher consolidation

        # Breakout detection
        recent_high = latest['recent_high']
        recent_low = latest['recent_low']
        breakout_up = close > recent_high * 0.999  # Close to recent high
        breakout_down = close < recent_low * 1.001  # Close to recent low
        breakout_score = 100 if (breakout_up or breakout_down) else 0

        # RSI momentum
        rsi_val = latest['RSI_14']
        momentum_score = abs(50 - rsi_val) * 2  # Distance from neutral

        # Regime decision logic
        regimes = {
            'trend': {
                'score': trend_strength,
                'condition': trend_strength > 30
            },
            'breakout': {
                'score': (breakout_score + volatility_score) / 2,
                'condition': breakout_score > 50 and volatility_score > 40
            },
            'range': {
                'score': consolidation_score,
                'condition': consolidation_score > 60 and trend_strength < 20
            },
            'volatile': {
                'score': volatility_score,
                'condition': volatility_score > 70 and bb_width > 0.025
            }
        }

        # Select regime with highest score that meets condition
        best_regime = 'unknown'
        best_score = 0

        for regime, info in regimes.items():
            if info['condition'] and info['score'] > best_score:
                best_regime = regime
                best_score = info['score']

        # If no regime meets conditions, default to range (most conservative)
        if best_regime == 'unknown':
            best_regime = 'range'
            best_score = consolidation_score

        return {
            'regime': best_regime,
            'confidence': round(best_score, 2),
            'components': {
                'trend_strength': round(trend_strength, 2),
                'volatility_score': round(volatility_score, 2),
                'consolidation_score': round(consolidation_score, 2),
                'breakout_score': breakout_score,
                'momentum_score': round(momentum_score, 2),
                'ema_diff_pct': round(ema_diff_pct, 2),
                'bb_width': round(bb_width, 4),
                'atr_relative': round(atr_relative, 4)
            }
        }

    def get_strategy_mapping(self, regime):
        """
        Map regime to appropriate strategy.

        Args:
            regime (str): Detected regime

        Returns:
            str: Strategy name
        """
        mapping = {
            'trend': 'trend_trading',
            'breakout': 'breakout_retest',
            'range': 'swing_trading',
            'volatile': 'scalping',
            'unknown': 'basic'  # Fallback to basic strategy
        }

        return mapping.get(regime, 'basic')

    def should_switch_strategy(self, current_regime, new_regime, confidence_threshold=60):
        """
        Determine if strategy should switch based on regime change.

        Args:
            current_regime (str): Current regime
            new_regime (str): New detected regime
            confidence_threshold (float): Minimum confidence for switch

        Returns:
            dict: Switch decision
        """
        if current_regime == new_regime:
            return {
                'should_switch': False,
                'reason': 'same_regime'
            }

        # Allow switch if confidence is high enough
        regime_info = self.detect_regime(pd.DataFrame())  # Would need current data
        confidence = regime_info.get('confidence', 0)

        if confidence >= confidence_threshold:
            return {
                'should_switch': True,
                'reason': f'regime_change_{current_regime}_to_{new_regime}',
                'confidence': confidence
            }
        else:
            return {
                'should_switch': False,
                'reason': 'low_confidence',
                'confidence': confidence
            }


if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data with different regimes
    dates = pd.date_range('2023-01-01', periods=200, freq='D')

    # Mix of trending and ranging periods
    trend_period = np.cumsum(np.random.randn(100) * 2)
    range_period = np.random.randn(100) * 5
    prices = 1800 + np.concatenate([trend_period, range_period])

    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 2,
        'high': prices + abs(np.random.randn(200) * 3),
        'low': prices - abs(np.random.randn(200) * 3),
        'close': prices
    }, index=dates)

    # Create and test regime detector
    detector = RegimeDetector()

    # Prepare data
    prepared_data = detector.prepare_data(sample_data)
    print("📊 Data prepared with regime indicators:")
    print(prepared_data[['close', 'EMA_20', 'EMA_50', 'RSI_14', 'BB_width']].tail())

    # Detect regime
    regime_info = detector.detect_regime(prepared_data)
    print(f"\n📊 Detected regime: {regime_info['regime']} (confidence: {regime_info['confidence']}%)")
    print(f"Components: {regime_info['components']}")

    # Get strategy mapping
    strategy = detector.get_strategy_mapping(regime_info['regime'])
    print(f"Recommended strategy: {strategy}")

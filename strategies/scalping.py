# scalping.py - Scalping Strategy Implementation

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import unified signal generator
from signal_generator import UnifiedSignalGenerator

# Import indicators (for backward compatibility)
from indicators.ema import calculate_ema
from indicators.rsi_clean_final import calculate_rsi
from indicators.bollinger import calculate_bollinger_bands

# Removed long-term patterns - focusing on pure scalping only

class ScalpingStrategy:
    """
    Scalping Strategy - Take many small trades on micro price movements in high-volatility periods.
    """

    def __init__(self, ema_fast=9, ema_slow=21, rsi_period=7, bb_period=10, bb_std=1.5, tick_size=0.01, pattern_min_strength=65):
        """
        Initialize strategy parameters.

        Args:
            ema_fast (int): Fast EMA period for microtrend
            ema_slow (int): Slow EMA period for trend filter
            rsi_period (int): Short RSI period for quick signals
            bb_period (int): Bollinger Bands period
            bb_std (float): Bollinger Bands standard deviation
            tick_size (float): Minimum price movement (tick size)
            pattern_min_strength (int): Minimum strength for pattern signals
        """
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.tick_size = tick_size
        self.pattern_min_strength = pattern_min_strength

        # Initialize the centralized signal generator
        self.signal_generator = UnifiedSignalGenerator()

    def prepare_data(self, data):
        """
        Prepare data with scalping indicators.

        Args:
            data (pd.DataFrame): OHLC data

        Returns:
            pd.DataFrame: Data with scalping indicators added
        """
        df = data.copy()

        # Fast EMAs for microtrend detection
        df[f'EMA_{self.ema_fast}'] = calculate_ema(df, self.ema_fast, 'close')
        df[f'EMA_{self.ema_slow}'] = calculate_ema(df, self.ema_slow, 'close')

        # Short RSI for quick momentum signals
        df[f'RSI_{self.rsi_period}'] = calculate_rsi(df, self.rsi_period, 'close')

        # Tight Bollinger Bands for volatility
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df, self.bb_period, self.bb_std, 'close')
        df['BB_upper'] = bb_upper
        df['BB_middle'] = bb_middle
        df['BB_lower'] = bb_lower
        df['BB_width'] = (bb_upper - bb_lower) / bb_middle

        # Micro volatility (recent range)
        df['micro_range'] = df['high'].rolling(window=5).max() - df['low'].rolling(window=5).min()
        df['micro_volatility'] = df['micro_range'] / df['close']

        # Tick volume (if available) or price changes as proxy
        if 'volume' in df.columns:
            df['tick_volume'] = df['volume']
        else:
            # Use price change magnitude as volume proxy
            df['tick_volume'] = abs(df['close'] - df['open']) / self.tick_size

        # Average tick volume
        df['avg_tick_volume'] = df['tick_volume'].rolling(window=10).mean()
        df['volume_ratio'] = df['tick_volume'] / df['avg_tick_volume']

        return df

    def _detect_microtrend(self, data):
        """
        Detect short-term microtrend direction.

        Args:
            data (pd.DataFrame): Data with EMAs

        Returns:
            str: 'up', 'down', or 'sideways'
        """
        latest = data.iloc[-1]
        ema_fast = latest[f'EMA_{self.ema_fast}']
        ema_slow = latest[f'EMA_{self.ema_slow}']

        if ema_fast > ema_slow * 1.0001:  # Small threshold for noise
            return 'up'
        elif ema_fast < ema_slow * 0.9999:
            return 'down'
        else:
            return 'sideways'

    def _check_scalping_conditions(self, data):
        """
        Check all scalping entry conditions.

        Args:
            data (pd.DataFrame): Data with indicators

        Returns:
            dict: Condition check results
        """
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else latest

        microtrend = self._detect_microtrend(data)
        rsi_val = latest[f'RSI_{self.rsi_period}']
        close = latest['close']
        bb_upper = latest['BB_upper']
        bb_lower = latest['BB_lower']
        volume_ratio = latest['volume_ratio']
        micro_volatility = latest['micro_volatility']

        # Microtrend alignment
        trend_up = microtrend == 'up'
        trend_down = microtrend == 'down'

        # RSI timing
        rsi_buy_signal = rsi_val > 55 and rsi_val < 75  # Not overbought
        rsi_sell_signal = rsi_val < 45 and rsi_val > 25  # Not oversold

        # Price position within BB
        price_above_mid = close > latest['BB_middle']
        price_below_mid = close < latest['BB_middle']

        # Volume confirmation
        volume_confirmed = volume_ratio > 1.1  # Above average

        # Volatility filter (prefer moderate volatility for scalping)
        volatility_ok = 0.001 < micro_volatility < 0.005  # 0.1% to 0.5% range

        # Small pullback detection
        pullback_up = trend_up and close < prev['close'] and abs(close - prev['close']) / prev['close'] < 0.002
        pullback_down = trend_down and close > prev['close'] and abs(close - prev['close']) / prev['close'] < 0.002

        return {
            'trend_up': trend_up,
            'trend_down': trend_down,
            'rsi_buy_signal': rsi_buy_signal,
            'rsi_sell_signal': rsi_sell_signal,
            'price_above_mid': price_above_mid,
            'price_below_mid': price_below_mid,
            'volume_confirmed': volume_confirmed,
            'volatility_ok': volatility_ok,
            'pullback_up': pullback_up,
            'pullback_down': pullback_down,
            'microtrend': microtrend,
            'rsi_val': rsi_val,
            'volume_ratio': volume_ratio,
            'micro_volatility': micro_volatility
        }

    def generate_signal(self, data):
        """
        Generate scalping signal based on micro movements and patterns.

        Args:
            data (pd.DataFrame): OHLC data with indicators

        Returns:
            dict: Signal information with BUY, SELL, or HOLD
        """
        if len(data) < max(self.ema_slow, self.bb_period, 10):
            return {
                'signal': 'HOLD',
                'strength': 0,
                'reasons': ['Not enough data for scalping analysis'],
                'components': {
                    'microtrend': 'unknown',
                    'rsi_condition': 'neutral',
                    'volatility_ok': False
                }
            }

        # Check all conditions - Pure scalping only, no long-term patterns
        conditions = self._check_scalping_conditions(data)

        latest = data.iloc[-1]
        close = latest['close']

        reasons = []
        signal = "HOLD"
        strength = 0

        # Pure scalping conditions - no pattern analysis
        # BUY signal conditions (all must be met for strict scalping)
        buy_conditions = [
            conditions['trend_up'],
            conditions['rsi_buy_signal'],
            conditions['price_above_mid'],
            conditions['volume_confirmed'],
            conditions['volatility_ok'],
            conditions['pullback_up']
        ]

        if all(buy_conditions):
            signal = "BUY"
            strength = 65  # Moderate confidence for scalping
            reasons.append("All bullish scalping conditions met")
            reasons.append("Microtrend up with RSI timing")
            reasons.append("Volume and volatility confirm setup")

        # SELL signal conditions
        sell_conditions = [
            conditions['trend_down'],
            conditions['rsi_sell_signal'],
            conditions['price_below_mid'],
            conditions['volume_confirmed'],
            conditions['volatility_ok'],
            conditions['pullback_down']
        ]

        if all(sell_conditions):
            signal = "SELL"
            strength = 65
            reasons.append("All bearish scalping conditions met")
            reasons.append("Microtrend down with RSI timing")
            reasons.append("Volume and volatility confirm setup")

        # Adjust strength based on condition strength
        if signal != "HOLD":
            # Bonus for stronger volume or volatility
            if conditions['volume_ratio'] > 1.3:
                strength += 10
                reasons.append("Strong volume confirmation")
            if conditions['micro_volatility'] > 0.003:
                strength += 5
                reasons.append("Good volatility for scalping")

            strength = min(strength, 85)  # Cap at 85 for scalping

        # Tight stop loss and take profit for scalping
        if signal in ["BUY", "SELL"]:
            if 'sl' not in locals():
                micro_range = latest['micro_range']
                bb_width = latest['BB_width'] * close

                # Very tight stops (5-15 ticks/pips)
                stop_distance = max(self.tick_size * 7, micro_range * 0.3, bb_width * 0.2)

                # Small targets (10-30 ticks/pips)
                target_distance = max(self.tick_size * 15, micro_range * 0.6, bb_width * 0.4)

                if signal == "BUY":
                    sl = close - stop_distance
                    tp = close + target_distance
                else:
                    sl = close + stop_distance
                    tp = close - target_distance

                size_factor = 0.5  # Smaller than other strategies

        else:
            sl = None
            tp = None
            size_factor = 1.0

        return {
            'signal': signal,
            'strength': round(strength, 2),
            'entry_price': float(close),
            'stop_loss': float(sl) if sl is not None else None,
            'take_profit': float(tp) if tp is not None else None,
            'size_factor': float(size_factor),
            'reasons': reasons,
            'components': {
                'microtrend': conditions['microtrend'],
                'rsi_condition': 'bullish' if conditions['rsi_buy_signal'] else 'bearish' if conditions['rsi_sell_signal'] else 'neutral',
                'volatility_ok': conditions['volatility_ok'],
                'volume_confirmed': conditions['volume_confirmed'],
                'pullback_detected': conditions['pullback_up'] or conditions['pullback_down'],
                'pattern_detected': None  # Pure scalping - no patterns
            }
        }

    def detect_scalp_exhaustion(self, data):
        """
        Detect scalping exhaustion (too many consecutive small moves).

        Args:
            data (pd.DataFrame): OHLC data with indicators

        Returns:
            dict: Exhaustion detection results
        """
        if len(data) < 10:
            return {'exhausted': False, 'reason': None}

        # Check for RSI extreme levels
        latest_rsi = data[f'RSI_{self.rsi_period}'].iloc[-1]
        rsi_extreme = latest_rsi > 80 or latest_rsi < 20

        # Check for widening BB (increasing volatility may signal end of scalp setup)
        recent_bb_width = data['BB_width'].tail(5).mean()
        prev_bb_width = data['BB_width'].shift(5).tail(5).mean()
        bb_expanding = recent_bb_width > prev_bb_width * 1.2

        # Check for weakening microtrend
        recent_ema_diff = (data[f'EMA_{self.ema_fast}'] - data[f'EMA_{self.ema_slow}']).tail(3)
        trend_weakening = recent_ema_diff.is_monotonic_decreasing and recent_ema_diff.iloc[-1] < 0

        exhausted = rsi_extreme or bb_expanding or trend_weakening

        reason = None
        if rsi_extreme:
            reason = "RSI reached extreme levels"
        elif bb_expanding:
            reason = "Bollinger Bands expanding - volatility increasing"
        elif trend_weakening:
            reason = "Microtrend weakening"

        return {
            'exhausted': exhausted,
            'reason': reason,
            'rsi_extreme': rsi_extreme,
            'bb_expanding': bb_expanding,
            'trend_weakening': trend_weakening
        }

    def should_exit_scalp(self, position_type, current_signal, time_held, data):
        """
        Determine if scalping position should be closed.

        Args:
            position_type (str): 'BUY' or 'SELL'
            current_signal (str): Current signal
            time_held (int): Seconds held
            data (pd.DataFrame): Current data

        Returns:
            dict: Exit decision
        """
        # Scalping exits are quick - target hit, stop hit, or time limit
        time_limit = 300  # 5 minutes max hold time

        if time_held > time_limit:
            return {'should_exit': True, 'reason': 'time_limit_exceeded'}

        # Opposite signal
        if position_type == 'BUY' and current_signal == 'SELL':
            return {'should_exit': True, 'reason': 'opposite_signal'}
        elif position_type == 'SELL' and current_signal == 'BUY':
            return {'should_exit': True, 'reason': 'opposite_signal'}

        # Exhaustion detected
        exhaustion = self.detect_scalp_exhaustion(data)
        if exhaustion['exhausted']:
            return {'should_exit': True, 'reason': f"exhaustion_{exhaustion['reason'].replace(' ', '_')}"}

        return {'should_exit': False, 'reason': None}


if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data with micro movements
    dates = pd.date_range('2023-01-01', periods=200, freq='H')  # Hourly data for scalping

    # Create microtrend with small oscillations
    base_trend = np.cumsum(np.random.randn(200) * 0.5)
    micro_noise = np.sin(np.arange(200) * 0.5) * 2
    prices = 1800 + base_trend + micro_noise

    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 0.5,
        'high': prices + abs(np.random.randn(200) * 1),
        'low': prices - abs(np.random.randn(200) * 1),
        'close': prices,
        'volume': np.random.randint(100, 1000, 200)
    }, index=dates)

    # Create and test strategy
    strategy = ScalpingStrategy()

    # Prepare data
    prepared_data = strategy.prepare_data(sample_data)
    print("📊 Data prepared with scalping indicators:")
    print(prepared_data[['close', 'EMA_9', 'EMA_21', 'RSI_7', 'BB_upper', 'BB_lower']].tail())

    # Generate signal
    signal = strategy.generate_signal(prepared_data)
    print(f"\n📈 Current scalping signal: {signal['signal']} (strength: {signal['strength']})")
    print(f"Reasons: {signal['reasons']}")
    print(f"Entry: {signal.get('entry_price')}, SL: {signal.get('stop_loss')}, TP: {signal.get('take_profit')}")

    # Check for exhaustion
    exhaustion = strategy.detect_scalp_exhaustion(prepared_data)
    print(f"\n📊 Scalping exhaustion detected: {exhaustion}")

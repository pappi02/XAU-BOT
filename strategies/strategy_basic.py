# strategy_basic.py - Basic trading strategy combining multiple indicators

import logging

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import indicators
from indicators.ema import add_ema_signals
from indicators.rsi import add_rsi_signals
from indicators.bollinger import add_bollinger_signals

logger = logging.getLogger(__name__)


class BasicTradingStrategy:
    """
    Basic trading strategy combining EMA, RSI, and Bollinger Bands.
    """

    def __init__(self, ema_fast=12, ema_slow=26, rsi_period=14, bb_period=20, bb_std=2):
        """
        Initialize strategy parameters.

        Args:
            ema_fast (int): Fast EMA period
            ema_slow (int): Slow EMA period
            rsi_period (int): RSI period
            bb_period (int): Bollinger Bands period
            bb_std (float): Bollinger Bands standard deviation
        """
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.bb_std = bb_std

    def prepare_data(self, data):
        """
        Prepare data with all indicators.

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

        return df

    def generate_signal(self, data):
        """
        Generate trading signal based on combined indicators with enhanced scoring logic.

        Args:
            data (pd.DataFrame): OHLC data with indicators

        Returns:
            dict: Signal information with BUY, SELL, or HOLD
        """
        if len(data) < max(self.ema_slow, self.rsi_period, self.bb_period):
            # Provide default components to avoid KeyError in callers (UI/dashboard)
            return {
                'signal': 'HOLD',
                'strength': 0,
                'reasons': ['Not enough data'],
                'components': {
                    'ema_signal': 0,
                    'rsi_condition': 'neutral',
                    'bb_position': 'NEUTRAL'
                }
            }

        # Get current values
        latest = data.iloc[-1]

        # Get actual indicator values
        ema_fast_val = latest.get(f'EMA_{self.ema_fast}', latest['close'])
        ema_slow_val = latest.get(f'EMA_{self.ema_slow}', latest['close'])
        rsi_val = latest.get(f'RSI_{self.rsi_period}', 50)
        close = latest['close']
        upper = latest.get(f'BB_upper_{self.bb_period}', close)
        lower = latest.get(f'BB_lower_{self.bb_period}', close)

        # Compute signals for weighted scoring (standardized thresholds)
        ema_signal = 1 if ema_fast_val > ema_slow_val else (-1 if ema_fast_val < ema_slow_val else 0)
        rsi_condition = "bullish" if rsi_val < 30 else ("bearish" if rsi_val > 70 else "neutral")
        # Stricter BB condition with trend alignment: BUY when price <= lower band AND EMA bullish, SELL when price >= upper band AND EMA bearish
        bb_signal = 1 if ema_signal == 1 and close <= lower else (-1 if ema_signal == -1 and close >= upper else 0)

        reasons = []
        if ema_signal == 1:
            reasons.append("Short-term trend bullish")
        elif ema_signal == -1:
            reasons.append("Short-term trend bearish")

        if rsi_condition == "bullish":
            reasons.append("RSI oversold")
        elif rsi_condition == "bearish":
            reasons.append("RSI overbought")

        if bb_signal == 1:
            reasons.append("Price below lower Bollinger Band")
        elif bb_signal == -1:
            reasons.append("Price above upper Bollinger Band")

        # --- Phase 9.3 (audit H-08): continuous, separable scoring ---
        #
        # The block that lived here produced exactly FOUR distinct strength
        # values, {0, 20, 40, 100}, and six of the seven separately-tuned
        # thresholds partitioned that set identically -- all of them meaning
        # `strength == 100`. Worse, the three "independent" indicators were not:
        # bb_signal was DEFINED as a conjunction with ema_signal, both bonus
        # terms were EMA-gated, and enumerating RSI 0-100 against every
        # reachable Bollinger state shows neither could change the signal.
        # The decision was exactly the sign of (EMA_fast - EMA_slow).
        #
        # See strategies/signal_strength.py and docs/STRATEGY-HYPOTHESIS.md.
        from strategies.signal_strength import compute_strength

        atr_val = latest.get('ATR', latest.get(f'ATR_{getattr(self, "atr_period", 14)}'))
        if atr_val is None or atr_val != atr_val:
            # Fall back to a bar-range proxy rather than scoring against an
            # unknown scale. compute_strength returns 0 for the EMA term when
            # ATR is unusable, so this keeps the term meaningful.
            atr_val = abs(float(latest.get('high', close)) - float(latest.get('low', close))) or None

        atr_history = None
        if 'ATR' in data.columns:
            atr_history = [v for v in data['ATR'].tail(300).tolist()
                           if v is not None and v == v]

        scored = compute_strength(
            ema_fast=ema_fast_val, ema_slow=ema_slow_val, rsi=rsi_val,
            close=close, bb_upper=upper, bb_lower=lower, atr=atr_val,
            atr_history=atr_history,
        )
        signal = scored['signal']
        strength = scored['strength']

        # Components for logging/dashboard display (updated for consistency
        # with the continuous score above).
        ema_signal = 1 if ema_fast_val > ema_slow_val else (-1 if ema_fast_val < ema_slow_val else 0)
        rsi_condition = 'overbought' if rsi_val > 70 else ('oversold' if rsi_val < 30 else 'neutral')
        bb_position = 'above_upper' if close >= upper else ('below_lower' if close <= lower else 'within_bands')

        logger.info(
            "🧩 Signal — EMA_fast=%.2f EMA_slow=%.2f RSI=%.2f score=%.4f -> %s %.1f%%",
            ema_fast_val, ema_slow_val, rsi_val, scored['score'], signal, strength,
        )

        return {
            'signal': signal,
            'strength': strength,
            'reasons': reasons,
            'components': {
                'ema_signal': ema_signal,
                'rsi_condition': rsi_condition,
                'bb_position': bb_position
            },
        }

    def detect_trend_reversal(self, data):
        """
        Detect potential trend reversals based on indicator changes.

        Args:
            data (pd.DataFrame): OHLC data with indicators

        Returns:
            dict: Reversal detection results
        """
        no_reversal = {'reversal_detected': False, 'direction': None, 'strength': 0}
        if len(data) < 10:  # Need some history
            return no_reversal

        # Check for EMA crossover reversals. EMA_signal is the trend STATE
        # (+1/-1/0), so a change between the last two bars is a crossover.
        if 'EMA_signal' in data.columns:
            recent_ema_signals = data['EMA_signal'].tail(2).values
            current_signal = recent_ema_signals[-1]
            prev_signal = recent_ema_signals[-2]

            if current_signal != prev_signal and current_signal != 0:
                # Signal changed - potential reversal
                reversal_strength = abs(current_signal - prev_signal) * 50  # Scale to 0-100
                return {
                    'reversal_detected': True,
                    'direction': 'bullish_to_bearish' if current_signal == -1 else 'bearish_to_bullish',
                    'strength': min(reversal_strength, 100)
                }

        # Check for RSI extreme reversals. Phase 12: the column was hardcoded
        # as RSI_14 and raised KeyError for any other rsi_period.
        rsi_column = f'RSI_{self.rsi_period}'
        if rsi_column in data.columns:
            current_rsi = data[rsi_column].iloc[-1]
            prev_rsi = data[rsi_column].iloc[-2]

            # RSI moving away from extreme levels (NaN compares False)
            if (prev_rsi < 30 and current_rsi > 35) or (prev_rsi > 70 and current_rsi < 65):
                return {
                    'reversal_detected': True,
                    'direction': 'from_oversold' if prev_rsi < 30 else 'from_overbought',
                    'strength': 70
                }

        return no_reversal

    # should_close_position() deleted in Phase 12 (dead code; see docs/SECURITY-DECISIONS.md).

    # backtest() deleted in Phase 12 (dead code; see docs/SECURITY-DECISIONS.md).

def create_strategy(strategy_type='basic', **kwargs):
    """
    Factory function to create trading strategies.

    Args:
        strategy_type (str): Type of strategy to create
        **kwargs: Strategy parameters

    Returns:
        Strategy instance
    """
    if strategy_type == 'basic':
        return BasicTradingStrategy(**kwargs)
    else:
        raise ValueError(f"Unknown strategy type: {strategy_type}")

if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=200, freq='D')
    prices = 1800 + np.cumsum(np.random.randn(200) * 2) + np.sin(np.arange(200) * 0.1) * 20
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 2,
        'high': prices + abs(np.random.randn(200) * 5),
        'low': prices - abs(np.random.randn(200) * 5),
        'close': prices
    }, index=dates)

    # Create and test strategy
    strategy = BasicTradingStrategy()

    # Prepare data
    prepared_data = strategy.prepare_data(sample_data)
    print("📊 Data prepared with indicators:")
    print(prepared_data[['close', 'EMA_12', 'EMA_26', 'RSI_14', 'BB_upper_20', 'BB_lower_20']].tail())

    # Generate signal
    signal = strategy.generate_signal(prepared_data)
    print(f"\n📈 Current signal: {signal['signal']} (strength: {signal['strength']})")
    print(f"Reasons: {signal['reasons']}")

    # Backtesting lives in backtest/engine.py (Phase 9.2). The method that used
    # to be called here executed zero trades on any input (audit C-07).
    print("\nFor a costed backtest see scripts/run_gate_c.py.")

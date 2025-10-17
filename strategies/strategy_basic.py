# strategy_basic.py - Basic trading strategy combining multiple indicators

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Import indicators
from indicators.ema import add_ema_signals, get_ema_trend
from indicators.rsi import add_rsi_signals, get_rsi_condition
from indicators.bollinger import add_bollinger_signals, get_bollinger_position

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
        Generate trading signal based on combined indicators.

        Args:
            data (pd.DataFrame): OHLC data with indicators

        Returns:
            dict: Signal information with BUY, SELL, or HOLD
        """
        if len(data) < max(self.ema_slow, self.rsi_period, self.bb_period):
            # Provide default components to avoid KeyError in callers (UI/dashboard)
            # Enhanced fallback: try to generate signal even with limited data
            try:
                # Attempt to prepare data and generate signal with available data
                prepared_data = self.prepare_data(data)
                if len(prepared_data) >= 2:  # Minimum for basic analysis
                    return self._generate_signal_with_available_data(prepared_data)
            except Exception as e:
                logger.warning(f"Could not generate signal with limited data: {e}")

            # Ultimate fallback
            return {
                'signal': 'HOLD',
                'strength': 0,
                'reasons': ['Not enough data for reliable signal generation'],
                'components': {
                    'ema_signal': 0,
                    'rsi_condition': 'neutral',
                    'bb_position': 'NEUTRAL'
                }
            }

        # Get current values
        latest = data.iloc[-1]

        # Initialize signal components
        buy_signals = 0
        sell_signals = 0
        reasons = []

        # EMA Analysis
        ema_signal = latest.get('EMA_signal', 0)
        ema_crossover = latest.get('EMA_crossover', 0)

        if ema_signal == 1:
            buy_signals += 1
            reasons.append("EMA bullish")
        elif ema_signal == -1:
            sell_signals += 1
            reasons.append("EMA bearish")

        if ema_crossover == 1:
            buy_signals += 1  # Additional weight for crossover
            reasons.append("EMA bullish crossover")
        elif ema_crossover == -1:
            sell_signals += 1
            reasons.append("EMA bearish crossover")

        # RSI Analysis
        rsi_signal = latest.get('RSI_signal', 0)
        rsi_condition = get_rsi_condition(data, self.rsi_period)

        if rsi_signal == 1:  # Oversold
            buy_signals += 1
            reasons.append("RSI oversold")
        elif rsi_signal == -1:  # Overbought
            sell_signals += 1
            reasons.append("RSI overbought")

        # Bollinger Bands Analysis
        bb_signal = latest.get('BB_signal', 0)
        bb_position = get_bollinger_position(data, self.bb_period, self.bb_std)

        if bb_signal == 1:  # Price touched lower band
            buy_signals += 1
            reasons.append("Price at lower Bollinger Band")
        elif bb_signal == -1:  # Price touched upper band
            sell_signals += 1
            reasons.append("Price at upper Bollinger Band")

        # Maximum possible signals (3 indicators)
        max_signals = 3

        # Determine overall signal
        total_buy = buy_signals
        total_sell = sell_signals

        if total_buy > total_sell:
            signal = 'BUY'
            strength = (total_buy / max_signals) * 100  # Strength as percentage
        elif total_sell > total_buy:
            signal = 'SELL'
            strength = (total_sell / max_signals) * 100
        else:
            signal = 'HOLD'
            strength = 0

        return {
            'signal': signal,
            'strength': strength,
            'reasons': reasons,
            'components': {
                'ema_signal': ema_signal,
                'rsi_condition': rsi_condition,
                'bb_position': bb_position
            }
        }

    def _generate_signal_with_available_data(self, data):
        """
        Generate signal with limited data when full indicator periods are not available.
        Uses simplified logic with available indicators.

        Args:
            data (pd.DataFrame): Data with some indicators available

        Returns:
            dict: Signal information
        """
        try:
            latest = data.iloc[-1]
            buy_signals = 0
            sell_signals = 0
            reasons = []

            # Check available indicators
            if 'EMA_signal' in latest.index:
                ema_signal = latest.get('EMA_signal', 0)
                if ema_signal == 1:
                    buy_signals += 1
                    reasons.append("EMA bullish (limited data)")
                elif ema_signal == -1:
                    sell_signals += 1
                    reasons.append("EMA bearish (limited data)")

            if 'RSI_signal' in latest.index:
                rsi_signal = latest.get('RSI_signal', 0)
                if rsi_signal == 1:
                    buy_signals += 1
                    reasons.append("RSI oversold (limited data)")
                elif rsi_signal == -1:
                    sell_signals += 1
                    reasons.append("RSI overbought (limited data)")

            if 'BB_signal' in latest.index:
                bb_signal = latest.get('BB_signal', 0)
                if bb_signal == 1:
                    buy_signals += 1
                    reasons.append("Price at lower BB (limited data)")
                elif bb_signal == -1:
                    sell_signals += 1
                    reasons.append("Price at upper BB (limited data)")

            # Determine signal based on available indicators
            available_indicators = sum([1 for col in ['EMA_signal', 'RSI_signal', 'BB_signal'] if col in latest.index])
            max_signals = max(available_indicators, 1)  # Avoid division by zero

            if buy_signals > sell_signals:
                signal = 'BUY'
                strength = (buy_signals / max_signals) * 100
            elif sell_signals > buy_signals:
                signal = 'SELL'
                strength = (sell_signals / max_signals) * 100
            else:
                signal = 'HOLD'
                strength = 0

            return {
                'signal': signal,
                'strength': strength,
                'reasons': reasons,
                'components': {
                    'ema_signal': latest.get('EMA_signal', 0),
                    'rsi_condition': 'neutral',
                    'bb_position': 'NEUTRAL'
                }
            }

        except Exception as e:
            logger.warning(f"Failed to generate signal with limited data: {e}")
            return {
                'signal': 'HOLD',
                'strength': 0,
                'reasons': ['Error in limited data signal generation'],
                'components': {
                    'ema_signal': 0,
                    'rsi_condition': 'neutral',
                    'bb_position': 'NEUTRAL'
                }
            }

    def detect_trend_reversal(self, data):
        """
        Detect trend reversals using multiple indicators with enhanced logic.
        """
        import config

        if len(data) < 20:
            return {'reversal_detected': False, 'direction': None, 'strength': 0, 'reasons': []}

        # Get current signal components
        signal_info = self.generate_signal(data)
        current_signal = signal_info['signal']
        strength = signal_info['strength']

        # Enhanced reversal detection
        reversal_detected = False
        direction = None
        reversal_strength = 0
        reasons = []

        # 1. Strong opposite signal with high strength
        if current_signal == 'SELL' and strength >= config.TREND_REVERSAL_STRENGTH:
            # Check if previous trend was bullish (EMA fast > slow)
            recent_ema_fast = data['EMA_12'].tail(10).mean()
            recent_ema_slow = data['EMA_26'].tail(10).mean()
            if recent_ema_fast > recent_ema_slow:
                reversal_detected = True
                direction = 'bullish_to_bearish'
                reversal_strength = strength
                reasons.append(f"Strong SELL signal ({strength:.1f}%) vs bullish EMA trend")

        elif current_signal == 'BUY' and strength >= config.TREND_REVERSAL_STRENGTH:
            # Check if previous trend was bearish (EMA fast < slow)
            recent_ema_fast = data['EMA_12'].tail(10).mean()
            recent_ema_slow = data['EMA_26'].tail(10).mean()
            if recent_ema_fast < recent_ema_slow:
                reversal_detected = True
                direction = 'bearish_to_bullish'
                reversal_strength = strength
                reasons.append(f"Strong BUY signal ({strength:.1f}%) vs bearish EMA trend")

        # 2. RSI divergence signals with enhanced detection
        if not reversal_detected and len(data) >= config.SIGNAL_EXIT_WEAKENING_WINDOW:
            recent_prices = data['close'].tail(config.SIGNAL_EXIT_WEAKENING_WINDOW)
            recent_rsi = data['RSI_14'].tail(config.SIGNAL_EXIT_WEAKENING_WINDOW)

            # Check for bearish divergence (price higher, RSI lower)
            price_trend = recent_prices.iloc[-1] - recent_prices.iloc[0]
            rsi_trend = recent_rsi.iloc[-1] - recent_rsi.iloc[0]

            if (price_trend > 0 and rsi_trend < 0 and
                current_signal == 'SELL' and strength >= config.SIGNAL_EXIT_OPPOSITE_THRESHOLD):
                reversal_detected = True
                direction = 'bullish_to_bearish'
                reversal_strength = strength * 1.2  # Boost strength for divergence
                reasons.append(f"RSI bearish divergence with SELL signal ({strength:.1f}%)")

            # Check for bullish divergence (price lower, RSI higher)
            elif (price_trend < 0 and rsi_trend > 0 and
                  current_signal == 'BUY' and strength >= config.SIGNAL_EXIT_OPPOSITE_THRESHOLD):
                reversal_detected = True
                direction = 'bearish_to_bullish'
                reversal_strength = strength * 1.2  # Boost strength for divergence
                reasons.append(f"RSI bullish divergence with BUY signal ({strength:.1f}%)")

        # 3. Bollinger Band squeeze breakouts with momentum confirmation
        if not reversal_detected:
            current_bb_upper = data[f'BB_upper_{self.bb_period}'].iloc[-1]
            current_bb_lower = data[f'BB_lower_{self.bb_period}'].iloc[-1]
            current_bb_middle = data[f'BB_middle_{self.bb_period}'].iloc[-1]
            current_price = data['close'].iloc[-1]

            # Calculate BB squeeze (bandwidth)
            bb_bandwidth = (current_bb_upper - current_bb_lower) / current_bb_middle
            prev_bb_bandwidth = (data[f'BB_upper_{self.bb_period}'].iloc[-2] - data[f'BB_lower_{self.bb_period}'].iloc[-2]) / data[f'BB_middle_{self.bb_period}'].iloc[-2]

            # Price breaking upper BB with bearish signal and expanding bands
            if (current_price > current_bb_upper and
                current_signal == 'SELL' and strength >= config.SIGNAL_EXIT_OPPOSITE_THRESHOLD and
                bb_bandwidth > prev_bb_bandwidth):
                reversal_detected = True
                direction = 'bullish_to_bearish'
                reversal_strength = strength * 1.1  # Slight boost for breakout
                reasons.append(f"BB upper breakout with SELL signal and expanding bands ({strength:.1f}%)")

            # Price breaking lower BB with bullish signal and expanding bands
            elif (current_price < current_bb_lower and
                  current_signal == 'BUY' and strength >= config.SIGNAL_EXIT_OPPOSITE_THRESHOLD and
                  bb_bandwidth > prev_bb_bandwidth):
                reversal_detected = True
                direction = 'bearish_to_bullish'
                reversal_strength = strength * 1.1  # Slight boost for breakout
                reasons.append(f"BB lower breakout with BUY signal and expanding bands ({strength:.1f}%)")

        # 4. Enhanced signal weakening detection
        if not reversal_detected:
            weakening_info = self._check_signal_weakening(data)
            if weakening_info['weakening_detected']:
                reversal_detected = True
                direction = weakening_info['direction']
                reversal_strength = weakening_info['strength']
                reasons.extend(weakening_info['reasons'])

        return {
            'reversal_detected': reversal_detected,
            'direction': direction,
            'strength': reversal_strength,
            'reasons': reasons
        }

    def _check_signal_weakening(self, data):
        """
        Enhanced signal weakening detection using multiple timeframes and indicators.
        """
        import config

        if len(data) < config.SIGNAL_EXIT_WEAKENING_WINDOW + 5:
            return {'weakening_detected': False, 'direction': None, 'strength': 0, 'reasons': []}

        # Analyze signal strength over the weakening window
        signal_history = []
        for i in range(config.SIGNAL_EXIT_WEAKENING_WINDOW):
            idx = len(data) - config.SIGNAL_EXIT_WEAKENING_WINDOW + i
            if idx >= 0:
                window_data = data.iloc[idx:idx+1]
                prepared_data = self.prepare_data(window_data)
                signal_info = self.generate_signal(prepared_data)
                signal_history.append({
                    'signal': signal_info['signal'],
                    'strength': signal_info['strength'],
                    'timestamp': data.index[idx]
                })

        if len(signal_history) < 3:
            return {'weakening_detected': False, 'direction': None, 'strength': 0, 'reasons': []}

        # Check for consistent signal weakening
        current_signal = signal_history[-1]['signal']
        current_strength = signal_history[-1]['strength']

        # Calculate strength trend
        strengths = [s['strength'] for s in signal_history]
        strength_trend = strengths[-1] - strengths[0]  # Current minus oldest

        # Check if signal has weakened significantly
        if (current_strength < config.SIGNAL_EXIT_STRENGTH_DROP and
            strength_trend < -config.SIGNAL_EXIT_STRENGTH_DROP):

            # Determine direction based on current signal
            direction = None
            reasons = []

            if current_signal == 'SELL':
                direction = 'bullish_to_bearish'
                reasons.append(f"SELL signal weakened from {strengths[0]:.1f}% to {current_strength:.1f}%")
            elif current_signal == 'BUY':
                direction = 'bearish_to_bullish'
                reasons.append(f"BUY signal weakened from {strengths[0]:.1f}% to {current_strength:.1f}%")

            # Additional checks for confirmation
            if len(data) >= 10:
                # Check if EMA alignment is breaking
                recent_ema_fast = data['EMA_12'].tail(5).mean()
                recent_ema_slow = data['EMA_26'].tail(5).mean()

                if current_signal == 'SELL' and recent_ema_fast < recent_ema_slow:
                    reasons.append("EMA alignment confirms weakening SELL signal")
                elif current_signal == 'BUY' and recent_ema_fast > recent_ema_slow:
                    reasons.append("EMA alignment confirms weakening BUY signal")

            return {
                'weakening_detected': True,
                'direction': direction,
                'strength': current_strength,
                'reasons': reasons
            }

        return {'weakening_detected': False, 'direction': None, 'strength': 0, 'reasons': []}

    def should_close_position(self, position_type, current_signal, signal_strength, reversal_info, news_sentiment, position_age):
        """
        Legacy method - now delegates to TradeExecutor.should_close_trade() for comprehensive auto-close logic.

        This method is kept for backward compatibility but enhanced to use the new comprehensive logic.
        For new implementations, use TradeExecutor.should_close_trade() directly.

        Args:
            position_type (str): 'BUY' or 'SELL'
            current_signal (str): Current signal ('BUY', 'SELL', 'HOLD')
            signal_strength (float): Current signal strength (0-100)
            reversal_info (dict): Trend reversal detection results
            news_sentiment (str): Current news sentiment
            position_age (int): Position age in seconds

        Returns:
            dict: Close decision with reason
        """
        import config

        # Emergency close conditions
        if position_age > config.MAX_POSITION_AGE:
            return {'should_close': True, 'reason': 'max_age_exceeded'}

        # Signal reversal close
        if config.TREND_REVERSAL_CLOSE and reversal_info['reversal_detected']:
            if position_type == 'BUY' and reversal_info['direction'] == 'bullish_to_bearish':
                return {'should_close': True, 'reason': 'trend_reversal_bearish'}
            elif position_type == 'SELL' and reversal_info['direction'] == 'bearish_to_bullish':
                return {'should_close': True, 'reason': 'trend_reversal_bullish'}

        # Strong opposite signal
        if signal_strength >= config.SIGNAL_REVERSAL_THRESHOLD:
            if position_type == 'BUY' and current_signal == 'SELL':
                return {'should_close': True, 'reason': 'strong_sell_signal'}
            elif position_type == 'SELL' and current_signal == 'BUY':
                return {'should_close': True, 'reason': 'strong_buy_signal'}

        # News sentiment adverse to position
        if config.NEWS_SENTIMENT_CLOSE:
            if position_type == 'BUY' and news_sentiment == 'bearish':
                return {'should_close': True, 'reason': 'adverse_news_sentiment'}
            elif position_type == 'SELL' and news_sentiment == 'bullish':
                return {'should_close': True, 'reason': 'adverse_news_sentiment'}

        return {'should_close': False, 'reason': None}

    def backtest(self, data, initial_balance=10000, position_size_pct=0.1):
        """
        Backtest the strategy on historical data.

        Args:
            data (pd.DataFrame): Historical OHLC data
            initial_balance (float): Starting balance
            position_size_pct (float): Position size as percentage of balance

        Returns:
            dict: Backtest results
        """
        df = self.prepare_data(data)
        balance = initial_balance
        position = 0  # 0 = no position, 1 = long, -1 = short
        trades = []

        for i in range(len(df)):
            current_data = df.iloc[:i+1]
            signal_info = self.generate_signal(current_data)

            signal = signal_info['signal']
            current_price = df.iloc[i]['close']

            # Execute trades
            if signal == 'buy' and position == 0:
                # Enter long position
                position_size = balance * position_size_pct
                shares = position_size / current_price
                position = 1
                entry_price = current_price

                trades.append({
                    'type': 'buy',
                    'price': current_price,
                    'shares': shares,
                    'timestamp': df.index[i]
                })

            elif signal == 'sell' and position == 1:
                # Exit long position
                exit_value = position * shares * current_price
                pnl = exit_value - (shares * entry_price)
                balance += pnl
                position = 0

                trades.append({
                    'type': 'sell',
                    'price': current_price,
                    'shares': shares,
                    'pnl': pnl,
                    'timestamp': df.index[i]
                })

        # Calculate final balance if still in position
        if position == 1:
            final_value = shares * df.iloc[-1]['close']
            pnl = final_value - (shares * entry_price)
            balance += pnl

        total_return = (balance - initial_balance) / initial_balance * 100

        return {
            'initial_balance': initial_balance,
            'final_balance': balance,
            'total_return_pct': total_return,
            'total_trades': len(trades),
            'trades': trades
        }

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

    # Backtest
    backtest_results = strategy.backtest(sample_data)
    print("\n📊 Backtest Results:")
    print(f"Initial Balance: ${backtest_results['initial_balance']:.2f}")
    print(f"Final Balance: ${backtest_results['final_balance']:.2f}")
    print(f"Total Return: {backtest_results['total_return_pct']:.2f}%")
    print(f"Total Trades: {backtest_results['total_trades']}")

# strategy_basic.py - Basic trading strategy combining multiple indicators

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import indicators
from indicators.ema import add_ema_signals, get_ema_trend
from indicators.rsi import add_rsi_signals, get_rsi_condition
from indicators.bollinger import add_bollinger_signals, get_bollinger_position

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

    def detect_trend_reversal(self, data):
        """
        Detect potential trend reversals based on indicator changes.

        Args:
            data (pd.DataFrame): OHLC data with indicators

        Returns:
            dict: Reversal detection results
        """
        if len(data) < 10:  # Need some history
            return {'reversal_detected': False, 'direction': None, 'strength': 0}

        # Check for EMA crossover reversals
        recent_ema_signals = data['EMA_signal'].tail(5).values
        if len(recent_ema_signals) >= 3:
            # Check if signal changed from bullish to bearish or vice versa
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

        # Check for RSI extreme reversals
        rsi_values = data['RSI_14'].tail(10)
        if len(rsi_values) >= 5:
            current_rsi = rsi_values.iloc[-1]
            prev_rsi = rsi_values.iloc[-2]

            # RSI moving away from extreme levels
            if (prev_rsi < 30 and current_rsi > 35) or (prev_rsi > 70 and current_rsi < 65):
                return {
                    'reversal_detected': True,
                    'direction': 'from_oversold' if prev_rsi < 30 else 'from_overbought',
                    'strength': 70
                }

        return {'reversal_detected': False, 'direction': None, 'strength': 0}

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

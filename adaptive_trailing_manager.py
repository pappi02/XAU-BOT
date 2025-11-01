"""
Adaptive Trailing Manager - Smart Self-Learning Trailing System

This module implements advanced adaptive trailing stop functionality with:
- Machine learning from trade history
- Momentum detection using RSI/MACD
- Partial profit securing
- Momentum-aware trailing adjustments
"""

import time
import numpy as np
import pandas as pd
import talib
from typing import Dict, List, Optional, Tuple
from logger_config import setup_logger

logger = setup_logger()

class TradePerformanceAnalyzer:
    """
    Analyzes past profitable trades to learn optimal trailing behavior.
    Learns trail distance, ATR multipliers, and time factors from history.
    """

    def __init__(self, history: List[Dict] = None):
        """
        Initialize with trade history.

        Args:
            history: List of trade dictionaries with keys like 'profit', 'trail_distance', 'atr_at_entry', 'time_in_trade'
        """
        self.history = pd.DataFrame(history) if history else pd.DataFrame()

    def learn_trailing_behavior(self) -> Dict[str, float]:
        """
        Learn optimal trailing coefficients from profitable trades.

        Returns:
            Dict with learned coefficients:
            - trail_atr_mult: ATR multiplier for trail distance
            - trail_time_factor: Time factor for trailing frequency
        """
        if self.history.empty:
            logger.info("No trade history available, using default trailing coefficients")
            return {
                "trail_atr_mult": 1.0,
                "trail_time_factor": 1.0
            }

        # Filter profitable trades with required data
        profitable = self.history[
            (self.history.get('profit', 0) > 0) &
            (self.history.get('trail_distance', 0) > 0) &
            (self.history.get('atr_at_entry', 0) > 0) &
            (self.history.get('time_in_trade', 0) > 0)
        ]

        if profitable.empty:
            logger.info("No profitable trades with trailing data, using defaults")
            return {
                "trail_atr_mult": 1.0,
                "trail_time_factor": 1.0
            }

        # Calculate learned coefficients
        avg_atr_mult = np.mean(profitable['trail_distance'] / profitable['atr_at_entry'])
        avg_time_factor = np.mean(profitable['time_in_trade'] / profitable['profit'])

        learned = {
            "trail_atr_mult": np.clip(avg_atr_mult, 0.8, 2.0),
            "trail_time_factor": np.clip(avg_time_factor, 0.5, 1.5)
        }

        logger.info(f"Learned trailing coefficients: ATR_mult={learned['trail_atr_mult']:.2f}, Time_factor={learned['trail_time_factor']:.2f}")
        return learned

    def update_history(self, new_trades: List[Dict]):
        """Update trade history with new trades."""
        if new_trades:
            new_df = pd.DataFrame(new_trades)
            self.history = pd.concat([self.history, new_df], ignore_index=True)
            logger.info(f"Updated trade history with {len(new_trades)} new trades")


def get_momentum_state(closes: List[float]) -> str:
    """
    Detect momentum state using RSI and MACD slope.

    Args:
        closes: List of closing prices (recent candles)

    Returns:
        str: 'strong_up', 'strong_down', or 'weak'
    """
    if len(closes) < 14:
        return "weak"

    closes_array = np.array(closes)

    # Calculate RSI
    rsi = talib.RSI(closes_array, timeperiod=14)
    if len(rsi) < 4:
        return "weak"

    # Calculate MACD
    macd, macdsignal, _ = talib.MACD(closes_array, fastperiod=12, slowperiod=26, signalperiod=9)
    if len(macd) < 4:
        return "weak"

    # Calculate slopes (recent change)
    rsi_slope = (rsi[-1] - rsi[-4]) / 4
    macd_slope = (macd[-1] - macd[-4]) / 4

    # Determine momentum state
    if rsi_slope > 0.1 and macd_slope > 0:
        return "strong_up"
    elif rsi_slope < -0.1 and macd_slope < 0:
        return "strong_down"
    else:
        return "weak"


class AdaptiveTrailingManager:
    """
    Main manager for adaptive trailing functionality.
    Integrates learning, momentum detection, and smart trailing logic.
    """

    def __init__(self, config, mt5_module=None, trade_history: List[Dict] = None):
        """
        Initialize the adaptive trailing manager.

        Args:
            config: Configuration object
            mt5_module: MT5 trading module (optional for testing)
            trade_history: Initial trade history for learning
        """
        self.config = config
        self.mt5 = mt5_module
        self.performance_analyzer = TradePerformanceAnalyzer(trade_history)

        # Learned coefficients (updated periodically)
        self.learned_coeffs = {
            "trail_atr_mult": 1.0,
            "trail_time_factor": 1.0
        }

        # Track last trailing updates per position
        self.last_trail_updates = {}

        # Initialize learned coefficients
        self._update_learned_coefficients()

    def _update_learned_coefficients(self):
        """Update learned coefficients from trade history."""
        self.learned_coeffs = self.performance_analyzer.learn_trailing_behavior()

    def maybe_partial_close(self, position, current_price: float) -> bool:
        """
        Check if partial profit should be secured before full trailing.

        Args:
            position: MT5 position object
            current_price: Current market price

        Returns:
            bool: True if partial close was executed
        """
        if not hasattr(position, 'tp') or position.tp == 0:
            return False

        symbol_info = self.mt5.symbol_info(position.symbol)
        if not symbol_info:
            return False

        point = symbol_info.point
        profit_pips = abs(current_price - position.price_open) / point
        target_pips = abs(position.tp - position.price_open) / point

        if target_pips > 0 and profit_pips >= target_pips * 0.7:
            close_volume = position.volume * 0.3  # Close 30%
            if close_volume >= symbol_info.volume_min:
                result = self._close_partial_position(position, close_volume)
                if result:
                    logger.info(f"💰 Partial close executed on {position.symbol} at {profit_pips:.1f} pips.")
                    return True

        return False

    def _close_partial_position(self, position, volume: float) -> bool:
        """
        Execute partial position closure.

        Args:
            position: MT5 position object
            volume: Volume to close

        Returns:
            bool: Success of partial close
        """
        try:
            is_buy = position.type == self.mt5.POSITION_TYPE_BUY
            symbol = position.symbol

            order_type = self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY
            tick = self.mt5.symbol_info_tick(symbol)
            if not tick:
                return False

            price = float(tick.bid if is_buy else tick.ask)

            req = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(volume),
                "type": order_type,
                "position": position.ticket,
                "price": price,
                "deviation": self.config.ORDER_DEVIATION,
                "magic": self.config.MAGIC if hasattr(self.config, 'MAGIC') else 987654321,
                "comment": "Partial close - profit securing",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }

            result = self.mt5.order_send(req)
            if result.retcode == self.mt5.TRADE_RETCODE_DONE:
                logger.info(f"Successfully closed partial position {position.ticket}: {volume} lots")
                return True
            else:
                logger.error(f"Failed to close partial position {position.ticket}: {result}")
                return False

        except Exception as e:
            logger.error(f"Exception in partial close for {position.ticket}: {str(e)}")
            return False

    def smart_adaptive_trailing(self, position, candles: List[Dict]) -> bool:
        """
        Enhanced adaptive trailing with momentum awareness and learning.

        Args:
            position: MT5 position object
            candles: Recent candle data

        Returns:
            bool: True if trailing stop was updated
        """
        try:
            symbol = position.symbol
            now = time.time()

            # Check cooldown
            last_update = self.last_trail_updates.get(position.ticket, 0)
            if now - last_update < self.config.SMART_TRAILING_COOLDOWN:
                return False

            # Extract candle data
            closes = [c.get('close', c.get('c', 0)) for c in candles]
            highs = [c.get('high', c.get('h', 0)) for c in candles]
            lows = [c.get('low', c.get('l', 0)) for c in candles]

            if len(closes) < self.config.SMART_TRAILING_ATR_LOOKBACK:
                return False

            # Get momentum state
            momentum = get_momentum_state(closes)

            # Pause trailing on weak momentum
            if momentum == "weak":
                logger.info(f"🧠 Trailing paused due to weak momentum (temporary pullback detected) for {symbol}")
                return False

            # Calculate ATR for buffer
            atr = np.mean(np.array(highs[-self.config.SMART_TRAILING_ATR_LOOKBACK:]) -
                         np.array(lows[-self.config.SMART_TRAILING_ATR_LOOKBACK:]))

            # Get current price
            tick = self.mt5.symbol_info_tick(symbol)
            if not tick:
                return False

            current_price = tick.bid if position.type == self.mt5.POSITION_TYPE_BUY else tick.ask

            # Check minimum profit threshold
            entry_price = position.price_open
            profit_points = abs(current_price - entry_price) / self.mt5.symbol_info(symbol).point
            if profit_points < getattr(self.config, 'DYNAMIC_TRAILING_START_PROFIT', 5):
                return False

            # Check candle confirmation
            if position.type == self.mt5.POSITION_TYPE_BUY:
                favor_candles = sum(1 for i in range(-self.config.SMART_TRAILING_CANDLE_CONFIRMATION, 0)
                                   if i-1 >= 0 and closes[i] > closes[i-1] or i-1 < 0)
            else:
                favor_candles = sum(1 for i in range(-self.config.SMART_TRAILING_CANDLE_CONFIRMATION, 0)
                                   if i-1 >= 0 and closes[i] < closes[i-1] or i-1 < 0)

            if favor_candles < self.config.SMART_TRAILING_CANDLE_CONFIRMATION:
                return False

            # Calculate adaptive trailing distance
            dynamic_atr_mult = self.learned_coeffs["trail_atr_mult"]
            buffer_zone = atr * dynamic_atr_mult * self.config.SMART_TRAILING_BUFFER_MULTIPLIER

            # Calculate swing buffers
            recent_swing_low = np.min(lows[-self.config.SMART_TRAILING_SWING_LOOKBACK:])
            recent_swing_high = np.max(highs[-self.config.SMART_TRAILING_SWING_LOOKBACK:])

            # Determine new SL
            if position.type == self.mt5.POSITION_TYPE_BUY:
                # Use swing low with ATR buffer
                new_sl = max(position.sl or 0, recent_swing_low - buffer_zone)
                # Ensure SL doesn't exceed current price significantly
                max_sl = current_price - (atr * 0.3)
                new_sl = min(new_sl, max_sl)
            else:
                # Use swing high with ATR buffer
                new_sl = min(position.sl or float('inf'), recent_swing_high + buffer_zone)
                # Ensure SL doesn't go below current price significantly
                min_sl = current_price + (atr * 0.3)
                new_sl = max(new_sl, min_sl)

            # Only update if SL improves
            if position.type == self.mt5.POSITION_TYPE_BUY and new_sl > (position.sl or 0):
                success = self._modify_position_sl(position, new_sl)
                if success:
                    self.last_trail_updates[position.ticket] = now
                    logger.info(f"🧠 Adaptive Trailing updated BUY SL ({momentum}) → {new_sl:.5f}")
                    return True
            elif position.type == self.mt5.POSITION_TYPE_SELL and new_sl < (position.sl or float('inf')):
                success = self._modify_position_sl(position, new_sl)
                if success:
                    self.last_trail_updates[position.ticket] = now
                    logger.info(f"🧠 Adaptive Trailing updated SELL SL ({momentum}) → {new_sl:.5f}")
                    return True

            return False

        except Exception as e:
            logger.error(f"Exception in smart_adaptive_trailing for {position.symbol}: {str(e)}")
            return False

    def _modify_position_sl(self, position, new_sl: float) -> bool:
        """
        Safely modify position stop loss.

        Args:
            position: MT5 position object
            new_sl: New stop loss price

        Returns:
            bool: Success of modification
        """
        try:
            symbol_info = self.mt5.symbol_info(position.symbol)
            if not symbol_info:
                return False

            point = symbol_info.point
            stop_level = symbol_info.trade_stops_level * point or (symbol_info.spread * point * 3)
            current_price = position.price_current

            # Validate SL distance
            if position.type == self.mt5.POSITION_TYPE_BUY:
                if new_sl >= (current_price - stop_level):
                    logger.warning(f"SL {new_sl} too close to BUY price {current_price}")
                    return False
            else:
                if new_sl <= (current_price + stop_level):
                    logger.warning(f"SL {new_sl} too close to SELL price {current_price}")
                    return False

            request = {
                "action": self.mt5.TRADE_ACTION_SLTP,
                "position": position.ticket,
                "symbol": position.symbol,
                "sl": float(new_sl),
                "tp": float(position.tp) if position.tp > 0 else 0.0,
            }

            result = self.mt5.order_send(request)
            if result.retcode == self.mt5.TRADE_RETCODE_DONE:
                return True
            else:
                logger.error(f"Failed SL update for {position.ticket}: {result.comment}")
                return False

        except Exception as e:
            logger.error(f"Exception updating SL for {position.ticket}: {str(e)}")
            return False

    def update_trade_history(self, new_trades: List[Dict]):
        """Update trade history and refresh learned coefficients."""
        self.performance_analyzer.update_history(new_trades)
        self._update_learned_coefficients()

    def get_momentum_state(self, closes: List[float]) -> str:
        """Get current momentum state."""
        return get_momentum_state(closes)


# Convenience functions for easy integration
def create_adaptive_trailing_manager(config, mt5_module=None, trade_history=None):
    """Factory function to create AdaptiveTrailingManager instance."""
    return AdaptiveTrailingManager(config, mt5_module, trade_history)


def get_trailing_coefficients_from_history(history: List[Dict]) -> Dict[str, float]:
    """Standalone function to get learned coefficients from history."""
    analyzer = TradePerformanceAnalyzer(history)
    return analyzer.learn_trailing_behavior()


# Example usage and testing
if __name__ == "__main__":
    # Mock config for testing
    class MockConfig:
        SMART_TRAILING_CANDLE_CONFIRMATION = 2
        SMART_TRAILING_COOLDOWN = 60
        SMART_TRAILING_BUFFER_MULTIPLIER = 0.5
        SMART_TRAILING_ATR_LOOKBACK = 14
        SMART_TRAILING_SWING_LOOKBACK = 5
        ORDER_DEVIATION = 10
        MAGIC = 987654321

    config = MockConfig()

    # Sample trade history
    sample_history = [
        {'profit': 50, 'trail_distance': 20, 'atr_at_entry': 15, 'time_in_trade': 1800},
        {'profit': 30, 'trail_distance': 25, 'atr_at_entry': 20, 'time_in_trade': 1200},
        {'profit': -10, 'trail_distance': 0, 'atr_at_entry': 18, 'time_in_trade': 600},
    ]

    # Create manager
    manager = create_adaptive_trailing_manager(config, trade_history=sample_history)

    # Test momentum detection
    sample_closes = [2000 + i * 0.1 for i in range(20)]
    momentum = manager.get_momentum_state(sample_closes)
    print(f"Momentum state: {momentum}")

    # Test learned coefficients
    coeffs = get_trailing_coefficients_from_history(sample_history)
    print(f"Learned coefficients: {coeffs}")

    print("Adaptive Trailing Manager initialized successfully!")

import time
import random
from datetime import datetime, timedelta
from datetime import time as dt_time
from logger_config import setup_logger

logger = setup_logger()
MAGIC = 987654321

class TradeExecutor:
    def __init__(self, mt5_module=None, config=None, risk_manager=None):
        if mt5_module is None:
            from unittest.mock import Mock
            self.mt5 = Mock()
            self.mt5.symbol_info_tick.return_value = Mock(ask=2000.50, bid=2000.40)
            self.mt5.order_send.return_value = Mock(retcode=10009)
            self.mt5.ORDER_TYPE_BUY = 0
            self.mt5.ORDER_TYPE_SELL = 1
            self.mt5.TRADE_ACTION_DEAL = 1
            self.mt5.ORDER_TIME_GTC = 0
            self.mt5.ORDER_FILLING_IOC = 0
            self.mt5.TRADE_RETCODE_DONE = 10009
            self.mt5.POSITION_TYPE_BUY = 0
            self.mt5.POSITION_TYPE_SELL = 1
        else:
            self.mt5 = mt5_module

        if config is None:
            from unittest.mock import Mock
            self.config = Mock()
            self.config.ORDER_DEVIATION = 10
            self.config.ORDER_RETRY = 3
            self.config.MAX_CONCURRENT_POSITIONS = 10
            self.config.CONTRACT_SIZE = 100000
            self.config.TRAIL_START_PIPS = 20
            self.config.TRAIL_DISTANCE_PIPS = 10
            self.config.SIGNAL_REVERSAL_THRESHOLD = 70
            self.config.SIGNAL_WEAKENING_THRESHOLD = 30
            self.config.MIN_HOLDING_TIME = 300
            self.config.ADAPTIVE_SCALING_ENABLED = True
            self.config.SCALING_MIN_TIME_BETWEEN_ADDS = 300  # seconds
            self.config.SCALING_MAX_TIME_SINCE_ENTRY = 3600  # 1 hour
            self.config.MAX_ADDITIONAL_POSITIONS = 3
            self.config.MAX_TOTAL_EXPOSURE_MULTIPLIER = 3.0
            self.config.SCALING_SIGNAL_STRENGTH_THRESHOLD = 70
            self.config.SCALING_PROFIT_THRESHOLD_PIPS = 20
            self.config.SCALING_NEWS_FAVORABLE_THRESHOLD = 0.3
            self.config.SCALING_NEWS_ADVERSE_THRESHOLD = -0.3
            self.config.SCALING_LOSS_THRESHOLD_PIPS = -10
            self.config.SCALING_CLOSE_ADVERSE_THRESHOLD = 70
            self.config.SCALING_LOT_SIZE_MULTIPLIER = 0.5
            self.config.MAX_LOT_SIZE = 1.0
            self.config.TP_RISK_REWARD = 2
            self.config.SCALING_TREND_STRENGTH_MULTIPLIER = 0.01
            self.config.ATR_SPIKE_MULTIPLIER = 2.0  # Example
            self.config.MAX_POSITION_AGE = 86400  # 24 hours, example
            self.config.SESSION_END_CLOSE = True
            self.config.SESSION_END_BUFFER_MINUTES = 30  # Example
            self.config.FRACTAL_PERIOD = 5  # Example
            self.config.RR_REVERSAL_ENABLED = True
            self.config.RR_REVERSAL_THRESHOLD = 0.5  # Example
            self.config.PORTFOLIO_DRAWDOWN_CLOSE = True
            self.config.EMERGENCY_CLOSE_THRESHOLD = 0.1  # 10%
            self.config.CORRELATION_CLOSE_ENABLED = True
            self.config.MAX_CORRELATED_POSITIONS = 5  # Example
            self.config.AUTO_CLOSE_ENABLED = True
            self.config.TRAILING_STOP_ENABLED = True
            self.config.NEWS_SENTIMENT_CLOSE = True
            self.config.VOLATILITY_SPIKE_ENABLED = True
            self.config.BREAK_OF_STRUCTURE_ENABLED = True
            self.config.TREND_REVERSAL_CLOSE = True
            self.config.BREAK_EVEN_ENABLED = True
            self.config.BREAK_EVEN_PROFIT_PIPS = 20
            self.config.BREAK_EVEN_BUFFER_PIPS = 5
            self.config.BREAK_EVEN_ATR_MULTIPLIER = 0.5
            self.config.BREAK_EVEN_TREND_STRENGTH_MULTIPLIER = 0.1
            self.config.BREAK_EVEN_NEWS_SENTIMENT_MULTIPLIER = 0.2
            self.config.BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER = 0.05
            self.config.BREAK_EVEN_PROFIT_LEVEL_MULTIPLIER = 0.1
        else:
            self.config = config

        if risk_manager is None:
            from unittest.mock import Mock
            self.risk_manager = Mock()
            self.risk_manager.compute_lot_size.return_value = 0.1
            self.risk_manager.enough_balance.return_value = True
            self.risk_manager.check_daily_loss_limit.return_value = True
            self.risk_manager.current_open_positions_count.return_value = 0
            self.risk_manager.refresh_account.return_value = Mock(balance=10000.0)  # Example
        else:
            self.risk_manager = risk_manager

        # Track signal history for candle confirmation
        self.signal_history = []

        # Track scaling information for positions
        self.position_scaling_data = {}  # ticket -> scaling info

        # Initialize scaling data for existing positions
        positions = self.get_open_positions()
        for pos in positions:
            if pos.ticket not in self.position_scaling_data:
                self.position_scaling_data[pos.ticket] = {
                    'original_ticket': pos.ticket,
                    'entry_time': pos.time,
                    'original_volume': pos.volume,
                    'total_volume': pos.volume,
                    'additional_positions': 0,
                    'last_scaling_time': time.time(),
                    'scaling_history': []
                }
                logger.info(f"Initialized scaling data for existing position {pos.ticket}")

    def get_open_positions(self, symbol=None):
        """
        Get open positions for a specific symbol or all symbols.
        
        Args:
            symbol (str, optional): Trading symbol to filter positions. Defaults to None (all symbols).
        
        Returns:
            list: List of MT5 position objects, or empty list if none.
        """
        try:
            if symbol:
                positions = self.mt5.positions_get(symbol=symbol)
            else:
                positions = self.mt5.positions_get()
            return positions if positions else []
        except Exception as e:
            logger.error(f"Error getting open positions: {str(e)}")
            return []

    def _place_market_order(self, symbol, is_buy, volume, sl_price, tp_price):
        terminal_info = self.mt5.terminal_info()
        if terminal_info is None or not terminal_info.trade_allowed:
            raise RuntimeError("Auto-trading is disabled in MetaTrader 5 terminal.")

        order_type = self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("No tick data available")
        price = float(tick.ask if is_buy else tick.bid)

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": float(sl_price) if sl_price else 0.0,
            "tp": float(tp_price) if tp_price else 0.0,
            "deviation": self.config.ORDER_DEVIATION,
            "magic": MAGIC,
            "comment": "XAU Bot Auto",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }

        last_err = None
        for attempt in range(self.config.ORDER_RETRY):
            result = self.mt5.order_send(request)
            try:
                retcode = result.retcode
            except Exception:
                retcode = None

            if retcode == self.mt5.TRADE_RETCODE_DONE:
                logger.info(f"Order success: {result}")
                return result
            else:
                logger.warning(f"Order attempt {attempt+1} failed: {result}")
                last_err = result
                time.sleep(1)

        raise RuntimeError(f"Order failed after retries: {last_err}")

    def enter_trade(self, symbol, signal, entry_price, stop_price, tp_price=None, volume=None):
        is_buy = signal.upper() == "BUY"
        if volume is None:
            lots = self.risk_manager.compute_lot_size(stop_price, entry_price)
        else:
            lots = volume

        if lots is None or lots <= 0:
            raise RuntimeError("Cannot compute valid lot size")
        if not self.risk_manager.enough_balance():
            raise RuntimeError("Account balance too low")
        if not self.risk_manager.check_daily_loss_limit():
            raise RuntimeError("Daily loss limit reached")
        if self.risk_manager.current_open_positions_count(symbol) >= self.config.MAX_CONCURRENT_POSITIONS:
            raise RuntimeError("Max concurrent positions reached")

        logger.info(f"Placing {'BUY' if is_buy else 'SELL'} {lots} lots @ {entry_price}, SL={stop_price}, TP={tp_price}")
        result = self._place_market_order(symbol, is_buy, lots, stop_price, tp_price)

        # Track scaling data for new positions
        if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
            ticket = getattr(result, 'order', None)  # Use 'order' as ticket
            if ticket:
                self.position_scaling_data[ticket] = {
                    'original_ticket': ticket,
                    'entry_time': time.time(),
                    'original_volume': lots,
                    'total_volume': lots,
                    'additional_positions': 0,
                    'last_scaling_time': time.time(),
                    'scaling_history': []
                }
                logger.info(f"Initialized scaling data for position {ticket}")

        return result

    def place_order(self, symbol, signal, volume, sl, tp):
        """
        Places a new order using current market price as entry price.
        Used for scaling positions.

        Args:
            symbol (str): Trading symbol
            signal (str): "BUY" or "SELL"
            volume (float): Lot size
            sl (float): Stop loss price
            tp (float): Take profit price

        Returns:
            MT5 order result
        """
        tick = self.mt5.symbol_info_tick(symbol)
        if not tick:
            raise RuntimeError(f"No tick data for {symbol}")
        entry_price = float(tick.ask if signal.upper() == "BUY" else tick.bid)
        return self.enter_trade(symbol, signal, entry_price, sl, tp, volume)

    def execute_trade(self, signal_dict):
        signal = signal_dict.get("signal")
        if not signal:
            raise ValueError("No signal in signal_dict")
        symbol = signal_dict.get("symbol", "XAUUSDm")
        tick = self.mt5.symbol_info_tick(symbol)
        if not tick:
            raise RuntimeError("No tick data")

        entry_price = signal_dict.get("entry_price", float(tick.ask if signal.upper() == "BUY" else tick.bid))
        stop_price = signal_dict.get("stop_price")
        tp_price = signal_dict.get("tp_price")
        volume = signal_dict.get("volume", self.risk_manager.compute_lot_size(stop_price, entry_price) if stop_price else 0.1)

        if stop_price is None:
            atr = signal_dict.get("atr", 10)
            stop_price = entry_price - atr if signal.upper() == "BUY" else entry_price + atr

        if tp_price is None:
            rr_ratio = signal_dict.get("rr_ratio", 2)
            stop_distance = abs(entry_price - stop_price)
            tp_price = entry_price + stop_distance * rr_ratio if signal.upper() == "BUY" else entry_price - stop_distance * rr_ratio

        return self.enter_trade(symbol, signal, entry_price, stop_price, tp_price, volume)

    def close_all_positions(self, symbol):
        positions = self.get_open_positions(symbol)
        if not positions:
            logger.info("No positions to close")
            return 0

        closed_count = 0
        for pos in positions:
            if self.close_position_by_ticket(pos.ticket):
                closed_count += 1
        logger.info(f"Closed {closed_count} positions for {symbol}")
        return closed_count

    def close_position_by_ticket(self, ticket):
        positions = self.mt5.positions_get(ticket=ticket)
        if not positions:
            logger.warning(f"No position found with ticket {ticket}")
            return False

        pos = positions[0]
        volume = pos.volume
        is_buy = pos.type == self.mt5.POSITION_TYPE_BUY
        symbol = pos.symbol

        order_type = self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"No tick data for {symbol}")
            return False

        price = float(tick.bid if is_buy else tick.ask)
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": self.config.ORDER_DEVIATION,
            "magic": MAGIC,
            "comment": "Manual close",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        res = self.mt5.order_send(req)
        if res.retcode == self.mt5.TRADE_RETCODE_DONE:
            logger.info(f"Successfully closed position {ticket}: {res}")
            # Clean up scaling data
            if ticket in self.position_scaling_data:
                del self.position_scaling_data[ticket]
            return True
        else:
            logger.error(f"Failed to close position {ticket}: {res}")
            return False

    def close_profitable_positions(self, symbol):
        positions = self.get_open_positions(symbol)
        closed_count = 0
        for pos in positions:
            if pos.profit > 0:
                if self.close_position_by_ticket(pos.ticket):
                    closed_count += 1
        logger.info(f"Closed {closed_count} profitable positions for {symbol}")
        return closed_count

    def close_loss_positions(self, symbol):
        positions = self.get_open_positions(symbol)
        closed_count = 0
        for pos in positions:
            if pos.profit < 0:
                if self.close_position_by_ticket(pos.ticket):
                    closed_count += 1
        logger.info(f"Closed {closed_count} loss positions for {symbol}")
        return closed_count

    def close_buy_positions(self, symbol):
        positions = self.get_open_positions(symbol)
        closed_count = 0
        for pos in positions:
            if pos.type == self.mt5.POSITION_TYPE_BUY:
                if self.close_position_by_ticket(pos.ticket):
                    closed_count += 1
        logger.info(f"Closed {closed_count} buy positions for {symbol}")
        return closed_count

    def close_sell_positions(self, symbol):
        positions = self.get_open_positions(symbol)
        closed_count = 0
        for pos in positions:
            if pos.type == self.mt5.POSITION_TYPE_SELL:
                if self.close_position_by_ticket(pos.ticket):
                    closed_count += 1
        logger.info(f"Closed {closed_count} sell positions for {symbol}")
        return closed_count

    def should_update_trailing_stop(self, position, last_update_time, min_interval=600):
        """
        Prevents the trailing stop from being updated too frequently.
        Ensures at least `min_interval` seconds between updates.
        """
        if not hasattr(position, "last_trail_update"):
            position.last_trail_update = datetime.utcnow() - timedelta(seconds=min_interval * 2)
        if (datetime.utcnow() - position.last_trail_update).total_seconds() < min_interval:
            return False
        position.last_trail_update = datetime.utcnow()
        return True

    def calculate_trailing_stop(self, position, current_price, atr=None, volatility=None, trend_strength=None, news_sentiment=None):
        """
        Calculates a dynamic trailing stop based on market conditions.
        If adaptive mode is off, falls back to static trailing stop.
        """

        import config
        adaptive_enabled = getattr(config, "ADAPTIVE_TRAILING_STOP", True)

        base_trail_pips = self.config.TRAIL_DISTANCE_PIPS
        trail_distance = base_trail_pips

        if adaptive_enabled:
            # Adjust trail distance based on volatility (ATR or custom)
            if atr and atr > 0:
                trail_distance *= (atr / 10)  # Example: if ATR = 20, trail widens

            # Adjust based on trend strength
            if trend_strength is not None:
                if trend_strength > 70:  # strong trend → looser trailing stop
                    trail_distance *= 1.3
                elif trend_strength < 40:  # weak trend → tighter trailing stop
                    trail_distance *= 0.8

            # Adjust for news sentiment
            if news_sentiment:
                sentiment_score = 0.0
                if isinstance(news_sentiment, dict):
                    sentiment_score = news_sentiment.get("avg_sentiment_score", 0.0)
                    sentiment_type = news_sentiment.get("sentiment", "")
                else:
                    sentiment_type = news_sentiment
                if sentiment_type == "bullish" and position.type == self.mt5.POSITION_TYPE_BUY:
                    trail_distance *= 0.9
                elif sentiment_type == "bearish" and position.type == self.mt5.POSITION_TYPE_SELL:
                    trail_distance *= 0.9
                else:
                    trail_distance *= 1.1  # increase margin under uncertainty

            # Random jitter (prevent over-optimization)
            trail_distance *= random.uniform(0.95, 1.05)

        # Convert pips → actual price distance
        trail_distance_points = trail_distance / 100000 * self.config.CONTRACT_SIZE

        # Add volatility-based buffer
        safety_buffer = 2 * self.mt5.symbol_info(position.symbol).point

        if position.type == self.mt5.POSITION_TYPE_BUY:
            new_sl = current_price - trail_distance_points - safety_buffer
            # Ensure SL doesn't go above current price
            if new_sl >= current_price:
                new_sl = current_price - (trail_distance_points * 1.2)
        else:
            new_sl = current_price + trail_distance_points + safety_buffer
            if new_sl <= current_price:
                new_sl = current_price + (trail_distance_points * 1.2)

        return round(new_sl, 2)

    def _check_trailing_stop(self, position, current_price):
        """
        Determines whether the trailing stop should be updated safely.
        Prevents premature closes by ensuring SL stays far enough from current price.
        """
        import config

        profit_pips = (
            (current_price - position.price_open) / self.config.CONTRACT_SIZE * 100000
            if position.type == self.mt5.POSITION_TYPE_BUY
            else (position.price_open - current_price) / self.config.CONTRACT_SIZE * 100000
        )

        # Don’t trail until position has at least X pips of profit
        if profit_pips < config.TRAIL_START_PIPS:
            return False

        # Skip frequent updates (less than every 5 mins)
        if not self.should_update_trailing_stop(position, getattr(position, "last_trail_update", None), min_interval=300):
            return False

        # Calculate adaptive trailing stop
        atr_value = getattr(config, "CURRENT_ATR", 10)
        trail_distance_points = max((atr_value * 2), 10)  # at least 10 points away

        symbol_info = self.mt5.symbol_info(position.symbol)
        point = symbol_info.point
        spread = symbol_info.spread * point

        # Apply safe buffers
        safety_buffer = (trail_distance_points * point) + (spread * 2)

        if position.type == self.mt5.POSITION_TYPE_BUY:
            # Only move SL if price moved upward significantly beyond current SL
            new_sl = max(position.sl, current_price - safety_buffer)
            # SL must be at least 3x spread away from price
            if (current_price - new_sl) < (spread * 3):
                return False
        else:
            new_sl = min(position.sl or current_price, current_price + safety_buffer)
            if (new_sl - current_price) < (spread * 3):
                return False

        return round(new_sl, 2)

    def apply_break_even_sl(self, position):
        """
        Applies adaptive break-even stop loss based on market factors.
        Moves SL to a dynamic level above entry price considering ATR, trend strength, news sentiment, etc.
        """
        import config

        if not config.BREAK_EVEN_ENABLED:
            logger.info("Break-even disabled in config")
            return False

        # Check if position is profitable enough
        profit_pips = (
            (position.price_current - position.price_open) / self.config.CONTRACT_SIZE * 100000
            if position.type == self.mt5.POSITION_TYPE_BUY
            else (position.price_open - position.price_current) / self.config.CONTRACT_SIZE * 100000
        )
        if profit_pips < config.BREAK_EVEN_PROFIT_PIPS:
            logger.info(f"Position {position.ticket} not profitable enough for break-even: {profit_pips:.1f} pips < {config.BREAK_EVEN_PROFIT_PIPS}")
            return False

        # Check if already at break-even (SL near entry)
        entry_sl_distance = abs(position.sl - position.price_open) if position.sl > 0 else float('inf')
        if entry_sl_distance < config.BREAK_EVEN_BUFFER_PIPS / 100000 * self.config.CONTRACT_SIZE:
            logger.info(f"Position {position.ticket} already at break-even")
            return False

        # Calculate dynamic buffer
        base_buffer = config.BREAK_EVEN_BUFFER_PIPS

        # ATR-based adjustment
        atr_value = getattr(config, 'CURRENT_ATR', 10)
        atr_buffer = config.BREAK_EVEN_ATR_MULTIPLIER * atr_value
        base_buffer += atr_buffer

        # Trend strength adjustment
        trend_strength = getattr(config, 'CURRENT_TREND_STRENGTH', 50)
        trend_buffer = config.BREAK_EVEN_TREND_STRENGTH_MULTIPLIER * trend_strength
        if trend_strength > 70:  # Strong trend, tighter buffer
            base_buffer -= trend_buffer
        elif trend_strength < 40:  # Weak trend, wider buffer
            base_buffer += trend_buffer

        # News sentiment adjustment
        news_sentiment = getattr(config, 'CURRENT_NEWS_SENTIMENT', {'sentiment': 'neutral', 'avg_sentiment_score': 0.0})
        sentiment_score = news_sentiment.get('avg_sentiment_score', 0.0) if isinstance(news_sentiment, dict) else 0.0
        sentiment_buffer = config.BREAK_EVEN_NEWS_SENTIMENT_MULTIPLIER * sentiment_score * 100  # Convert to pips scale
        if position.type == self.mt5.POSITION_TYPE_BUY and news_sentiment.get('sentiment') == 'bullish':
            base_buffer -= sentiment_buffer
        elif position.type == self.mt5.POSITION_TYPE_SELL and news_sentiment.get('sentiment') == 'bearish':
            base_buffer -= sentiment_buffer
        else:
            base_buffer += sentiment_buffer

        # Time since entry adjustment
        time_since_entry = time.time() - position.time
        time_buffer = config.BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER * (time_since_entry / 60)  # Per minute
        base_buffer += time_buffer

        # Profit level adjustment
        profit_buffer = config.BREAK_EVEN_PROFIT_LEVEL_MULTIPLIER * profit_pips
        base_buffer += profit_buffer

        # Add random jitter to prevent over-optimization
        base_buffer *= random.uniform(0.95, 1.05)

        # Ensure minimum buffer
        base_buffer = max(base_buffer, 1.0)  # At least 1 pip

        # Calculate new SL
        buffer_points = base_buffer / 100000 * self.config.CONTRACT_SIZE
        if position.type == self.mt5.POSITION_TYPE_BUY:
            new_sl = position.price_open + buffer_points
        else:
            new_sl = position.price_open - buffer_points

        # Ensure SL doesn't exceed current price (for safety)
        if position.type == self.mt5.POSITION_TYPE_BUY and new_sl >= position.price_current:
            new_sl = position.price_current - (buffer_points * 0.5)
        elif position.type == self.mt5.POSITION_TYPE_SELL and new_sl <= position.price_current:
            new_sl = position.price_current + (buffer_points * 0.5)

        logger.info(f"Applying break-even SL for position {position.ticket}: Entry {position.price_open:.5f}, New SL {new_sl:.5f}, Buffer {base_buffer:.1f} pips")
        return self.modify_trade_sl(position, new_sl)

    def modify_trade_sl(self, position, new_sl):
        """
        Safely updates SL without triggering premature closure.
        Verifies SL is far enough from market price and valid per broker constraints.
        """
        try:
            symbol_info = self.mt5.symbol_info(position.symbol)
            point = symbol_info.point
            stop_level = symbol_info.trade_stops_level * point or (symbol_info.spread * point * 3)
            current_price = position.price_current

            # Enforce safe stop distance
            if position.type == self.mt5.POSITION_TYPE_BUY:
                if new_sl >= (current_price - stop_level):
                    logger.warning(f"⚠️ Skipped SL update for {position.ticket}: SL {new_sl} too close to BUY price {current_price}")
                    return False
            else:
                if new_sl <= (current_price + stop_level):
                    logger.warning(f"⚠️ Skipped SL update for {position.ticket}: SL {new_sl} too close to SELL price {current_price}")
                    return False

            request = {
                "action": self.mt5.TRADE_ACTION_SLTP,
                "position": position.ticket,
                "symbol": position.symbol,
                "sl": float(new_sl),
                "tp": float(position.tp),
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }

            result = self.mt5.order_send(request)
            if result.retcode == self.mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Trailing SL updated for position {position.ticket} → {new_sl:.2f}")
                return True
            else:
                logger.error(f"❌ Failed SL update for {position.ticket}: {result.comment}")
                return False

        except Exception as e:
            logger.error(f"❌ Exception updating SL for {position.ticket}: {str(e)}")
            return False

    def should_close_trade(self, position, current_data, strategy, news_sentiment, atr_value=None, entry_atr=None):
        """
        Enhanced auto-close logic with stricter conditions to prevent premature closures.

        Args:
            position: MT5 position object
            current_data: Current market data (DataFrame with indicators)
            strategy: Trading strategy instance
            news_sentiment: Current news sentiment ('bullish', 'bearish', 'neutral') or dict with 'sentiment' and 'avg_sentiment_score'
            atr_value: Current ATR value
            entry_atr: ATR value at position entry

        Returns:
            dict: Close decision with reason and details
        """
        import config

        if not config.AUTO_CLOSE_ENABLED:
            return {'should_close': False, 'reason': 'auto_close_disabled'}

        position_type = 'BUY' if position.type == self.mt5.POSITION_TYPE_BUY else 'SELL'
        current_price = current_data['close'].iloc[-1] if len(current_data) > 0 else position.price_current
        position_age = int(time.time() - position.time)
        unrealized_profit = position.profit

        # Enforce minimum holding time
        timeframe_minutes = {
            'M1': 5, 'M5': 15, 'M15': 30, 'M30': 60,
            'H1': 120, 'H4': 240, 'D1': 1440
        }
        min_hold_time = config.MIN_HOLDING_TIME or timeframe_minutes.get(config.TIMEFRAME.upper(), 300)
        if position_age < min_hold_time:
            return {'should_close': False, 'reason': f'position_too_young_{position_age}s'}

        # Get signal information
        signal_info = strategy.generate_signal(current_data)
        current_signal = signal_info['signal']
        signal_strength = signal_info['strength']

        # Update signal history
        self.signal_history.append({'signal': current_signal, 'strength': signal_strength})
        if len(self.signal_history) > 2:
            self.signal_history.pop(0)

        # Check for two consecutive opposite candles
        def has_two_opposite_candles():
            if len(self.signal_history) < 2:
                return False
            last_signal = self.signal_history[-1]['signal']
            prev_signal = self.signal_history[-2]['signal']
            last_strength = self.signal_history[-1]['strength']
            prev_strength = self.signal_history[-2]['strength']
            return (last_signal != position_type and prev_signal != position_type and
                    last_strength >= config.SIGNAL_REVERSAL_THRESHOLD and prev_strength >= config.SIGNAL_REVERSAL_THRESHOLD)

        # Get news sentiment score
        news_score = news_sentiment.get('avg_sentiment_score', 0.0) if isinstance(news_sentiment, dict) else 0.0
        news_sentiment_value = news_sentiment['sentiment'] if isinstance(news_sentiment, dict) else news_sentiment

        # Get reversal information
        reversal_info = strategy.detect_trend_reversal(current_data)

        # Check each factor
        close_checks = []

        # 1. Take Profit Reached
        if self._check_take_profit_reached(position, current_price):
            close_checks.append({'factor': 'take_profit_reached', 'should_close': True})

        # 2. Stop Loss Hit
        if self._check_stop_loss_hit(position, current_price):
            close_checks.append({'factor': 'stop_loss_hit', 'should_close': True})

        # 3. Trailing Stop
        if config.TRAILING_STOP_ENABLED and self._check_trailing_stop(position, current_price):
            close_checks.append({'factor': 'trailing_stop', 'should_close': True})

        # 4. Opposite Signal Trigger (require two candles and high strength)
        if self._check_opposite_signal(position_type, current_signal, signal_strength) and has_two_opposite_candles():
            close_checks.append({'factor': 'opposite_signal', 'should_close': True})

        # 5. Signal Weakening (require two candles and very low strength)
        if self._check_signal_weakening(position, current_data, strategy) and has_two_opposite_candles():
            close_checks.append({'factor': 'signal_weakening', 'should_close': True})

        # 6. News/Economic Event Risk (require strong score and technical confirmation)
        if config.NEWS_SENTIMENT_CLOSE and news_score > 0.5 and self._check_news_economic_event(position_type, news_sentiment_value) and has_two_opposite_candles():
            close_checks.append({'factor': 'news_economic_event', 'should_close': True})

        # 7. Volatility Spike
        if config.VOLATILITY_SPIKE_ENABLED and self._check_volatility_spike(atr_value, entry_atr):
            close_checks.append({'factor': 'volatility_spike', 'should_close': True})

        # 8. Time-Based Exit
        if self._check_time_based_exit(position_age):
            close_checks.append({'factor': 'time_based_exit', 'should_close': True})

        # 9. Market Session End
        if config.SESSION_END_CLOSE and self._check_market_session_end():
            close_checks.append({'factor': 'market_session_end', 'should_close': True})

        # 10. Break of Structure
        if config.BREAK_OF_STRUCTURE_ENABLED and self._check_break_of_structure(current_data, position_type):
            close_checks.append({'factor': 'break_of_structure', 'should_close': True})

        # 11. Risk/Reward Ratio Reversal
        if config.RR_REVERSAL_ENABLED and self._check_rr_ratio_reversal(position, unrealized_profit):
            close_checks.append({'factor': 'rr_ratio_reversal', 'should_close': True})

        # 12. Portfolio/Account Drawdown
        if config.PORTFOLIO_DRAWDOWN_CLOSE and self._check_portfolio_drawdown():
            close_checks.append({'factor': 'portfolio_drawdown', 'should_close': True})

        # 13. Correlation/Position Conflicts
        if config.CORRELATION_CLOSE_ENABLED and self._check_correlation_conflict(position.symbol):
            close_checks.append({'factor': 'correlation_conflict', 'should_close': True})

        # 14. Trend Reversal (require two candles)
        if config.TREND_REVERSAL_CLOSE and reversal_info['reversal_detected'] and has_two_opposite_candles():
            if position_type == 'BUY' and reversal_info['direction'] == 'bullish_to_bearish':
                close_checks.append({'factor': 'trend_reversal', 'should_close': True})
            elif position_type == 'SELL' and reversal_info['direction'] == 'bearish_to_bullish':
                close_checks.append({'factor': 'trend_reversal', 'should_close': True})

        # Determine if any factor triggered close
        triggered_factors = [check for check in close_checks if check['should_close']]
        if triggered_factors:
            return {
                'should_close': True,
                'reason': triggered_factors[0]['factor'],
                'all_factors': triggered_factors,
                'position_info': {
                    'type': position_type,
                    'age_seconds': position_age,
                    'profit': unrealized_profit,
                    'current_price': current_price
                }
            }

        return {'should_close': False, 'reason': None}

    def _check_take_profit_reached(self, position, current_price):
        if position.tp == 0:
            return False
        return current_price >= position.tp if position.type == self.mt5.POSITION_TYPE_BUY else current_price <= position.tp

    def _check_stop_loss_hit(self, position, current_price):
        if position.sl == 0:
            return False
        return current_price <= position.sl if position.type == self.mt5.POSITION_TYPE_BUY else current_price >= position.sl

    def _check_trailing_stop(self, position, current_price):
        import config
        profit_pips = (current_price - position.price_open) / self.config.CONTRACT_SIZE * 100000 if position.type == self.mt5.POSITION_TYPE_BUY else (position.price_open - current_price) / self.config.CONTRACT_SIZE * 100000
        if profit_pips > config.TRAIL_START_PIPS:
            trail_distance = config.TRAIL_DISTANCE_PIPS / 100000 * self.config.CONTRACT_SIZE
            new_sl = current_price - trail_distance if position.type == self.mt5.POSITION_TYPE_BUY else current_price + trail_distance
            return position.sl == 0 or (new_sl > position.sl if position.type == self.mt5.POSITION_TYPE_BUY else new_sl < position.sl)
        return False

    def _check_opposite_signal(self, position_type, current_signal, signal_strength):
        import config
        return signal_strength >= config.SIGNAL_REVERSAL_THRESHOLD and (
            (position_type == 'BUY' and current_signal == 'SELL') or
            (position_type == 'SELL' and current_signal == 'BUY')
        )

    def _check_signal_weakening(self, position, current_data, strategy):
        import config
        signal_info = strategy.generate_signal(current_data)
        return signal_info['strength'] < config.SIGNAL_WEAKENING_THRESHOLD

    def _check_news_economic_event(self, position_type, news_sentiment):
        import config
        if not config.NEWS_SENTIMENT_CLOSE:
            return False
        return (position_type == 'BUY' and news_sentiment == 'bearish') or (position_type == 'SELL' and news_sentiment == 'bullish')

    def _check_volatility_spike(self, current_atr, entry_atr):
        import config
        if current_atr is None or entry_atr is None or entry_atr == 0:
            return False
        return current_atr > entry_atr * config.ATR_SPIKE_MULTIPLIER

    def _check_time_based_exit(self, position_age):
        import config
        return position_age > config.MAX_POSITION_AGE

    def _check_market_session_end(self):
        import config
        now = datetime.utcnow()
        return now.weekday() == 4 and now.time() >= dt_time(22 - config.SESSION_END_BUFFER_MINUTES // 60, 0)

    def _check_break_of_structure(self, current_data, position_type):
        import config
        if len(current_data) < config.FRACTAL_PERIOD * 2:
            return False
        recent_highs = current_data['high'].tail(config.FRACTAL_PERIOD * 2).max()
        recent_lows = current_data['low'].tail(config.FRACTAL_PERIOD * 2).min()
        current_price = current_data['close'].iloc[-1]
        return (position_type == 'BUY' and current_price < recent_lows) or (position_type == 'SELL' and current_price > recent_highs)

    def _check_rr_ratio_reversal(self, position, unrealized_profit):
        import config
        if not config.RR_REVERSAL_ENABLED:
            return False
        max_profit = abs(position.price_open - position.sl) * config.TP_RISK_REWARD * position.volume * 100000
        return max_profit > 0 and unrealized_profit < max_profit * config.RR_REVERSAL_THRESHOLD

    def _check_portfolio_drawdown(self):
        import config
        try:
            account = self.risk_manager.refresh_account()
            initial_balance = config.INITIAL_ACCOUNT_BALANCE
            current_balance = float(account.balance)
            drawdown_pct = (initial_balance - current_balance) / initial_balance
            return drawdown_pct >= config.EMERGENCY_CLOSE_THRESHOLD
        except:
            return False

    def _check_correlation_conflict(self, symbol):
        import config
        positions = self.get_open_positions()
        symbol_positions = [p for p in positions if p.symbol == symbol]
        correlated_positions = [p for p in positions if p.symbol != symbol]
        return len(symbol_positions) + len(correlated_positions) > config.MAX_CORRELATED_POSITIONS

    def evaluate_position_scaling(self, position, current_data, strategy, news_sentiment, atr_value=None):
        """
        Evaluates whether to scale up or down a position based on market conditions.

        Args:
            position: MT5 position object
            current_data: Current market data (DataFrame with indicators)
            strategy: Trading strategy instance
            news_sentiment: Current news sentiment dict
            atr_value: Current ATR value

        Returns:
            dict: Scaling decision with action and details
        """
        import config

        if not self.config.ADAPTIVE_SCALING_ENABLED:
            return {'action': 'hold', 'reason': 'scaling_disabled'}

        position_type = 'BUY' if position.type == self.mt5.POSITION_TYPE_BUY else 'SELL'
        current_price = current_data['close'].iloc[-1] if len(current_data) > 0 else position.price_current
        position_age = int(time.time() - position.time)

        # Get scaling data for this position
        scaling_data = self.position_scaling_data.get(position.ticket)
        if not scaling_data:
            # Initialize if not found
            scaling_data = {
                'original_ticket': position.ticket,
                'entry_time': position.time,
                'original_volume': position.volume,
                'total_volume': position.volume,
                'additional_positions': 0,
                'last_scaling_time': time.time(),
                'scaling_history': []
            }
            self.position_scaling_data[position.ticket] = scaling_data
            logger.info(f"Initialized scaling data for position {position.ticket} during evaluation")

        # Check time since last scaling
        time_since_last_scale = time.time() - scaling_data['last_scaling_time']
        if time_since_last_scale < self.config.SCALING_MIN_TIME_BETWEEN_ADDS:
            return {'action': 'hold', 'reason': 'too_soon_since_last_scale'}

        # Check max time since entry
        if position_age > self.config.SCALING_MAX_TIME_SINCE_ENTRY:
            return {'action': 'hold', 'reason': 'too_old_for_scaling'}

        # Check max additional positions
        if scaling_data['additional_positions'] >= self.config.MAX_ADDITIONAL_POSITIONS:
            return {'action': 'hold', 'reason': 'max_additional_positions_reached'}

        # Check total exposure limit
        total_exposure = scaling_data['total_volume'] * position.price_open
        max_exposure = scaling_data['original_volume'] * position.price_open * self.config.MAX_TOTAL_EXPOSURE_MULTIPLIER
        if total_exposure >= max_exposure:
            return {'action': 'hold', 'reason': 'max_exposure_reached'}

        # Get signal information
        signal_info = strategy.generate_signal(current_data)
        current_signal = signal_info['signal']
        signal_strength = signal_info['strength']
        scaling_factors = signal_info.get('scaling_factors', {})

        # Calculate profit/loss in pips
        profit_pips = (
            (current_price - position.price_open) / self.config.CONTRACT_SIZE * 100000
            if position.type == self.mt5.POSITION_TYPE_BUY
            else (position.price_open - current_price) / self.config.CONTRACT_SIZE * 100000
        )

        # Get news sentiment score
        news_score = news_sentiment.get('avg_sentiment_score', 0.0) if isinstance(news_sentiment, dict) else 0.0
        news_sentiment_value = news_sentiment.get('sentiment', 'neutral') if isinstance(news_sentiment, dict) else news_sentiment

        # Evaluate scaling up conditions
        scale_up_score = 0
        scale_up_reasons = []

        # 1. Signal strength and alignment
        if signal_strength >= self.config.SCALING_SIGNAL_STRENGTH_THRESHOLD:
            if current_signal == position_type:
                scale_up_score += 2
                scale_up_reasons.append(f"strong_{position_type.lower()}_signal")
            else:
                scale_up_score -= 1
                scale_up_reasons.append("signal_misalignment")

        # 2. Profit threshold
        if profit_pips >= self.config.SCALING_PROFIT_THRESHOLD_PIPS:
            scale_up_score += 1.5
            scale_up_reasons.append("profitable_position")

        # 3. News sentiment favorability
        if news_score >= self.config.SCALING_NEWS_FAVORABLE_THRESHOLD:
            if (position_type == 'BUY' and news_sentiment_value == 'bullish') or \
               (position_type == 'SELL' and news_sentiment_value == 'bearish'):
                scale_up_score += 1
                scale_up_reasons.append("favorable_news")
        elif news_score <= self.config.SCALING_NEWS_ADVERSE_THRESHOLD:
            scale_up_score -= 1
            scale_up_reasons.append("adverse_news")

        # 4. Scaling factors from strategy
        trend_alignment = scaling_factors.get('trend_alignment', 0)
        momentum_strength = scaling_factors.get('momentum_strength', 0)
        volatility_adjustment = scaling_factors.get('volatility_adjustment', 1)

        scale_up_score += trend_alignment * self.config.SCALING_TREND_STRENGTH_MULTIPLIER
        scale_up_score += momentum_strength * 0.5
        scale_up_score *= volatility_adjustment

        # 5. ATR consideration
        if atr_value and atr_value > 0:
            atr_multiplier = min(atr_value / 10, 2)  # Cap at 2x
            scale_up_score *= (1 / atr_multiplier)  # Reduce scaling in high volatility

        # Evaluate scaling down conditions
        scale_down_score = 0
        scale_down_reasons = []

        # 1. Loss threshold
        if profit_pips <= self.config.SCALING_LOSS_THRESHOLD_PIPS:
            scale_down_score += 2
            scale_down_reasons.append("significant_loss")

        # 2. Adverse signal
        if signal_strength >= self.config.SCALING_CLOSE_ADVERSE_THRESHOLD:
            if current_signal != position_type:
                scale_down_score += 1.5
                scale_down_reasons.append("strong_opposite_signal")

        # 3. Adverse news
        if news_score <= self.config.SCALING_NEWS_ADVERSE_THRESHOLD:
            if (position_type == 'BUY' and news_sentiment_value == 'bearish') or \
               (position_type == 'SELL' and news_sentiment_value == 'bullish'):
                scale_down_score += 1
                scale_down_reasons.append("adverse_news_sentiment")

        # Decision logic
        if scale_up_score >= 3.0 and scale_down_score < 1.0:
            # Calculate additional lot size
            base_additional_lots = scaling_data['original_volume'] * self.config.SCALING_LOT_SIZE_MULTIPLIER
            additional_lots = min(base_additional_lots, self.config.MAX_LOT_SIZE)

            return {
                'action': 'scale_up',
                'additional_lots': additional_lots,
                'score': scale_up_score,
                'reasons': scale_up_reasons,
                'position_info': {
                    'type': position_type,
                    'profit_pips': profit_pips,
                    'signal_strength': signal_strength,
                    'news_score': news_score
                }
            }

        elif scale_down_score >= 2.0:
            return {
                'action': 'scale_down',
                'score': scale_down_score,
                'reasons': scale_down_reasons,
                'position_info': {
                    'type': position_type,
                    'profit_pips': profit_pips,
                    'signal_strength': signal_strength,
                    'news_score': news_score
                }
            }

        return {
            'action': 'hold',
            'scale_up_score': scale_up_score,
            'scale_down_score': scale_down_score,
            'reason': 'conditions_not_met'
        }

    def scale_up_position(self, position, additional_lots, scaling_decision):
        """
        Adds to an existing position by placing an additional order.

        Args:
            position: MT5 position object
            additional_lots: Additional lot size to add
            scaling_decision: Scaling decision dict from evaluate_position_scaling

        Returns:
            bool: Success of scaling operation
        """
        try:
            symbol = position.symbol
            position_type = 'BUY' if position.type == self.mt5.POSITION_TYPE_BUY else 'SELL'

            # Calculate stop loss and take profit for additional position
            # Use same SL distance but adjust for current price
            sl_distance = abs(position.price_open - position.sl) if position.sl > 0 else (10 / 100000 * self.config.CONTRACT_SIZE)
            tp_distance = sl_distance * self.config.TP_RISK_REWARD

            tick = self.mt5.symbol_info_tick(symbol)
            if not tick:
                logger.error(f"No tick data for {symbol}")
                return False

            entry_price = float(tick.ask if position_type == 'BUY' else tick.bid)

            if position_type == 'BUY':
                sl_price = entry_price - sl_distance
                tp_price = entry_price + tp_distance
            else:
                sl_price = entry_price + sl_distance
                tp_price = entry_price - tp_distance

            # Place the additional order
            result = self.place_order(symbol, position_type, additional_lots, sl_price, tp_price)

            if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
                # Update scaling data
                scaling_data = self.position_scaling_data.get(position.ticket)
                if scaling_data:
                    scaling_data['additional_positions'] += 1
                    scaling_data['total_volume'] += additional_lots
                    scaling_data['last_scaling_time'] = time.time()
                    scaling_data['scaling_history'].append({
                        'timestamp': time.time(),
                        'action': 'scale_up',
                        'additional_lots': additional_lots,
                        'reason': scaling_decision.get('reasons', []),
                        'ticket': getattr(result, 'order', None)
                    })

                logger.info(f"Successfully scaled up position {position.ticket} by {additional_lots} lots. New total: {scaling_data['total_volume']}")
                return True
            else:
                logger.error(f"Failed to scale up position {position.ticket}: {result}")
                return False

        except Exception as e:
            logger.error(f"Exception scaling up position {position.ticket}: {str(e)}")
            return False

    def scale_down_position(self, position, scaling_decision):
        """
        Scales down a position by closing a portion or the entire position.

        Args:
            position: MT5 position object
            scaling_decision: Scaling decision dict from evaluate_position_scaling

        Returns:
            bool: Success of scaling down operation
        """
        try:
            # For now, implement as partial close of 50% of position
            # In future, could be more sophisticated
            close_volume = position.volume * 0.5

            # Close partial position
            result = self.close_position_partial(position.ticket, close_volume)

            if result:
                # Update scaling data
                scaling_data = self.position_scaling_data.get(position.ticket)
                if scaling_data:
                    scaling_data['total_volume'] -= close_volume
                    scaling_data['last_scaling_time'] = time.time()
                    scaling_data['scaling_history'].append({
                        'timestamp': time.time(),
                        'action': 'scale_down',
                        'closed_volume': close_volume,
                        'reason': scaling_decision.get('reasons', [])
                    })

                logger.info(f"Successfully scaled down position {position.ticket} by {close_volume} lots")
                return True
            else:
                logger.error(f"Failed to scale down position {position.ticket}")
                return False

        except Exception as e:
            logger.error(f"Exception scaling down position {position.ticket}: {str(e)}")
            return False

    def close_position_partial(self, ticket, volume):
        """
        Closes a partial amount of a position.

        Args:
            ticket: Position ticket
            volume: Volume to close

        Returns:
            bool: Success
        """
        positions = self.mt5.positions_get(ticket=ticket)
        if not positions:
            logger.warning(f"No position found with ticket {ticket}")
            return False

        pos = positions[0]
        if volume >= pos.volume:
            # Close entire position
            return self.close_position_by_ticket(ticket)

        # Partial close
        volume = float(volume)
        is_buy = pos.type == self.mt5.POSITION_TYPE_BUY
        symbol = pos.symbol

        order_type = self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"No tick data for {symbol}")
            return False

        price = float(tick.bid if is_buy else tick.ask)
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": self.config.ORDER_DEVIATION,
            "magic": MAGIC,
            "comment": "Partial close - scaling",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        res = self.mt5.order_send(req)
        if res.retcode == self.mt5.TRADE_RETCODE_DONE:
            logger.info(f"Successfully closed partial position {ticket}: {volume} lots")
            return True
        else:
            logger.error(f"Failed to close partial position {ticket}: {res}")
            return False

# Legacy functions
def execute_trade(symbol, signal, volume=0.02, magic=123456, comment="XAUUSD Auto Bot"):
    logger.warning("execute_trade is deprecated; use TradeExecutor class")
    return False

def close_position(symbol, position_ticket=None, volume=None):
    logger.warning("close_position is deprecated; use TradeExecutor.close_all_positions")
    return False

def get_open_positions(symbol=None):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        return []
    try:
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        return positions if positions else []
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return []

if __name__ == "__main__":
    print("Testing trade executor...")
    print("Trade executor functions defined. Connect to MT5 to test.")
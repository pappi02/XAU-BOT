import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import time
import random
import sqlite3
import numpy as np
from datetime import datetime, timedelta
from datetime import time as dt_time
from logger_config import setup_logger
from risk.smart_risk import calculate_adaptive_lot, get_safe_lot
from utils.symbol_helpers import resolve_symbol, round_price, get_symbol_digits, get_min_stop_distance, validate_sl_tp, enforce_rr_minimum

class AdaptiveExposureController:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.dynamic_exposure = config.BASE_MAX_TOTAL_EXPOSURE_MULTIPLIER

    def update_dynamic_exposure(self, balance, volatility, recent_performance, signal_strength):
        """
        Dynamically adjust exposure multiplier based on real-time factors.
        """

        base = self.config.BASE_MAX_TOTAL_EXPOSURE_MULTIPLIER

        # 1️⃣ Account Balance Scaling
        balance_factor = 1 + (balance * self.config.EXPOSURE_BALANCE_SENSITIVITY)
        balance_factor = np.clip(balance_factor, 0.8, 1.3)

        # 2️⃣ Volatility Adjustment (ATR or StdDev)
        vol_factor = 1 / max(0.8, min(volatility, 2.5))  # high vol = lower exposure
        vol_factor *= self.config.EXPOSURE_VOLATILITY_SENSITIVITY

        # 3️⃣ Performance Adjustment
        if recent_performance < 0:
            perf_factor = 1 - abs(recent_performance) * self.config.EXPOSURE_PERFORMANCE_SENSITIVITY
        else:
            perf_factor = 1 + abs(recent_performance) * 0.2
        perf_factor = np.clip(perf_factor, 0.6, 1.4)

        # 4️⃣ Signal Confidence Factor
        conf_factor = 1 + (signal_strength / 100) * 0.4  # high signal = slightly higher exposure
        conf_factor = np.clip(conf_factor, 0.8, 1.4)

        # 🧠 Combine dynamically
        new_exposure = base * balance_factor * vol_factor * perf_factor * conf_factor
        new_exposure = np.clip(
            new_exposure,
            self.config.MIN_EXPOSURE_MULTIPLIER,
            self.config.MAX_EXPOSURE_MULTIPLIER
        )

        # Update internal value
        self.dynamic_exposure = round(new_exposure, 2)
        self.logger.info(f"⚙️ Adaptive Exposure Updated → {self.dynamic_exposure}x based on conditions.")
        return self.dynamic_exposure

logger = setup_logger()
MAGIC = 987654321

class TradeExecutor:
    def __init__(self, mt5_module=None, config=None, risk_manager=None, market_analyzer=None, signal_analyzer=None):
        if mt5_module is None:
            from unittest.mock import Mock
            self.mt5 = Mock()
            self.mt5.symbol_info_tick.return_value = Mock(ask=2000.50, bid=2000.40)
            self.mt5.symbol_info.return_value = Mock(contract_size=100000, volume_min=0.01, volume_max=100.0, volume_step=0.01)
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
            # Adaptive lot sizing
            self.config.MIN_LOT_SIZE = 0.01
            self.config.MAX_LOT_SIZE = 0.05
            self.config.LOT_STEP = 0.01
            self.config.RISK_PER_TRADE = 0.001
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

        if market_analyzer is None:
            self.market_analyzer = type('MockMarketAnalyzer', (), {'get_recent_volatility': lambda self, symbol: 20})()
        else:
            self.market_analyzer = market_analyzer

        if signal_analyzer is None:
            self.signal_analyzer = type('MockSignalAnalyzer', (), {'get_trend_confidence': lambda self, symbol: 0.8})()
        else:
            self.signal_analyzer = signal_analyzer

        # Track signal history for candle confirmation
        self.signal_history = []

        # Track scaling information for positions
        self.position_scaling_data = {}  # ticket -> scaling info

        # Track scaling failures for cooldown
        self.scaling_failures = 0
        self.scaling_cooldown_until = 0  # timestamp when cooldown ends

        # Dynamic scaling attributes
        self.signal_persistence_counter = 0
        self.last_scaling_time = 0

        # Simple performance tracker for recent trades
        self.recent_performance = []  # list of (profit, timestamp) tuples
        self.max_recent_trades = 10  # track last 10 trades

        # Initialize scaling data for existing positions
        if mt5_module is not None:
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

        # Resolve symbol to canonical form
        symbol = resolve_symbol(symbol)
        
        order_type = self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("No tick data available")
        price = float(tick.ask if is_buy else tick.bid)

        # Get symbol specs for rounding and validation
        digits = get_symbol_digits(self.mt5, symbol)
        min_stop_distance = get_min_stop_distance(self.mt5, symbol)

        # Validate and enforce SL/TP invariants
        sl_price, tp_price = validate_sl_tp(price, sl_price, tp_price, is_buy, min_stop_distance)
        
        # Enforce minimum RR ratio
        rr_min = getattr(self.config, 'TP_RR_MIN', 1.8)
        sl_price, tp_price = enforce_rr_minimum(price, sl_price, tp_price, is_buy, rr_min)
        
        # Round prices to correct decimal places per symbol
        price = round_price(price, digits)
        sl_price = round_price(sl_price, digits) if sl_price else 0.0
        tp_price = round_price(tp_price, digits) if tp_price else 0.0

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": self.config.ORDER_DEVIATION,
            "magic": MAGIC,
            "comment": "XAU Bot Auto",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }

        logger.info(f"Order request: {symbol} {'BUY' if is_buy else 'SELL'} {volume} @ {price:.{digits}f} | SL={sl_price:.{digits}f} TP={tp_price:.{digits}f} | RR={(tp_price - price) / (price - sl_price):.2f}x" if is_buy else f"RR={(price - tp_price) / (sl_price - price):.2f}x")

        last_err = None
        for attempt in range(self.config.ORDER_RETRY):
            # Refresh tick before each retry
            tick = self.mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.warning(f"Order attempt {attempt+1}: No tick data available")
                time.sleep(1)
                continue
            
            # Update price to latest
            request["price"] = round_price(float(tick.ask if is_buy else tick.bid), digits)
            
            result = self.mt5.order_send(request)
            try:
                retcode = result.retcode
            except Exception:
                retcode = None

            if retcode == self.mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Order success: ticket={result.order if hasattr(result, 'order') else 'N/A'}, {result}")
                return result
            else:
                logger.warning(f"Order attempt {attempt+1} failed (retcode={retcode}): {result}")
                last_err = result
                time.sleep(1)

        raise RuntimeError(f"Order failed after {self.config.ORDER_RETRY} retries: {last_err}")

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
        # Dynamic scaling: Check if new position should be opened based on signal conditions
        # This replaces the fixed MAX_CONCURRENT_POSITIONS check
        # The actual limit is determined dynamically in should_open_new_position

        # Ensure symbol is selected before checking margin
        if not self.mt5.symbol_select(symbol, True):
            raise RuntimeError(f"Failed to select symbol {symbol}")

        # Check margin requirements before placing order using safe margin check
        safe_lot = get_safe_lot(symbol, lots)
        if safe_lot is None:
            raise RuntimeError("Insufficient margin even for minimum lot size")
        if safe_lot != lots:
            logger.info(f"Reduced lot size from {lots} to {safe_lot} due to margin constraints")
            lots = safe_lot

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

                # Log the trade entry with ticket
                from trade_logger import trade_logger
                trade_logger.log_trade_entry(
                    symbol=symbol,
                    side="BUY" if is_buy else "SELL",
                    entry_price=entry_price,
                    volume=lots,
                    stop_loss=stop_price,
                    take_profit=tp_price,
                    strategy="basic",
                    notes=f"Auto trade entry",
                    ticket=ticket
                )

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
        pnl = pos.profit  # Capture P&L before closing

        order_type = self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"No tick data for {symbol}")
            return False

        exit_price = float(tick.bid if is_buy else tick.ask)
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": exit_price,
            "deviation": self.config.ORDER_DEVIATION,
            "magic": MAGIC,
            "comment": "Manual close",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        res = self.mt5.order_send(req)
        if res.retcode == self.mt5.TRADE_RETCODE_DONE:
            logger.info(f"Successfully closed position {ticket}: {res}")
            # Log trade exit to database
            try:
                from trade_logger import trade_logger
                # Find trade_id by ticket
                with sqlite3.connect(trade_logger.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM trades WHERE ticket = ? AND status = 'OPEN'", (ticket,))
                    result = cursor.fetchone()
                    if result:
                        trade_id = result[0]
                        trade_logger.log_trade_exit(trade_id, exit_price, pnl, "Manual close")
                        logger.info(f"Logged trade exit for ticket {ticket}: exit_price={exit_price}, pnl={pnl}")
            except Exception as e:
                logger.error(f"Failed to log trade exit for ticket {ticket}: {e}")
            # Clean up scaling data
            if ticket in self.position_scaling_data:
                del self.position_scaling_data[ticket]

            # Track recent performance
            self.recent_performance.append((pnl, time.time()))
            self.recent_performance = self.recent_performance[-self.max_recent_trades:]

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

    def apply_trailing_stop(self, position, current_price):
        """
        Applies trailing stop to a position based on current price.
        """
        new_sl = self._check_trailing_stop(position, current_price)
        if new_sl:
            return self.modify_trade_sl(position, new_sl)
        return False

    def smart_adaptive_trailing(self, position, candles):
        """
        Enhanced dynamic trailing that avoids whipsaws and adapts to candle structure.
        """
        if not self.config.SMART_TRAILING_ENABLED:
            return

        symbol = position.symbol
        now = datetime.now()

        # Prevent too-frequent updates
        last_update = getattr(position, "last_trail_update", None)
        if last_update and (now - last_update).total_seconds() < self.config.SMART_TRAILING_COOLDOWN:
            return

        # Extract recent candle data
        closes = np.array([c['close'] for c in candles])
        highs = np.array([c['high'] for c in candles])
        lows = np.array([c['low'] for c in candles])

        atr = np.mean(highs[-self.config.SMART_TRAILING_ATR_LOOKBACK:] - lows[-self.config.SMART_TRAILING_ATR_LOOKBACK:])
        last_close = closes[-1]

        current_price = self.mt5.symbol_info_tick(symbol).bid if position.type == 0 else self.mt5.symbol_info_tick(symbol).ask
        entry_price = position.price_open

        profit_points = abs(current_price - entry_price) / self.mt5.symbol_info(symbol).point
        if profit_points < self.config.DYNAMIC_TRAILING_START_PROFIT:
            return

        # Check direction confirmation (N candles in favor)
        if position.type == 0:  # BUY
            favor_candles = sum(1 for i in range(-self.config.SMART_TRAILING_CANDLE_CONFIRMATION, 0)
                                if closes[i] > closes[i-1])
        else:  # SELL
            favor_candles = sum(1 for i in range(-self.config.SMART_TRAILING_CANDLE_CONFIRMATION, 0)
                                if closes[i] < closes[i-1])

        if favor_candles < self.config.SMART_TRAILING_CANDLE_CONFIRMATION:
            # Skip tightening until trend persists
            return

        # Calculate safety buffer (avoid trailing too close)
        recent_swing_low = np.min(lows[-self.config.SMART_TRAILING_SWING_LOOKBACK:])
        recent_swing_high = np.max(highs[-self.config.SMART_TRAILING_SWING_LOOKBACK:])

        if position.type == 0:
            buffer_zone = (atr * self.config.SMART_TRAILING_BUFFER_MULTIPLIER)
            new_sl = max(position.sl, recent_swing_low - buffer_zone)
            if new_sl > position.sl and (current_price - new_sl) > atr * 0.3:
                self.mt5.order_modify(position.ticket, sl=new_sl)
                position.last_trail_update = now
                self.logger.info(f"🧠 SMART TRAILING → BUY SL updated to {new_sl:.2f}")
        else:
            buffer_zone = (atr * self.config.SMART_TRAILING_BUFFER_MULTIPLIER)
            new_sl = min(position.sl, recent_swing_high + buffer_zone)
            if new_sl < position.sl and (new_sl - current_price) > atr * 0.3:
                self.mt5.order_modify(position.ticket, sl=new_sl)
                position.last_trail_update = now
                self.logger.info(f"🧠 SMART TRAILING → SELL SL updated to {new_sl:.2f}")

    def update_dynamic_trailing_stop(self, position, df, signal_strength, trend_confidence):
        """
        Dynamically adjusts trailing stop loss based on volatility, signal strength, and trend persistence.
        """

        symbol = position.symbol
        atr = self.market_analyzer.get_atr(symbol, period=14) if hasattr(self.market_analyzer, 'get_atr') else 5.0
        current_price = self.mt5.symbol_info_tick(symbol).bid if position.type == self.mt5.POSITION_TYPE_BUY else self.mt5.symbol_info_tick(symbol).ask

        # --- Normalize Inputs ---
        normalized_signal = min(max(signal_strength / 100, 0.1), 1.0)
        normalized_trend = min(max(trend_confidence, 0.1), 1.0)
        normalized_atr = max(atr, 1e-3)

        # --- Adaptive Trailing Logic ---
        # Base trail factor — tighter for high-confidence signals
        base_trail = normalized_atr * (1.5 - normalized_signal * 0.8)

        # Adjust for trend confidence (tighter in weaker trends)
        adaptive_trail = base_trail * (1.2 - normalized_trend * 0.5)

        # Compute the proposed trailing stop price
        if position.type == self.mt5.POSITION_TYPE_BUY:
            new_sl = max(position.sl, current_price - adaptive_trail)
        else:
            new_sl = min(position.sl, current_price + adaptive_trail)

        # --- Trailing Conditions ---
        profit_pips = (current_price - position.price_open) * 100 if position.type == self.mt5.POSITION_TYPE_BUY else (position.price_open - current_price) * 100

        if profit_pips > 5:  # Start trailing only when trade is slightly profitable
            sl_distance = abs(current_price - new_sl)
            min_trail_distance = normalized_atr * 0.5

            if sl_distance > min_trail_distance:
                request = {
                    "action": self.mt5.TRADE_ACTION_SLTP,
                    "position": position.ticket,
                    "symbol": symbol,
                    "sl": round(new_sl, 3),
                    "tp": position.tp,
                }

                result = self.mt5.order_send(request)
                if result.retcode == self.mt5.TRADE_RETCODE_DONE:
                    logger.info(f"🔁 Updated dynamic SL for {symbol} | New SL={new_sl:.3f} | ATR={atr:.2f} | Profit={profit_pips:.1f} pips")
                else:
                    logger.warning(f"⚠️ Failed to update dynamic SL for {symbol}: {result.comment}")

        # Breakeven logic
        if profit_pips > (normalized_atr * 2):
            if position.type == self.mt5.POSITION_TYPE_BUY and position.sl < position.price_open:
                request["sl"] = position.price_open
                self.mt5.order_send(request)
                logger.info(f"🟢 Moved SL to breakeven for {symbol} | Profit: {profit_pips:.1f} pips")

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
                logger.info(f"✅ Trailing SL updated for position {position.ticket} → SL={new_sl:.2f}")
                return True
            else:
                logger.error(f"❌ Failed SL update for {position.ticket}: {result.comment}")
                return False

        except Exception as e:
            logger.error(f"❌ Exception updating SL for {position.ticket}: {str(e)}")
            return False

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

    def normalize_lot_size(self, volume):
        """
        Normalizes lot size to be within broker constraints and step size.

        Args:
            volume (float): Raw volume to normalize

        Returns:
            float: Normalized volume, or None if below minimum
        """
        if volume <= 0:
            return None

        # Round to step size
        normalized = round(volume / self.config.LOT_STEP) * self.config.LOT_STEP

        # Ensure within bounds
        normalized = max(self.config.MIN_LOT_SIZE, min(self.config.MAX_LOT_SIZE, normalized))

        # If normalized volume is below minimum, return None
        if normalized < self.config.MIN_LOT_SIZE:
            return None

        return normalized

    def get_dynamic_scaling_ratio(self, loss_pips, atr_value=None, trend_strength=None):
        """
        Calculates dynamic scaling ratio based on market conditions.

        Args:
            loss_pips (float): Current loss in pips
            atr_value (float, optional): Current ATR value
            trend_strength (float, optional): Current trend strength (0-100)

        Returns:
            float: Scaling ratio (0.1 to 0.8)
        """
        base_ratio = 0.5  # Default 50%

        # Adjust based on loss severity
        if loss_pips <= -50:  # Heavy loss
            base_ratio = 0.3  # Scale down more aggressively
        elif loss_pips <= -20:  # Moderate loss
            base_ratio = 0.4
        elif loss_pips <= -10:  # Light loss
            base_ratio = 0.45
        else:  # Small loss or profit
            base_ratio = 0.5

        # ATR adjustment (higher volatility = smaller scaling)
        if atr_value:
            if atr_value > 20:  # High volatility
                base_ratio *= 0.8
            elif atr_value > 10:  # Moderate volatility
                base_ratio *= 0.9

        # Trend strength adjustment (stronger trend = larger scaling)
        if trend_strength is not None:
            if trend_strength > 70:  # Strong trend
                base_ratio *= 1.1
            elif trend_strength < 40:  # Weak trend
                base_ratio *= 0.9

        # Ensure within bounds
        return max(0.1, min(0.8, base_ratio))

    def compute_dynamic_scaling_interval(self, signal_strength, volatility, trend_confidence):
        """
        Computes dynamic scaling interval based on market conditions.

        Args:
            signal_strength (float): Current signal strength (0-100)
            volatility (float): Recent volatility measure
            trend_confidence (float): Trend confidence score (0-1)

        Returns:
            float: Dynamic scaling interval in seconds
        """
        base_interval = 300  # 5 minutes base

        # Adjust based on signal strength (stronger signals = shorter wait)
        if signal_strength > 80:
            signal_multiplier = 0.5  # 50% faster scaling
        elif signal_strength > 60:
            signal_multiplier = 0.75
        else:
            signal_multiplier = 1.0

        # Adjust based on volatility (higher volatility = longer wait)
        if volatility > 30:
            volatility_multiplier = 1.5  # 50% longer wait
        elif volatility > 15:
            volatility_multiplier = 1.2
        else:
            volatility_multiplier = 1.0

        # Adjust based on trend confidence (higher confidence = shorter wait)
        if trend_confidence > 0.8:
            trend_multiplier = 0.7  # 30% faster
        elif trend_confidence > 0.6:
            trend_multiplier = 0.85
        else:
            trend_multiplier = 1.0

        # Calculate final interval
        dynamic_interval = base_interval * signal_multiplier * volatility_multiplier * trend_multiplier

        # Ensure reasonable bounds
        return max(60, min(1800, dynamic_interval))  # Between 1 minute and 30 minutes

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
        symbol = position.symbol
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

        # Get signal information first to compute dynamic interval
        signal_info = strategy.generate_signal(current_data)
        current_signal = signal_info['signal']
        signal_strength = signal_info['strength']
        scaling_factors = signal_info.get('scaling_factors', {})

        # Check time since last scaling with dynamic interval
        time_since_last_scale = time.time() - scaling_data['last_scaling_time']
        # --- Dynamic adaptive scaling interval ---
        volatility = self.market_analyzer.get_recent_volatility(symbol) if hasattr(self.market_analyzer, 'get_recent_volatility') else 20
        trend_confidence = self.signal_analyzer.get_trend_confidence(symbol) if hasattr(self.signal_analyzer, 'get_trend_confidence') else 0.8
        adaptive_interval = self.compute_dynamic_scaling_interval(signal_strength, volatility, trend_confidence)

        if time_since_last_scale < adaptive_interval:
            logger.info(f"⏱ Waiting before scaling again (elapsed: {time_since_last_scale:.1f}s, required: {adaptive_interval:.1f}s)")
            return {'action': 'hold', 'reason': 'too_soon_since_last_scale'}

        # Check max time since entry (dynamic based on market conditions)
        dynamic_max_time = config.get_dynamic_scaling_max_time_since_entry(signal_strength, atr_value, trend_confidence)
        if position_age > dynamic_max_time:
            return {'action': 'hold', 'reason': 'too_old_for_scaling'}

        # Check max additional positions
        if scaling_data['additional_positions'] >= self.config.MAX_ADDITIONAL_POSITIONS:
            return {'action': 'hold', 'reason': 'max_additional_positions_reached'}

        # Check total exposure limit
        total_exposure = scaling_data['total_volume'] * position.price_open
        max_exposure = scaling_data['original_volume'] * position.price_open * self.config.BASE_MAX_TOTAL_EXPOSURE_MULTIPLIER
        if total_exposure >= max_exposure:
            return {'action': 'hold', 'reason': 'max_exposure_reached'}

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
            additional_lots = max(additional_lots, self.config.MIN_LOT_SIZE)
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

    def should_open_new_position(self, signal_strength, trend_score, news_score, spread):
        """
        Determines if a new position should be opened based on dynamic scaling logic.
        This method implements the discretionary trader behavior for position sizing.

        Args:
            signal_strength (float): Current signal strength (0-100)
            trend_score (float): Current trend score (0-100)
            news_score (float): Current news sentiment score (-1 to 1)
            spread (float): Current spread in points

        Returns:
            dict: Decision with 'should_open', 'max_positions', 'reason'
        """
        import config

        # Check if dynamic scaling is enabled
        if not config.ADAPTIVE_SCALING_ENABLED:
            return {
                'should_open': True,
                'max_positions': config.MAX_CONCURRENT_POSITIONS,
                'reason': 'scaling_disabled'
            }

        current_positions = len(self.get_open_positions())
        current_time = time.time()

        # Immediate execution on 100% signal with favorable conditions
        if signal_strength >= 100:
            if trend_score > 60 and news_score > -0.1 and spread < 30:
                logger.info(f"Immediate execution: 100% signal with favorable conditions (trend:{trend_score}, news:{news_score}, spread:{spread})")
                return {
                    'should_open': True,
                    'max_positions': config.MAX_CONCURRENT_POSITIONS,
                    'reason': 'immediate_100pct_favorable'
                }

        # Gradual scaling on mixed conditions with persistence
        if signal_strength >= 90:
            # Check signal persistence
            if self.signal_persistence_counter >= config.CONFIRMATION_CANDLE_WINDOW:
                # Check cooldown
                if current_time - self.last_scaling_time >= config.SCALING_DELAY_SECONDS:
                    # Allow expansion up to dynamic limit
                    max_allowed = min(config.DYNAMIC_SCALING_EXPAND_LIMIT, config.MAX_CONCURRENT_POSITIONS)
                    if current_positions < max_allowed:
                        logger.info(f"Gradual scaling: {self.signal_persistence_counter} persistent signals, expanding to {max_allowed}")
                        return {
                            'should_open': True,
                            'max_positions': max_allowed,
                            'reason': 'gradual_scaling_persistence'
                        }

        # Reset persistence counter if signal weakens
        if signal_strength < config.SIGNAL_PERSISTENCE_THRESHOLD * 100:
            if self.signal_persistence_counter > 0:
                logger.info(f"Signal persistence reset: strength {signal_strength} < threshold {config.SIGNAL_PERSISTENCE_THRESHOLD * 100}")
            self.signal_persistence_counter = 0

        return {
            'should_open': False,
            'max_positions': current_positions,
            'reason': 'conditions_not_met'
        }

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

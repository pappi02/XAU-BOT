import time
from logger_config import setup_logger

logger = setup_logger()
MAGIC = 987654321

class TradeExecutor:
    def __init__(self, mt5_module, config, risk_manager):
        self.mt5 = mt5_module
        self.config = config
        self.risk_manager = risk_manager

    def _place_market_order(self, symbol, is_buy, volume, sl_price, tp_price):
        # Check if auto-trading is enabled
        terminal_info = self.mt5.terminal_info()
        if terminal_info is None or not terminal_info.trade_allowed:
            raise RuntimeError("Auto-trading is disabled in MetaTrader 5 terminal. Please enable it in Tools > Options > Expert Advisors.")

        order_type = self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL
        # price to send
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
            # result is a struct; check retcode
            try:
                retcode = result.retcode
            except Exception:
                retcode = None

            if retcode == self.mt5.TRADE_RETCODE_DONE or getattr(result, "retcode", 0) == 10009:
                logger.info(f"Order success: {result}")
                return result
            else:
                logger.warning(f"Order attempt {attempt+1} failed: {result}")
                last_err = result
                time.sleep(1)  # small wait before retry

        # after retries
        raise RuntimeError(f"Order failed after retries: {last_err}")

    def enter_trade(self, symbol, signal, entry_price, stop_price, tp_price=None):
        is_buy = signal.upper() == "BUY"
        # compute lot based on stop and entry
        lots = self.risk_manager.compute_lot_size(stop_price, entry_price)
        if lots is None or lots <= 0:
            raise RuntimeError("Cannot compute valid lot size; aborting trade")

        # check risk/circuit breakers
        if not self.risk_manager.enough_balance():
            raise RuntimeError("Account balance too low to enter trade")
        if not self.risk_manager.check_daily_loss_limit():
            raise RuntimeError("Daily loss limit reached; aborting trades")
        if self.risk_manager.current_open_positions_count(symbol) >= self.config.MAX_CONCURRENT_POSITIONS:
            raise RuntimeError("Max concurrent positions reached")

        # Place order
        logger.info(f"Placing {'BUY' if is_buy else 'SELL'} {lots} lots @ {entry_price}, SL={stop_price}, TP={tp_price}")
        result = self._place_market_order(symbol, is_buy, lots, stop_price, tp_price)
        return result

    def close_all_positions(self, symbol):
        positions = self.mt5.positions_get(symbol=symbol)
        if not positions:
            logger.info("No positions to close")
            return
        for pos in positions:
            ticket = pos.ticket
            volume = pos.volume
            is_buy = pos.type == self.mt5.POSITION_TYPE_BUY
            # create opposite order to close
            order_type = self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY
            tick = self.mt5.symbol_info_tick(symbol)
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
                "comment": "Close by bot",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }
            res = self.mt5.order_send(req)
            logger.info(f"Close position result: {res}")

    def close_position_by_ticket(self, ticket):
        """Close a specific position by ticket number."""
        positions = self.mt5.positions_get(ticket=ticket)
        if not positions:
            logger.warning(f"No position found with ticket {ticket}")
            return False

        pos = positions[0]
        volume = pos.volume
        is_buy = pos.type == self.mt5.POSITION_TYPE_BUY
        symbol = pos.symbol

        # create opposite order to close
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
            "comment": "Manual close from dashboard",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        res = self.mt5.order_send(req)
        if res.retcode == self.mt5.TRADE_RETCODE_DONE:
            logger.info(f"Successfully closed position {ticket}: {res}")
            return True
        else:
            logger.error(f"Failed to close position {ticket}: {res}")
            return False

    def close_profitable_positions(self, symbol):
        """Close all profitable positions for the given symbol."""
        positions = self.mt5.positions_get(symbol=symbol)
        if not positions:
            logger.info("No positions to close")
            return 0

        closed_count = 0
        for pos in positions:
            if pos.profit > 0:
                if self.close_position_by_ticket(pos.ticket):
                    closed_count += 1
        logger.info(f"Closed {closed_count} profitable positions for {symbol}")
        return closed_count

    def close_loss_positions(self, symbol):
        """Close all loss positions for the given symbol."""
        positions = self.mt5.positions_get(symbol=symbol)
        if not positions:
            logger.info("No positions to close")
            return 0

        closed_count = 0
        for pos in positions:
            if pos.profit < 0:
                if self.close_position_by_ticket(pos.ticket):
                    closed_count += 1
        logger.info(f"Closed {closed_count} loss positions for {symbol}")
        return closed_count

    def close_buy_positions(self, symbol):
        """Close all buy positions for the given symbol."""
        positions = self.mt5.positions_get(symbol=symbol)
        if not positions:
            logger.info("No positions to close")
            return 0

        closed_count = 0
        for pos in positions:
            if pos.type == self.mt5.POSITION_TYPE_BUY:
                if self.close_position_by_ticket(pos.ticket):
                    closed_count += 1
        logger.info(f"Closed {closed_count} buy positions for {symbol}")
        return closed_count

    def close_sell_positions(self, symbol):
        """Close all sell positions for the given symbol."""
        positions = self.mt5.positions_get(symbol=symbol)
        if not positions:
            logger.info("No positions to close")
            return 0

        closed_count = 0
        for pos in positions:
            if pos.type == self.mt5.POSITION_TYPE_SELL:
                if self.close_position_by_ticket(pos.ticket):
                    closed_count += 1
        logger.info(f"Closed {closed_count} sell positions for {symbol}")
        return closed_count

    def should_close_trade(self, position, current_data, strategy, news_sentiment, atr_value=None, entry_atr=None):
        """
        Comprehensive auto-close logic implementing 13 factors for automatic trade closure.

        Args:
            position: MT5 position object
            current_data: Current market data (DataFrame with indicators)
            strategy: Trading strategy instance
            news_sentiment: Current news sentiment ('bullish', 'bearish', 'neutral')
            atr_value: Current ATR value
            entry_atr: ATR value at position entry

        Returns:
            dict: Close decision with reason and details
        """
        import config
        import time
        from datetime import datetime

        if not config.AUTO_CLOSE_ENABLED:
            return {'should_close': False, 'reason': 'auto_close_disabled'}

        position_type = 'BUY' if position.type == self.mt5.POSITION_TYPE_BUY else 'SELL'
        current_price = current_data['close'].iloc[-1] if len(current_data) > 0 else position.price_current
        position_age = int(time.time() - position.time)
        unrealized_profit = position.profit

        # Get signal information
        signal_info = strategy.generate_signal(current_data)
        current_signal = signal_info['signal']
        signal_strength = signal_info['strength']

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

        # 4. Opposite Signal Trigger
        if self._check_opposite_signal(position_type, current_signal, signal_strength):
            close_checks.append({'factor': 'opposite_signal', 'should_close': True})

        # 5. Signal Weakening
        if self._check_signal_weakening(position, current_data, strategy):
            close_checks.append({'factor': 'signal_weakening', 'should_close': True})

        # 6. News/Economic Event Risk
        if self._check_news_economic_event(position_type, news_sentiment):
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

        # 14. Trend Reversal (additional check)
        if config.TREND_REVERSAL_CLOSE and reversal_info['reversal_detected']:
            if position_type == 'BUY' and reversal_info['direction'] == 'bullish_to_bearish':
                close_checks.append({'factor': 'trend_reversal', 'should_close': True})
            elif position_type == 'SELL' and reversal_info['direction'] == 'bearish_to_bullish':
                close_checks.append({'factor': 'trend_reversal', 'should_close': True})

        # Determine if any factor triggered close
        triggered_factors = [check for check in close_checks if check['should_close']]

        if triggered_factors:
            return {
                'should_close': True,
                'reason': triggered_factors[0]['factor'],  # Return first triggered factor
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
        """Check if take profit level is reached."""
        if position.tp == 0:  # No TP set
            return False

        if position.type == self.mt5.POSITION_TYPE_BUY:
            return current_price >= position.tp
        else:  # SELL
            return current_price <= position.tp

    def _check_stop_loss_hit(self, position, current_price):
        """Check if stop loss level is hit."""
        if position.sl == 0:  # No SL set
            return False

        if position.type == self.mt5.POSITION_TYPE_BUY:
            return current_price <= position.sl
        else:  # SELL
            return current_price >= position.sl

    def _check_trailing_stop(self, position, current_price):
        """Check trailing stop conditions."""
        import config

        # Calculate profit in pips
        if position.type == self.mt5.POSITION_TYPE_BUY:
            profit_pips = (current_price - position.price_open) / self.config.CONTRACT_SIZE * 100000  # Assuming 5-digit broker
        else:
            profit_pips = (position.price_open - current_price) / self.config.CONTRACT_SIZE * 100000

        # Check if profit exceeds trail start threshold
        if profit_pips > config.TRAIL_START_PIPS:
            # Calculate new trailing stop
            trail_distance = config.TRAIL_DISTANCE_PIPS / 100000 * self.config.CONTRACT_SIZE  # Convert pips to price

            if position.type == self.mt5.POSITION_TYPE_BUY:
                new_sl = current_price - trail_distance
                return position.sl == 0 or new_sl > position.sl  # Move SL up
            else:
                new_sl = current_price + trail_distance
                return position.sl == 0 or new_sl < position.sl  # Move SL down

        return False

    def _check_opposite_signal(self, position_type, current_signal, signal_strength):
        """Check for strong opposite signal."""
        import config

        if signal_strength >= config.SIGNAL_REVERSAL_THRESHOLD:
            if position_type == 'BUY' and current_signal == 'SELL':
                return True
            elif position_type == 'SELL' and current_signal == 'BUY':
                return True

        return False

    def _check_signal_weakening(self, position, current_data, strategy):
        """Check if signal strength has weakened significantly."""
        import config

        # This would require tracking initial signal strength at entry
        # For now, check if current signal strength is below threshold
        signal_info = strategy.generate_signal(current_data)
        current_strength = signal_info['strength']

        return current_strength < config.SIGNAL_WEAKENING_THRESHOLD

    def _check_news_economic_event(self, position_type, news_sentiment):
        """Check news sentiment adverse to position."""
        import config

        if not config.NEWS_SENTIMENT_CLOSE:
            return False

        if position_type == 'BUY' and news_sentiment == 'bearish':
            return True
        elif position_type == 'SELL' and news_sentiment == 'bullish':
            return True

        return False

    def _check_volatility_spike(self, current_atr, entry_atr):
        """Check for volatility spike using ATR."""
        import config

        if current_atr is None or entry_atr is None or entry_atr == 0:
            return False

        return current_atr > entry_atr * config.ATR_SPIKE_MULTIPLIER

    def _check_time_based_exit(self, position_age):
        """Check time-based exit conditions."""
        import config

        return position_age > config.MAX_POSITION_AGE

    def _check_market_session_end(self):
        """Check if approaching market session end."""
        import config
        from datetime import datetime, time

        if not config.SESSION_END_CLOSE:
            return False

        # Simple check for weekend close (Friday 22:00 UTC)
        now = datetime.utcnow()
        if now.weekday() == 4 and now.time() >= time(22 - config.SESSION_END_BUFFER_MINUTES // 60, 0):
            return True

        return False

    def _check_break_of_structure(self, current_data, position_type):
        """Check for break of key support/resistance structure."""
        import config

        if len(current_data) < config.FRACTAL_PERIOD * 2:
            return False

        # Simple fractal-based structure detection
        recent_highs = current_data['high'].tail(config.FRACTAL_PERIOD * 2).max()
        recent_lows = current_data['low'].tail(config.FRACTAL_PERIOD * 2).min()
        current_price = current_data['close'].iloc[-1]

        if position_type == 'BUY' and current_price < recent_lows:
            return True  # Broke below support
        elif position_type == 'SELL' and current_price > recent_highs:
            return True  # Broke above resistance

        return False

    def _check_rr_ratio_reversal(self, position, unrealized_profit):
        """Check risk/reward ratio reversal."""
        import config

        if not config.RR_REVERSAL_ENABLED:
            return False

        # Calculate potential max profit (would need to track this at entry)
        # For now, use a simple heuristic
        max_profit = abs(position.price_open - position.sl) * config.TP_RISK_REWARD * position.volume * 100000

        if max_profit > 0 and unrealized_profit < max_profit * config.RR_REVERSAL_THRESHOLD:
            return True

        return False

    def _check_portfolio_drawdown(self):
        """Check portfolio/account drawdown levels."""
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
        """Check for correlation conflicts with other positions."""
        import config

        # Get all positions
        positions = self.mt5.positions_get()
        if not positions:
            return False

        # Count positions in same symbol or correlated symbols
        symbol_positions = [p for p in positions if p.symbol == symbol]
        correlated_positions = [p for p in positions if p.symbol != symbol]  # Would need correlation matrix

        total_positions = len(symbol_positions) + len(correlated_positions)

        return total_positions > config.MAX_CORRELATED_POSITIONS

# Legacy functions for backward compatibility
def execute_trade(symbol, signal, volume=0.02, magic=123456, comment="XAUUSD Auto Bot"):
    """
    Legacy function - use TradeExecutor class instead
    """
    logger.warning("execute_trade is deprecated; use TradeExecutor class")
    return False

def close_position(symbol, position_ticket=None, volume=None):
    """
    Legacy function - use TradeExecutor.close_all_positions instead
    """
    logger.warning("close_position is deprecated; use TradeExecutor.close_all_positions")
    return False

def get_open_positions(symbol=None):
    """
    Legacy function - kept for compatibility
    """
    import MetaTrader5 as mt5
    if not mt5.initialize():
        return []

    try:
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        return positions if positions else []

    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return []

if __name__ == "__main__":
    # Test trade execution (requires MT5 to be running)
    print("Testing trade executor...")

    # This would require MT5 to be connected
    # executor = TradeExecutor(mt5, config, risk_manager)
    # executor.enter_trade("XAUUSD", "BUY", 1800, 1790, 1820)
    print("Trade executor functions defined. Connect to MT5 to test.")

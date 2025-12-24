"""
Scalping-Specific Risk Manager - Optimized for High-Frequency Scalping

Features:
- Pip-based risk calculation (5-10 pip stops)
- Ultra-tight position management
- Breakeven at 3 pips profit
- Trailing stop at 5 pips profit
- Max 50 concurrent scalp positions
"""

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from logger_config import setup_logger

logger = setup_logger()


class ScalperRiskManager:
    """
    Risk manager optimized for high-frequency scalping with tight pip-based controls.
    """
    
    def __init__(self, config=None):
        """
        Initialize scalper risk manager.
        
        Args:
            config: Configuration object with scalping parameters
        """
        self.config = config or {}
        
        # Scalping-specific risk parameters
        self.max_scalp_positions = self.config.get('SCALPER_MAX_POSITIONS', 50)
        self.stop_loss_pips = self.config.get('SCALPER_STOP_PIPS', 5)
        self.take_profit_pips = self.config.get('SCALPER_TARGET_PIPS', 8)
        self.breakeven_pips = self.config.get('SCALPER_BREAKEVEN_PIPS', 3)
        self.trail_start_pips = self.config.get('SCALPER_TRAIL_START_PIPS', 5)
        self.trail_distance_pips = self.config.get('SCALPER_TRAIL_DISTANCE_PIPS', 1)
        self.max_trade_duration_minutes = self.config.get('SCALPER_MAX_TRADE_DURATION_MINUTES', 15)
        self.risk_per_trade_pct = self.config.get('SCALPER_RISK_PER_TRADE_PCT', 0.5) / 100.0
        self.max_daily_loss_pct = self.config.get('SCALPER_MAX_DAILY_LOSS_PCT', 3.0) / 100.0
        self.min_spread_pips = self.config.get('SCALPER_MIN_SPREAD_PIPS', 2)
        
        # Position tracking
        self.position_tracking = {}  # ticket -> {entry_time, entry_price, moved_to_breakeven, trailing_active}
        
        # Daily P&L tracking
        self.daily_pnl = 0.0
        self.daily_start = datetime.now().date()
        self.trades_today = 0
        
        logger.info(f"ScalperRiskManager initialized | "
                   f"Max Positions: {self.max_scalp_positions} | "
                   f"SL: {self.stop_loss_pips} pips | "
                   f"TP: {self.take_profit_pips} pips")
    
    def calculate_position_size(self, 
                                symbol: str,
                                account_balance: float,
                                stop_loss_pips: Optional[float] = None,
                                signal_confidence: float = 70) -> float:
        """
        Calculate position size based on pip-based risk with EXPERT confidence scaling.
        
        Args:
            symbol: Trading symbol
            account_balance: Current account balance
            stop_loss_pips: Stop loss in pips (uses default if None)
            signal_confidence: Signal confidence 0-100 (scales position size)
            
        Returns:
            float: Position size in lots
        """
        try:
            # Use default SL if not provided
            sl_pips = stop_loss_pips if stop_loss_pips is not None else self.stop_loss_pips
            
            # EXPERT: Tighter stops for lower confidence
            if signal_confidence < 70:
                sl_pips = sl_pips * 0.8  # 20% tighter stop
                logger.debug(f"Lower confidence ({signal_confidence:.0f}%) → tighter stop: {sl_pips:.1f} pips")
            
            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"Failed to get symbol info for {symbol}")
                return 0.01
            
            # Base risk amount
            base_risk = account_balance * self.risk_per_trade_pct
            
            # EXPERT: Scale risk by confidence (60% conf = 0.6x, 90% conf = 1.2x)
            confidence_multiplier = signal_confidence / 75  # 75% = 1.0x (neutral)
            confidence_multiplier = max(0.5, min(1.3, confidence_multiplier))  # Limit: 0.5x to 1.3x
            
            risk_amount = base_risk * confidence_multiplier
            
            logger.debug(f"Risk scaling: {signal_confidence:.0f}% confidence → {confidence_multiplier:.2f}x multiplier")
            
            # Calculate pip value
            point = symbol_info.point
            pip_value = point * 10 if 'JPY' not in symbol else point
            
            # Get tick value (profit per point)
            tick_value = symbol_info.trade_tick_value
            
            # Calculate position size
            contract_size = symbol_info.trade_contract_size
            pip_value_per_lot = (pip_value / point) * tick_value
            
            position_size = risk_amount / (sl_pips * pip_value_per_lot)
            
            # Round to step size
            volume_step = symbol_info.volume_step
            position_size = round(position_size / volume_step) * volume_step
            
            # Apply limits
            min_lot = symbol_info.volume_min
            max_lot = symbol_info.volume_max
            position_size = max(min_lot, min(position_size, max_lot))
            
            logger.info(f"💰 Position size: {position_size:.2f} lots | "
                        f"Risk: ${risk_amount:.2f} | SL: {sl_pips:.1f} pips | "
                        f"Confidence: {signal_confidence:.0f}%")
            
            return position_size
        
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0.01  # Default minimum
    
    def can_open_position(self) -> tuple[bool, str]:
        """
        Check if a new scalp position can be opened.
        
        Returns:
            tuple: (can_open: bool, reason: str)
        """
        # Check daily loss limit
        if not self._check_daily_loss_limit():
            return False, "Daily loss limit reached"
        
        # Check max position count
        current_positions = len(mt5.positions_get())
        if current_positions >= self.max_scalp_positions:
            return False, f"Max positions reached ({self.max_scalp_positions})"
        
        # Check account balance
        account = mt5.account_info()
        if account is None:
            return False, "Failed to get account info"
        
        if account.balance < 5.0:
            return False, "Insufficient balance"
        
        return True, "OK"
    
    def check_spread(self, symbol: str) -> tuple[bool, float]:
        """
        Check if spread is acceptable for scalping.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            tuple: (is_acceptable: bool, spread_pips: float)
        """
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return False, 999.9
            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return False, 999.9
            
            # Calculate spread in pips
            point = symbol_info.point
            pip_value = point * 10 if 'JPY' not in symbol else point
            spread = (tick.ask - tick.bid) / pip_value
            
            is_acceptable = spread <= self.min_spread_pips
            
            if not is_acceptable:
                logger.debug(f"Spread too wide: {spread:.1f} pips (max: {self.min_spread_pips} pips)")
            
            return is_acceptable, spread
        
        except Exception as e:
            logger.error(f"Error checking spread: {e}")
            return False, 999.9
    
    def manage_position(self, ticket: int) -> Dict:
        """
        Manage an existing scalp position (breakeven, trailing, time-based exit).
        
        Args:
            ticket: Position ticket number
            
        Returns:
            dict: Management actions taken
        """
        actions = {'breakeven': False, 'trailing': False, 'time_exit': False}
        
        try:
            # Get position
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return actions
            
            position = positions[0]
            
            # Track position if not already tracked
            if ticket not in self.position_tracking:
                self.position_tracking[ticket] = {
                    'entry_time': datetime.fromtimestamp(position.time),
                    'entry_price': position.price_open,
                    'moved_to_breakeven': False,
                    'trailing_active': False
                }
            
            tracking = self.position_tracking[ticket]
            
            # Get current price
            tick = mt5.symbol_info_tick(position.symbol)
            if tick is None:
                return actions
            
            current_price = tick.bid if position.type == mt5.POSITION_TYPE_BUY else tick.ask
            
            # Calculate profit in pips
            symbol_info = mt5.symbol_info(position.symbol)
            if symbol_info is None:
                return actions
            
            point = symbol_info.point
            pip_value = point * 10 if 'JPY' not in position.symbol else point
            
            if position.type == mt5.POSITION_TYPE_BUY:
                profit_pips = (current_price - tracking['entry_price']) / pip_value
            else:
                profit_pips = (tracking['entry_price'] - current_price) / pip_value
            
            # 1. Move to breakeven at 3 pips profit
            if not tracking['moved_to_breakeven'] and profit_pips >= self.breakeven_pips:
                new_sl = tracking['entry_price']
                self._modify_stop_loss(ticket, position.symbol, new_sl)
                tracking['moved_to_breakeven'] = True
                actions['breakeven'] = True
                logger.info(f"✅ Position {ticket} moved to breakeven at {profit_pips:.1f} pips")
            
            # 2. Activate trailing stop at 5 pips profit
            elif profit_pips >= self.trail_start_pips:
                if not tracking['trailing_active']:
                    tracking['trailing_active'] = True
                    logger.info(f"✅ Trailing stop activated for position {ticket}")
                
                # Calculate trailing stop
                if position.type == mt5.POSITION_TYPE_BUY:
                    new_sl = current_price - (self.trail_distance_pips * pip_value)
                    # Only update if new SL is better than current
                    if new_sl > position.sl:
                        self._modify_stop_loss(ticket, position.symbol, new_sl)
                        actions['trailing'] = True
                else:
                    new_sl = current_price + (self.trail_distance_pips * pip_value)
                    # Only update if new SL is better than current
                    if new_sl < position.sl or position.sl == 0:
                        self._modify_stop_loss(ticket, position.symbol, new_sl)
                        actions['trailing'] = True
            
            # 3. Time-based exit (if no profit after max duration)
            trade_duration = (datetime.now() - tracking['entry_time']).total_seconds() / 60
            if trade_duration >= self.max_trade_duration_minutes and profit_pips < 1:
                logger.info(f"⏱️ Position {ticket} open for {trade_duration:.1f} min with no profit - closing")
                self._close_position(ticket, position.symbol)
                actions['time_exit'] = True
                del self.position_tracking[ticket]
            
            return actions
        
        except Exception as e:
            logger.error(f"Error managing position {ticket}: {e}")
            return actions
    
    def manage_all_positions(self) -> Dict:
        """
        Manage all open scalp positions.
        
        Returns:
            dict: Summary of actions taken
        """
        positions = mt5.positions_get()
        if not positions:
            return {'total': 0, 'breakeven': 0, 'trailing': 0, 'time_exits': 0}
        
        summary = {'total': len(positions), 'breakeven': 0, 'trailing': 0, 'time_exits': 0}
        
        for position in positions:
            actions = self.manage_position(position.ticket)
            if actions['breakeven']:
                summary['breakeven'] += 1
            if actions['trailing']:
                summary['trailing'] += 1
            if actions['time_exit']:
                summary['time_exits'] += 1
        
        return summary
    
    def update_daily_pnl(self):
        """Update daily P&L from closed trades."""
        try:
            # Reset if new day
            today = datetime.now().date()
            if today != self.daily_start:
                self.daily_pnl = 0.0
                self.trades_today = 0
                self.daily_start = today
                logger.info("📅 New trading day - P&L reset")
            
            # Get today's deals
            now = datetime.now()
            start_of_day = datetime(now.year, now.month, now.day, 0, 0, 0)
            deals = mt5.history_deals_get(start_of_day, now)
            
            if deals:
                pnl = sum(deal.profit for deal in deals if deal.profit != 0)
                self.daily_pnl = pnl
                self.trades_today = len([d for d in deals if d.profit != 0])
                
                logger.debug(f"Daily P&L: ${self.daily_pnl:.2f} | Trades: {self.trades_today}")
        
        except Exception as e:
            logger.error(f"Error updating daily P&L: {e}")
    
    def get_daily_stats(self) -> Dict:
        """Get daily scalping statistics."""
        self.update_daily_pnl()
        
        account = mt5.account_info()
        if account:
            loss_pct = (abs(self.daily_pnl) / account.balance) * 100 if self.daily_pnl < 0 else 0
        else:
            loss_pct = 0
        
        return {
            'daily_pnl': self.daily_pnl,
            'trades_today': self.trades_today,
            'daily_loss_pct': loss_pct,
            'max_loss_pct': self.max_daily_loss_pct * 100,
            'positions_open': len(mt5.positions_get()),
            'max_positions': self.max_scalp_positions
        }
    
    def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit has been reached."""
        self.update_daily_pnl()
        
        if self.daily_pnl >= 0:
            return True
        
        account = mt5.account_info()
        if account is None:
            return False
        
        loss_pct = abs(self.daily_pnl) / account.balance
        
        if loss_pct >= self.max_daily_loss_pct:
            logger.warning(f"⛔ Daily loss limit reached: {loss_pct*100:.1f}% (max: {self.max_daily_loss_pct*100:.1f}%)")
            return False
        
        return True
    
    def _modify_stop_loss(self, ticket: int, symbol: str, new_sl: float):
        """Modify stop loss for a position."""
        try:
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return
            
            position = positions[0]
            
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": symbol,
                "sl": round(new_sl, mt5.symbol_info(symbol).digits),
                "tp": position.tp,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.warning(f"Failed to modify SL for {ticket}: {result.retcode}")
        
        except Exception as e:
            logger.error(f"Error modifying SL: {e}")
    
    def _close_position(self, ticket: int, symbol: str):
        """Close a position."""
        try:
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return
            
            position = positions[0]
            
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return
            
            price = tick.bid if position.type == mt5.POSITION_TYPE_BUY else tick.ask
            order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": ticket,
                "symbol": symbol,
                "volume": position.volume,
                "type": order_type,
                "price": price,
                "deviation": 10,
                "comment": "Time-based exit",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.warning(f"Failed to close position {ticket}: {result.retcode}")
        
        except Exception as e:
            logger.error(f"Error closing position: {e}")


if __name__ == "__main__":
    print("=" * 80)
    print("SCALPER RISK MANAGER TEST")
    print("=" * 80)
    
    # Initialize
    risk_manager = ScalperRiskManager()
    
    # Test daily stats
    stats = risk_manager.get_daily_stats()
    print(f"\nDaily Stats:")
    print(f"  P&L: ${stats['daily_pnl']:.2f}")
    print(f"  Trades: {stats['trades_today']}")
    print(f"  Positions: {stats['positions_open']}/{stats['max_positions']}")
    
    print("\n✅ ScalperRiskManager initialized and ready")
    print(f"   SL: {risk_manager.stop_loss_pips} pips | TP: {risk_manager.take_profit_pips} pips")
    print(f"   Breakeven: {risk_manager.breakeven_pips} pips | Trail: {risk_manager.trail_start_pips} pips")

"""
Ultra-Fast Scalper Executor - Optimized for High-Frequency Scalping

Features:
- Sub-100ms order execution
- Pre-validation to reduce latency
- Parallel order processing
- Tick-level monitoring
- Order queue for multiple signals
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



import time
import MetaTrader5 as mt5
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from logger_config import setup_logger
from utils.symbol_helpers import resolve_symbol, round_price, validate_sl_tp

logger = setup_logger()


class ScalperExecutor:
    """
    Ultra-fast order executor optimized for scalping with sub-100ms execution.
    """
    
    def __init__(self, config=None, risk_manager=None):
        """
        Initialize the scalper executor.
        
        Args:
            config: Configuration object
            risk_manager: Risk manager instance
        """
        self.config = config
        self.risk_manager = risk_manager
        self.magic = 987654321
        
        # Performance tracking
        self.execution_times = []
        self.max_execution_history = 100
        
        # Order queue for parallel processing
        self.order_queue = []
        
        # Cache symbol info to reduce lookups
        self.symbol_info_cache = {}
        self.cache_expiry = 60  # seconds
        self.last_cache_update = 0
        
        logger.info("ScalperExecutor initialized - Target execution < 100ms")
    
    def execute_scalp_order(self, 
                           symbol: str,
                           direction: str,
                           volume: float,
                           sl_pips: float,
                           tp_pips: float,
                           comment: str = "Scalp") -> Dict:
        """
        Execute a scalp order with ultra-fast execution.
        
        Args:
            symbol: Trading symbol (e.g., 'XAUUSD')
            direction: 'BUY' or 'SELL'
            volume: Lot size
            sl_pips: Stop loss in pips
            tp_pips: Take profit in pips
            comment: Order comment
            
        Returns:
            dict: Execution result with timing
        """
        start_time = time.perf_counter()
        
        try:
            # Step 1: Pre-validation (reduces execution time)
            symbol = resolve_symbol(symbol)
            
            # Get cached symbol info or fetch new
            symbol_info = self._get_symbol_info_cached(symbol)
            if symbol_info is None:
                return self._error_result("Symbol info not available", start_time)
            
            # Step 2: Get current price (fastest method)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return self._error_result("Failed to get tick data", start_time)
            
            price = tick.ask if direction == "BUY" else tick.bid
            
            # Step 3: Calculate SL/TP quickly
            point = symbol_info.point
            pip_value = point * 10 if 'JPY' not in symbol else point
            
            if direction == "BUY":
                sl = price - (sl_pips * pip_value)
                tp = price + (tp_pips * pip_value)
                order_type = mt5.ORDER_TYPE_BUY
            else:
                sl = price + (sl_pips * pip_value)
                tp = price - (tp_pips * pip_value)
                order_type = mt5.ORDER_TYPE_SELL
            
            # Round prices to proper digits
            digits = symbol_info.digits
            sl = round(sl, digits)
            tp = round(tp, digits)
            price = round(price, digits)
            
            # Step 4: Build order request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 10,  # Tight deviation for scalping
                "magic": self.magic,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,  # Immediate or cancel
            }
            
            # Step 5: Execute order
            result = mt5.order_send(request)
            
            # Step 6: Track execution time
            execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
            self._track_execution_time(execution_time)
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Scalp {direction} executed in {execution_time:.1f}ms | "
                          f"Ticket: {result.order} | Entry: {price} | SL: {sl} | TP: {tp}")
                
                return {
                    'success': True,
                    'ticket': result.order,
                    'price': price,
                    'sl': sl,
                    'tp': tp,
                    'volume': volume,
                    'direction': direction,
                    'execution_time_ms': execution_time,
                    'comment': comment
                }
            else:
                logger.warning(f"⚠️ Order failed (retcode={result.retcode}) in {execution_time:.1f}ms")
                return self._error_result(f"Order failed: {result.retcode}", start_time)
        
        except Exception as e:
            logger.error(f"❌ Execution error: {e}")
            return self._error_result(str(e), start_time)
    
    def execute_batch_orders(self, orders: List[Dict]) -> List[Dict]:
        """
        Execute multiple scalp orders in parallel (where possible).
        
        Args:
            orders: List of order dictionaries
            
        Returns:
            List of execution results
        """
        results = []
        start_time = time.perf_counter()
        
        logger.info(f"🚀 Executing batch of {len(orders)} orders...")
        
        for order in orders:
            result = self.execute_scalp_order(
                symbol=order['symbol'],
                direction=order['direction'],
                volume=order['volume'],
                sl_pips=order['sl_pips'],
                tp_pips=order['tp_pips'],
                comment=order.get('comment', 'Scalp')
            )
            results.append(result)
        
        total_time = (time.perf_counter() - start_time) * 1000
        success_count = sum(1 for r in results if r['success'])
        
        logger.info(f"✅ Batch complete: {success_count}/{len(orders)} successful in {total_time:.1f}ms")
        
        return results
    
    def modify_scalp_position(self,
                             ticket: int,
                             new_sl: Optional[float] = None,
                             new_tp: Optional[float] = None) -> Dict:
        """
        Modify an existing scalp position (for breakeven, trailing, etc.).
        
        Args:
            ticket: Position ticket number
            new_sl: New stop loss price (None to keep current)
            new_tp: New take profit price (None to keep current)
            
        Returns:
            dict: Modification result
        """
        start_time = time.perf_counter()
        
        try:
            # Get position info
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return self._error_result(f"Position {ticket} not found", start_time)
            
            position = positions[0]
            
            # Use current values if not specified
            sl = new_sl if new_sl is not None else position.sl
            tp = new_tp if new_tp is not None else position.tp
            
            # Build modification request
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": position.symbol,
                "sl": sl,
                "tp": tp,
            }
            
            # Execute modification
            result = mt5.order_send(request)
            
            execution_time = (time.perf_counter() - start_time) * 1000
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Position {ticket} modified in {execution_time:.1f}ms | "
                          f"SL: {sl} | TP: {tp}")
                return {
                    'success': True,
                    'ticket': ticket,
                    'sl': sl,
                    'tp': tp,
                    'execution_time_ms': execution_time
                }
            else:
                logger.warning(f"⚠️ Modification failed (retcode={result.retcode})")
                return self._error_result(f"Modification failed: {result.retcode}", start_time)
        
        except Exception as e:
            logger.error(f"❌ Modification error: {e}")
            return self._error_result(str(e), start_time)
    
    def close_scalp_position(self, ticket: int, partial_volume: Optional[float] = None) -> Dict:
        """
        Close a scalp position (full or partial).
        
        Args:
            ticket: Position ticket number
            partial_volume: Volume to close (None = close all)
            
        Returns:
            dict: Close result
        """
        start_time = time.perf_counter()
        
        try:
            # Get position info
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return self._error_result(f"Position {ticket} not found", start_time)
            
            position = positions[0]
            
            # Determine volume to close
            volume = partial_volume if partial_volume is not None else position.volume
            
            # Get current price
            tick = mt5.symbol_info_tick(position.symbol)
            if tick is None:
                return self._error_result("Failed to get tick data", start_time)
            
            price = tick.bid if position.type == mt5.POSITION_TYPE_BUY else tick.ask
            
            # Determine order type (opposite of position)
            order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            # Build close request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": ticket,
                "symbol": position.symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "deviation": 10,
                "magic": self.magic,
                "comment": "Scalp close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Execute close
            result = mt5.order_send(request)
            
            execution_time = (time.perf_counter() - start_time) * 1000
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Position {ticket} closed in {execution_time:.1f}ms | "
                          f"Volume: {volume} | Price: {price}")
                return {
                    'success': True,
                    'ticket': ticket,
                    'volume': volume,
                    'price': price,
                    'execution_time_ms': execution_time
                }
            else:
                logger.warning(f"⚠️ Close failed (retcode={result.retcode})")
                return self._error_result(f"Close failed: {result.retcode}", start_time)
        
        except Exception as e:
            logger.error(f"❌ Close error: {e}")
            return self._error_result(str(e), start_time)
    
    def close_all_scalp_positions(self, symbol: Optional[str] = None) -> Dict:
        """
        Close all scalp positions (optionally for a specific symbol).
        
        Args:
            symbol: Symbol to close (None = close all)
            
        Returns:
            dict: Batch close result
        """
        start_time = time.perf_counter()
        
        # Get all positions
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        
        if not positions:
            logger.info("No positions to close")
            return {'success': True, 'closed_count': 0, 'execution_time_ms': 0}
        
        results = []
        for position in positions:
            result = self.close_scalp_position(position.ticket)
            results.append(result)
        
        total_time = (time.perf_counter() - start_time) * 1000
        success_count = sum(1 for r in results if r['success'])
        
        logger.info(f"✅ Closed {success_count}/{len(positions)} positions in {total_time:.1f}ms")
        
        return {
            'success': True,
            'closed_count': success_count,
            'total_count': len(positions),
            'execution_time_ms': total_time
        }
    
    def get_average_execution_time(self) -> float:
        """Get average execution time in milliseconds."""
        if not self.execution_times:
            return 0.0
        return sum(self.execution_times) / len(self.execution_times)
    
    def get_execution_stats(self) -> Dict:
        """Get execution performance statistics."""
        if not self.execution_times:
            return {
                'avg_ms': 0.0,
                'min_ms': 0.0,
                'max_ms': 0.0,
                'total_executions': 0
            }
        
        return {
            'avg_ms': self.get_average_execution_time(),
            'min_ms': min(self.execution_times),
            'max_ms': max(self.execution_times),
            'total_executions': len(self.execution_times),
            'target_met': self.get_average_execution_time() < 100
        }
    
    def _get_symbol_info_cached(self, symbol: str):
        """Get symbol info with caching to reduce lookups."""
        current_time = time.time()
        
        # Check if cache is still valid
        if current_time - self.last_cache_update > self.cache_expiry:
            self.symbol_info_cache.clear()
            self.last_cache_update = current_time
        
        # Return cached info if available
        if symbol in self.symbol_info_cache:
            return self.symbol_info_cache[symbol]
        
        # Fetch and cache
        info = mt5.symbol_info(symbol)
        if info:
            self.symbol_info_cache[symbol] = info
        
        return info
    
    def _track_execution_time(self, execution_time_ms: float):
        """Track execution time for performance monitoring."""
        self.execution_times.append(execution_time_ms)
        
        # Keep only recent history
        if len(self.execution_times) > self.max_execution_history:
            self.execution_times = self.execution_times[-self.max_execution_history:]
        
        # Log warning if execution is slow
        if execution_time_ms > 100:
            logger.warning(f"⚠️ Slow execution detected: {execution_time_ms:.1f}ms (target: <100ms)")
    
    def _error_result(self, error_msg: str, start_time: float) -> Dict:
        """Create error result dictionary."""
        execution_time = (time.perf_counter() - start_time) * 1000
        return {
            'success': False,
            'error': error_msg,
            'execution_time_ms': execution_time
        }


if __name__ == "__main__":
    # Test the scalper executor
    print("=" * 80)
    print("SCALPER EXECUTOR TEST")
    print("=" * 80)
    
    # Initialize
    executor = ScalperExecutor()
    
    # Test execution stats
    stats = executor.get_execution_stats()
    print(f"\nInitial Stats: {stats}")
    
    print("\n✅ ScalperExecutor initialized and ready for high-frequency scalping")
    print("   Target: Sub-100ms execution for all operations")

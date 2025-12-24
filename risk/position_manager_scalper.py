"""
Multi-Position Manager for High-Frequency Scalping

Handles 50+ concurrent positions with:
- Position clustering by direction/correlation
- Risk balancing across all positions
- Coordinated exits for related positions
- Performance tracking per position cluster
- Exposure limits by position group
"""

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from logger_config import setup_logger
from collections import defaultdict
import numpy as np

logger = setup_logger()


class PositionManagerScalper:
    """
    Advanced position manager for high-frequency scalping with 50+ positions.
    
    Features:
    - Cluster positions by direction, entry time, strategy
    - Limit correlation exposure (don't overload one direction)
    - Coordinated exits (close related positions together)
    - Performance analytics per cluster
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize scalper position manager.
        
        Args:
            config: Configuration with position limits
        """
        self.config = config or {}
        
        # Position limits
        self.max_total_positions = self.config.get('max_positions', 50)
        self.max_same_direction = self.config.get('max_same_direction', 30)
        self.max_cluster_size = 10  # Max positions in one time cluster
        
        # Clustering parameters
        self.cluster_time_window_minutes = 5  # Positions within 5min = same cluster
        
        # Exposure management
        self.max_exposure_ratio = 0.7  # Max 70% exposure in one direction
        
        # Performance tracking
        self.position_clusters = {}  # {cluster_id: [position_tickets]}
        self.cluster_stats = defaultdict(lambda: {
            'total_profit': 0,
            'closed_count': 0,
            'avg_hold_time': 0
        })
        
        logger.info("PositionManagerScalper initialized")
        logger.info(f"  Max positions: {self.max_total_positions}")
        logger.info(f"  Max same direction: {self.max_same_direction}")
    
    def can_open_new_position(self, signal_direction: int, strategy: str = None) -> tuple[bool, str]:
        """
        Check if a new position can be opened based on exposure limits.
        
        Args:
            signal_direction: 1 (BUY) or -1 (SELL)
            strategy: Strategy name (optional)
            
        Returns:
            (can_open: bool, reason: str)
        """
        # Get all open positions
        positions = mt5.positions_get(symbol="XAUUSD")
        if positions is None:
            return True, "No positions open"
        
        # Total position limit
        if len(positions) >= self.max_total_positions:
            return False, f"Max total positions reached ({self.max_total_positions})"
        
        # Same direction limit
        same_direction_count = sum(1 for p in positions if p.type == (mt5.ORDER_TYPE_BUY if signal_direction == 1 else mt5.ORDER_TYPE_SELL))
        if same_direction_count >= self.max_same_direction:
            return False, f"Max same direction positions reached ({self.max_same_direction})"
        
        # Exposure ratio check
        buy_count = sum(1 for p in positions if p.type == mt5.ORDER_TYPE_BUY)
        sell_count = sum(1 for p in positions if p.type == mt5.ORDER_TYPE_SELL)
        total = len(positions)
        
        if signal_direction == 1:  # BUY
            new_buy_ratio = (buy_count + 1) / (total + 1)
            if new_buy_ratio > self.max_exposure_ratio:
                return False, f"Would exceed max exposure ratio ({new_buy_ratio:.1%} > {self.max_exposure_ratio:.1%})"
        else:  # SELL
            new_sell_ratio = (sell_count + 1) / (total + 1)
            if new_sell_ratio > self.max_exposure_ratio:
                return False, f"Would exceed max exposure ratio ({new_sell_ratio:.1%} > {self.max_exposure_ratio:.1%})"
        
        return True, "Position allowed"
    
    def cluster_positions(self) -> Dict[str, List]:
        """
        Cluster open positions by entry time, direction, and strategy.
        
        Returns:
            dict: {cluster_id: [positions]}
        """
        positions = mt5.positions_get(symbol="XAUUSD")
        if not positions:
            return {}
        
        clusters = defaultdict(list)
        
        for pos in positions:
            # Create cluster key: direction_timewindow_strategy
            entry_time = datetime.fromtimestamp(pos.time)
            time_window = entry_time.replace(second=0, microsecond=0)
            time_window = time_window - timedelta(minutes=time_window.minute % self.cluster_time_window_minutes)
            
            direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
            strategy = pos.comment if pos.comment else "unknown"
            
            cluster_key = f"{direction}_{time_window.strftime('%H%M')}_{strategy}"
            clusters[cluster_key].append(pos)
        
        self.position_clusters = dict(clusters)
        return self.position_clusters
    
    def get_position_summary(self) -> Dict:
        """
        Get comprehensive summary of all positions.
        
        Returns:
            dict: Position statistics and breakdown
        """
        positions = mt5.positions_get(symbol="XAUUSD")
        if not positions:
            return {
                'total': 0,
                'buy': 0,
                'sell': 0,
                'total_profit': 0,
                'avg_hold_time_minutes': 0,
                'clusters': {}
            }
        
        buy_count = sum(1 for p in positions if p.type == mt5.ORDER_TYPE_BUY)
        sell_count = sum(1 for p in positions if p.type == mt5.ORDER_TYPE_SELL)
        total_profit = sum(p.profit for p in positions)
        
        # Average hold time
        now = datetime.now()
        hold_times = [(now - datetime.fromtimestamp(p.time)).total_seconds() / 60 for p in positions]
        avg_hold_time = np.mean(hold_times) if hold_times else 0
        
        # Cluster positions
        clusters = self.cluster_positions()
        cluster_summary = {}
        for cluster_id, cluster_positions in clusters.items():
            cluster_profit = sum(p.profit for p in cluster_positions)
            cluster_summary[cluster_id] = {
                'count': len(cluster_positions),
                'profit': round(cluster_profit, 2),
                'avg_profit': round(cluster_profit / len(cluster_positions), 2)
            }
        
        return {
            'total': len(positions),
            'buy': buy_count,
            'sell': sell_count,
            'buy_ratio': buy_count / len(positions) if positions else 0,
            'sell_ratio': sell_count / len(positions) if positions else 0,
            'total_profit': round(total_profit, 2),
            'avg_hold_time_minutes': round(avg_hold_time, 1),
            'clusters': cluster_summary,
            'at_capacity': len(positions) >= self.max_total_positions * 0.9  # 90% = near capacity
        }
    
    def close_cluster(self, cluster_id: str, reason: str = "Coordinated exit") -> Dict:
        """
        Close all positions in a cluster.
        
        Args:
            cluster_id: Cluster identifier
            reason: Reason for closing
            
        Returns:
            dict: Close results
        """
        if cluster_id not in self.position_clusters:
            return {'success': False, 'error': 'Cluster not found'}
        
        cluster_positions = self.position_clusters[cluster_id]
        results = []
        total_profit = 0
        
        logger.info(f"Closing cluster '{cluster_id}' ({len(cluster_positions)} positions) - {reason}")
        
        for pos in cluster_positions:
            # Determine close order type
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            # Get current price
            symbol_info = mt5.symbol_info_tick("XAUUSD")
            if not symbol_info:
                logger.error(f"Failed to get price for position {pos.ticket}")
                continue
            
            price = symbol_info.bid if close_type == mt5.ORDER_TYPE_SELL else symbol_info.ask
            
            # Close position
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": "XAUUSD",
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": pos.magic,
                "comment": f"Cluster_close_{reason}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(close_request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                results.append({
                    'ticket': pos.ticket,
                    'success': True,
                    'profit': pos.profit
                })
                total_profit += pos.profit
            else:
                error = result.comment if result else "Unknown error"
                results.append({
                    'ticket': pos.ticket,
                    'success': False,
                    'error': error
                })
        
        success_count = sum(1 for r in results if r.get('success'))
        
        logger.info(f"Cluster close results: {success_count}/{len(cluster_positions)} closed, Total P&L: {total_profit:.2f}")
        
        return {
            'cluster_id': cluster_id,
            'attempted': len(cluster_positions),
            'closed': success_count,
            'failed': len(cluster_positions) - success_count,
            'total_profit': round(total_profit, 2),
            'results': results
        }
    
    def close_losing_positions(self, max_loss_per_position: float = -10.0) -> Dict:
        """
        Close all positions with loss exceeding threshold.
        
        Args:
            max_loss_per_position: Maximum acceptable loss per position
            
        Returns:
            dict: Close results
        """
        positions = mt5.positions_get(symbol="XAUUSD")
        if not positions:
            return {'closed': 0, 'message': 'No positions'}
        
        losing_positions = [p for p in positions if p.profit < max_loss_per_position]
        
        if not losing_positions:
            return {'closed': 0, 'message': 'No positions exceeding loss threshold'}
        
        logger.warning(f"Found {len(losing_positions)} positions with loss > {max_loss_per_position}")
        
        closed_count = 0
        total_loss = 0
        
        for pos in losing_positions:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            symbol_info = mt5.symbol_info_tick("XAUUSD")
            if not symbol_info:
                continue
            
            price = symbol_info.bid if close_type == mt5.ORDER_TYPE_SELL else symbol_info.ask
            
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": "XAUUSD",
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": pos.magic,
                "comment": "Emergency_stop_loss",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(close_request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
                total_loss += pos.profit
        
        logger.warning(f"Emergency close: {closed_count} positions closed, Total loss: {total_loss:.2f}")
        
        return {
            'closed': closed_count,
            'total_loss': round(total_loss, 2),
            'avg_loss': round(total_loss / closed_count, 2) if closed_count > 0 else 0
        }
    
    def rebalance_positions(self, target_ratio: float = 0.5) -> Dict:
        """
        Rebalance position exposure by closing excess positions in one direction.
        
        Args:
            target_ratio: Target BUY ratio (0.5 = 50/50 split)
            
        Returns:
            dict: Rebalance results
        """
        positions = mt5.positions_get(symbol="XAUUSD")
        if not positions or len(positions) < 5:
            return {'rebalanced': False, 'reason': 'Too few positions to rebalance'}
        
        buy_positions = [p for p in positions if p.type == mt5.ORDER_TYPE_BUY]
        sell_positions = [p for p in positions if p.type == mt5.ORDER_TYPE_SELL]
        
        current_buy_ratio = len(buy_positions) / len(positions)
        
        logger.info(f"Current exposure: {current_buy_ratio:.1%} BUY, {1-current_buy_ratio:.1%} SELL")
        
        # Check if rebalancing needed
        if abs(current_buy_ratio - target_ratio) < 0.15:  # Within 15% tolerance
            return {'rebalanced': False, 'reason': 'Already balanced'}
        
        # Determine which side to trim
        if current_buy_ratio > target_ratio:
            # Too many BUYs - close weakest BUY positions
            positions_to_close = sorted(buy_positions, key=lambda p: p.profit)[:5]  # Close 5 weakest
            direction = "BUY"
        else:
            # Too many SELLs - close weakest SELL positions
            positions_to_close = sorted(sell_positions, key=lambda p: p.profit)[:5]
            direction = "SELL"
        
        logger.info(f"Rebalancing: Closing {len(positions_to_close)} {direction} positions")
        
        closed_count = 0
        total_profit = 0
        
        for pos in positions_to_close:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            symbol_info = mt5.symbol_info_tick("XAUUSD")
            if not symbol_info:
                continue
            
            price = symbol_info.bid if close_type == mt5.ORDER_TYPE_SELL else symbol_info.ask
            
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": "XAUUSD",
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": pos.magic,
                "comment": "Rebalance",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(close_request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
                total_profit += pos.profit
        
        logger.info(f"Rebalanced: {closed_count} positions closed, P&L: {total_profit:.2f}")
        
        return {
            'rebalanced': True,
            'closed': closed_count,
            'direction_closed': direction,
            'total_profit': round(total_profit, 2),
            'new_buy_ratio': (len(buy_positions) - (closed_count if direction == "BUY" else 0)) / (len(positions) - closed_count)
        }
    
    def get_performance_by_strategy(self) -> Dict[str, Dict]:
        """
        Get performance breakdown by strategy.
        
        Returns:
            dict: {strategy_name: {count, profit, avg_profit}}
        """
        positions = mt5.positions_get(symbol="XAUUSD")
        if not positions:
            return {}
        
        strategy_stats = defaultdict(lambda: {'count': 0, 'profit': 0})
        
        for pos in positions:
            strategy = pos.comment if pos.comment else "unknown"
            strategy_stats[strategy]['count'] += 1
            strategy_stats[strategy]['profit'] += pos.profit
        
        # Calculate averages
        for strategy, stats in strategy_stats.items():
            stats['avg_profit'] = stats['profit'] / stats['count'] if stats['count'] > 0 else 0
        
        return dict(strategy_stats)


if __name__ == "__main__":
    print("=" * 80)
    print("POSITION MANAGER SCALPER TEST")
    print("=" * 80)
    
    # Initialize MT5
    if not mt5.initialize():
        print("❌ MT5 initialization failed")
        exit()
    
    # Initialize manager
    manager = PositionManagerScalper()
    
    # Test position limits
    print("\n1. Testing position limits:")
    can_open, reason = manager.can_open_new_position(signal_direction=1)
    print(f"  Can open BUY: {can_open} - {reason}")
    
    # Get position summary
    print("\n2. Position summary:")
    summary = manager.get_position_summary()
    print(f"  Total: {summary['total']}")
    print(f"  BUY: {summary['buy']} ({summary['buy_ratio']:.1%})")
    print(f"  SELL: {summary['sell']} ({summary['sell_ratio']:.1%})")
    print(f"  Total P&L: {summary['total_profit']}")
    print(f"  Avg Hold Time: {summary['avg_hold_time_minutes']:.1f} min")
    print(f"  Clusters: {len(summary['clusters'])}")
    
    # Cluster analysis
    print("\n3. Position clusters:")
    clusters = manager.cluster_positions()
    for cluster_id, positions in clusters.items():
        cluster_profit = sum(p.profit for p in positions)
        print(f"  {cluster_id}: {len(positions)} positions, P&L: {cluster_profit:.2f}")
    
    # Strategy performance
    print("\n4. Performance by strategy:")
    strategy_perf = manager.get_performance_by_strategy()
    for strategy, stats in strategy_perf.items():
        print(f"  {strategy}: {stats['count']} positions, Avg P&L: {stats['avg_profit']:.2f}")
    
    mt5.shutdown()
    print("\n✅ Test complete")

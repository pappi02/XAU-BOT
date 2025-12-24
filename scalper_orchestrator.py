"""
Expert Scalper Orchestrator

Master controller that integrates all scalping components:
- FastScalperSignals: Technical indicator signal generation
- ScalperExecutor: Ultra-fast order execution
- ScalperRiskManager: Pip-based risk management  
- PositionManagerScalper: Multi-position coordination
- SessionManager: Session-based optimization

This is the main entry point for professional scalping operations.
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from logger_config import setup_logger
import time

# Import scalping components
from strategies.fast_scalper_signals import FastScalperSignals
from execution.scalper_executor import ScalperExecutor
from risk.scalper_risk_manager import ScalperRiskManager
from risk.position_manager_scalper import PositionManagerScalper
from strategies.session_manager import SessionManager

logger = setup_logger()


class ExpertScalperOrchestrator:
    """
    Professional high-frequency scalping orchestrator.
    
    Target Performance:
    - 50-200 trades per day
    - 70%+ win rate
    - 5-10 pips per trade
    - Sub-100ms execution
    - 50+ concurrent positions
    
    Design:
    - Technical indicators drive signals (RSI, EMA, MACD, Stochastic, BB)
    - Session-aware (London/NY optimization)
    - Multi-position coordination
    - Aggressive but controlled risk
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize expert scalper orchestrator.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Initialize components
        logger.info("Initializing Expert Scalper components...")
        
        self.signal_generator = FastScalperSignals(config)
        self.executor = ScalperExecutor(config)
        self.risk_manager = ScalperRiskManager(config)
        self.position_manager = PositionManagerScalper(config)
        self.session_manager = SessionManager(config)
        
        # Trading parameters (will be adjusted by session)
        self.base_params = {
            'max_positions': self.config.get('max_positions', 50),
            'signal_confidence_threshold': self.config.get('min_confidence', 55),
            'max_spread_pips': self.config.get('max_spread', 2.0),
            'risk_per_trade_pct': self.config.get('risk_per_trade', 0.5)
        }
        
        # Performance tracking
        self.stats = {
            'signals_generated': 0,
            'signals_passed': 0,
            'trades_opened': 0,
            'trades_closed': 0,
            'total_profit': 0,
            'start_time': datetime.now()
        }
        
        # Cooldown to prevent over-trading
        self.last_trade_time = None
        self.min_trade_interval_seconds = self.config.get('min_trade_interval', 10)  # 10s between trades
        
        logger.info("✅ Expert Scalper Orchestrator initialized")
        logger.info(f"  Base max positions: {self.base_params['max_positions']}")
        logger.info(f"  Min confidence: {self.base_params['signal_confidence_threshold']}%")
        logger.info(f"  Max spread: {self.base_params['max_spread_pips']} pips")
    
    def run_trading_cycle(self, data: pd.DataFrame, timeframe: str = 'M1') -> Dict:
        """
        Execute one complete trading cycle.
        
        Steps:
        1. Check session (should we trade?)
        2. Generate signal (technical indicators)
        3. Check risk limits (position count, spread, etc.)
        4. Execute trade if all checks pass
        5. Manage existing positions
        
        Args:
            data: OHLCV DataFrame
            timeframe: 'M1', 'M3', or 'M5'
            
        Returns:
            dict: Cycle results
        """
        cycle_start = time.perf_counter()
        
        # Step 1: Check session
        should_trade, session_reason = self.session_manager.should_trade_in_session()
        current_session = self.session_manager.get_current_session()
        
        if not should_trade:
            logger.info(f"⏸️  Not trading: {session_reason}")
            return {
                'action': 'no_trade',
                'reason': session_reason,
                'session': current_session['name']
            }
        
        # Adjust parameters for session
        session_params = self.session_manager.adjust_parameters_for_session(self.base_params)
        
        # Step 2: Generate signal
        signal = self.signal_generator.generate_signal(data, timeframe)
        self.stats['signals_generated'] += 1
        
        if signal['signal'] == 0:
            # No signal or insufficient confidence
            return {
                'action': 'no_signal',
                'reason': signal.get('reason', 'No signal'),
                'session': current_session['name']
            }
        
        # Check confidence threshold (session-adjusted)
        if signal['confidence'] < session_params['signal_confidence_threshold']:
            logger.info(f"Signal confidence {signal['confidence']:.0f}% below threshold "
                       f"{session_params['signal_confidence_threshold']:.0f}%")
            return {
                'action': 'low_confidence',
                'confidence': signal['confidence'],
                'threshold': session_params['signal_confidence_threshold']
            }
        
        self.stats['signals_passed'] += 1
        
        # Step 3: Risk checks
        
        # 3a. Cooldown check
        if not self._check_cooldown():
            return {
                'action': 'cooldown',
                'reason': f'Must wait {self.min_trade_interval_seconds}s between trades'
            }
        
        # 3b. Position limit check
        can_open, limit_reason = self.position_manager.can_open_new_position(
            signal_direction=signal['signal']
        )
        if not can_open:
            logger.warning(f"Position limit reached: {limit_reason}")
            return {
                'action': 'position_limit',
                'reason': limit_reason
            }
        
        # 3c. Spread check
        spread_ok, spread_value = self.risk_manager.check_spread(
            max_spread_pips=session_params['max_spread_pips']
        )
        if not spread_ok:
            logger.warning(f"Spread too wide: {spread_value:.1f} pips")
            return {
                'action': 'spread_too_wide',
                'spread': spread_value,
                'max_allowed': session_params['max_spread_pips']
            }
        
        # 3d. Daily loss limit check
        can_trade, loss_reason = self.risk_manager.can_open_position()
        if not can_trade:
            logger.error(f"Daily loss limit: {loss_reason}")
            return {
                'action': 'daily_loss_limit',
                'reason': loss_reason
            }
        
        # Step 4: Calculate position size
        sl_pips = abs(signal['entry'] - signal['sl']) / 0.1  # XAUUSD: 1 pip = 0.1
        position_size = self.risk_manager.calculate_position_size(
            sl_pips=sl_pips,
            risk_pct=session_params['risk_per_trade_pct']
        )
        
        if position_size == 0:
            return {
                'action': 'zero_position_size',
                'reason': 'Risk calculation resulted in 0 lots'
            }
        
        # Step 5: Execute trade
        logger.info(f"🚀 Executing {signal['signal']} signal | "
                   f"Confidence: {signal['confidence']:.0f}% | "
                   f"Confluences: {len(signal['confluences'])}")
        
        order_result = self.executor.execute_scalp_order(
            signal_direction=signal['signal'],
            entry_price=signal['entry'],
            sl_price=signal['sl'],
            tp_price=signal['tp'],
            volume=position_size,
            comment=f"Scalp_{current_session['key']}"
        )
        
        if order_result['success']:
            self.stats['trades_opened'] += 1
            self.last_trade_time = time.time()
            
            logger.info(f"✅ Trade opened | Ticket: {order_result['ticket']} | "
                       f"Size: {position_size} | Exec time: {order_result['execution_time_ms']:.1f}ms")
        else:
            logger.error(f"❌ Trade failed: {order_result['error']}")
        
        cycle_time = (time.perf_counter() - cycle_start) * 1000
        
        return {
            'action': 'trade_executed' if order_result['success'] else 'trade_failed',
            'signal': signal,
            'order_result': order_result,
            'position_size': position_size,
            'session': current_session['name'],
            'cycle_time_ms': round(cycle_time, 1)
        }
    
    def manage_positions(self) -> Dict:
        """
        Manage all open positions (trailing stops, breakeven, time exits).
        
        Returns:
            dict: Management results
        """
        positions = mt5.positions_get(symbol="XAUUSD")
        if not positions:
            return {'managed': 0, 'message': 'No positions'}
        
        logger.info(f"Managing {len(positions)} positions...")
        
        # Use risk manager to manage all positions
        results = self.risk_manager.manage_all_positions()
        
        # Update stats
        self.stats['trades_closed'] += results.get('closed', 0)
        
        # Get position summary
        summary = self.position_manager.get_position_summary()
        
        logger.info(f"Position management complete:")
        logger.info(f"  Breakeven set: {results.get('breakeven_set', 0)}")
        logger.info(f"  Trailing updated: {results.get('trailing_updated', 0)}")
        logger.info(f"  Time exits: {results.get('time_exits', 0)}")
        logger.info(f"  Current P&L: {summary['total_profit']:.2f}")
        
        return {
            'managed': len(positions),
            'breakeven_set': results.get('breakeven_set', 0),
            'trailing_updated': results.get('trailing_updated', 0),
            'time_exits': results.get('time_exits', 0),
            'total_profit': summary['total_profit'],
            'position_count': summary['total']
        }
    
    def get_performance_stats(self) -> Dict:
        """
        Get comprehensive performance statistics.
        
        Returns:
            dict: Performance metrics
        """
        # Calculate runtime
        runtime = datetime.now() - self.stats['start_time']
        runtime_hours = runtime.total_seconds() / 3600
        
        # Get position summary
        position_summary = self.position_manager.get_position_summary()
        
        # Get executor stats
        executor_stats = self.executor.get_execution_stats()
        
        # Calculate rates
        signal_pass_rate = (self.stats['signals_passed'] / self.stats['signals_generated'] * 100) if self.stats['signals_generated'] > 0 else 0
        trades_per_hour = self.stats['trades_opened'] / runtime_hours if runtime_hours > 0 else 0
        
        return {
            'runtime': str(runtime).split('.')[0],  # Remove microseconds
            'runtime_hours': round(runtime_hours, 2),
            'signals_generated': self.stats['signals_generated'],
            'signals_passed': self.stats['signals_passed'],
            'signal_pass_rate': round(signal_pass_rate, 1),
            'trades_opened': self.stats['trades_opened'],
            'trades_closed': self.stats['trades_closed'],
            'trades_per_hour': round(trades_per_hour, 1),
            'open_positions': position_summary['total'],
            'total_profit': position_summary['total_profit'],
            'avg_execution_time_ms': executor_stats.get('avg_time_ms', 0),
            'current_session': self.session_manager.get_current_session()['name']
        }
    
    def _check_cooldown(self) -> bool:
        """Check if enough time has passed since last trade."""
        if self.last_trade_time is None:
            return True
        
        elapsed = time.time() - self.last_trade_time
        return elapsed >= self.min_trade_interval_seconds
    
    def emergency_close_all(self, reason: str = "Emergency") -> Dict:
        """
        Emergency close all positions.
        
        Args:
            reason: Reason for emergency close
            
        Returns:
            dict: Close results
        """
        logger.critical(f"🚨 EMERGENCY CLOSE ALL: {reason}")
        
        result = self.executor.close_all_scalp_positions(reason=reason)
        
        logger.critical(f"Emergency close complete: {result.get('closed', 0)} positions closed")
        
        return result


if __name__ == "__main__":
    import numpy as np
    
    print("=" * 80)
    print("EXPERT SCALPER ORCHESTRATOR TEST")
    print("=" * 80)
    
    # Initialize MT5
    if not mt5.initialize():
        print("❌ MT5 initialization failed")
        exit()
    
    # Create test config
    test_config = {
        'max_positions': 50,
        'min_confidence': 55,
        'max_spread': 2.0,
        'risk_per_trade': 0.5,
        'min_trade_interval': 10
    }
    
    # Initialize orchestrator
    orchestrator = ExpertScalperOrchestrator(test_config)
    
    # Create test data
    dates = pd.date_range('2024-01-01', periods=100, freq='1min')
    prices = 2050 + np.cumsum(np.random.randn(100) * 0.5)
    
    test_data = pd.DataFrame({
        'open': prices + np.random.randn(100) * 0.2,
        'high': prices + abs(np.random.randn(100) * 0.5),
        'low': prices - abs(np.random.randn(100) * 0.5),
        'close': prices,
        'volume': np.random.randint(1000, 5000, 100)
    }, index=dates)
    
    print("\n1. Running trading cycle:")
    cycle_result = orchestrator.run_trading_cycle(test_data, timeframe='M1')
    print(f"  Action: {cycle_result['action']}")
    print(f"  Session: {cycle_result.get('session', 'N/A')}")
    if 'signal' in cycle_result:
        print(f"  Signal confidence: {cycle_result['signal']['confidence']:.0f}%")
    
    print("\n2. Managing positions:")
    manage_result = orchestrator.manage_positions()
    print(f"  Managed: {manage_result['managed']}")
    print(f"  Breakeven set: {manage_result.get('breakeven_set', 0)}")
    print(f"  Trailing updated: {manage_result.get('trailing_updated', 0)}")
    
    print("\n3. Performance stats:")
    stats = orchestrator.get_performance_stats()
    print(f"  Runtime: {stats['runtime']}")
    print(f"  Signals generated: {stats['signals_generated']}")
    print(f"  Trades opened: {stats['trades_opened']}")
    print(f"  Trades per hour: {stats['trades_per_hour']}")
    print(f"  Open positions: {stats['open_positions']}")
    print(f"  Avg execution time: {stats['avg_execution_time_ms']:.1f}ms")
    print(f"  Current session: {stats['current_session']}")
    
    mt5.shutdown()
    print("\n✅ Test complete")

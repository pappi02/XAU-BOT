"""
Expert Scalper Main Runner

High-frequency scalping bot for XAUUSD focused on technical indicators.

Performance Targets:
- 50-200 trades/day
- 70%+ win rate
- 5-10 pips per trade
- Sub-100ms execution

Run: python run_expert_scalper.py
"""

import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
from logger_config import setup_logger
from scalper_orchestrator import ExpertScalperOrchestrator
from data.fetch_candles import fetch_ohlcv

logger = setup_logger()


class ExpertScalperRunner:
    """Main runner for expert scalping bot."""
    
    def __init__(self, config: dict = None):
        """
        Initialize scalper runner.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or self._default_config()
        
        # Initialize MT5
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            raise Exception("Failed to initialize MT5")
        
        logger.info("MT5 initialized successfully")
        logger.info(f"Connected to account: {mt5.account_info().login}")
        
        # Initialize orchestrator
        self.orchestrator = ExpertScalperOrchestrator(self.config)
        
        # Trading parameters
        self.symbol = "XAUUSD"
        self.timeframe = self.config.get('timeframe', 'M1')
        self.mt5_timeframe = mt5.PERIOD_M1  # M1 for scalping
        
        # Loop parameters
        self.check_interval_seconds = self.config.get('check_interval', 30)  # Check every 30s
        self.position_management_interval = self.config.get('management_interval', 60)  # Manage every 60s
        
        # State
        self.last_position_management = time.time()
        self.running = False
        
        logger.info("Expert Scalper Runner initialized")
        logger.info(f"  Symbol: {self.symbol}")
        logger.info(f"  Timeframe: {self.timeframe}")
        logger.info(f"  Check interval: {self.check_interval_seconds}s")
    
    def _default_config(self) -> dict:
        """Get default configuration."""
        return {
            'max_positions': 50,
            'min_confidence': 55,  # Lower for more signals
            'max_spread': 2.0,
            'risk_per_trade': 0.5,
            'min_trade_interval': 10,  # 10s between trades
            'timeframe': 'M1',
            'check_interval': 30,  # Check for signals every 30s
            'management_interval': 60  # Manage positions every 60s
        }
    
    def start(self):
        """Start the scalping bot."""
        self.running = True
        
        logger.info("=" * 80)
        logger.info("🚀 EXPERT SCALPER STARTED")
        logger.info("=" * 80)
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Max positions: {self.config['max_positions']}")
        logger.info("=" * 80)
        
        try:
            while self.running:
                cycle_start = time.time()
                
                # Fetch latest data
                data = self._fetch_data()
                
                if data is None or len(data) < 50:
                    logger.warning("Insufficient data, skipping cycle")
                    time.sleep(self.check_interval_seconds)
                    continue
                
                # Run trading cycle
                cycle_result = self.orchestrator.run_trading_cycle(data, self.timeframe)
                
                # Log cycle result
                self._log_cycle_result(cycle_result)
                
                # Manage positions periodically
                if time.time() - self.last_position_management > self.position_management_interval:
                    self.orchestrator.manage_positions()
                    self.last_position_management = time.time()
                
                # Print stats every 10 cycles (5 minutes if checking every 30s)
                if self.orchestrator.stats['signals_generated'] % 10 == 0:
                    self._print_stats()
                
                # Calculate sleep time to maintain interval
                cycle_time = time.time() - cycle_start
                sleep_time = max(0, self.check_interval_seconds - cycle_time)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            logger.info("\n⏸️  Keyboard interrupt received")
            self.stop()
        
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            logger.exception("Exception details:")
            self.stop()
    
    def stop(self):
        """Stop the bot gracefully."""
        logger.info("=" * 80)
        logger.info("🛑 STOPPING EXPERT SCALPER")
        logger.info("=" * 80)
        
        self.running = False
        
        # Final stats
        self._print_stats()
        
        # Ask about closing positions
        print("\nClose all open positions? (y/n): ", end='')
        try:
            response = input().strip().lower()
            if response == 'y':
                logger.info("Closing all positions...")
                result = self.orchestrator.emergency_close_all(reason="Bot stopped")
                logger.info(f"Closed {result.get('closed', 0)} positions")
        except:
            pass
        
        # Shutdown MT5
        mt5.shutdown()
        logger.info("✅ Expert Scalper stopped")
    
    def _fetch_data(self) -> pd.DataFrame:
        """Fetch latest OHLCV data."""
        try:
            rates = mt5.copy_rates_from_pos(self.symbol, self.mt5_timeframe, 0, 100)
            
            if rates is None or len(rates) == 0:
                logger.error("Failed to fetch rates from MT5")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Rename columns
            df.rename(columns={
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'tick_volume': 'volume'
            }, inplace=True)
            
            return df[['open', 'high', 'low', 'close', 'volume']]
        
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return None
    
    def _log_cycle_result(self, result: dict):
        """Log trading cycle result."""
        action = result.get('action')
        
        if action == 'trade_executed':
            logger.info(f"✅ Trade executed | Session: {result['session']} | "
                       f"Cycle time: {result['cycle_time_ms']:.1f}ms")
        elif action == 'trade_failed':
            logger.error(f"❌ Trade failed | Reason: {result['order_result'].get('error')}")
        elif action in ['no_signal', 'low_confidence']:
            logger.debug(f"No trade: {result.get('reason', action)}")
        elif action in ['position_limit', 'spread_too_wide', 'cooldown', 'daily_loss_limit']:
            logger.warning(f"⚠️  {action}: {result.get('reason', 'N/A')}")
    
    def _print_stats(self):
        """Print performance statistics."""
        stats = self.orchestrator.get_performance_stats()
        
        print("\n" + "=" * 80)
        print("📊 PERFORMANCE STATISTICS")
        print("=" * 80)
        print(f"Runtime:              {stats['runtime']}")
        print(f"Current Session:      {stats['current_session']}")
        print(f"Signals Generated:    {stats['signals_generated']}")
        print(f"Signals Passed:       {stats['signals_passed']} ({stats['signal_pass_rate']:.1f}%)")
        print(f"Trades Opened:        {stats['trades_opened']}")
        print(f"Trades Per Hour:      {stats['trades_per_hour']:.1f}")
        print(f"Open Positions:       {stats['open_positions']}")
        print(f"Total P&L:            ${stats['total_profit']:.2f}")
        print(f"Avg Execution Time:   {stats['avg_execution_time_ms']:.1f}ms")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                  EXPERT SCALPER BOT                       ║
    ║                                                           ║
    ║  High-Frequency Technical Indicator Scalping for XAUUSD  ║
    ║                                                           ║
    ║  Targets: 50-200 trades/day | 70%+ win rate             ║
    ║           5-10 pips/trade | <100ms execution            ║
    ║                                                           ║
    ║  Press Ctrl+C to stop                                    ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Configuration (can be loaded from config.yaml or config.py)
    config = {
        'max_positions': 50,
        'min_confidence': 55,
        'max_spread': 2.0,
        'risk_per_trade': 0.5,
        'min_trade_interval': 10,
        'timeframe': 'M1',
        'check_interval': 30,
        'management_interval': 60
    }
    
    # Create and start runner
    runner = ExpertScalperRunner(config)
    runner.start()

"""
Expert Scalper Backtest

Backtests the new expert scalper system with:
- FastScalperSignals (technical indicators)
- Pip-based risk management
- Session-aware trading
- High-frequency signal generation
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import json

from strategies.fast_scalper_signals import FastScalperSignals
from strategies.session_manager import SessionManager
from logger_config import setup_logger

logger = setup_logger()


class ExpertScalperBacktest:
    """Backtest for expert scalper system."""
    
    def __init__(self, initial_balance: float = 10000, config: dict = None):
        """
        Initialize backtest.
        
        Args:
            initial_balance: Starting balance in USD
            config: Scalper configuration
        """
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        
        self.config = config or {
            'max_positions': 50,
            'min_confidence': 55,
            'signal_confidence_threshold': 55,  # Base threshold (session manager will adjust)
            'max_spread': 2.0,
            'risk_per_trade': 0.5,
            'min_trade_interval': 10,
            'backtest_mode': True,  # Enable backtest mode
            'session_filter_enabled': False  # Disable session filters for backtest
        }
        
        # Initialize components
        # Default to BALANCED for higher trade count/profit; strict is opt-in via config
        if self.config.get('quality_mode') is None:
            self.config['quality_mode'] = 'balanced'
        if self.config.get('quality_mode') == 'strict':
            self.config.setdefault('strict_min_confidence', 60)
            self.config.setdefault('strict_min_trend_strength', 0.55)
            self.config.setdefault('strict_sr_proximity_pips', 2.0)
            self.config.setdefault('strict_min_confluences', 2)
            self.config.setdefault('strict_tp_atr_multiplier', 1.0)
        self.signal_generator = FastScalperSignals(self.config)
        self.session_manager = SessionManager(self.config)
        
        # Trading state
        self.positions = []  # Open positions
        self.closed_trades = []  # Completed trades
        self.equity_curve = []
        
        # Statistics
        self.stats = {
            'signals_generated': 0,
            'signals_passed': 0,
            'trades_opened': 0,
            'trades_closed': 0,
            'winners': 0,
            'losers': 0,
            'breakeven': 0
        }
        
        logger.info("Expert Scalper Backtest initialized")
        logger.info(f"  Initial balance: ${initial_balance:,.2f}")
        logger.info(f"  Min confidence: {self.config['min_confidence']}%")
    
    def run(self, data: pd.DataFrame, timeframe: str = 'M5') -> Dict:
        """
        Run backtest on historical data.
        
        Args:
            data: OHLCV DataFrame with datetime index
            timeframe: Timeframe (M1, M3, M5)
            
        Returns:
            dict: Backtest results
        """
        logger.info("=" * 80)
        logger.info("EXPERT SCALPER BACKTEST STARTED")
        logger.info("=" * 80)
        logger.info(f"Data: {len(data)} candles from {data.index[0]} to {data.index[-1]}")
        logger.info(f"Timeframe: {timeframe}")
        
        # Ensure we have enough data for indicators
        if len(data) < 50:
            logger.error("Insufficient data (need at least 50 candles)")
            return {'error': 'Insufficient data'}
        
        # Iterate through data
        for i in range(50, len(data)):
            # Get data window for signal generation
            window_data = data.iloc[:i+1]
            current_candle = data.iloc[i]
            current_time = current_candle.name
            current_close = current_candle['close']
            
            # Update positions (check SL/TP/time exits)
            self._update_positions(current_candle, current_time)
            
            # Record equity
            self._record_equity(current_time)
            
            # Check if we should trade in this session (pass 0 confidence for now, will check later)
            strict_filter = self.config.get('strict_session_filter', False)
            should_trade, session_reason = self.session_manager.should_trade_in_session(
                current_time, 
                signal_confidence=0,  # Will check actual signal confidence later
                strict_filter=strict_filter
            )
            current_session = self.session_manager.get_current_session(current_time)
            
            # Adjust parameters for session
            session_params = self.session_manager.adjust_parameters_for_session(self.config)
            
            # Generate signal
            signal = self.signal_generator.generate_signal(window_data, timeframe)
            self.stats['signals_generated'] += 1
            
            # Log HOLD signals to understand filtering
            if signal['signal'] == 0:
                logger.info(
                    f"HOLD: {signal.get('reason', 'No reason')} | "
                    f"Conf: {signal.get('confidence', 0):.0f}% | "
                    f"Confluences: {len(signal.get('confluences', []))}"
                )
                continue
            
            # Check confidence threshold (session-adjusted)
            threshold = session_params.get('signal_confidence_threshold', session_params.get('min_confidence', self.config['min_confidence']))
            if signal['confidence'] < threshold:
                logger.info(
                    f"Rejected: confidence {signal['confidence']:.0f}% < threshold {threshold:.0f}% | "
                    f"Confluences: {len(signal.get('confluences', []))} | "
                    f"Reason: {signal.get('reason', '')}"
                )
                continue
            
            self.stats['signals_passed'] += 1
            
            # Check if we can open position
            if not should_trade:
                logger.info(f"Skipped by session gate: {session_reason}")
                continue
            
            if len(self.positions) >= session_params['max_positions']:
                logger.info(
                    f"Skipped: position cap reached ({len(self.positions)}/{session_params['max_positions']})"
                )
                continue
            
            # Calculate position size
            sl_pips = abs(signal['entry'] - signal['sl']) / 0.1  # XAUUSD pip = 0.1
            risk_pct = session_params.get('risk_per_trade_pct', session_params.get('risk_per_trade', self.config['risk_per_trade']))
            position_size = self._calculate_position_size(sl_pips, risk_pct)
            
            if position_size == 0:
                logger.info("Skipped: position size computed as 0 (risk too low or SL too large)")
                continue
            
            # Open position
            logger.info(
                f"OPEN {('BUY' if signal['signal'] == 1 else 'SELL')} @ {signal['entry']:.2f} | "
                f"SL: {signal['sl']:.2f} | TP: {signal['tp']:.2f} | "
                f"Size: {position_size} | Conf: {signal['confidence']:.0f}% | "
                f"Confluences: {len(signal.get('confluences', []))}"
            )
            self._open_position(
                entry_time=current_time,
                direction=signal['signal'],
                entry_price=signal['entry'],
                sl_price=signal['sl'],
                tp_price=signal['tp'],
                volume=position_size,
                signal_confidence=signal['confidence'],
                confluences=signal['confluences'],
                session=current_session['key']
            )
        
        # Close remaining positions at end
        for pos in self.positions[:]:
            self._close_position(pos, data.iloc[-1]['close'], data.index[-1], 'Backtest end')
        
        # Generate results
        results = self._generate_results(data)
        
        logger.info("=" * 80)
        logger.info("BACKTEST COMPLETED")
        logger.info("=" * 80)
        
        return results
    
    def _calculate_position_size(self, sl_pips: float, risk_pct: float) -> float:
        """Calculate position size based on risk."""
        risk_amount = self.balance * (risk_pct / 100)
        
        # XAUUSD: 1 pip = 0.1, 0.01 lot = $0.10 per pip
        pip_value_per_lot = 10  # $10 per pip for 0.01 lot
        
        position_size = (risk_amount / sl_pips) / pip_value_per_lot
        position_size = round(position_size, 2)
        
        # Min 0.01, max based on balance
        position_size = max(0.01, min(position_size, self.balance / 1000))
        
        return position_size
    
    def _open_position(self, entry_time, direction, entry_price, sl_price, tp_price, 
                       volume, signal_confidence, confluences, session):
        """Open a new position."""
        position = {
            'id': len(self.closed_trades) + len(self.positions) + 1,
            'entry_time': entry_time,
            'direction': 'BUY' if direction == 1 else 'SELL',
            'entry_price': entry_price,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'volume': volume,
            'confidence': signal_confidence,
            'confluences': confluences,
            'session': session,
            'breakeven_set': False,
            'trailing_active': False
        }
        
        self.positions.append(position)
        self.stats['trades_opened'] += 1
        
        logger.debug(f"Opened {position['direction']} @ {entry_price:.2f} | "
                    f"SL: {sl_price:.2f} | TP: {tp_price:.2f} | "
                    f"Size: {volume} | Conf: {signal_confidence:.0f}%")
    
    def _update_positions(self, candle, current_time):
        """Update positions - check SL/TP/breakeven/trailing."""
        for pos in self.positions[:]:
            current_high = candle['high']
            current_low = candle['low']
            current_close = candle['close']
            
            # Calculate current profit in pips
            if pos['direction'] == 'BUY':
                profit_pips = (current_close - pos['entry_price']) / 0.1
            else:
                profit_pips = (pos['entry_price'] - current_close) / 0.1
            
            # Check stop loss
            if pos['direction'] == 'BUY':
                if current_low <= pos['sl_price']:
                    self._close_position(pos, pos['sl_price'], current_time, 'SL')
                    continue
            else:
                if current_high >= pos['sl_price']:
                    self._close_position(pos, pos['sl_price'], current_time, 'SL')
                    continue
            
            # Check take profit
            if pos['direction'] == 'BUY':
                if current_high >= pos['tp_price']:
                    self._close_position(pos, pos['tp_price'], current_time, 'TP')
                    continue
            else:
                if current_low <= pos['tp_price']:
                    self._close_position(pos, pos['tp_price'], current_time, 'TP')
                    continue
            
            # Breakeven management (at 3 pips profit)
            if not pos['breakeven_set'] and profit_pips >= 3:
                pos['sl_price'] = pos['entry_price']
                pos['breakeven_set'] = True
                logger.debug(f"Position #{pos['id']}: Breakeven set")
            
            # Trailing stop (at 5 pips profit, trail by 1 pip)
            if profit_pips >= 5:
                if not pos['trailing_active']:
                    pos['trailing_active'] = True
                
                # Update trailing stop
                if pos['direction'] == 'BUY':
                    new_sl = current_close - 0.1  # 1 pip trail
                    if new_sl > pos['sl_price']:
                        pos['sl_price'] = new_sl
                else:
                    new_sl = current_close + 0.1
                    if new_sl < pos['sl_price']:
                        pos['sl_price'] = new_sl
            
            # Time-based exit (15 minutes if no profit)
            time_in_trade = (current_time - pos['entry_time']).total_seconds() / 60
            if time_in_trade >= 15 and profit_pips < 2:
                self._close_position(pos, current_close, current_time, 'Time exit')
    
    def _close_position(self, position, exit_price, exit_time, reason):
        """Close a position."""
        # Calculate P&L
        if position['direction'] == 'BUY':
            pips = (exit_price - position['entry_price']) / 0.1
        else:
            pips = (position['entry_price'] - exit_price) / 0.1
        
        # Calculate P&L in USD (0.01 lot = $0.10 per pip)
        pnl = pips * position['volume'] * 10
        
        # Update balance
        self.balance += pnl
        
        # Record trade
        trade = {
            'id': position['id'],
            'entry_time': position['entry_time'],
            'exit_time': exit_time,
            'direction': position['direction'],
            'entry_price': position['entry_price'],
            'exit_price': exit_price,
            'sl_price': position['sl_price'],
            'tp_price': position['tp_price'],
            'volume': position['volume'],
            'pips': pips,
            'pnl': pnl,
            'reason': reason,
            'confidence': position['confidence'],
            'confluences': position['confluences'],
            'session': position['session'],
            'duration_minutes': (exit_time - position['entry_time']).total_seconds() / 60
        }
        
        self.closed_trades.append(trade)
        self.positions.remove(position)
        self.stats['trades_closed'] += 1
        
        if pnl > 0.5:
            self.stats['winners'] += 1
        elif pnl < -0.5:
            self.stats['losers'] += 1
        else:
            self.stats['breakeven'] += 1
        
        logger.debug(f"Closed {position['direction']} @ {exit_price:.2f} | "
                    f"Pips: {pips:.1f} | P&L: ${pnl:.2f} | Reason: {reason}")
    
    def _record_equity(self, timestamp):
        """Record current equity."""
        # Calculate unrealized P&L
        unrealized = 0
        for pos in self.positions:
            # Estimate current price (use last known close)
            # In real backtest, we'd use current candle close
            pass
        
        self.equity = self.balance + unrealized
        self.equity_curve.append({
            'time': timestamp,
            'balance': self.balance,
            'equity': self.equity,
            'positions': len(self.positions)
        })
    
    def _generate_results(self, data) -> Dict:
        """Generate comprehensive backtest results."""
        total_trades = len(self.closed_trades)
        
        if total_trades == 0:
            return {
                'error': 'No trades executed',
                'stats': self.stats
            }
        
        # Calculate metrics
        total_pnl = sum(t['pnl'] for t in self.closed_trades)
        total_pips = sum(t['pips'] for t in self.closed_trades)
        
        winning_trades = [t for t in self.closed_trades if t['pnl'] > 0.5]
        losing_trades = [t for t in self.closed_trades if t['pnl'] < -0.5]
        
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0
        
        profit_factor = (abs(sum(t['pnl'] for t in winning_trades)) / 
                        abs(sum(t['pnl'] for t in losing_trades))) if losing_trades and sum(t['pnl'] for t in losing_trades) != 0 else 0
        
        # Max drawdown
        equity_values = [e['equity'] for e in self.equity_curve]
        running_max = np.maximum.accumulate(equity_values)
        drawdowns = (equity_values - running_max) / running_max
        max_drawdown = np.min(drawdowns) * 100 if len(drawdowns) > 0 else 0
        
        # Session performance
        session_stats = {}
        for trade in self.closed_trades:
            session = trade['session']
            if session not in session_stats:
                session_stats[session] = {'trades': 0, 'pnl': 0, 'winners': 0}
            session_stats[session]['trades'] += 1
            session_stats[session]['pnl'] += trade['pnl']
            if trade['pnl'] > 0:
                session_stats[session]['winners'] += 1
        
        # Print summary
        print("\n" + "=" * 80)
        print("EXPERT SCALPER BACKTEST RESULTS")
        print("=" * 80)
        print(f"Period: {data.index[0]} to {data.index[-1]}")
        print(f"Duration: {(data.index[-1] - data.index[0]).days} days")
        print(f"\nBalance:")
        print(f"  Initial: ${self.initial_balance:,.2f}")
        print(f"  Final: ${self.balance:,.2f}")
        print(f"  Profit: ${total_pnl:,.2f} ({(total_pnl/self.initial_balance*100):.2f}%)")
        print(f"\nTrading Activity:")
        print(f"  Signals Generated: {self.stats['signals_generated']}")
        print(f"  Signals Passed: {self.stats['signals_passed']} ({self.stats['signals_passed']/self.stats['signals_generated']*100:.1f}%)")
        print(f"  Trades Executed: {total_trades}")
        print(f"  Avg Trades/Day: {total_trades / max(1, (data.index[-1] - data.index[0]).days):.1f}")
        print(f"\nPerformance:")
        print(f"  Win Rate: {win_rate:.1f}% ({len(winning_trades)}W / {len(losing_trades)}L)")
        print(f"  Total Pips: {total_pips:.1f}")
        print(f"  Avg Win: ${avg_win:.2f}")
        print(f"  Avg Loss: ${avg_loss:.2f}")
        print(f"  Profit Factor: {profit_factor:.2f}")
        print(f"  Max Drawdown: {max_drawdown:.2f}%")
        print(f"\nSession Breakdown:")
        for session, stats in session_stats.items():
            wr = (stats['winners'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
            print(f"  {session:8s}: {stats['trades']:3d} trades | ${stats['pnl']:7.2f} | WR: {wr:.0f}%")
        print("=" * 80)
        
        return {
            'initial_balance': self.initial_balance,
            'final_balance': self.balance,
            'total_pnl': total_pnl,
            'total_pips': total_pips,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'winners': len(winning_trades),
            'losers': len(losing_trades),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'session_stats': session_stats,
            'trades': self.closed_trades,
            'equity_curve': self.equity_curve,
            'stats': self.stats
        }


def fetch_mt5_data(symbol: str, timeframe: str, num_candles: int = None, 
                   start_date: datetime = None, end_date: datetime = None) -> pd.DataFrame:
    """
    Fetch data from MT5 or generate synthetic data.
    
    Args:
        symbol: Trading symbol
        timeframe: Timeframe (M1, M3, M5, etc.)
        num_candles: Number of candles (if start_date/end_date not provided)
        start_date: Start date for range fetch
        end_date: End date for range fetch
    """
    if not mt5.initialize():
        logger.warning("MT5 not available - generating synthetic data")
        candles = num_candles or 2000
        return generate_synthetic_data(candles)
    
    # Map timeframe
    tf_map = {
        'M1': mt5.TIMEFRAME_M1,
        'M3': mt5.TIMEFRAME_M3,
        'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15,
        'H1': mt5.TIMEFRAME_H1
    }
    
    mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_M5)
    
    # Fetch rates
    if start_date and end_date:
        # Fetch by date range
        logger.info(f"Fetching {symbol} {timeframe} from {start_date} to {end_date}")
        rates = mt5.copy_rates_range(symbol, mt5_tf, start_date, end_date)
    else:
        # Fetch by number of candles
        candles = num_candles or 2000
        logger.info(f"Fetching {candles} candles of {symbol} {timeframe}")
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, candles)
    
    mt5.shutdown()
    
    if rates is None or len(rates) == 0:
        logger.warning("Failed to fetch MT5 data - using synthetic data")
        candles = num_candles or 2000
        return generate_synthetic_data(candles)
    
    # Convert to DataFrame
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    
    return df[['open', 'high', 'low', 'close', 'volume']]


def generate_synthetic_data(num_candles: int, base_price: float = 2650.0) -> pd.DataFrame:
    """Generate realistic synthetic XAUUSD data."""
    logger.info(f"Generating {num_candles} synthetic candles")
    
    start_time = datetime.now() - timedelta(minutes=num_candles * 5)
    timestamps = [start_time + timedelta(minutes=i * 5) for i in range(num_candles)]
    
    opens, highs, lows, closes, volumes = [], [], [], [], []
    current_price = base_price
    trend = 0.0
    
    for i in range(num_candles):
        # Trend drift
        trend += np.random.normal(0, 0.0002)
        trend = np.clip(trend, -0.002, 0.002)
        
        # Generate candle
        open_price = current_price
        volatility = 2.0 + np.random.normal(0, 0.5)
        close_change = np.random.normal(trend * base_price, volatility * 0.1)
        close_price = open_price + close_change
        
        intrabar_range = abs(close_price - open_price) + volatility * 0.1
        high_price = max(open_price, close_price) + abs(np.random.normal(0, intrabar_range * 0.3))
        low_price = min(open_price, close_price) - abs(np.random.normal(0, intrabar_range * 0.3))
        
        opens.append(open_price)
        highs.append(high_price)
        lows.append(low_price)
        closes.append(close_price)
        volumes.append(np.random.randint(100, 1000))
        
        current_price = close_price
    
    df = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    }, index=timestamps)
    
    return df


if __name__ == "__main__":
    import sys
    
    # Parse arguments
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'XAUUSD'
    timeframe = sys.argv[2] if len(sys.argv) > 2 else 'M5'
    
    # Support both: num_candles OR date range
    start_date = None
    end_date = None
    num_candles = 2000
    
    if len(sys.argv) > 3:
        # Try to parse as date (YYYY-MM-DD format) or candle count
        try:
            # Try as date range: python backtest_expert_scalper.py XAUUSD M5 2025-12-01 2025-12-23
            if '-' in sys.argv[3] and len(sys.argv) > 4 and '-' in sys.argv[4]:
                start_date = datetime.strptime(sys.argv[3], '%Y-%m-%d')
                end_date = datetime.strptime(sys.argv[4], '%Y-%m-%d')
                # Set end_date to end of day
                end_date = end_date.replace(hour=23, minute=59, second=59)
            else:
                # Parse as candle count
                num_candles = int(sys.argv[3])
        except (ValueError, IndexError):
            num_candles = 2000
    
    if start_date and end_date:
        print(f"Fetching {symbol} {timeframe} from {start_date.date()} to {end_date.date()}...")
    else:
        print(f"Fetching {num_candles} candles of {symbol} {timeframe}...")
    
    # Fetch data
    data = fetch_mt5_data(symbol, timeframe, num_candles=num_candles, 
                          start_date=start_date, end_date=end_date)
    
    if data is None or len(data) < 50:
        print("ERROR: Insufficient data")
        sys.exit(1)
    
    # Run backtest
    backtest = ExpertScalperBacktest(initial_balance=200)
    results = backtest.run(data, timeframe)
    
    # Save results
    if 'error' not in results:
        output_file = f"expert_scalper_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            # Convert datetime objects to strings for JSON
            results_json = results.copy()
            results_json.pop('trades', None)
            results_json.pop('equity_curve', None)
            json.dump(results_json, f, indent=2, default=str)
        
        print(f"\nResults saved to: {output_file}")

"""
Structured logging for trading decisions.
Provides consistent, parseable logs for audit trail, debugging, and analysis.
"""

import logging
import json
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StructuredLogger:
    """Centralized structured logging for all trading decisions."""
    
    @staticmethod
    def log_order_attempt(symbol: str, direction: str, volume: float, 
                         entry_price: float, sl: float, tp: float,
                         reason: str, attempt: int = 1, 
                         market_state: Optional[Dict] = None):
        """Log order placement attempt with full context."""
        rr = abs(tp - entry_price) / abs(entry_price - sl) if sl != entry_price else 0
        
        context = {
            'event': 'order_attempt',
            'timestamp': datetime.utcnow().isoformat(),
            'symbol': symbol,
            'direction': direction,
            'volume': float(volume),
            'entry_price': float(entry_price),
            'sl': float(sl),
            'tp': float(tp),
            'rr_ratio': float(round(rr, 2)),
            'reason': reason,
            'attempt': int(attempt),
        }
        
        if market_state:
            context['market_state'] = {
                'atr': float(market_state.get('atr', 0)),
                'volatility': float(market_state.get('volatility', 0)),
                'regime': str(market_state.get('regime', 'unknown')),
                'open_positions': int(market_state.get('open_positions', 0)),
                'free_margin': float(market_state.get('free_margin', 0)),
            }
        
        logger.info(f"🎯 ORDER: {direction} {volume} {symbol} @ {entry_price:.2f} | SL={sl:.2f} TP={tp:.2f} RR={rr:.2f}x | {reason} (attempt {attempt})")
        logger.debug(f"STRUCT_LOG: {json.dumps(context)}")
    
    @staticmethod
    def log_order_result(symbol: str, result_code: int, ticket: Optional[int] = None,
                        deal: Optional[int] = None, error: Optional[str] = None,
                        attempt: int = 1, max_attempts: int = 3):
        """Log order execution result."""
        success = result_code == 10009 or result_code == 0  # TRADE_RETCODE_DONE varies by broker
        
        context = {
            'event': 'order_result',
            'timestamp': datetime.utcnow().isoformat(),
            'symbol': symbol,
            'success': success,
            'result_code': int(result_code),
            'ticket': ticket,
            'deal': deal,
            'error': error,
            'attempt': int(attempt),
            'max_attempts': int(max_attempts),
        }
        
        if success:
            logger.info(f"✅ ORDER FILLED: {symbol} ticket={ticket} deal={deal}")
        else:
            logger.warning(f"❌ ORDER FAILED: {symbol} retcode={result_code} error={error} (attempt {attempt}/{max_attempts})")
        
        logger.debug(f"STRUCT_LOG: {json.dumps(context)}")
    
    @staticmethod
    def log_signal_generated(symbol: str, signal: str, strength: float,
                            components: Dict[str, Any], reasons: list):
        """Log signal generation with component breakdown."""
        context = {
            'event': 'signal_generated',
            'timestamp': datetime.utcnow().isoformat(),
            'symbol': symbol,
            'signal': signal,
            'strength': float(strength),
            'components': {
                'technical': components.get('technical', {}).get('tech_score', 0),
                'patterns': components.get('patterns', {}).get('pattern_signal', 0),
                'news': components.get('news', {}).get('news_signal', 0),
            },
            'reasons': reasons,
        }
        
        logger.info(f"📊 SIGNAL: {signal.upper()} | Strength={strength:.1f}% | {' | '.join(reasons[:2])}")
        logger.debug(f"STRUCT_LOG: {json.dumps(context)}")
    
    @staticmethod
    def log_position_opened(ticket: int, symbol: str, direction: str, volume: float,
                           entry_price: float, sl: float, tp: float,
                           account_state: Optional[Dict] = None):
        """Log successful position opening."""
        rr = abs(tp - entry_price) / abs(entry_price - sl) if sl != entry_price else 0
        
        context = {
            'event': 'position_opened',
            'timestamp': datetime.utcnow().isoformat(),
            'ticket': int(ticket),
            'symbol': symbol,
            'direction': direction,
            'volume': float(volume),
            'entry_price': float(entry_price),
            'sl': float(sl),
            'tp': float(tp),
            'rr_ratio': float(round(rr, 2)),
        }
        
        if account_state:
            context['account'] = {
                'balance': float(account_state.get('balance', 0)),
                'equity': float(account_state.get('equity', 0)),
                'free_margin': float(account_state.get('free_margin', 0)),
                'margin_level': float(account_state.get('margin_level', 0)),
            }
        
        logger.info(f"🟢 POSITION OPENED: #{ticket} {direction} {volume} {symbol} @ {entry_price:.2f} | RR={rr:.2f}x")
        logger.debug(f"STRUCT_LOG: {json.dumps(context)}")
    
    @staticmethod
    def log_position_closed(ticket: int, symbol: str, reason: str, 
                           entry_price: float, close_price: float, profit: float,
                           volume: float):
        """Log position closure with P&L."""
        pips = (close_price - entry_price) * 10000  # Convert to pips
        pnl_pct = (profit / (entry_price * volume * 100)) * 100 if entry_price > 0 else 0
        
        context = {
            'event': 'position_closed',
            'timestamp': datetime.utcnow().isoformat(),
            'ticket': int(ticket),
            'symbol': symbol,
            'entry_price': float(entry_price),
            'close_price': float(close_price),
            'volume': float(volume),
            'pips': float(round(pips, 1)),
            'profit': float(round(profit, 2)),
            'profit_pct': float(round(pnl_pct, 2)),
            'reason': reason,
        }
        
        status = "✅" if profit >= 0 else "❌"
        logger.info(f"{status} POSITION CLOSED: #{ticket} {symbol} {profit:.2f} ({pnl_pct:.2f}%) | {reason}")
        logger.debug(f"STRUCT_LOG: {json.dumps(context)}")
    
    @staticmethod
    def log_scaling_attempt(base_ticket: int, symbol: str, additional_volume: float,
                           reason: str, open_positions: int, max_allowed: int,
                           market_state: Optional[Dict] = None):
        """Log scaling attempt."""
        allowed = open_positions < max_allowed
        
        context = {
            'event': 'scaling_attempt',
            'timestamp': datetime.utcnow().isoformat(),
            'base_ticket': int(base_ticket),
            'symbol': symbol,
            'additional_volume': float(additional_volume),
            'reason': reason,
            'open_positions': int(open_positions),
            'max_allowed': int(max_allowed),
            'allowed': allowed,
        }
        
        if market_state:
            context['market_state'] = {
                'floating_profit': float(market_state.get('floating_profit', 0)),
                'free_margin_ratio': float(market_state.get('free_margin_ratio', 0)),
                'signal_strength': float(market_state.get('signal_strength', 0)),
            }
        
        status = "✅" if allowed else "⏸️"
        logger.info(f"{status} SCALING: Base #{base_ticket} + {additional_volume} {symbol} | {reason} | {open_positions}/{max_allowed} positions")
        logger.debug(f"STRUCT_LOG: {json.dumps(context)}")
    
    @staticmethod
    def log_trade_error(error_type: str, error_msg: str, context_dict: Optional[Dict] = None):
        """Log trading errors with context."""
        context = {
            'event': 'trade_error',
            'timestamp': datetime.utcnow().isoformat(),
            'error_type': error_type,
            'error_message': error_msg,
        }
        
        if context_dict:
            context.update(context_dict)
        
        logger.error(f"⚠️  {error_type}: {error_msg}")
        logger.debug(f"STRUCT_LOG: {json.dumps(context)}")
    
    @staticmethod
    def log_daily_summary(summary_dict: Dict[str, Any]):
        """Log daily trading summary."""
        context = {
            'event': 'daily_summary',
            'timestamp': datetime.utcnow().isoformat(),
        }
        context.update(summary_dict)
        
        trades = summary_dict.get('total_trades', 0)
        wins = summary_dict.get('winning_trades', 0)
        losses = summary_dict.get('losing_trades', 0)
        pnl = summary_dict.get('total_pnl', 0)
        
        win_pct = (wins / trades * 100) if trades > 0 else 0
        logger.info(f"📈 DAILY SUMMARY: {trades} trades ({wins}W {losses}L {win_pct:.1f}%) | PnL: ${pnl:.2f}")
        logger.debug(f"STRUCT_LOG: {json.dumps(context)}")


# Convenience functions for easy access
def log_order_attempt(symbol: str, direction: str, volume: float, 
                     entry_price: float, sl: float, tp: float,
                     reason: str, attempt: int = 1, market_state: Optional[Dict] = None):
    """Convenience wrapper."""
    StructuredLogger.log_order_attempt(symbol, direction, volume, entry_price, sl, tp, reason, attempt, market_state)


def log_order_result(symbol: str, result_code: int, ticket: Optional[int] = None,
                    deal: Optional[int] = None, error: Optional[str] = None,
                    attempt: int = 1, max_attempts: int = 3):
    """Convenience wrapper."""
    StructuredLogger.log_order_result(symbol, result_code, ticket, deal, error, attempt, max_attempts)


def log_position_opened(ticket: int, symbol: str, direction: str, volume: float,
                       entry_price: float, sl: float, tp: float,
                       account_state: Optional[Dict] = None):
    """Convenience wrapper."""
    StructuredLogger.log_position_opened(ticket, symbol, direction, volume, entry_price, sl, tp, account_state)


def log_position_closed(ticket: int, symbol: str, reason: str, 
                       entry_price: float, close_price: float, profit: float, volume: float):
    """Convenience wrapper."""
    StructuredLogger.log_position_closed(ticket, symbol, reason, entry_price, close_price, profit, volume)

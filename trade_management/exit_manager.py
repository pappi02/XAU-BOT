# trade_management/exit_manager.py
import MetaTrader5 as mt5
import logging
import time
import math
import pandas as pd
from datetime import datetime, timedelta

from utils.indicators import atr
from analysis.multi_timeframe_analyzer import MultiTimeframeAnalyzer
import config
from trade_logger import trade_logger  # your existing trade logger, assumed present

logger = logging.getLogger(__name__)

# Helper: read position info
def _get_positions(symbol=None):
    return mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()

def _get_tick(symbol):
    return mt5.symbol_info_tick(symbol)

# Helper: calculate profit in price units
def _profit_price_units(position):
    tick = _get_tick(position.symbol)
    price = tick.bid if position.type == mt5.POSITION_TYPE_BUY else tick.ask
    # profit in price units (absolute)
    return abs(price - position.price_open)

# Modify SL helper
def _modify_sl(ticket, new_sl):
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return False
    pos = pos[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": pos.symbol,
        "sl": float(new_sl),
        "tp": float(pos.tp) if pos.tp else 0.0
    }
    res = mt5.order_send(request)
    logger.debug("modify_sl result %s", res)
    return getattr(res, "retcode", None) in (mt5.TRADE_RETCODE_DONE, 10009)

# Close volume helper
def _close_volume(ticket, volume):
    pos = mt5.positions_get(ticket=ticket)[0]
    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = _get_tick(pos.symbol)
    price = float(tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask)
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": float(volume),
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": config.ORDER_DEVIATION if hasattr(config, "ORDER_DEVIATION") else 20,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    logger.debug("partial close result %s", res)
    return getattr(res, "retcode", None) in (mt5.TRADE_RETCODE_DONE, 10009)

# Close full position
def _close_full(ticket):
    pos = mt5.positions_get(ticket=ticket)[0]
    return _close_volume(ticket, pos.volume)

# Get entry ATR saved or fallback compute ATR on open timeframe
def _entry_atr_estimate(symbol, timeframe=mt5.TIMEFRAME_M15, lookback=200):
    df = None
    try:
        from data.fetch_candles import get_candles
        df = get_candles(symbol, timeframe=timeframe, num_candles=lookback)
    except Exception:
        df = None
    if df is None or df.empty:
        return None
    return float(atr(df, period=14).iloc[-1])

# Check news - placeholder stub, integrate your news reader
def _recent_high_impact_news_within(minutes=10):
    try:
        from utils.news_reader import get_upcoming_high_impact  # implement this to return list with times
        upcoming = get_upcoming_high_impact()
        now = datetime.utcnow()
        for event in upcoming:
            event_time = event.get("time")  # should be datetime
            if event_time and 0 <= (event_time - now).total_seconds() <= minutes * 60:
                return True, event
    except Exception:
        pass
    return False, None

# Check opposite strong signal using multi-TF analysis
def _opposite_strong_signal(position):
    try:
        symbol = position.symbol
        analyzer = MultiTimeframeAnalyzer()
        signal = analyzer.analyze_market(symbol)
        if not signal:
            return False
        current_direction = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"
        # If aggregator direction opposes AND strength > 0.7 -> opposite strong
        if signal["action"] == "BUY" and current_direction == "SELL" and signal["should_trade"]:
            return True
        if signal["action"] == "SELL" and current_direction == "BUY" and signal["should_trade"]:
            return True
    except Exception:
        return False
    return False

# Main management function to call periodically
def manage_positions(symbol=None):
    """
    Run this continuously (e.g., every 10-60s). It will:
     - apply break-even
     - apply trailing stops
     - partial close at milestones
     - close on opposite strong signal / news / volatility spike / time-based rules
    """
    positions = _get_positions(symbol)
    if not positions:
        return

    # Get account metrics for drawdown checks
    account = mt5.account_info()
    balance = float(account.balance)
    equity = float(account.equity)
    # Evaluate daily PnL via trade_logger or mt5.history_deals_get (not implemented here)
    daily_pnl = trade_logger.get_daily_pnl(1)  # returns list/dict; implement accordingly
    daily_loss = 0.0
    if daily_pnl:
        # daily_pnl may be list of dicts: [{'date':..., 'total_pnl':...}]
        try:
            daily_loss = -float(daily_pnl[-1]['total_pnl']) if daily_pnl[-1]['total_pnl'] < 0 else 0.0
        except Exception:
            daily_loss = 0.0

    # Circuit breaker: if daily loss exceeds threshold, close all
    max_dd = config.EXIT.get("MAX_DRAWDOWN_PERCENT_CLOSE_ALL", 0.2)
    if daily_loss > balance * max_dd:
        logger.warning("Daily loss exceed threshold -> closing all positions")
        for p in positions:
            _close_full(p.ticket)
        return

    for pos in positions:
        try:
            ticket = pos.ticket
            symbol = pos.symbol
            volume = pos.volume
            entry_price = pos.price_open
            tick = _get_tick(symbol)
            cur_price = float(tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask)
            profit_price_units = abs(cur_price - entry_price)

            # 1) Break-even
            be_trigger = config.EXIT.get("BREAKEVEN_TRIGGER_PTS", 0)
            if profit_price_units >= be_trigger:
                # move SL to entry if SL currently worse than entry
                if pos.sl == 0 or (pos.type == mt5.POSITION_TYPE_BUY and pos.sl < entry_price) or (pos.type == mt5.POSITION_TYPE_SELL and pos.sl > entry_price):
                    moved = _modify_sl(ticket, entry_price)
                    if moved:
                        logger.info(f"Moved SL to breakeven for ticket {ticket}")

            # 2) Trailing stop
            if config.EXIT.get("TRAILING_ENABLED", True):
                ts_start = config.EXIT.get("TRAILING_START_PTS", 30)
                ts_step = config.EXIT.get("TRAILING_STEP_PTS", 50)
                # only start trailing when profit exceeds start pts
                if profit_price_units >= ts_start:
                    # calculate candidate SL: for BUY = cur_price - step ; SELL = cur_price + step
                    if pos.type == mt5.POSITION_TYPE_BUY:
                        candidate_sl = cur_price - (ts_step * 0.01)  # adjust scale if points different (for gold adapt)
                        if candidate_sl > pos.sl:
                            if _modify_sl(ticket, candidate_sl):
                                logger.info(f"Trailing SL moved up to {candidate_sl:.4f} for ticket {ticket}")
                    else:
                        candidate_sl = cur_price + (ts_step * 0.01)
                        if candidate_sl < pos.sl or pos.sl == 0:
                            if _modify_sl(ticket, candidate_sl):
                                logger.info(f"Trailing SL moved down to {candidate_sl:.4f} for ticket {ticket}")

            # 3) Partial close tiers
            if config.EXIT.get("PARTIAL_CLOSE_ENABLED", True):
                tiers = config.EXIT.get("PARTIAL_CLOSE_AT_PTS", [])
                percents = config.EXIT.get("PARTIAL_CLOSE_PERCENTS", [])
                for i, tier in enumerate(tiers):
                    if profit_price_units >= tier and volume > 0.0:
                        # check if we've already applied this tier by reading trade_logger or position comments
                        # we'll use trade_logger to see if ticket had a partial event recorded
                        if not trade_logger.has_partial(ticket, tier):
                            close_vol = volume * percents[i] if i < len(percents) else volume * 0.5
                            # enforce broker min volume
                            min_v = mt5.symbol_info(symbol).volume_min if mt5.symbol_info(symbol) else 0.01
                            close_vol = max(min_v, round(close_vol, 2))
                            if close_vol >= min_v and close_vol < volume - 0.0001:
                                ok = _close_volume(ticket, close_vol)
                                if ok:
                                    logger.info(f"Partial close {close_vol} executed for ticket {ticket} at profit {profit_price_units:.4f}")
                                    trade_logger.log_partial(ticket, tier, close_vol)  # implement logger function
                                    # update position volume variable to reflect new remaining amount (we won't refetch here)
                                    volume -= close_vol

            # 4) Volatility spike based on ATR
            entry_atr = trade_logger.get_entry_atr(ticket) or _entry_atr_estimate(symbol)
            if entry_atr:
                atr_now = _entry_atr_estimate(symbol, timeframe=mt5.TIMEFRAME_M15)
                if atr_now and atr_now > entry_atr * config.EXIT.get("VOLATILITY_SPIKE_MULTIPLIER", 2.5):
                    logger.warning(f"Volatility spike detected for {symbol}, closing ticket {ticket}")
                    _close_full(ticket)
                    trade_logger.log_exit(ticket, "vol_spike")
                    continue

            # 5) Opposite strong signal
            if config.EXIT.get("CLOSE_ON_OPPOSITE_SIGNAL", True) and _opposite_strong_signal(pos):
                logger.info(f"Opposite strong signal detected, closing ticket {ticket}")
                _close_full(ticket)
                trade_logger.log_exit(ticket, "opposite_signal")
                continue

            # 6) News-based closing
            news_coming, event = _recent_high_impact_news_within(config.EXIT.get("NEWS_CLOSE_BEFORE_MIN", 10))
            if news_coming:
                logger.info(f"High-impact news upcoming -> closing {ticket} preemptively")
                _close_full(ticket)
                trade_logger.log_exit(ticket, "news_close")
                continue

            # 7) Time-based exit
            open_time = datetime.fromtimestamp(pos.time)
            max_minutes = config.EXIT.get("TIME_BASED_EXIT_MINUTES", None)
            if max_minutes:
                if datetime.utcnow() - open_time > timedelta(minutes=max_minutes):
                    logger.info(f"Position {ticket} aged > {max_minutes}mins -> closing")
                    _close_full(ticket)
                    trade_logger.log_exit(ticket, "time_exit")
                    continue

        except Exception as e:
            logger.exception("Error managing position %s: %s", getattr(pos, "ticket", "unknown"), e)

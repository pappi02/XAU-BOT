"""
Symbol and price helpers for consistent handling across the bot.
Ensures single source of truth for symbols and proper decimal rounding per broker spec.
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Symbol mapping: normalize variant spellings
SYMBOL_MAP = {
    'XAUUSD': 'XAUUSD',
    'XAUUSDm': 'XAUUSD',  # Normalize to base
    'xauusd': 'XAUUSD',
    'xauusdm': 'XAUUSD'
}

def resolve_symbol(symbol: str) -> str:
    """
    Resolve symbol variants to canonical form.
    Maps XAUUSDm -> XAUUSD for consistency.
    
    Args:
        symbol (str): Input symbol (may contain variants)
    
    Returns:
        str: Canonical symbol name
    """
    if not symbol:
        return 'XAUUSD'
    
    canonical = SYMBOL_MAP.get(symbol.upper(), symbol.upper())
    if canonical != symbol:
        logger.debug(f"Symbol resolved: {symbol} -> {canonical}")
    return canonical


def round_price(price: float, digits: int = 2) -> float:
    """
    Round price to the correct number of decimal places per symbol spec.
    
    Args:
        price (float): Price to round
        digits (int): Number of decimal places (from symbol_info.digits)
    
    Returns:
        float: Rounded price
    """
    if price is None or price == 0:
        return 0.0
    
    # Clamp digits to reasonable range [0, 5]
    digits = max(0, min(5, int(digits)))
    
    try:
        return round(float(price), digits)
    except (ValueError, TypeError):
        logger.warning(f"Failed to round price {price} to {digits} digits, returning as-is")
        return float(price)


def get_symbol_digits(mt5_module, symbol: str) -> int:
    """
    Fetch decimal places (digits) for a symbol from MT5.
    
    Args:
        mt5_module: MetaTrader5 module
        symbol (str): Trading symbol
    
    Returns:
        int: Number of decimal places (default 2 for XAU)
    """
    try:
        symbol_info = mt5_module.symbol_info(symbol)
        if symbol_info and hasattr(symbol_info, 'digits'):
            return int(symbol_info.digits)
    except Exception as e:
        logger.warning(f"Failed to get digits for {symbol}: {e}")
    
    # Default for gold/precious metals
    return 2


def get_min_stop_distance(mt5_module, symbol: str) -> float:
    """
    Fetch minimum stop distance (trade_stops_level) for a symbol in price units.
    
    Args:
        mt5_module: MetaTrader5 module
        symbol (str): Trading symbol
    
    Returns:
        float: Minimum stop distance in price units (default 0 for no constraint)
    """
    try:
        symbol_info = mt5_module.symbol_info(symbol)
        if not symbol_info:
            logger.warning(f"Symbol info not available for {symbol}")
            return 0.0
        
        point = getattr(symbol_info, 'point', 0.01)
        stops_level_points = 0
        
        # Try multiple attribute names for broker compatibility
        for attr in ('trade_stops_level', 'stops_level'):
            if hasattr(symbol_info, attr):
                stops_level_points = getattr(symbol_info, attr) or 0
                break
        
        min_distance = max(stops_level_points, 0) * point
        
        if stops_level_points > 0:
            logger.debug(f"Symbol {symbol}: min_stop_distance = {stops_level_points} points = {min_distance:.5f} price units")
        
        return min_distance
    
    except Exception as e:
        logger.warning(f"Failed to get min stop distance for {symbol}: {e}")
        return 0.0


def validate_sl_tp(price: float, sl: Optional[float], tp: Optional[float], 
                   is_buy: bool, min_stop_dist: float = 0.0) -> Tuple[Optional[float], Optional[float]]:
    """
    Validate and enforce SL/TP invariants for a trade direction.
    
    For BUY: SL < entry_price and TP > entry_price
    For SELL: SL > entry_price and TP < entry_price
    
    Args:
        price (float): Current entry price
        sl (float): Proposed stop loss
        tp (float): Proposed take profit
        is_buy (bool): True for BUY, False for SELL
        min_stop_dist (float): Minimum distance from price to SL/TP
    
    Returns:
        Tuple[float, float]: Validated (sl, tp) or (None, None) if validation fails
    """
    if sl is None or tp is None:
        return sl, tp
    
    sl = float(sl) if sl else None
    tp = float(tp) if tp else None
    price = float(price)
    
    if is_buy:
        # BUY: SL must be below price, TP must be above price
        if sl is not None and sl >= price - min_stop_dist:
            logger.warning(f"BUY: SL {sl:.5f} is above/near price {price:.5f}, adjusting")
            sl = price - min_stop_dist
        
        if tp is not None and tp <= price + min_stop_dist:
            logger.warning(f"BUY: TP {tp:.5f} is below/near price {price:.5f}, adjusting")
            tp = price + min_stop_dist
    else:
        # SELL: SL must be above price, TP must be below price
        if sl is not None and sl <= price + min_stop_dist:
            logger.warning(f"SELL: SL {sl:.5f} is below/near price {price:.5f}, adjusting")
            sl = price + min_stop_dist
        
        if tp is not None and tp >= price - min_stop_dist:
            logger.warning(f"SELL: TP {tp:.5f} is above/near price {price:.5f}, adjusting")
            tp = price - min_stop_dist
    
    return sl, tp


def enforce_rr_minimum(price: float, sl: Optional[float], tp: Optional[float], 
                       is_buy: bool, min_rr: float = 1.8) -> Tuple[Optional[float], Optional[float]]:
    """
    Enforce a minimum risk-reward ratio.
    Adjusts TP upward (or SL inward) to ensure TP_distance >= SL_distance * min_rr.
    
    Args:
        price (float): Entry price
        sl (float): Stop loss price
        tp (float): Take profit price
        is_buy (bool): Trade direction
        min_rr (float): Minimum RR ratio (TP_dist / SL_dist)
    
    Returns:
        Tuple[float, float]: Adjusted (sl, tp)
    """
    if sl is None or tp is None:
        return sl, tp
    
    sl = float(sl)
    tp = float(tp)
    price = float(price)
    
    sl_dist = abs(price - sl)
    tp_dist = abs(price - tp)
    
    # If TP distance is less than SL distance * min_rr, adjust TP
    if tp_dist < sl_dist * min_rr:
        new_tp_dist = sl_dist * min_rr
        if is_buy:
            tp = price + new_tp_dist
        else:
            tp = price - new_tp_dist
        logger.info(f"RR enforced: adjusted TP from {abs(price - tp) / sl_dist:.2f}x to {min_rr:.2f}x SL distance")
    
    return sl, tp

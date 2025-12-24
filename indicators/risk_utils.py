# risk_utils.py - Risk calculation utilities (RR ratios, SL/TP management)

import pandas as pd
import numpy as np

def calculate_dynamic_rr_ratio(signal_strength, atr_value, news_sentiment, trend_strength, 
                               rsi_condition, position_type, adx_value=None):
    """
    Calculate dynamic risk-reward ratio based on multiple market factors.
    Professional-grade position sizing logic.

    Args:
        signal_strength (float): Signal strength percentage (0-100)
        atr_value (float): Current ATR value for volatility assessment
        news_sentiment (str): News sentiment ('bullish', 'bearish', 'neutral')
        trend_strength (int): Trend strength from EMA (-1=bearish, 0=neutral, 1=bullish)
        rsi_condition (str): RSI condition ('oversold', 'overbought', 'neutral')
        position_type (str): Position type ('BUY' or 'SELL')
        adx_value (float, optional): ADX value for trend strength (0-100)

    Returns:
        float: Dynamic risk-reward ratio (1.2-4.0)
    """
    base_rr = 2.0

    # Signal strength factor (0-100% -> 0.5-1.5 multiplier)
    strength_factor = 0.5 + (signal_strength / 100) * 1.0

    # ATR factor - higher volatility suggests larger moves
    atr_factor = 1.0
    if atr_value and atr_value > 0:
        if atr_value > 3.0:
            atr_factor = 1.15  # High volatility
        elif atr_value < 1.5:
            atr_factor = 0.85  # Low volatility
        else:
            atr_factor = 1.0  # Normal volatility

    # News sentiment factor
    news_factor = 1.0
    if news_sentiment == 'bullish':
        news_factor = 1.2 if position_type == 'BUY' else 0.9
    elif news_sentiment == 'bearish':
        news_factor = 1.2 if position_type == 'SELL' else 0.9

    # Trend strength factor
    trend_factor = 1.0
    if trend_strength == 1:  # Bullish trend
        trend_factor = 1.15 if position_type == 'BUY' else 0.85
    elif trend_strength == -1:  # Bearish trend
        trend_factor = 1.15 if position_type == 'SELL' else 0.85

    # RSI condition factor
    rsi_factor = 1.0
    if rsi_condition == 'oversold' and position_type == 'BUY':
        rsi_factor = 1.1
    elif rsi_condition == 'overbought' and position_type == 'SELL':
        rsi_factor = 1.1
    elif rsi_condition == 'oversold' and position_type == 'SELL':
        rsi_factor = 0.9
    elif rsi_condition == 'overbought' and position_type == 'BUY':
        rsi_factor = 0.9

    # ADX factor - stronger trends support higher RR
    adx_factor = 1.0
    if adx_value is not None:
        if adx_value > 40:
            adx_factor = 1.15  # Very strong trend
        elif adx_value > 25:
            adx_factor = 1.1  # Strong trend
        elif adx_value < 15:
            adx_factor = 0.9  # Weak trend/range

    # Calculate dynamic RR
    dynamic_rr = base_rr * strength_factor * atr_factor * news_factor * trend_factor * rsi_factor * adx_factor

    # Clamp to reasonable range
    dynamic_rr = max(1.2, min(4.0, dynamic_rr))

    return round(dynamic_rr, 2)

def calculate_dynamic_stop_loss(signal_strength, atr_value, news_sentiment, trend_strength, 
                               rsi_condition, position_type, adx_value=None, volume_factor=1.0):
    """
    Calculate dynamic stop loss multiplier based on multiple market factors.
    Professional-grade risk management logic.

    Args:
        signal_strength (float): Signal strength percentage (0-100)
        atr_value (float): Current ATR value for volatility assessment
        news_sentiment (str): News sentiment ('bullish', 'bearish', 'neutral')
        trend_strength (int): Trend strength from EMA (-1=bearish, 0=neutral, 1=bullish)
        rsi_condition (str): RSI condition ('oversold', 'overbought', 'neutral')
        position_type (str): Position type ('BUY' or 'SELL')
        adx_value (float, optional): ADX value for trend strength (0-100)
        volume_factor (float, optional): Volume/liquidity factor (0.5-2.0)

    Returns:
        float: Dynamic stop loss multiplier (0.5-3.0)
    """
    base_sl = 1.5

    # 1. Volatility (ATR) - Higher ATR = wider SL
    atr_multiplier = 1.0
    if atr_value and atr_value > 0:
        if atr_value > 3.0:
            atr_multiplier = 1.3  # High volatility
        elif atr_value < 1.5:
            atr_multiplier = 0.8  # Low volatility
        else:
            atr_multiplier = 1.0  # Normal volatility

    # 2. Signal Strength - Stronger signal = tighter SL
    strength_multiplier = 1.0
    if signal_strength > 80:
        strength_multiplier = 0.8  # Strong signal, tighter SL
    elif signal_strength > 60:
        strength_multiplier = 0.9  # Moderate signal
    elif signal_strength < 40:
        strength_multiplier = 1.2  # Weak signal, wider SL
    else:
        strength_multiplier = 1.0

    # 3. Trend Strength (EMA/ADX) - Strong trend = tighter SL
    trend_multiplier = 1.0
    if adx_value is not None:
        if adx_value > 25:
            trend_multiplier = 0.85  # Strong trend
        elif adx_value < 15:
            trend_multiplier = 1.15  # Weak trend/range
        else:
            trend_multiplier = 1.0
    else:
        if trend_strength != 0:
            trend_multiplier = 0.9
        else:
            trend_multiplier = 1.1

    # 4. Market Volumes & Liquidity - Lower liquidity = wider SL
    liquidity_multiplier = 1.0 / volume_factor

    # 5. News Impact - High impact news = wider SL
    news_multiplier = 1.0
    if news_sentiment in ['bullish', 'bearish']:
        news_multiplier = 1.2

    # 6. RSI Extreme Conditions - Give more room in extremes
    rsi_multiplier = 1.0
    if rsi_condition in ['oversold', 'overbought']:
        rsi_multiplier = 1.1

    # 7. Position Type
    position_multiplier = 1.0

    # Calculate dynamic SL
    dynamic_sl = (base_sl * atr_multiplier * strength_multiplier * trend_multiplier *
                  liquidity_multiplier * news_multiplier * rsi_multiplier * position_multiplier)

    # Clamp to reasonable range
    min_sl = 0.5
    max_sl = 3.0
    dynamic_sl = max(min_sl, min(max_sl, dynamic_sl))

    return round(dynamic_sl, 2)

def calculate_sl_from_atr(entry_price, atr_value, multiplier=2.0, position_type='BUY'):
    """
    Calculate stop loss price from ATR.
    
    Args:
        entry_price (float): Entry price
        atr_value (float): ATR value
        multiplier (float): SL multiplier on ATR
        position_type (str): 'BUY' or 'SELL'
    
    Returns:
        float: Stop loss price
    """
    sl_distance = atr_value * multiplier
    
    if position_type == 'BUY':
        return entry_price - sl_distance
    else:
        return entry_price + sl_distance

def calculate_tp_from_atr(entry_price, atr_value, rr_ratio=2.0, position_type='BUY'):
    """
    Calculate take profit price from RR ratio.
    
    Args:
        entry_price (float): Entry price
        atr_value (float): ATR value for SL calculation
        rr_ratio (float): Risk-reward ratio
        position_type (str): 'BUY' or 'SELL'
    
    Returns:
        float: Take profit price
    """
    # Calculate SL distance
    sl_distance = atr_value * 1.5  # Standard 1.5x ATR SL
    
    # TP distance is RR * SL distance
    tp_distance = sl_distance * rr_ratio
    
    if position_type == 'BUY':
        return entry_price + tp_distance
    else:
        return entry_price - tp_distance

def optimize_position_size(account_balance, risk_per_trade_pct, entry_price, sl_price, 
                          instrument_point_value=1.0):
    """
    Calculate optimal position size based on risk management rules.
    
    Args:
        account_balance (float): Current account balance
        risk_per_trade_pct (float): Risk per trade (e.g., 0.5 for 0.5%)
        entry_price (float): Entry price
        sl_price (float): Stop loss price
        instrument_point_value (float): Points value per unit (e.g., $1 per point for XAUUSD)
    
    Returns:
        tuple: (position_size, risk_amount, potential_loss)
    """
    # Risk amount in dollars
    risk_amount = account_balance * (risk_per_trade_pct / 100)
    
    # Distance to SL in price points
    sl_distance = abs(entry_price - sl_price)
    
    if sl_distance == 0:
        return 0, 0, 0
    
    # Calculate position size
    position_size = risk_amount / (sl_distance * instrument_point_value)
    
    # Potential loss
    potential_loss = position_size * sl_distance * instrument_point_value
    
    return round(position_size, 2), round(risk_amount, 2), round(potential_loss, 2)

import pandas as pd
import numpy as np

def atr(df, period=14):
    """
    Average True Range (ATR)
    df: DataFrame must contain 'high','low','close'
    """
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def dynamic_rr_ratio(signal_strength, atr_value, news_sentiment, trend_strength, rsi_condition, position_type):
    """
    Calculate dynamic risk-reward ratio based on multiple market factors.

    Args:
        signal_strength (float): Signal strength percentage (0-100)
        atr_value (float): Current ATR value for volatility assessment
        news_sentiment (str): News sentiment ('bullish', 'bearish', 'neutral')
        trend_strength (int): Trend strength from EMA (-1=bearish, 0=neutral, 1=bullish)
        rsi_condition (str): RSI condition ('oversold', 'overbought', 'neutral')
        position_type (str): Position type ('BUY' or 'SELL')

    Returns:
        float: Dynamic risk-reward ratio (1.2-4.0)
    """
    # Base RR ratio (fallback)
    base_rr = 2.0

    # Signal strength factor (0-100% -> 0.5-1.5 multiplier)
    strength_factor = 0.5 + (signal_strength / 100) * 1.0

    # ATR factor - higher volatility suggests larger moves (normalized ATR contribution)
    # Assume ATR around 1-5 for XAUUSD, scale to 0.8-1.2
    atr_factor = min(max(atr_value / 3.0, 0.8), 1.2) if atr_value and atr_value > 0 else 1.0

    # News sentiment factor
    news_factor = 1.0
    if news_sentiment == 'bullish':
        news_factor = 1.2 if position_type == 'BUY' else 0.9
    elif news_sentiment == 'bearish':
        news_factor = 1.2 if position_type == 'SELL' else 0.9
    # neutral = 1.0 (no change)

    # Trend strength factor
    trend_factor = 1.0
    if trend_strength == 1:  # Bullish trend
        trend_factor = 1.15 if position_type == 'BUY' else 0.85
    elif trend_strength == -1:  # Bearish trend
        trend_factor = 1.15 if position_type == 'SELL' else 0.85
    # neutral = 1.0

    # RSI condition factor
    rsi_factor = 1.0
    if rsi_condition == 'oversold' and position_type == 'BUY':
        rsi_factor = 1.1  # Good to buy when oversold
    elif rsi_condition == 'overbought' and position_type == 'SELL':
        rsi_factor = 1.1  # Good to sell when overbought
    elif rsi_condition == 'oversold' and position_type == 'SELL':
        rsi_factor = 0.9  # Risky to sell when oversold
    elif rsi_condition == 'overbought' and position_type == 'BUY':
        rsi_factor = 0.9  # Risky to buy when overbought

    # Calculate dynamic RR
    dynamic_rr = base_rr * strength_factor * atr_factor * news_factor * trend_factor * rsi_factor

    # Clamp to reasonable range (1.2-4.0)
    dynamic_rr = max(1.2, min(4.0, dynamic_rr))

    return round(dynamic_rr, 2)

def dynamic_stop_loss(signal_strength, atr_value, news_sentiment, trend_strength, rsi_condition, position_type, adx_value=None, volume_factor=1.0):
    """
    Calculate dynamic stop loss multiplier based on multiple market factors.

    Args:
        signal_strength (float): Signal strength percentage (0-100)
        atr_value (float): Current ATR value for volatility assessment
        news_sentiment (str): News sentiment ('bullish', 'bearish', 'neutral')
        trend_strength (int): Trend strength from EMA (-1=bearish, 0=neutral, 1=bullish)
        rsi_condition (str): RSI condition ('oversold', 'overbought', 'neutral')
        position_type (str): Position type ('BUY' or 'SELL')
        adx_value (float, optional): ADX value for trend strength (0-100)
        volume_factor (float, optional): Volume/liquidity factor (0.5-2.0, higher = more liquidity)

    Returns:
        float: Dynamic stop loss multiplier (0.5-3.0)
    """
    # Base SL multiplier (fallback)
    base_sl = 1.5

    # 1. Volatility (ATR) - Higher ATR = wider SL
    atr_multiplier = 1.0
    if atr_value and atr_value > 0:
        # Normalize ATR: assume typical ATR range 1-5 for XAUUSD
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
        strength_multiplier = 1.0  # Neutral

    # 3. Trend Strength (EMA Alignment / ADX) - Strong trend = tighter SL
    trend_multiplier = 1.0
    if adx_value is not None:
        if adx_value > 25:  # Strong trend
            trend_multiplier = 0.85 if trend_strength != 0 else 1.0
        elif adx_value < 15:  # Weak trend/range
            trend_multiplier = 1.15
        else:  # Moderate trend
            trend_multiplier = 1.0
    else:
        # Fallback to EMA trend only
        if trend_strength != 0:  # Trending
            trend_multiplier = 0.9
        else:  # Sideways
            trend_multiplier = 1.1

    # 4. Market Volumes & Liquidity - Lower liquidity = wider SL
    liquidity_multiplier = 1.0 / volume_factor  # Inverse relationship

    # 5. News / Sentiment Impact - High impact news = wider SL
    news_multiplier = 1.0
    if news_sentiment in ['bullish', 'bearish']:
        news_multiplier = 1.2  # Increase SL during news events

    # 6. RSI or Overbought/Oversold Conditions - Extreme RSI = wider SL for counter-trend
    rsi_multiplier = 1.0
    if rsi_condition in ['oversold', 'overbought']:
        rsi_multiplier = 1.1  # Give more room in extreme conditions

    # 7. Position Type - Different multipliers for BUY vs SELL if needed
    position_multiplier = 1.0
    # For XAU/USD, we can keep neutral, but this allows for future customization
    # if position_type == "BUY":
    #     position_multiplier = 1.0
    # elif position_type == "SELL":
    #     position_multiplier = 1.0

    # Calculate dynamic SL multiplier
    dynamic_sl = (base_sl * atr_multiplier * strength_multiplier * trend_multiplier *
                  liquidity_multiplier * news_multiplier * rsi_multiplier * position_multiplier)

    # 8. Minimum & Maximum Stop Loss Boundaries
    min_sl = 0.5  # Minimum 0.5x ATR
    max_sl = 3.0  # Maximum 3.0x ATR

    # Clamp to reasonable range
    dynamic_sl = max(min_sl, min(max_sl, dynamic_sl))

    return round(dynamic_sl, 2)

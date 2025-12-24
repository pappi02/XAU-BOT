"""
Scalping Dips Strategy

Professional dip scalping strategy that buys temporary pullbacks in strong uptrends
and sells temporary rallies in strong downtrends. Uses RSI/Stochastic for oversold/
overbought confirmation during dips.

Timeframes: 1-5 minute charts (M1, M3, M5)
Risk-Reward: 1:1.5 to 1:2
Stop Loss: Tight (below recent low for longs, above recent high for shorts)
Take Profit: Quick recovery to recent high (10-20 pips)

Entry Criteria:
BUY (Dips in Uptrend):
- Strong uptrend confirmed (EMA 8 > EMA 21, MACD positive)
- Temporary pullback/dip to support or key retracement
- RSI oversold (< 35) during dip
- Stochastic oversold (K < 30) during dip
- Price hits support level or Bollinger lower band

SELL (Rallies in Downtrend):
- Strong downtrend confirmed (EMA 8 < EMA 21, MACD negative)
- Temporary rally to resistance
- RSI overbought (> 65) during rally
- Stochastic overbought (K > 70)
- Price hits resistance or Bollinger upper band

Exit Criteria:
- Take profit as price recovers from dip
- Stop loss if dip continues (below support)
- Exit if trend shows signs of reversal

Best Market Conditions:
- Strong trending markets with healthy pullbacks
- High liquidity periods
- Avoid during trend reversals
"""

import pandas as pd
import numpy as np
from typing import Dict

from indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_stochastic,
    calculate_bollinger_bands,
    calculate_macd
)


class DipScalping:
    """Professional Scalping Dips Strategy - Buy dips in uptrends, sell rallies in downtrends"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.ema_fast = self.config.get('ema_fast', 8)
        self.ema_slow = self.config.get('ema_slow', 21)
        self.rsi_period = self.config.get('rsi_period', 7)
        self.rsi_oversold = self.config.get('rsi_oversold', 35)
        self.rsi_overbought = self.config.get('rsi_overbought', 65)
        self.stoch_oversold = self.config.get('stoch_oversold', 30)
        self.stoch_overbought = self.config.get('stoch_overbought', 70)
        self.bb_period = self.config.get('bb_period', 20)
        self.sl_atr_mult = self.config.get('sl_atr_mult', 1.5)
        self.tp_rr = self.config.get('tp_rr', 1.5)
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        if len(data) < 100:
            return {'signal': 0, 'confidence': 0, 'entry': None, 'sl': None, 'tp': None,
                   'confluences': [], 'reason': 'Insufficient data'}
        
        # Calculate indicators
        ema_fast = calculate_ema(data, self.ema_fast)
        ema_slow = calculate_ema(data, self.ema_slow)
        rsi = calculate_rsi(data, self.rsi_period)
        stoch_k, stoch_d = calculate_stochastic(data, k_period=14, d_period=3)
        stoch = {'K': stoch_k, 'D': stoch_d}
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(data, period=self.bb_period, std_dev=2)
        bb = {'upper': bb_upper, 'middle': bb_middle, 'lower': bb_lower}
        macd_line, macd_signal, macd_hist = calculate_macd(data, fast_period=8, slow_period=17, signal_period=9)
        macd = {'macd': macd_line, 'signal': macd_signal, 'histogram': macd_hist}
        
        current_close = data['close'].iloc[-1]
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_stoch_k = stoch['K'].iloc[-1]
        macd_hist = macd['macd'].iloc[-1] - macd['signal'].iloc[-1]
        
        # Determine trend
        uptrend = current_ema_fast > current_ema_slow and macd_hist > 0
        downtrend = current_ema_fast < current_ema_slow and macd_hist < 0
        
        if not (uptrend or downtrend):
            return {'signal': 0, 'confidence': 0, 'entry': None, 'sl': None, 'tp': None,
                   'confluences': [], 'reason': 'No clear trend'}
        
        confluences = []
        confidence = 0
        signal = 0
        
        # BUY DIP (in uptrend)
        if uptrend:
            if current_rsi < self.rsi_oversold:
                confluences.append('RSI_oversold_in_uptrend')
                confidence += 25
                signal = 1
            if current_stoch_k < self.stoch_oversold:
                confluences.append('Stochastic_oversold_in_uptrend')
                confidence += 20
                signal = 1
            if current_close < bb['lower'].iloc[-1]:
                confluences.append('Price_at_BB_lower_in_uptrend')
                confidence += 15
                signal = 1
            confluences.append('Strong_uptrend')
            confidence += 10
        
        # SELL RALLY (in downtrend)
        elif downtrend:
            if current_rsi > self.rsi_overbought:
                confluences.append('RSI_overbought_in_downtrend')
                confidence += 25
                signal = -1
            if current_stoch_k > self.stoch_overbought:
                confluences.append('Stochastic_overbought_in_downtrend')
                confidence += 20
                signal = -1
            if current_close > bb['upper'].iloc[-1]:
                confluences.append('Price_at_BB_upper_in_downtrend')
                confidence += 15
                signal = -1
            confluences.append('Strong_downtrend')
            confidence += 10
        
        if len(confluences) < 2:
            return {'signal': 0, 'confidence': confidence, 'entry': None, 'sl': None, 'tp': None,
                   'confluences': confluences, 'reason': 'Insufficient dip confluence'}
        
        # Calculate SL/TP
        atr = data['high'].iloc[-1] - data['low'].iloc[-1]
        if signal == 1:
            entry = current_close
            sl = current_close - (atr * self.sl_atr_mult)
            tp = current_close + ((current_close - sl) * self.tp_rr)
        else:
            entry = current_close
            sl = current_close + (atr * self.sl_atr_mult)
            tp = current_close - ((sl - current_close) * self.tp_rr)
        
        return {
            'signal': signal,
            'confidence': min(100, confidence),
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'confluences': confluences,
            'rsi': current_rsi,
            'stoch_k': current_stoch_k,
            'trend': 'uptrend' if uptrend else 'downtrend',
            'risk_reward': f"1:{self.tp_rr}",
            'reason': 'Dip/rally in trend with confluence'
        }

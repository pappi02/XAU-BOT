"""
Moving Average Scalping Strategy

Professional MA scalping strategy that combines short-term price movements with
moving averages to identify quick trading opportunities. Uses EMA crossovers
and price bounces from fast MA for entries.

Timeframes: 1-5 minute charts (M1, M3, M5)
Risk-Reward: 1:1.5 to 1:2
Stop Loss: Tight (5-10 pips)
Take Profit: Quick (10-20 pips)

Entry Criteria:
- Price bounces up from fast MA (5-10 period EMA) = BUY
- Price bounces down from fast MA = SELL
- MA crossover confirmation (fast crosses slow)
- Trade in direction of larger trend (slow MA)
- MACD confirms direction

Exit Criteria:
- Take profit at predetermined level (10-20 pips)
- Stop loss below recent low or above recent high
- Exit if price crosses back through fast MA (wrong direction)
- Exit if MA crossover reverses

Best Market Conditions:
- Trending markets with moderate volatility
- Active market hours (London/NY sessions)
- Avoid during major news events
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

from indicators import (
    calculate_ema,
    calculate_ema_stack,
    get_ema_crossover_signal,
    calculate_macd,
    calculate_atr
)


class MovingAverageScalping:
    """
    Professional Moving Average Scalping Strategy
    
    Combines short-term price movements with EMA bounces and crossovers
    for quick scalping opportunities.
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize MA Scalping Strategy.
        
        Args:
            config: Configuration dictionary with strategy parameters
        """
        self.config = config or {}
        
        # EMA parameters (fast and slow for scalping)
        self.ema_fast_period = self.config.get('ema_fast', 8)  # Fast EMA (8 for scalping)
        self.ema_slow_period = self.config.get('ema_slow', 21)  # Slow EMA (21 for trend)
        
        # MACD parameters (confirmation)
        self.macd_fast = self.config.get('macd_fast', 8)
        self.macd_slow = self.config.get('macd_slow', 17)
        self.macd_signal = self.config.get('macd_signal', 9)
        
        # Bounce detection parameters
        self.bounce_proximity = self.config.get('bounce_proximity', 0.002)  # 0.2% from MA
        self.bounce_confirmation_candles = self.config.get('bounce_confirmation', 2)
        
        # Risk management
        self.stop_loss_pips = self.config.get('sl_pips', 8)  # 8 pips tight SL
        self.take_profit_pips = self.config.get('tp_pips', 15)  # 15 pips quick TP
        self.pip_value = self.config.get('pip_value', 0.1)  # For XAUUSD
    
    def detect_ma_bounce(self, data: pd.DataFrame, ema_fast: pd.Series) -> Dict:
        """
        Detect if price has bounced off the fast MA.
        
        Bounce = price touches/crosses MA then moves back in trend direction.
        
        Args:
            data: OHLCV DataFrame
            ema_fast: Fast EMA series
        
        Returns:
            Dict with bounce info
        """
        if len(data) < self.bounce_confirmation_candles + 1:
            return {'detected': False, 'direction': 0, 'strength': 0}
        
        current_close = data['close'].iloc[-1]
        current_ema = ema_fast.iloc[-1]
        
        # Calculate distance from MA (as percentage)
        distance_pct = abs(current_close - current_ema) / current_ema
        
        # Check if within bounce proximity
        if distance_pct > self.bounce_proximity:
            return {'detected': False, 'direction': 0, 'strength': 0, 'reason': 'Too far from MA'}
        
        # Check previous candles for bounce pattern
        recent_closes = data['close'].tail(self.bounce_confirmation_candles + 1).values
        recent_emas = ema_fast.tail(self.bounce_confirmation_candles + 1).values
        
        # Bullish bounce: Price was below MA, now above and moving up
        if current_close > current_ema:
            # Check if previous candle(s) were below or at MA
            previous_below_ma = any(recent_closes[i] <= recent_emas[i] 
                                   for i in range(len(recent_closes) - 1))
            
            # Check if price is rising
            price_rising = current_close > recent_closes[-2]
            
            if previous_below_ma and price_rising:
                strength = min(100, (1 - distance_pct / self.bounce_proximity) * 100)
                return {
                    'detected': True,
                    'direction': 1,
                    'strength': strength,
                    'type': 'bullish_bounce',
                    'distance': distance_pct
                }
        
        # Bearish bounce: Price was above MA, now below and moving down
        elif current_close < current_ema:
            # Check if previous candle(s) were above or at MA
            previous_above_ma = any(recent_closes[i] >= recent_emas[i] 
                                   for i in range(len(recent_closes) - 1))
            
            # Check if price is falling
            price_falling = current_close < recent_closes[-2]
            
            if previous_above_ma and price_falling:
                strength = min(100, (1 - distance_pct / self.bounce_proximity) * 100)
                return {
                    'detected': True,
                    'direction': -1,
                    'strength': strength,
                    'type': 'bearish_bounce',
                    'distance': distance_pct
                }
        
        return {'detected': False, 'direction': 0, 'strength': 0, 'reason': 'No bounce pattern'}
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Analyze market for MA scalping opportunities.
        
        Args:
            data: OHLCV DataFrame with at least 100 candles
        
        Returns:
            Dict with signal, confidence, entry, sl, tp, confluences
        """
        if len(data) < 100:
            return {
                'signal': 0,
                'confidence': 0,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': [],
                'reason': 'Insufficient data'
            }
        
        # Step 1: Calculate EMAs
        ema_fast = calculate_ema(data, period=self.ema_fast_period)
        ema_slow = calculate_ema(data, period=self.ema_slow_period)
        
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        
        # Step 2: Determine trend direction (slow MA)
        trend_bullish = current_ema_fast > current_ema_slow
        trend_bearish = current_ema_fast < current_ema_slow
        
        if not (trend_bullish or trend_bearish):
            return {
                'signal': 0,
                'confidence': 0,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': [],
                'reason': 'No clear trend (EMAs too close)'
            }
        
        # Step 3: Detect MA bounce
        bounce = self.detect_ma_bounce(data, ema_fast)
        
        if not bounce['detected']:
            return {
                'signal': 0,
                'confidence': 0,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': [],
                'reason': bounce.get('reason', 'No MA bounce detected')
            }
        
        # Step 4: Check bounce aligns with trend
        if (trend_bullish and bounce['direction'] == 1) or (trend_bearish and bounce['direction'] == -1):
            trend_aligned = True
        else:
            return {
                'signal': 0,
                'confidence': 0,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': [],
                'reason': 'Bounce against trend direction'
            }
        
        # Step 5: MA Crossover confirmation
        crossover_signal = get_ema_crossover_signal(data, fast_period=self.ema_fast_period,
                                                    slow_period=self.ema_slow_period)
        recent_crossover = crossover_signal != 0
        crossover_aligned = crossover_signal == bounce['direction']
        
        # Step 6: MACD confirmation
        macd_line, macd_signal, macd_histogram_series = calculate_macd(
            data, fast_period=self.macd_fast, slow_period=self.macd_slow,
            signal_period=self.macd_signal
        )
        macd_histogram = macd_histogram_series.iloc[-1]
        macd_confirmed = (
            (bounce['direction'] == 1 and macd_histogram > 0) or
            (bounce['direction'] == -1 and macd_histogram < 0)
        )
        
        # Step 7: Count confluences
        confluences = []
        confidence = 40  # Base confidence for bounce
        signal_direction = bounce['direction']
        
        confluences.append(f'MA_bounce_{bounce["type"]}')
        confidence += bounce['strength'] * 0.2  # Add bounce strength
        
        confluences.append(f'Trend_{"bullish" if trend_bullish else "bearish"}_aligned')
        confidence += 15
        
        if recent_crossover and crossover_aligned:
            confluences.append(f'EMA_crossover_{"bullish" if signal_direction == 1 else "bearish"}')
            confidence += 20
        
        if macd_confirmed:
            confluences.append(f'MACD_histogram_{"positive" if signal_direction == 1 else "negative"}')
            confidence += 15
        
        # Require minimum 2 confluences
        if len(confluences) < 2:
            return {
                'signal': 0,
                'confidence': confidence,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': confluences,
                'reason': 'Insufficient confluence (need 2+)'
            }
        
        # Step 8: Calculate entry, SL, TP
        current_close = data['close'].iloc[-1]
        current_low = data['low'].iloc[-1]
        current_high = data['high'].iloc[-1]
        
        if signal_direction == 1:  # Bullish bounce
            entry = current_close
            sl = current_close - (self.stop_loss_pips * self.pip_value)
            tp = current_close + (self.take_profit_pips * self.pip_value)
        else:  # Bearish bounce
            entry = current_close
            sl = current_close + (self.stop_loss_pips * self.pip_value)
            tp = current_close - (self.take_profit_pips * self.pip_value)
        
        risk_reward = self.take_profit_pips / self.stop_loss_pips
        
        return {
            'signal': signal_direction,
            'confidence': min(100, confidence),
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'confluences': confluences,
            'ema_fast': current_ema_fast,
            'ema_slow': current_ema_slow,
            'bounce_strength': bounce['strength'],
            'bounce_distance': bounce['distance'],
            'macd_histogram': macd_histogram,
            'risk_reward': f"1:{risk_reward:.1f}",
            'reason': 'MA bounce with trend and confluences'
        }


if __name__ == "__main__":
    # Example usage
    dates = pd.date_range('2024-01-01', periods=200, freq='5min')
    prices = 2600 + np.cumsum(np.random.randn(200) * 2)
    
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 0.5,
        'high': prices + np.abs(np.random.randn(200)),
        'low': prices - np.abs(np.random.randn(200)),
        'close': prices,
        'volume': np.random.randint(1000, 10000, 200)
    }, index=dates)
    
    # Test strategy
    strategy = MovingAverageScalping()
    result = strategy.analyze(sample_data)
    
    print("=" * 80)
    print("MOVING AVERAGE SCALPING STRATEGY TEST")
    print("=" * 80)
    print(f"Signal: {result['signal']}")
    print(f"Confidence: {result['confidence']}%")
    print(f"Entry: {result.get('entry')}")
    print(f"SL: {result.get('sl')}")
    print(f"TP: {result.get('tp')}")
    print(f"Confluences: {result['confluences']}")
    print(f"Reason: {result['reason']}")
    print("=" * 80)

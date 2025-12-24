"""
Momentum Scalping Strategy

Professional momentum scalping strategy that capitalizes on strong price movements
in very short timeframes using RSI, MACD, Stochastic and volume analysis.

Timeframes: 1-5 minute charts (M1, M3, M5)
Risk-Reward: 1:1.5 to 1:2
Stop Loss: Tight (5-15 pips)
Take Profit: Quick (10-25 pips)

Entry Criteria:
- RSI shows momentum (>60 for bullish, <40 for bearish, NOT extreme)
- MACD histogram confirms momentum direction
- Stochastic confirms momentum (K>50 for bullish, K<50 for bearish)
- Volume confirms move (above average)
- Strong candle patterns (long bodies, minimal wicks)

Exit Criteria:
- Take profit at predetermined level (10-25 pips)
- Stop loss if momentum reverses (RSI crosses back)
- Exit if volume drops significantly
- Exit if MACD histogram reverses

Best Market Conditions:
- Volatile markets with clear directional moves
- High trading volume periods
- Active market hours (London/NY sessions)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

from indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_stochastic,
    detect_volume_spike,
    calculate_relative_volume,
    calculate_atr
)


class MomentumScalping:
    """
    Professional Momentum Scalping Strategy
    
    Capitalizes on strong price movements using momentum indicators
    (RSI, MACD, Stochastic) combined with volume analysis.
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize Momentum Scalping Strategy.
        
        Args:
            config: Configuration dictionary with strategy parameters
        """
        self.config = config or {}
        
        # RSI parameters (7-period for scalping)
        self.rsi_period = self.config.get('rsi_period', 7)
        self.rsi_momentum_bullish = self.config.get('rsi_momentum_bullish', 55)  # Above 55 = bullish momentum
        self.rsi_momentum_bearish = self.config.get('rsi_momentum_bearish', 45)  # Below 45 = bearish momentum
        
        # MACD parameters (fast scalping settings)
        self.macd_fast = self.config.get('macd_fast', 8)
        self.macd_slow = self.config.get('macd_slow', 17)
        self.macd_signal = self.config.get('macd_signal', 9)
        
        # Stochastic parameters
        self.stoch_period = self.config.get('stoch_period', 14)
        self.stoch_k_smooth = self.config.get('stoch_k_smooth', 3)
        self.stoch_d_smooth = self.config.get('stoch_d_smooth', 3)
        self.stoch_momentum_bullish = self.config.get('stoch_momentum_bullish', 50)
        self.stoch_momentum_bearish = self.config.get('stoch_momentum_bearish', 50)
        
        # Volume parameters
        self.volume_threshold = self.config.get('volume_threshold', 1.2)  # 1.2x average = momentum
        self.volume_period = self.config.get('volume_period', 20)
        
        # Risk management
        self.stop_loss_pips = self.config.get('sl_pips', 10)  # 10 pips tight SL
        self.take_profit_pips = self.config.get('tp_pips', 20)  # 20 pips quick TP
        self.pip_value = self.config.get('pip_value', 0.1)  # For XAUUSD
    
    def detect_candle_momentum(self, data: pd.DataFrame) -> Dict:
        """
        Detect strong candle patterns indicating momentum.
        
        Strong momentum candles have:
        - Long body (close far from open)
        - Small wicks (minimal rejection)
        - Body at least 70% of total candle range
        
        Args:
            data: OHLCV DataFrame
        
        Returns:
            Dict with candle momentum info
        """
        current = data.iloc[-1]
        
        # Calculate candle metrics
        body = abs(current['close'] - current['open'])
        upper_wick = current['high'] - max(current['open'], current['close'])
        lower_wick = min(current['open'], current['close']) - current['low']
        total_range = current['high'] - current['low']
        
        if total_range == 0:
            return {
                'has_momentum': False,
                'direction': 0,
                'body_ratio': 0,
                'strength': 0
            }
        
        body_ratio = body / total_range
        
        # Strong bullish candle
        if current['close'] > current['open'] and body_ratio >= 0.7:
            return {
                'has_momentum': True,
                'direction': 1,
                'body_ratio': body_ratio,
                'strength': min(100, body_ratio * 100),
                'type': 'strong_bullish'
            }
        
        # Strong bearish candle
        elif current['close'] < current['open'] and body_ratio >= 0.7:
            return {
                'has_momentum': True,
                'direction': -1,
                'body_ratio': body_ratio,
                'strength': min(100, body_ratio * 100),
                'type': 'strong_bearish'
            }
        
        return {
            'has_momentum': False,
            'direction': 0,
            'body_ratio': body_ratio,
            'strength': 0,
            'type': 'weak_momentum'
        }
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Analyze market for momentum scalping opportunities.
        
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
        
        # Step 1: Calculate RSI
        rsi = calculate_rsi(data, period=self.rsi_period)
        current_rsi = rsi.iloc[-1]
        
        # Determine RSI momentum
        rsi_bullish = current_rsi > self.rsi_momentum_bullish
        rsi_bearish = current_rsi < self.rsi_momentum_bearish
        
        if not (rsi_bullish or rsi_bearish):
            return {
                'signal': 0,
                'confidence': 0,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': [],
                'reason': 'No RSI momentum detected'
            }
        
        # Step 2: Calculate MACD
        macd_line, signal_line, macd_histogram_series = calculate_macd(
            data, fast_period=self.macd_fast, slow_period=self.macd_slow,
            signal_period=self.macd_signal
        )
        macd_line_val = macd_line.iloc[-1]
        signal_line_val = signal_line.iloc[-1]
        macd_histogram = macd_line_val - signal_line_val
        
        # MACD confirmation
        macd_confirmed = (
            (rsi_bullish and macd_histogram > 0) or
            (rsi_bearish and macd_histogram < 0)
        )
        
        # Step 3: Calculate Stochastic
        stoch_k, stoch_d = calculate_stochastic(data, k_period=self.stoch_period, d_period=self.stoch_d_smooth)
        stoch = {'K': stoch_k, 'D': stoch_d}
        stoch_k = stoch['K'].iloc[-1]
        stoch_d = stoch['D'].iloc[-1]
        
        # Stochastic confirmation
        stoch_confirmed = (
            (rsi_bullish and stoch_k > self.stoch_momentum_bullish) or
            (rsi_bearish and stoch_k < self.stoch_momentum_bearish)
        )
        
        # Step 4: Volume confirmation
        volume_ratio = calculate_relative_volume(data, period=self.volume_period)
        volume_confirmed = volume_ratio >= self.volume_threshold
        
        # Step 5: Candle momentum check
        candle_momentum = self.detect_candle_momentum(data)
        candle_confirmed = (
            candle_momentum['has_momentum'] and
            ((rsi_bullish and candle_momentum['direction'] == 1) or
             (rsi_bearish and candle_momentum['direction'] == -1))
        )
        
        # Step 6: Count confluences
        confluences = []
        confidence = 30  # Base confidence
        signal_direction = 1 if rsi_bullish else -1
        
        confluences.append(f'RSI_momentum_{"bullish" if rsi_bullish else "bearish"}')
        confidence += 20
        
        if macd_confirmed:
            confluences.append(f'MACD_histogram_{"positive" if signal_direction == 1 else "negative"}')
            confidence += 20
        
        if stoch_confirmed:
            confluences.append(f'Stochastic_{"above_50" if signal_direction == 1 else "below_50"}')
            confidence += 15
        
        if volume_confirmed:
            confluences.append(f'Volume_above_average_{volume_ratio:.2f}x')
            confidence += 10
        
        if candle_confirmed:
            confluences.append(f'Strong_candle_{candle_momentum["type"]}')
            confidence += 5
        
        # Require minimum 3 confluences (RSI + 2 others)
        if len(confluences) < 3:
            return {
                'signal': 0,
                'confidence': confidence,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': confluences,
                'reason': 'Insufficient momentum confluence (need 3+)'
            }
        
        # Step 7: Calculate entry, SL, TP
        current_close = data['close'].iloc[-1]
        
        if signal_direction == 1:  # Bullish momentum
            entry = current_close
            sl = current_close - (self.stop_loss_pips * self.pip_value)
            tp = current_close + (self.take_profit_pips * self.pip_value)
        else:  # Bearish momentum
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
            'rsi': current_rsi,
            'macd_histogram': macd_histogram,
            'stochastic_k': stoch_k,
            'volume_ratio': volume_ratio,
            'candle_strength': candle_momentum.get('strength', 0),
            'risk_reward': f"1:{risk_reward:.1f}",
            'reason': 'Strong momentum with confluences'
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
    strategy = MomentumScalping()
    result = strategy.analyze(sample_data)
    
    print("=" * 80)
    print("MOMENTUM SCALPING STRATEGY TEST")
    print("=" * 80)
    print(f"Signal: {result['signal']}")
    print(f"Confidence: {result['confidence']}%")
    print(f"Entry: {result.get('entry')}")
    print(f"SL: {result.get('sl')}")
    print(f"TP: {result.get('tp')}")
    print(f"Confluences: {result['confluences']}")
    print(f"Reason: {result['reason']}")
    print("=" * 80)

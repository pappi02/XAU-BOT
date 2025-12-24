"""
Scalping Breakouts Strategy

Professional breakout scalping strategy that captures rapid price movements when
an asset breaks above or below key technical levels. Uses volume confirmation
and the 8-indicator professional system for entry validation.

Timeframes: 1-5 minute charts (M1, M3, M5)
Risk-Reward: 1:1 to 1:2
Stop Loss: Tight (5-15 pips, just below/above breakout level)
Take Profit: Quick (10-25 pips)

Entry Criteria:
- Price breaks above resistance or below support (clear breakout)
- Volume confirms breakout (1.5x average volume spike)
- CCI extreme levels confirm momentum (>100 for bullish, <-100 for bearish)
- MACD histogram confirms direction
- Parabolic SAR dots align with breakout direction

Exit Criteria:
- Take profit at 1:1.5 or 1:2 R:R
- Stop loss triggered if breakout fails
- Exit immediately if volume drops or SAR reverses

Best Market Conditions:
- High volatility periods
- Clear technical levels (support/resistance)
- High liquidity market hours (London/NY sessions)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

from indicators import (
    calculate_bollinger_bands,
    calculate_cci,
    calculate_macd,
    calculate_parabolic_sar,
    detect_volume_spike,
    calculate_relative_volume
)


class BreakoutScalping:
    """
    Professional Scalping Breakouts Strategy
    
    Focuses on capturing quick profits from rapid price movements at key breakout levels.
    Uses volume confirmation and multiple indicator confluence for high-probability entries.
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize Breakout Scalping Strategy.
        
        Args:
            config: Configuration dictionary with strategy parameters
        """
        self.config = config or {}
        
        # Breakout detection parameters
        self.lookback_period = self.config.get('breakout_lookback', 20)
        self.breakout_strength_threshold = self.config.get('breakout_strength', 0.5)  # % beyond level
        
        # Volume confirmation
        self.volume_spike_threshold = self.config.get('volume_spike_threshold', 1.5)
        self.volume_period = self.config.get('volume_period', 20)
        
        # CCI parameters
        self.cci_period = self.config.get('cci_period', 20)
        self.cci_breakout_threshold = self.config.get('cci_breakout_threshold', 100)
        
        # MACD parameters (fast scalping settings)
        self.macd_fast = self.config.get('macd_fast', 8)
        self.macd_slow = self.config.get('macd_slow', 17)
        self.macd_signal = self.config.get('macd_signal', 9)
        
        # Risk management
        self.stop_loss_atr_multiplier = self.config.get('sl_atr_multiplier', 1.5)
        self.take_profit_rr_ratio = self.config.get('tp_rr_ratio', 1.5)  # 1:1.5 R:R
        self.max_risk_per_trade = self.config.get('max_risk_pct', 0.01)  # 1% max risk
    
    def identify_support_resistance(self, data: pd.DataFrame) -> Dict:
        """
        Identify key support and resistance levels using recent swing highs/lows.
        
        Args:
            data: OHLCV DataFrame
        
        Returns:
            Dict with support and resistance levels
        """
        # Get recent highs and lows
        recent_data = data.tail(self.lookback_period)
        
        # Find swing highs (resistance)
        resistance_levels = []
        for i in range(2, len(recent_data) - 2):
            if (recent_data['high'].iloc[i] > recent_data['high'].iloc[i-1] and
                recent_data['high'].iloc[i] > recent_data['high'].iloc[i-2] and
                recent_data['high'].iloc[i] > recent_data['high'].iloc[i+1] and
                recent_data['high'].iloc[i] > recent_data['high'].iloc[i+2]):
                resistance_levels.append(recent_data['high'].iloc[i])
        
        # Find swing lows (support)
        support_levels = []
        for i in range(2, len(recent_data) - 2):
            if (recent_data['low'].iloc[i] < recent_data['low'].iloc[i-1] and
                recent_data['low'].iloc[i] < recent_data['low'].iloc[i-2] and
                recent_data['low'].iloc[i] < recent_data['low'].iloc[i+1] and
                recent_data['low'].iloc[i] < recent_data['low'].iloc[i+2]):
                support_levels.append(recent_data['low'].iloc[i])
        
        return {
            'resistance': resistance_levels[-3:] if len(resistance_levels) >= 3 else resistance_levels,
            'support': support_levels[-3:] if len(support_levels) >= 3 else support_levels,
            'nearest_resistance': max(resistance_levels) if resistance_levels else None,
            'nearest_support': min(support_levels) if support_levels else None
        }
    
    def detect_breakout(self, data: pd.DataFrame, levels: Dict) -> Dict:
        """
        Detect if price has broken above resistance or below support.
        
        Args:
            data: OHLCV DataFrame
            levels: Support/resistance levels from identify_support_resistance()
        
        Returns:
            Dict with breakout info: direction, level, strength
        """
        current_close = data['close'].iloc[-1]
        current_high = data['high'].iloc[-1]
        current_low = data['low'].iloc[-1]
        
        breakout_info = {
            'detected': False,
            'direction': 0,
            'level': None,
            'strength': 0,
            'type': None
        }
        
        # Check bullish breakout (above resistance)
        if levels['nearest_resistance']:
            resistance = levels['nearest_resistance']
            if current_close > resistance:
                breakout_strength = (current_close - resistance) / resistance * 100
                if breakout_strength >= self.breakout_strength_threshold:
                    breakout_info = {
                        'detected': True,
                        'direction': 1,
                        'level': resistance,
                        'strength': breakout_strength,
                        'type': 'resistance_breakout'
                    }
        
        # Check bearish breakout (below support)
        if levels['nearest_support'] and not breakout_info['detected']:
            support = levels['nearest_support']
            if current_close < support:
                breakout_strength = (support - current_close) / support * 100
                if breakout_strength >= self.breakout_strength_threshold:
                    breakout_info = {
                        'detected': True,
                        'direction': -1,
                        'level': support,
                        'strength': breakout_strength,
                        'type': 'support_breakout'
                    }
        
        return breakout_info
    
    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Analyze market for breakout scalping opportunities.
        
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
        
        # Step 1: Identify support/resistance levels
        levels = self.identify_support_resistance(data)
        
        # Step 2: Detect breakout
        breakout = self.detect_breakout(data, levels)
        
        if not breakout['detected']:
            return {
                'signal': 0,
                'confidence': 0,
                'entry': None,
                'sl': None,
                'tp': None,
                'confluences': [],
                'reason': 'No breakout detected'
            }
        
        # Step 3: Volume confirmation
        volume_spike = detect_volume_spike(data, threshold=self.volume_spike_threshold,
                                          period=self.volume_period)
        volume_confirmed = volume_spike['is_spike']
        
        # Step 4: CCI confirmation
        cci = calculate_cci(data, period=self.cci_period)
        current_cci = cci.iloc[-1]
        cci_confirmed = (
            (breakout['direction'] == 1 and current_cci > self.cci_breakout_threshold) or
            (breakout['direction'] == -1 and current_cci < -self.cci_breakout_threshold)
        )
        
        # Step 5: MACD confirmation
        macd_line, macd_signal, macd_histogram_series = calculate_macd(
            data, fast_period=self.macd_fast, slow_period=self.macd_slow,
            signal_period=self.macd_signal
        )
        macd_histogram = macd_histogram_series.iloc[-1]
        macd_confirmed = (
            (breakout['direction'] == 1 and macd_histogram > 0) or
            (breakout['direction'] == -1 and macd_histogram < 0)
        )
        
        # Step 6: Parabolic SAR confirmation
        sar = calculate_parabolic_sar(data)
        current_close = data['close'].iloc[-1]
        current_sar = sar.iloc[-1]
        sar_confirmed = (
            (breakout['direction'] == 1 and current_close > current_sar) or
            (breakout['direction'] == -1 and current_close < current_sar)
        )
        
        # Step 7: Count confluences
        confluences = []
        confidence = 40  # Base confidence for breakout detection
        
        if volume_confirmed:
            confluences.append('Volume_spike_confirmation')
            confidence += 20
        
        if cci_confirmed:
            confluences.append(f'CCI_{"bullish" if breakout["direction"] == 1 else "bearish"}_momentum')
            confidence += 15
        
        if macd_confirmed:
            confluences.append(f'MACD_histogram_{"positive" if breakout["direction"] == 1 else "negative"}')
            confidence += 15
        
        if sar_confirmed:
            confluences.append(f'SAR_{"above" if breakout["direction"] == 1 else "below"}_price')
            confidence += 10
        
        # Require minimum 2 confluences for signal
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
        current_high = data['high'].iloc[-1]
        current_low = data['low'].iloc[-1]
        atr = current_high - current_low  # Simple ATR for current candle
        
        if breakout['direction'] == 1:  # Bullish breakout
            entry = current_close
            sl = breakout['level'] - (atr * self.stop_loss_atr_multiplier)
            risk = entry - sl
            tp = entry + (risk * self.take_profit_rr_ratio)
        else:  # Bearish breakout
            entry = current_close
            sl = breakout['level'] + (atr * self.stop_loss_atr_multiplier)
            risk = sl - entry
            tp = entry - (risk * self.take_profit_rr_ratio)
        
        return {
            'signal': breakout['direction'],
            'confidence': min(100, confidence),
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'confluences': confluences,
            'breakout_type': breakout['type'],
            'breakout_level': breakout['level'],
            'breakout_strength': breakout['strength'],
            'volume_spike': volume_spike['spike_ratio'],
            'cci': current_cci,
            'macd_histogram': macd_histogram,
            'risk_reward': f"1:{self.take_profit_rr_ratio}",
            'reason': 'Breakout confirmed with confluences'
        }


if __name__ == "__main__":
    # Example usage
    import pandas as pd
    
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
    strategy = BreakoutScalping()
    result = strategy.analyze(sample_data)
    
    print("=" * 80)
    print("BREAKOUT SCALPING STRATEGY TEST")
    print("=" * 80)
    print(f"Signal: {result['signal']}")
    print(f"Confidence: {result['confidence']}%")
    print(f"Entry: {result.get('entry')}")
    print(f"SL: {result.get('sl')}")
    print(f"TP: {result.get('tp')}")
    print(f"Confluences: {result['confluences']}")
    print(f"Reason: {result['reason']}")
    print("=" * 80)

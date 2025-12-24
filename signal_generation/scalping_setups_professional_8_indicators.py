"""
scalping_setups_professional_8_indicators.py

Enhanced Professional Scalping Setups combining all 8 indicators
from the Professional Trading Guide:

1. RSI (7-period) - Overbought/oversold levels
2. Bollinger Bands (20-period) - Volatility and reversal zones
3. Stochastic Oscillator (20/80 levels) - Fast momentum detection
4. Parabolic SAR - 3-dot entry strategy (trend following)
5. Commodity Channel Index (CCI) - Extreme level reversals (±200)
6. MACD (8/17/9) - Fast momentum and divergence
7. Ichimoku Cloud - Cloud breakout entries
8. TRIX (Triple EMA) - Zero-line momentum crosses

This module provides 4 enhanced analyzer classes that combine these indicators
for high-probability scalping setups on M5/M15 timeframes.

Author: Professional Scalping Suite
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

# Import all indicators
from indicators import (
    # Core indicators
    calculate_rsi, detect_rsi_divergence, is_rsi_overbought, is_rsi_oversold,
    calculate_bollinger_bands, get_bollinger_signal, get_bollinger_position,
    calculate_stochastic, is_stoch_overbought, is_stoch_oversold,
    calculate_macd, detect_macd_divergence,
    
    # Scalping indicators
    calculate_parabolic_sar, get_parabolic_sar_signal,
    calculate_cci, get_cci_signal, get_cci_extremes,
    calculate_ichimoku, get_ichimoku_signal,
    calculate_trix, get_trix_signal, detect_trix_divergence
)

class OscillatorReversal:
    """
    Setup 1: Oscillator Reversal (RSI + CCI + Stochastic + Bollinger)
    
    High-probability reversal entries when multiple oscillators align:
    - RSI at extreme levels (>70 or <30)
    - CCI at extreme levels (±200)
    - Stochastic confirming (20/80 levels)
    - Price near Bollinger Bands
    
    Entry: When oscillators align (2+) + momentum confirmation
    Exit: When reversal starts to fade (opposite oscillator signal)
    """
    
    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.rsi = calculate_rsi(data, period=7)
        self.cci = calculate_cci(data, period=20)
        self.stoch = calculate_stochastic(data, period=14, k=3, d=3)
        bb = calculate_bollinger_bands(data, period=20, num_std=2)
        self.bb_upper = bb['upper']
        self.bb_lower = bb['lower']
        self.bb_middle = bb['middle']
    
    def analyze(self) -> Dict:
        """
        Analyze reversal setup.
        
        Returns:
            Dict with: signal, strength (0-100), entry_type, sl, tp, confluences
        """
        # Get current values
        current_rsi = self.rsi.iloc[-1]
        current_cci = self.cci.iloc[-1]
        current_stoch_k = self.stoch['K'].iloc[-1]
        current_close = self.data['close'].iloc[-1]
        current_high = self.data['high'].iloc[-1]
        current_low = self.data['low'].iloc[-1]
        current_atr = (current_high - current_low)
        
        confluences = []
        signal_strength = 0
        signal = 0
        
        # Bullish Reversal Setup (From Oversold)
        if current_rsi < 30:
            confluences.append('RSI_oversold')
            signal_strength += 25
            signal = 1
        
        if current_cci < -100:
            confluences.append('CCI_oversold')
            signal_strength += 25
            signal = 1
        
        if current_stoch_k < 20:
            confluences.append('Stochastic_oversold')
            signal_strength += 20
            signal = 1
        
        if current_close < self.bb_lower.iloc[-1]:
            confluences.append('Price_below_lower_BB')
            signal_strength += 15
            signal = 1
        
        # Bearish Reversal Setup (From Overbought)
        if current_rsi > 70:
            confluences.append('RSI_overbought')
            signal_strength += 25
            signal = -1
        
        if current_cci > 100:
            confluences.append('CCI_overbought')
            signal_strength += 25
            signal = -1
        
        if current_stoch_k > 80:
            confluences.append('Stochastic_overbought')
            signal_strength += 20
            signal = -1
        
        if current_close > self.bb_upper.iloc[-1]:
            confluences.append('Price_above_upper_BB')
            signal_strength += 15
            signal = -1
        
        # Cap strength at 100
        signal_strength = min(100, signal_strength)
        
        # Only signal if we have at least 2 confluences
        if len(confluences) < 2:
            signal = 0
            signal_strength = 0
        
        # Calculate SL and TP
        sl = current_low - (current_atr * 1.5) if signal == 1 else current_high + (current_atr * 1.5)
        tp = current_high + (current_atr * 2) if signal == 1 else current_low - (current_atr * 2)
        
        return {
            'signal': signal,
            'strength': signal_strength,
            'entry_type': 'reversal',
            'confluences': confluences,
            'sl': sl,
            'tp': tp,
            'rsi': current_rsi,
            'cci': current_cci,
            'stoch': current_stoch_k
        }

class CloudBreakout:
    """
    Setup 2: Ichimoku Cloud Breakout (Ichimoku + TRIX + MACD)
    
    Strong trend entries when price breaks Ichimoku cloud with momentum:
    - Price breaks above/below cloud (primary signal)
    - TRIX crosses zero in same direction (momentum confirmation)
    - MACD confirms trend (histogram positive/negative)
    - Chikou Span above/below price (strength confirmation)
    
    Per Guide: "Don't wait for confirmation, momentum is important"
    Entry: Immediate on cloud breakout
    Exit: Reverse cloud breakout or trend failure
    """
    
    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.ichimoku = calculate_ichimoku(data, tenkan_period=9, kijun_period=26,
                                          senkou_b_period=52, chikou_period=26)
        self.trix = calculate_trix(data, period=15)
        self.macd = calculate_macd(data, fast=8, slow=17, signal_period=9)
    
    def analyze(self) -> Dict:
        """
        Analyze cloud breakout setup.
        
        Returns:
            Dict with: signal, strength (0-100), entry_type, sl, tp, confluences
        """
        # Get current values
        current_close = self.data['close'].iloc[-1]
        current_high = self.data['high'].iloc[-1]
        current_low = self.data['low'].iloc[-1]
        current_atr = current_high - current_low
        
        # Get Ichimoku values
        senkou_a = self.ichimoku['senkou_a'].iloc[-1]
        senkou_b = self.ichimoku['senkou_b'].iloc[-1]
        chikou = self.ichimoku['chikou'].iloc[-1]
        cloud_top = max(senkou_a, senkou_b) if not pd.isna(senkou_a) and not pd.isna(senkou_b) else None
        cloud_bottom = min(senkou_a, senkou_b) if not pd.isna(senkou_a) and not pd.isna(senkou_b) else None
        
        # Get TRIX
        current_trix = self.trix.iloc[-1] if len(self.trix) > 0 else 0
        prev_trix = self.trix.iloc[-2] if len(self.trix) > 1 else 0
        
        # Get MACD
        macd_line = self.macd['macd'].iloc[-1]
        signal_line = self.macd['signal'].iloc[-1]
        histogram = macd_line - signal_line
        prev_histogram = self.macd['macd'].iloc[-2] - self.macd['signal'].iloc[-2] if len(self.macd) > 1 else 0
        
        confluences = []
        signal_strength = 0
        signal = 0
        
        # Check cloud breakout conditions
        if cloud_top is not None and cloud_bottom is not None:
            # Bullish breakout (price above cloud)
            if current_close > cloud_top:
                confluences.append('Above_Cloud')
                signal_strength += 40
                signal = 1
                
                # TRIX confirmation
                if current_trix > 0 and prev_trix <= 0:
                    confluences.append('TRIX_crosses_zero_bullish')
                    signal_strength += 20
                elif current_trix > 0:
                    confluences.append('TRIX_positive')
                    signal_strength += 10
                
                # MACD confirmation
                if histogram > 0 and prev_histogram <= 0:
                    confluences.append('MACD_bullish_crossover')
                    signal_strength += 20
                elif histogram > 0:
                    confluences.append('MACD_bullish')
                    signal_strength += 10
                
                # Chikou confirmation
                if not pd.isna(chikou) and chikou > current_close:
                    confluences.append('Chikou_above_price')
                    signal_strength += 10
            
            # Bearish breakout (price below cloud)
            elif current_close < cloud_bottom:
                confluences.append('Below_Cloud')
                signal_strength += 40
                signal = -1
                
                # TRIX confirmation
                if current_trix < 0 and prev_trix >= 0:
                    confluences.append('TRIX_crosses_zero_bearish')
                    signal_strength += 20
                elif current_trix < 0:
                    confluences.append('TRIX_negative')
                    signal_strength += 10
                
                # MACD confirmation
                if histogram < 0 and prev_histogram >= 0:
                    confluences.append('MACD_bearish_crossover')
                    signal_strength += 20
                elif histogram < 0:
                    confluences.append('MACD_bearish')
                    signal_strength += 10
                
                # Chikou confirmation
                if not pd.isna(chikou) and chikou < current_close:
                    confluences.append('Chikou_below_price')
                    signal_strength += 10
        
        # Cap strength at 100
        signal_strength = min(100, signal_strength)
        
        # Require at least cloud breakout + 1 confirmation
        if len(confluences) < 2:
            signal = 0
            signal_strength = 0
        
        # Calculate SL and TP
        sl = current_low - (current_atr * 1.5) if signal == 1 else current_high + (current_atr * 1.5)
        tp = current_high + (current_atr * 3) if signal == 1 else current_low - (current_atr * 3)
        
        return {
            'signal': signal,
            'strength': signal_strength,
            'entry_type': 'breakout',
            'confluences': confluences,
            'sl': sl,
            'tp': tp,
            'trix': current_trix,
            'macd_histogram': histogram
        }

class TrendFollowingSAR:
    """
    Setup 3: Parabolic SAR Trend Following (SAR + MACD + Bollinger)
    
    Reliable trend continuation entries using SAR 3-dot strategy:
    - SAR produces 3+ consecutive dots (more reliable than 1st dot)
    - MACD confirms trend direction (histogram aligned)
    - Price aligns with Bollinger middle line
    
    Entry: SAR 3-dot signal + MACD confirmation
    Exit: SAR reversal or trend break
    """
    
    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.sar = calculate_parabolic_sar(data, iaf=0.02, maxaf=0.2)
        self.macd = calculate_macd(data, fast=8, slow=17, signal_period=9)
        bb = calculate_bollinger_bands(data, period=20, num_std=2)
        self.bb_middle = bb['middle']
        self.bb_upper = bb['upper']
        self.bb_lower = bb['lower']
    
    def analyze(self) -> Dict:
        """
        Analyze SAR trend following setup.
        
        Returns:
            Dict with: signal, strength (0-100), entry_type, sl, tp, confluences
        """
        # Get SAR signal
        sar_signal = get_parabolic_sar_signal(self.data)
        
        # Get current values
        current_close = self.data['close'].iloc[-1]
        current_high = self.data['high'].iloc[-1]
        current_low = self.data['low'].iloc[-1]
        current_sar = self.sar.iloc[-1]
        
        # Get MACD values
        macd_line = self.macd['macd'].iloc[-1]
        signal_line = self.macd['signal'].iloc[-1]
        histogram = macd_line - signal_line
        
        # Get Bollinger values
        bb_middle = self.bb_middle.iloc[-1]
        
        confluences = []
        signal_strength = 0
        signal = 0
        
        # SAR Bullish (3 dots below price)
        if sar_signal == 1:
            confluences.append('SAR_bullish_signal')
            signal_strength += 40
            signal = 1
            
            # MACD confirmation
            if histogram > 0:
                confluences.append('MACD_bullish')
                signal_strength += 20
            
            # Price near middle Bollinger (trend confirmation)
            if current_close > bb_middle:
                confluences.append('Price_above_BB_middle')
                signal_strength += 15
            
            # SAR below current price (good entry area)
            if current_sar < current_low:
                confluences.append('SAR_well_below_price')
                signal_strength += 10
        
        # SAR Bearish (3 dots above price)
        elif sar_signal == -1:
            confluences.append('SAR_bearish_signal')
            signal_strength += 40
            signal = -1
            
            # MACD confirmation
            if histogram < 0:
                confluences.append('MACD_bearish')
                signal_strength += 20
            
            # Price near middle Bollinger (trend confirmation)
            if current_close < bb_middle:
                confluences.append('Price_below_BB_middle')
                signal_strength += 15
            
            # SAR above current price (good entry area)
            if current_sar > current_high:
                confluences.append('SAR_well_above_price')
                signal_strength += 10
        
        # Cap strength at 100
        signal_strength = min(100, signal_strength)
        
        # Require SAR signal + at least 1 confirmation
        if len(confluences) < 2:
            signal = 0
            signal_strength = 0
        
        # Calculate SL and TP
        atr = current_high - current_low
        if signal == 1:
            sl = current_sar
            tp = current_close + (atr * 2.5)
        else:
            sl = current_sar
            tp = current_close - (atr * 2.5)
        
        return {
            'signal': signal,
            'strength': signal_strength,
            'entry_type': 'trend_following',
            'confluences': confluences,
            'sl': sl,
            'tp': tp,
            'sar_value': current_sar,
            'macd_histogram': histogram
        }

class ScalpingMasterAnalyzer:
    """
    Master analyzer combining all 3 setups (8 indicators total).
    
    Weighted analysis:
    1. Oscillator Reversal: 30% weight (good for ranging markets)
    2. Cloud Breakout: 35% weight (best for trending markets)
    3. SAR Trend Following: 35% weight (reliable entry/exit)
    
    Returns highest-probability setup for each bar.
    """
    
    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.oscillator = OscillatorReversal(data)
        self.cloud = CloudBreakout(data)
        self.sar = TrendFollowingSAR(data)
    
    def analyze(self) -> Dict:
        """
        Analyze all 3 setups and return master signal.
        
        Returns:
            Dict with: signal, strength, entry_type, all_setups, primary_setup,
                      sl, tp, confluences
        """
        # Analyze each setup
        oscillator_analysis = self.oscillator.analyze()
        cloud_analysis = self.cloud.analyze()
        sar_analysis = self.sar.analyze()
        
        # Weighted scoring
        oscillator_score = oscillator_analysis['strength'] * 0.30
        cloud_score = cloud_analysis['strength'] * 0.35
        sar_score = sar_analysis['strength'] * 0.35
        
        # Get all signals
        all_signals = [
            oscillator_analysis['signal'],
            cloud_analysis['signal'],
            sar_analysis['signal']
        ]
        
        # Determine master signal (majority vote)
        bullish_count = sum(1 for s in all_signals if s == 1)
        bearish_count = sum(1 for s in all_signals if s == -1)
        
        if bullish_count > bearish_count:
            master_signal = 1
        elif bearish_count > bullish_count:
            master_signal = -1
        else:
            master_signal = 0
        
        # Determine primary setup (highest individual strength)
        scores = {
            'oscillator_reversal': oscillator_score,
            'cloud_breakout': cloud_score,
            'sar_trend_following': sar_score
        }
        
        primary_setup = max(scores, key=scores.get)
        master_strength = max(oscillator_score, cloud_score, sar_score)
        
        # Collect all confluences
        all_confluences = (
            oscillator_analysis.get('confluences', []) +
            cloud_analysis.get('confluences', []) +
            sar_analysis.get('confluences', [])
        )
        
        # Determine SL and TP
        if primary_setup == 'oscillator_reversal':
            sl = oscillator_analysis['sl']
            tp = oscillator_analysis['tp']
        elif primary_setup == 'cloud_breakout':
            sl = cloud_analysis['sl']
            tp = cloud_analysis['tp']
        else:
            sl = sar_analysis['sl']
            tp = sar_analysis['tp']
        
        return {
            'signal': master_signal,
            'strength': min(100, master_strength),
            'entry_type': primary_setup,
            'all_setups': {
                'oscillator_reversal': oscillator_analysis,
                'cloud_breakout': cloud_analysis,
                'sar_trend_following': sar_analysis
            },
            'primary_setup': primary_setup,
            'sl': sl,
            'tp': tp,
            'confluences': all_confluences,
            'setup_scores': scores,
            'signal_agreement': sum(1 for s in all_signals if s == master_signal) if master_signal != 0 else 0
        }

if __name__ == "__main__":
    # Example usage
    dates = pd.date_range('2024-01-01', periods=100, freq='5min')
    prices = 2600 + np.cumsum(np.random.randn(100) * 2)
    
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(100) * 0.5,
        'high': prices + np.abs(np.random.randn(100)),
        'low': prices - np.abs(np.random.randn(100)),
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)
    
    # Test master analyzer
    print("=" * 80)
    print("PROFESSIONAL 8-INDICATOR SCALPING SETUP ANALYSIS")
    print("=" * 80)
    
    analyzer = ScalpingMasterAnalyzer(sample_data)
    result = analyzer.analyze()
    
    print(f"\n📊 Master Signal: {result['signal']}")
    print(f"   Strength: {result['strength']:.1f}%")
    print(f"   Entry Type: {result['entry_type']}")
    print(f"   Signal Agreement: {result['signal_agreement']}/3 setups")
    
    print(f"\n💰 Risk Management:")
    print(f"   Stop Loss: {result['sl']:.2f}")
    print(f"   Take Profit: {result['tp']:.2f}")
    
    print(f"\n🎯 Setup Scores:")
    for setup, score in result['setup_scores'].items():
        print(f"   {setup}: {score:.1f}")
    
    print(f"\n✓ Total Confluences: {len(result['confluences'])}")
    for confluence in result['confluences'][:10]:
        print(f"   • {confluence}")
    
    print("\n" + "=" * 80)

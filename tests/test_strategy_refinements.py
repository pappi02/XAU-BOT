"""
Tests for strategy refinement components.
Validates regime calibration, multi-timeframe confirmation, and indicator smoothing.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.strategy_refinements import (
    RegimeCalibrator, MultiTimeframeConfirmation, IndicatorSmoother
)


def create_sample_data(trend: str = 'bullish', volatility: str = 'normal', length: int = 100) -> pd.DataFrame:
    """
    Create sample OHLC data for testing.
    
    Args:
        trend: 'bullish', 'bearish', or 'ranging'
        volatility: 'low', 'normal', or 'high'
        length: Number of candles
    
    Returns:
        DataFrame with OHLC data
    """
    dates = pd.date_range('2023-01-01', periods=length, freq='5min')
    
    # Base price movement
    if trend == 'bullish':
        base = np.cumsum(np.abs(np.random.randn(length)) * 0.5)
    elif trend == 'bearish':
        base = -np.cumsum(np.abs(np.random.randn(length)) * 0.5)
    else:  # ranging
        base = np.sin(np.arange(length) * 0.1) * 5
    
    # Volatility adjustment
    vol_multiplier = {'low': 0.3, 'normal': 1.0, 'high': 2.5}[volatility]
    noise = np.random.randn(length) * vol_multiplier
    
    prices = 2000 + base + noise
    
    df = pd.DataFrame({
        'time': dates,
        'open': prices + np.random.randn(length) * 0.2,
        'high': prices + abs(np.random.randn(length) * 0.5),
        'low': prices - abs(np.random.randn(length) * 0.5),
        'close': prices
    })
    
    # Add indicators
    df['ema_fast'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=26, adjust=False).mean()
    df['rsi'] = 50 + np.random.randn(length) * 15  # Simplified RSI
    
    # Calculate ATR
    high_low = df['high'] - df['low']
    df['atr'] = high_low.rolling(window=14).mean()
    
    # Calculate ADX (simplified)
    if trend == 'bullish' or trend == 'bearish':
        df['adx'] = 30 + np.random.randn(length) * 5  # Trending
    else:
        df['adx'] = 15 + np.random.randn(length) * 3  # Ranging
    
    return df


def test_regime_detection():
    """Test market regime detection."""
    print("\n🔍 Testing market regime detection...")
    
    calibrator = RegimeCalibrator()
    
    # Test trending bullish
    data_trending_bull = create_sample_data(trend='bullish', volatility='normal')
    regime = calibrator.detect_regime(data_trending_bull)
    print(f"  ✅ Trending bullish data → Regime: {regime}")
    
    # Test trending bearish
    data_trending_bear = create_sample_data(trend='bearish', volatility='normal')
    regime = calibrator.detect_regime(data_trending_bear)
    print(f"  ✅ Trending bearish data → Regime: {regime}")
    
    # Test ranging
    data_ranging = create_sample_data(trend='ranging', volatility='normal')
    regime = calibrator.detect_regime(data_ranging)
    print(f"  ✅ Ranging data → Regime: {regime}")
    
    # Test volatile
    data_volatile = create_sample_data(trend='bullish', volatility='high')
    regime = calibrator.detect_regime(data_volatile)
    print(f"  ✅ High volatility data → Regime: {regime}")


def test_regime_calibration():
    """Test regime-specific parameter calibration."""
    print("\n🔍 Testing regime-specific calibration...")
    
    calibrator = RegimeCalibrator()
    
    base_params = {
        'ema_fast': 12,
        'ema_slow': 26,
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0
    }
    
    # Test trending calibration
    calibrated_trending = calibrator.calibrate_indicator_params('trending_bullish', base_params)
    print(f"  ✅ Trending calibration: EMA {calibrated_trending['ema_fast']}/{calibrated_trending['ema_slow']}, "
          f"RSI period {calibrated_trending['rsi_period']}")
    
    # Test ranging calibration
    calibrated_ranging = calibrator.calibrate_indicator_params('ranging', base_params)
    print(f"  ✅ Ranging calibration: EMA {calibrated_ranging['ema_fast']}/{calibrated_ranging['ema_slow']}, "
          f"RSI period {calibrated_ranging['rsi_period']}")
    
    # Test volatile calibration
    calibrated_volatile = calibrator.calibrate_indicator_params('volatile', base_params)
    print(f"  ✅ Volatile calibration: BB period {calibrated_volatile['bb_period']}, "
          f"BB std {calibrated_volatile['bb_std']}")
    
    # Verify ranges
    assert calibrated_ranging['ema_fast'] <= 12, "Ranging EMA should be shorter or equal"
    assert calibrated_trending['rsi_period'] >= 14, "Trending RSI should be longer or equal"


def test_rsi_thresholds():
    """Test RSI threshold adjustment by regime."""
    print("\n🔍 Testing RSI threshold adjustment...")
    
    calibrator = RegimeCalibrator()
    
    regimes = ['trending_bullish', 'trending_bearish', 'ranging', 'volatile', 'default']
    
    for regime in regimes:
        thresholds = calibrator.get_rsi_thresholds(regime)
        print(f"  ✅ {regime}: oversold={thresholds['oversold']}, "
              f"overbought={thresholds['overbought']}")
        
        # Verify logic
        assert thresholds['oversold'] < thresholds['overbought'], "Oversold should be < overbought"
        assert 15 <= thresholds['oversold'] <= 40, "Oversold should be in reasonable range"
        assert 60 <= thresholds['overbought'] <= 85, "Overbought should be in reasonable range"


def test_indicator_smoothing():
    """Test indicator smoothing."""
    print("\n🔍 Testing indicator smoothing...")
    
    smoother = IndicatorSmoother()
    
    # Create noisy data
    data = create_sample_data(trend='bullish', volatility='high')
    
    # Smooth EMA
    smoothed_ema = smoother.smooth_ema(data, 'ema_fast', smooth_period=3)
    original_std = data['ema_fast'].std()
    smoothed_std = smoothed_ema.std()
    
    print(f"  ✅ EMA smoothing: original std={original_std:.2f}, smoothed std={smoothed_std:.2f}")
    assert smoothed_std <= original_std, "Smoothed EMA should have lower volatility"
    
    # Smooth RSI
    smoothed_rsi = smoother.smooth_rsi(data, 'rsi', smooth_period=3)
    rsi_original_std = data['rsi'].std()
    rsi_smoothed_std = smoothed_rsi.std()
    
    print(f"  ✅ RSI smoothing: original std={rsi_original_std:.2f}, smoothed std={rsi_smoothed_std:.2f}")
    assert rsi_smoothed_std <= rsi_original_std, "Smoothed RSI should have lower volatility"


def test_conflict_detection():
    """Test signal conflict detection."""
    print("\n🔍 Testing signal conflict detection...")
    
    smoother = IndicatorSmoother()
    
    # Test no conflict
    has_conflict, desc = smoother.remove_conflicting_signals(
        technical_score=50,    # Bullish
        pattern_signal=1,      # Bullish
        news_signal=1          # Bullish
    )
    print(f"  ✅ No conflict case: {desc}")
    assert not has_conflict, "Should detect no conflict"
    
    # Test technical vs pattern conflict
    has_conflict, desc = smoother.remove_conflicting_signals(
        technical_score=50,    # Bullish
        pattern_signal=-1,     # Bearish
        news_signal=0          # Neutral
    )
    print(f"  ✅ Conflict case: {desc}")
    assert has_conflict, "Should detect conflict"
    
    # Test all conflicting
    has_conflict, desc = smoother.remove_conflicting_signals(
        technical_score=50,    # Bullish
        pattern_signal=-1,     # Bearish
        news_signal=-1         # Bearish
    )
    print(f"  ✅ Multiple conflicts: {desc}")
    assert has_conflict, "Should detect multiple conflicts"


def test_signal_persistence():
    """Test signal persistence filter."""
    print("\n🔍 Testing signal persistence filter...")
    
    smoother = IndicatorSmoother()
    
    # Test not persistent
    history = ['HOLD', 'BUY']
    is_persistent, reason = smoother.apply_signal_persistence_filter(
        history, 'BUY', min_persistence=3
    )
    print(f"  ✅ Not persistent: {reason}")
    assert not is_persistent, "Should detect non-persistent signal"
    
    # Test persistent
    history = ['BUY', 'BUY']
    is_persistent, reason = smoother.apply_signal_persistence_filter(
        history, 'BUY', min_persistence=3
    )
    print(f"  ✅ Persistent: {reason}")
    assert is_persistent, "Should detect persistent signal"
    
    # Test HOLD always accepted
    history = ['SELL', 'BUY']
    is_persistent, reason = smoother.apply_signal_persistence_filter(
        history, 'HOLD', min_persistence=3
    )
    print(f"  ✅ HOLD accepted: {reason}")
    assert is_persistent, "HOLD should always be persistent"


def test_mtf_trend_detection():
    """Test multi-timeframe trend detection."""
    print("\n🔍 Testing multi-timeframe trend detection...")
    
    mtf = MultiTimeframeConfirmation(mt5_connection=None)
    
    # Test bullish trend
    data_bull = create_sample_data(trend='bullish')
    trend = mtf.get_trend_direction(data_bull)
    print(f"  ✅ Bullish data → Trend: {trend}")
    assert trend in ['bullish', None], "Should detect bullish or unclear"
    
    # Test bearish trend
    data_bear = create_sample_data(trend='bearish')
    trend = mtf.get_trend_direction(data_bear)
    print(f"  ✅ Bearish data → Trend: {trend}")
    assert trend in ['bearish', None], "Should detect bearish or unclear"
    
    # Test ranging (unclear)
    data_range = create_sample_data(trend='ranging')
    trend = mtf.get_trend_direction(data_range)
    print(f"  ✅ Ranging data → Trend: {trend}")


def run_all_tests():
    """Run all strategy refinement tests."""
    print("\n" + "="*80)
    print("🎯 STRATEGY REFINEMENT TEST SUITE")
    print("="*80)
    
    test_regime_detection()
    test_regime_calibration()
    test_rsi_thresholds()
    test_indicator_smoothing()
    test_conflict_detection()
    test_signal_persistence()
    test_mtf_trend_detection()
    
    print("\n" + "="*80)
    print("✅ All strategy refinement tests completed successfully!")
    print("="*80)


if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

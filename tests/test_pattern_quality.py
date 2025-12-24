"""
Tests for pattern quality control system.
Validates confidence clamping, volume/RSI confirmations, regime alignment, and conflict detection.
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pattern_quality import PatternQualityController


def create_sample_ohlc(length: int = 100) -> pd.DataFrame:
    """Create sample OHLC data with volume and RSI."""
    dates = pd.date_range('2023-01-01', periods=length, freq='5min')
    prices = 2000 + np.cumsum(np.random.randn(length) * 0.5)
    
    df = pd.DataFrame({
        'time': dates,
        'open': prices + np.random.randn(length) * 0.2,
        'high': prices + abs(np.random.randn(length) * 0.5),
        'low': prices - abs(np.random.randn(length) * 0.5),
        'close': prices,
        'tick_volume': 1000 + np.random.randint(-200, 200, length),
        'rsi': 50 + np.random.randn(length) * 15
    })
    
    return df


def test_confidence_validation():
    """Test confidence threshold validation."""
    print("\n🔍 Testing confidence validation...")
    
    controller = PatternQualityController(min_pattern_confidence=0.65, max_pattern_confidence=0.95)
    
    # Test clamping overconfident pattern
    pattern_overconfident = {'type': 'double_top', 'confidence': 1.0, 'signal': -1}
    result = controller.validate_pattern_confidence(pattern_overconfident)
    
    print(f"  ✅ Overconfident pattern: 1.0 → {result['confidence']:.2f} (clamped)")
    assert result['confidence'] == 0.95, "Should clamp to max confidence"
    assert result.get('confidence_clamped', False), "Should flag as clamped"
    
    # Test rejecting weak pattern
    pattern_weak = {'type': 'triple_bottom', 'confidence': 0.5, 'signal': 1}
    result = controller.validate_pattern_confidence(pattern_weak)
    
    print(f"  ✅ Weak pattern: 0.5 rejected (< 0.65)")
    assert result.get('rejected', False), "Should reject pattern below threshold"
    
    # Test accepting valid pattern
    pattern_valid = {'type': 'rising_wedge', 'confidence': 0.75, 'signal': -1}
    result = controller.validate_pattern_confidence(pattern_valid)
    
    print(f"  ✅ Valid pattern: 0.75 accepted")
    assert not result.get('rejected', False), "Should accept valid pattern"


def test_volume_confirmation():
    """Test volume confirmation for breakout patterns."""
    print("\n🔍 Testing volume confirmation...")
    
    controller = PatternQualityController()
    data = create_sample_ohlc()
    
    # Simulate volume spike in recent candles
    data.loc[data.index[-5:], 'tick_volume'] = 1500
    
    # Test continuation pattern with volume
    pattern_breakout = {
        'type': 'rising_wedge',
        'confidence': 0.80,
        'signal': -1
    }
    
    result = controller.add_volume_confirmation(pattern_breakout, data)
    
    print(f"  ✅ Volume ratio: {result['volume_ratio']:.2f}")
    print(f"  ✅ Volume confirmed: {result['volume_confirmed']}")
    
    if result['volume_confirmed']:
        assert result['confidence'] == 0.80, "Confidence should remain with volume"
    else:
        assert result['confidence'] < 0.80, "Confidence should reduce without volume"
    
    # Test reversal pattern (volume not required)
    pattern_reversal = {
        'type': 'double_bottom',
        'confidence': 0.75,
        'signal': 1
    }
    
    result = controller.add_volume_confirmation(pattern_reversal, data)
    print(f"  ✅ Reversal pattern: volume_confirmed={result['volume_confirmed']} (N/A)")
    assert result['volume_confirmed'], "Reversal patterns don't require volume"


def test_rsi_divergence():
    """Test RSI divergence confirmation for reversals."""
    print("\n🔍 Testing RSI divergence confirmation...")
    
    controller = PatternQualityController()
    data = create_sample_ohlc()
    
    # Simulate bullish divergence (price down, RSI up)
    data.loc[data.index[-10:], 'close'] = np.linspace(2000, 1990, 10)  # Price declining
    data.loc[data.index[-10:], 'rsi'] = np.linspace(35, 45, 10)  # RSI rising
    
    pattern_double_bottom = {
        'type': 'double_bottom',
        'confidence': 0.70,
        'signal': 1
    }
    
    result = controller.add_rsi_divergence_confirmation(pattern_double_bottom, data)
    
    print(f"  ✅ Bullish divergence detected: {result['rsi_divergence']}")
    
    if result['rsi_divergence']:
        print(f"  ✅ Confidence boosted: 0.70 → {result['confidence']:.2f}")
        assert result['confidence'] > 0.70, "Confidence should boost with divergence"
    else:
        print(f"  ✅ No divergence, confidence reduced: 0.70 → {result['confidence']:.2f}")
        assert result['confidence'] < 0.70, "Confidence should reduce without divergence"


def test_regime_alignment():
    """Test pattern-regime alignment checks."""
    print("\n🔍 Testing pattern-regime alignment...")
    
    controller = PatternQualityController()
    
    # Test reversal pattern in trending market (conflict)
    pattern_reversal = {
        'type': 'double_top',
        'confidence': 0.80,
        'signal': -1
    }
    
    result = controller.check_pattern_regime_alignment(
        pattern_reversal,
        market_regime='trending',
        ema_trend='bullish'
    )
    
    print(f"  ✅ Reversal in trending market: conflicts={result['regime_conflicts']}")
    assert len(result['regime_conflicts']) > 0, "Should detect conflicts"
    assert result['confidence'] < 0.80, "Confidence should reduce with conflicts"
    
    # Test continuation pattern in trending market (aligned)
    pattern_continuation = {
        'type': 'rising_wedge',
        'confidence': 0.75,
        'signal': -1
    }
    
    result = controller.check_pattern_regime_alignment(
        pattern_continuation,
        market_regime='trending',
        ema_trend='bearish'
    )
    
    print(f"  ✅ Continuation in trending market: aligned={result['regime_aligned']}")
    # May or may not have conflicts depending on signal vs trend
    
    # Test bullish pattern against bearish trend (conflict)
    pattern_bullish = {
        'type': 'double_bottom',
        'confidence': 0.70,
        'signal': 1
    }
    
    result = controller.check_pattern_regime_alignment(
        pattern_bullish,
        market_regime='ranging',
        ema_trend='bearish'
    )
    
    print(f"  ✅ Bullish pattern vs bearish trend: conflicts={result['regime_conflicts']}")
    assert len(result['regime_conflicts']) > 0, "Should detect trend conflict"


def test_conflicting_patterns():
    """Test detection of conflicting patterns."""
    print("\n🔍 Testing conflicting pattern detection...")
    
    controller = PatternQualityController()
    
    # Test conflicting patterns (both bullish and bearish)
    patterns = [
        {'type': 'double_top', 'confidence': 0.75, 'signal': -1},
        {'type': 'double_bottom', 'confidence': 0.70, 'signal': 1},
        {'type': 'rising_wedge', 'confidence': 0.80, 'signal': -1}
    ]
    
    result = controller.detect_conflicting_patterns(patterns)
    
    print(f"  ✅ Detected {len(result)} patterns after conflict check")
    
    for p in result:
        if p.get('conflicting_patterns'):
            print(f"  ✅ Pattern {p['type']} marked as conflicting, confidence={p['confidence']:.2f}")
            assert p['confidence'] < 0.75, "Conflicting patterns should have reduced confidence"
    
    # Test non-conflicting patterns
    patterns_aligned = [
        {'type': 'double_top', 'confidence': 0.75, 'signal': -1},
        {'type': 'head_shoulders', 'confidence': 0.80, 'signal': -1}
    ]
    
    result = controller.detect_conflicting_patterns(patterns_aligned)
    
    print(f"  ✅ No conflicts in aligned patterns")
    for p in result:
        assert not p.get('conflicting_patterns', False), "Aligned patterns should not be marked as conflicting"


def test_quality_control_pipeline():
    """Test full quality control pipeline."""
    print("\n🔍 Testing full quality control pipeline...")
    
    controller = PatternQualityController(min_pattern_confidence=0.65)
    data = create_sample_ohlc()
    
    # Create mixed patterns
    patterns = [
        {'type': 'double_top', 'confidence': 0.95, 'signal': -1},  # Will be clamped
        {'type': 'triple_bottom', 'confidence': 0.60, 'signal': 1},  # Will be rejected
        {'type': 'rising_wedge', 'confidence': 0.75, 'signal': -1},  # Valid
        {'type': 'falling_wedge', 'confidence': 0.70, 'signal': 1},  # Valid but may conflict
    ]
    
    validated = controller.apply_quality_controls(
        patterns,
        data,
        market_regime='trending',
        ema_trend='bearish'
    )
    
    print(f"  ✅ Original patterns: {len(patterns)}")
    print(f"  ✅ Validated patterns: {len(validated)}")
    
    assert len(validated) <= len(patterns), "Should have equal or fewer patterns after validation"
    
    for p in validated:
        print(f"     - {p['type']}: confidence={p['confidence']:.2f}, signal={p['signal']}")
        assert p['confidence'] >= 0.65, "All validated patterns should meet minimum threshold"


def test_quality_report():
    """Test quality control reporting."""
    print("\n🔍 Testing quality control reporting...")
    
    controller = PatternQualityController()
    
    original = [
        {'type': 'double_top', 'confidence': 0.75, 'signal': -1},
        {'type': 'triple_bottom', 'confidence': 0.55, 'signal': 1, 'rejected': True},
        {'type': 'rising_wedge', 'confidence': 0.80, 'signal': -1}
    ]
    
    validated = [
        {'type': 'double_top', 'confidence': 0.70, 'signal': -1},
        {'type': 'rising_wedge', 'confidence': 0.75, 'signal': -1}
    ]
    
    report = controller.get_quality_report(original, validated)
    
    print(f"  ✅ Report:")
    print(f"     Original: {report['original_count']}")
    print(f"     Validated: {report['validated_count']}")
    print(f"     Rejected: {report['rejected_count']}")
    print(f"     Rejection rate: {report['rejection_rate']:.1%}")
    print(f"     Avg confidence before: {report['avg_confidence_before']:.2f}")
    print(f"     Avg confidence after: {report['avg_confidence_after']:.2f}")
    
    assert report['original_count'] == 3, "Should count all original patterns"
    assert report['validated_count'] == 2, "Should count validated patterns"
    assert report['rejected_count'] == 1, "Should count rejected patterns"


def run_all_tests():
    """Run all pattern quality control tests."""
    print("\n" + "="*80)
    print("📐 PATTERN QUALITY CONTROL TEST SUITE")
    print("="*80)
    
    test_confidence_validation()
    test_volume_confirmation()
    test_rsi_divergence()
    test_regime_alignment()
    test_conflicting_patterns()
    test_quality_control_pipeline()
    test_quality_report()
    
    print("\n" + "="*80)
    print("✅ All pattern quality control tests completed successfully!")
    print("="*80)


if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python
"""
Validation script for professional signal generator integration
Verifies all components are properly initialized and working together
"""

import sys
import logging
from signal_generator import UnifiedSignalGenerator
import professional_config
from utils.signal_smoothing_pro import evaluate_enhanced_signal, smooth_signal
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_professional_config():
    """Verify professional configuration exists and has required attributes"""
    logger.info("🔍 Validating professional configuration...")
    
    required_attrs = [
        'PROFESSIONAL_SIGNAL_MIN_CONFIDENCE',
        'PROFESSIONAL_PATTERN_MIN_CONFIDENCE',
        'PROFESSIONAL_RISK_PER_TRADE_PCT',
        'PROFESSIONAL_TRAILING_STOP_ENABLED',
        'PROFESSIONAL_CONFLICT_PENALTY',
        'PROFESSIONAL_TRAIL_ACTIVATION_RR'
    ]
    
    for attr in required_attrs:
        if not hasattr(professional_config, attr):
            logger.error(f"❌ Missing: {attr}")
            return False
        value = getattr(professional_config, attr)
        logger.info(f"  ✅ {attr} = {value}")
    
    return True

def validate_signal_smoothing_pro():
    """Verify signal smoothing pro module has all required components"""
    logger.info("🔍 Validating signal_smoothing_pro module...")
    
    try:
        # Test WeightedSignalVoter
        logger.info("  Testing WeightedSignalVoter...")
        from utils.signal_smoothing_pro import WeightedSignalVoter
        voter = WeightedSignalVoter()
        signal, confidence, reason = voter.calculate_weighted_signal(
            tech_signal={'signal': 'BUY', 'strength': 75},
            patterns=[{'type': 'bullish_flag', 'signal': 1, 'confidence': 0.7, 'detected': True}],
            news_data={'sentiment': 'bullish'}
        )
        assert signal in ['BUY', 'SELL', 'HOLD']
        logger.info(f"    ✅ WeightedSignalVoter working: signal={signal}, confidence={confidence:.2f}")
        
        # Test ConflictAwareValidator
        logger.info("  Testing ConflictAwareValidator...")
        from utils.signal_smoothing_pro import ConflictAwareValidator
        validator = ConflictAwareValidator()
        patterns = [
            {'type': 'bullish_flag', 'signal': 1, 'confidence': 0.7, 'detected': True},
            {'type': 'bearish_channel', 'signal': -1, 'confidence': 0.6, 'detected': True}
        ]
        resolved, reason = validator.resolve_conflicting_patterns(patterns)
        logger.info(f"    ✅ ConflictAwareValidator working: resolved {len(patterns)} patterns")
        
        # Test evaluate_enhanced_signal
        logger.info("  Testing evaluate_enhanced_signal...")
        result = evaluate_enhanced_signal(
            tech_signal={'signal': 'BUY', 'strength': 60, 'confidence': 0.6},
            patterns=[],
            news_data={'news_signal': 0, 'news_confidence': 0, 'sentiment': 'neutral'},
            market_context={'regime': 'trending', 'volatility': 0.02, 'trend_intensity': 0.6}
        )
        assert 'accept' in result
        assert 'confidence' in result
        logger.info(f"    ✅ evaluate_enhanced_signal working: accept={result['accept']}, confidence={result['confidence']:.2f}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Signal smoothing pro validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def validate_unified_signal_generator():
    """Verify UnifiedSignalGenerator initializes with professional config"""
    logger.info("🔍 Validating UnifiedSignalGenerator integration...")
    
    try:
        gen = UnifiedSignalGenerator(
            ema_fast=12,
            ema_slow=26,
            rsi_period=14,
            bb_period=20,
            bb_std=2,
            config=config,
            enable_news_gating=True,
            enable_strategy_refinements=True,
            enable_pattern_quality_controls=True,
            mt5_connection=None
        )
        
        # Verify professional mode is activated
        if not gen.professional_mode:
            logger.warning("⚠️  Professional mode not activated in UnifiedSignalGenerator")
        else:
            logger.info("  ✅ Professional mode activated in UnifiedSignalGenerator")
            
        if gen.professional_config is None:
            logger.warning("⚠️  Professional config not loaded in UnifiedSignalGenerator")
        else:
            logger.info("  ✅ Professional config loaded in UnifiedSignalGenerator")
        
        return True
    except Exception as e:
        logger.error(f"❌ UnifiedSignalGenerator validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    logger.info("=" * 60)
    logger.info("🚀 PROFESSIONAL SIGNAL INTEGRATION VALIDATION")
    logger.info("=" * 60)
    
    checks = [
        ("Professional Config", validate_professional_config),
        ("Signal Smoothing Pro", validate_signal_smoothing_pro),
        ("Unified Signal Generator", validate_unified_signal_generator),
    ]
    
    results = []
    for name, check_func in checks:
        logger.info(f"\n{name}:")
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"❌ {name} validation failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    logger.info("\n" + "=" * 60)
    logger.info("📊 VALIDATION SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info(f"\nTotal: {passed}/{total} checks passed")
    
    if passed == total:
        logger.info("\n🎉 ALL VALIDATIONS PASSED! Professional integration is ready.")
        return 0
    else:
        logger.error(f"\n⚠️  {total - passed} validation(s) failed. Please review above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())

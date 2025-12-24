"""
Validation Script - Tests the new modular signal generation system
Validates all components and their integration
"""

import sys
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_sample_data(periods=200):
    """Generate sample OHLC data for testing"""
    logger.info(f"Generating {periods} sample candles...")
    
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=periods, freq='5min')
    
    # Generate realistic price action
    prices = np.random.randn(periods).cumsum() + 2000
    df = pd.DataFrame({
        'open': prices + np.random.randn(periods) * 0.5,
        'high': prices + np.abs(np.random.randn(periods)) + 0.5,
        'low': prices - np.abs(np.random.randn(periods)) - 0.5,
        'close': prices,
        'volume': np.random.randint(1000, 10000, periods)
    }, index=dates)
    
    # Ensure high/low are correctly ordered
    df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
    df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)
    
    logger.info(f"Sample data generated: {len(df)} candles")
    return df

def test_indicator_analyzer():
    """Test the TechnicalIndicatorAnalyzer"""
    logger.info("\n" + "="*60)
    logger.info("TEST 1: Technical Indicator Analyzer")
    logger.info("="*60)
    
    try:
        from signal_generation.indicator_analyzer import TechnicalIndicatorAnalyzer
        
        analyzer = TechnicalIndicatorAnalyzer()
        df = generate_sample_data(100)
        
        result = analyzer.analyze(df)
        
        logger.info(f"✓ Signal: {result['signal']}")
        logger.info(f"✓ Strength: {result['strength']:.1f}%")
        logger.info(f"✓ Condition: {result['condition']}")
        logger.info(f"✓ Volatility: {result['volatility_level']}")
        logger.info(f"✓ Trend: {result['trend_strength']}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        return False

def test_pattern_detector():
    """Test the PatternDetector"""
    logger.info("\n" + "="*60)
    logger.info("TEST 2: Pattern Detector")
    logger.info("="*60)
    
    try:
        from signal_generation.pattern_detector import PatternDetector
        
        detector = PatternDetector()
        df = generate_sample_data(100)
        
        result = detector.analyze(df)
        
        logger.info(f"✓ Signal: {result['signal']}")
        logger.info(f"✓ Confidence: {result['confidence']:.1f}%")
        logger.info(f"✓ Condition: {result['condition']}")
        logger.info(f"✓ Total Patterns: {result['total_patterns']}")
        logger.info(f"✓ Bullish Patterns: {result['bullish_count']}")
        logger.info(f"✓ Bearish Patterns: {result['bearish_count']}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        return False

def test_news_sentiment_analyzer():
    """Test the NewsSentimentAnalyzer"""
    logger.info("\n" + "="*60)
    logger.info("TEST 3: News Sentiment Analyzer")
    logger.info("="*60)
    
    try:
        from signal_generation.news_sentiment_analyzer import NewsSentimentAnalyzer
        
        analyzer = NewsSentimentAnalyzer()
        result = analyzer.analyze()
        
        logger.info(f"✓ Signal: {result['signal']}")
        logger.info(f"✓ Confidence: {result['confidence']:.1f}%")
        logger.info(f"✓ Condition: {result['condition']}")
        logger.info(f"✓ Impact: {result['impact_assessment']}")
        logger.info(f"✓ Bullish News: {result['bullish_count']}")
        logger.info(f"✓ Bearish News: {result['bearish_count']}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        return False

def test_strategy_analyzer():
    """Test the StrategyAnalyzer"""
    logger.info("\n" + "="*60)
    logger.info("TEST 4: Strategy Analyzer")
    logger.info("="*60)
    
    try:
        from signal_generation.strategy_analyzer import StrategyAnalyzer
        
        analyzer = StrategyAnalyzer()
        df = generate_sample_data(100)
        
        result = analyzer.analyze(df, market_regime='trending')
        
        logger.info(f"✓ Signal: {result['signal']}")
        logger.info(f"✓ Confidence: {result['confidence']:.1f}%")
        logger.info(f"✓ Condition: {result['condition']}")
        logger.info(f"✓ Market Regime: {result['market_regime']}")
        logger.info(f"✓ Recommendation: {result['recommendation']}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        return False

def test_adaptive_signal_analyzer():
    """Test the AdaptiveSignalAnalyzer"""
    logger.info("\n" + "="*60)
    logger.info("TEST 5: Adaptive Signal Analyzer")
    logger.info("="*60)
    
    try:
        from signal_generation.adaptive_signal_analyzer import AdaptiveSignalAnalyzer
        
        analyzer = AdaptiveSignalAnalyzer()
        df = generate_sample_data(100)
        
        result = analyzer.analyze(
            original_signal=1,
            signal_strength=75,
            data=df,
            market_conditions={'volatility': 'NORMAL', 'trend': 'STRONG'}
        )
        
        logger.info(f"✓ Final Signal: {result['signal']}")
        logger.info(f"✓ Strength: {result['strength']:.1f}%")
        logger.info(f"✓ Smoothed: {result['smoothed']}")
        logger.info(f"✓ Persistence: {result['persistence_confirmed']}")
        logger.info(f"✓ Recommendation: {result['recommendation']}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        return False

def test_signal_master():
    """Test the SignalMaster coordinator"""
    logger.info("\n" + "="*60)
    logger.info("TEST 6: Signal Master (Full Integration)")
    logger.info("="*60)
    
    try:
        from signal_generation import SignalMaster
        
        master = SignalMaster()
        df = generate_sample_data(100)
        
        result = master.generate_signal(df, market_regime='trending')
        
        logger.info(f"✓ Final Signal: {result['signal']}")
        logger.info(f"✓ Strength: {result['strength']:.1f}%")
        logger.info(f"✓ Recommendation: {result['recommendation']}")
        logger.info(f"✓ Market Conditions: {result['market_conditions']}")
        
        # Check component breakdown
        components = result.get('components', {})
        logger.info(f"✓ Indicators - Signal: {components.get('indicators', {}).get('signal')}")
        logger.info(f"✓ Patterns - Signal: {components.get('patterns', {}).get('signal')}")
        logger.info(f"✓ News - Signal: {components.get('news', {}).get('signal')}")
        logger.info(f"✓ Strategy - Signal: {components.get('strategy', {}).get('signal')}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        return False

def test_unified_signal_generator():
    """Test the UnifiedSignalGenerator wrapper"""
    logger.info("\n" + "="*60)
    logger.info("TEST 7: Unified Signal Generator (Main Entry Point)")
    logger.info("="*60)
    
    try:
        from signal_generator_new import UnifiedSignalGenerator
        
        generator = UnifiedSignalGenerator(professional_mode=True)
        df = generate_sample_data(100)
        
        result = generator.generate_signal(df)
        
        logger.info(f"✓ Recommendation: {result['recommendation']}")
        logger.info(f"✓ Strength: {result['strength']:.1f}%")
        logger.info(f"✓ Signal Type: {result.get('signal_type')}")
        logger.info(f"✓ Direction: {result.get('direction')}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        return False

def main():
    """Run all validation tests"""
    logger.info("\n" + "="*60)
    logger.info("SIGNAL GENERATION ARCHITECTURE VALIDATION")
    logger.info("="*60)
    
    tests = [
        ("Technical Indicator Analyzer", test_indicator_analyzer),
        ("Pattern Detector", test_pattern_detector),
        ("News Sentiment Analyzer", test_news_sentiment_analyzer),
        ("Strategy Analyzer", test_strategy_analyzer),
        ("Adaptive Signal Analyzer", test_adaptive_signal_analyzer),
        ("Signal Master (Full Integration)", test_signal_master),
        ("Unified Signal Generator", test_unified_signal_generator)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            logger.error(f"Test {test_name} encountered error: {e}")
            results.append((test_name, False))
    
    # Print summary
    logger.info("\n" + "="*60)
    logger.info("VALIDATION SUMMARY")
    logger.info("="*60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nResult: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        logger.info("\n✓ ALL TESTS PASSED - Signal generation system is fully operational!")
        return 0
    else:
        logger.error(f"\n✗ {total_count - passed_count} test(s) failed - Please review errors above")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

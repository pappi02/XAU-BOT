"""
Professional Scalping Strategies - Integration Test

Tests all 5 scalping strategies and the strategy selector.
"""

import pandas as pd
import numpy as np
from datetime import datetime

# Import all strategies
from strategies import (
    BreakoutScalping,
    MomentumScalping,
    MovingAverageScalping,
    DipScalping,
    RangeScalping,
    StrategySelector
)


def create_sample_data(periods=200, volatility='medium'):
    """Create sample OHLCV data for testing"""
    dates = pd.date_range('2024-01-01', periods=periods, freq='5min')
    
    # Adjust volatility
    if volatility == 'high':
        vol_factor = 3.0
    elif volatility == 'low':
        vol_factor = 0.5
    else:
        vol_factor = 1.5
    
    base_price = 2050
    prices = base_price + np.cumsum(np.random.randn(periods) * vol_factor)
    
    data = pd.DataFrame({
        'open': prices + np.random.randn(periods) * 0.5,
        'high': prices + abs(np.random.randn(periods) * vol_factor),
        'low': prices - abs(np.random.randn(periods) * vol_factor),
        'close': prices,
        'volume': np.random.randint(1000, 10000, periods)
    }, index=dates)
    
    return data


def test_individual_strategy(strategy, name, data):
    """Test a single strategy"""
    print(f"\n{'='*80}")
    print(f"Testing: {name}")
    print(f"{'='*80}")
    
    try:
        result = strategy.analyze(data)
        
        print(f"✅ Signal: {'BUY' if result['signal'] == 1 else 'SELL' if result['signal'] == -1 else 'HOLD'}")
        print(f"   Confidence: {result['confidence']}%")
        print(f"   Entry: {result.get('entry')}")
        print(f"   SL: {result.get('sl')}")
        print(f"   TP: {result.get('tp')}")
        print(f"   Confluences: {len(result.get('confluences', []))} - {result.get('confluences', [])}")
        print(f"   Reason: {result.get('reason', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_strategy_selector(data):
    """Test the strategy selector"""
    print(f"\n{'='*80}")
    print(f"Testing: Strategy Selector")
    print(f"{'='*80}")
    
    try:
        selector = StrategySelector(cooldown_sec=60, min_confidence=0.5)
        
        # Get available strategies
        print("\n📊 Available Strategies:")
        strategies = selector.get_available_strategies()
        for name, desc in strategies.items():
            print(f"   - {name}: {desc}")
        
        # Select strategy
        print("\n🔍 Selecting Strategy...")
        selection = selector.select_strategy(data)
        
        print(f"\n✅ Selected: {selection['selected_strategy']}")
        print(f"   Regime: {selection['regime_info']['regime']} "
              f"(confidence: {selection['regime_info']['confidence']:.1f}%)")
        print(f"   Selection Confidence: {selection['selection_info']['confidence']:.1f}%")
        print(f"   Votes: {selection['selection_info']['votes']}")
        print(f"   Total Votes: {selection['selection_info']['total_votes']}")
        
        # Generate signal
        print("\n📈 Generating Signal...")
        signal = selector.generate_signal(data)
        
        signal_type = 'BUY' if signal['signal'] == 1 else 'SELL' if signal['signal'] == -1 else 'HOLD'
        print(f"\n   Signal: {signal_type}")
        print(f"   Confidence: {signal['confidence']:.1f}%")
        print(f"   Entry: {signal.get('entry')}")
        print(f"   SL: {signal.get('sl')}")
        print(f"   TP: {signal.get('tp')}")
        print(f"   Strategy Used: {signal.get('strategy_used')}")
        print(f"   Confluences: {signal.get('confluences', [])}")
        
        # Performance
        print("\n📊 Performance:")
        performance = selector.get_strategy_performance()
        print(f"   Total Switches: {performance['total_switches']}")
        print(f"   Current Strategy: {performance['current_strategy']}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    print("=" * 80)
    print("PROFESSIONAL SCALPING STRATEGIES - INTEGRATION TEST")
    print("=" * 80)
    print(f"Test Started: {datetime.now()}")
    
    # Create test data
    print("\n📊 Creating test data (200 5-minute candles)...")
    data = create_sample_data(periods=200, volatility='medium')
    print(f"   Data shape: {data.shape}")
    print(f"   Date range: {data.index[0]} to {data.index[-1]}")
    print(f"   Price range: {data['close'].min():.2f} to {data['close'].max():.2f}")
    
    # Test results
    results = {}
    
    # Test 1: Breakout Scalping
    strategy = BreakoutScalping()
    results['breakout'] = test_individual_strategy(strategy, "Breakout Scalping", data)
    
    # Test 2: Momentum Scalping
    strategy = MomentumScalping()
    results['momentum'] = test_individual_strategy(strategy, "Momentum Scalping", data)
    
    # Test 3: Moving Average Scalping
    strategy = MovingAverageScalping()
    results['ma'] = test_individual_strategy(strategy, "Moving Average Scalping", data)
    
    # Test 4: Dip Scalping
    strategy = DipScalping()
    results['dip'] = test_individual_strategy(strategy, "Dip Scalping", data)
    
    # Test 5: Range Scalping
    strategy = RangeScalping()
    results['range'] = test_individual_strategy(strategy, "Range Scalping", data)
    
    # Test 6: Strategy Selector
    results['selector'] = test_strategy_selector(data)
    
    # Summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} - {name.upper()}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Integration successful!")
    else:
        print(f"\n⚠️ {total - passed} tests failed. Check errors above.")
    
    print(f"\nTest Completed: {datetime.now()}")
    print("=" * 80)


if __name__ == "__main__":
    main()

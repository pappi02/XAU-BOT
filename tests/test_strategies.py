#!/usr/bin/env python3
"""
test_strategies.py - Test script for all trading strategies
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategies import (
    create_strategy,
    StrategySelector,
    TrendTradingStrategy,
    BreakoutRetestStrategy,
    SwingTradingStrategy,
    ScalpingStrategy
)

def create_sample_data(length=200, volatility=0.02, trend_strength=0.5):
    """
    Create sample OHLC data for testing.

    Args:
        length (int): Number of data points
        volatility (float): Price volatility
        trend_strength (float): Trend component strength

    Returns:
        pd.DataFrame: Sample OHLC data
    """
    dates = pd.date_range('2023-01-01', periods=length, freq='h')

    # Create base price with trend and noise
    trend = np.cumsum(np.random.randn(length) * trend_strength)
    noise = np.random.randn(length) * volatility
    prices = 1800 + trend + noise

    # Create OHLC data
    high_noise = abs(np.random.randn(length) * volatility * 2)
    low_noise = abs(np.random.randn(length) * volatility * 2)

    data = pd.DataFrame({
        'open': prices + np.random.randn(length) * volatility * 0.5,
        'high': prices + high_noise,
        'low': prices - low_noise,
        'close': prices,
        'volume': np.random.randint(1000, 10000, length)
    }, index=dates)

    return data

def test_individual_strategies():
    """Test each strategy individually."""
    print("🧪 Testing Individual Strategies")
    print("=" * 50)

    # Create sample data
    data = create_sample_data(200)

    strategies = [
        ('Trend Trading', TrendTradingStrategy()),
        ('Breakout & Retest', BreakoutRetestStrategy()),
        ('Swing Trading', SwingTradingStrategy()),
        ('Scalping', ScalpingStrategy())
    ]

    for name, strategy in strategies:
        print(f"\n📊 Testing {name} Strategy:")
        try:
            # Prepare data
            prepared_data = strategy.prepare_data(data)

            # Generate signal
            signal = strategy.generate_signal(prepared_data)

            print(f"  Signal: {signal['signal']} (Strength: {signal['strength']}%)")
            print(f"  Reasons: {signal['reasons'][:2]}...")  # Show first 2 reasons

            if signal['signal'] != 'HOLD':
                print(f"  Entry: {signal.get('entry_price', 'N/A')}")
                print(f"  Stop Loss: {signal.get('stop_loss', 'N/A')}")
                print(f"  Take Profit: {signal.get('take_profit', 'N/A')}")

        except Exception as e:
            print(f"  ❌ Error: {str(e)}")

def test_strategy_selector():
    """Test the strategy selector."""
    print("\n🎯 Testing Strategy Selector")
    print("=" * 50)

    # Create sample data
    data = create_sample_data(200)

    try:
        # Initialize selector
        selector = StrategySelector(cooldown_sec=10)  # Short cooldown for testing

        # Select strategy
        selection = selector.select_strategy(data)
        print(f"Selected Strategy: {selection['selected_strategy']}")
        print(f"Regime: {selection['regime_info']['regime']} (Confidence: {selection['regime_info']['confidence']}%)")

        # Generate signal
        signal = selector.generate_signal(data)
        print(f"Signal: {signal['signal']} (Strength: {signal['strength']}%)")
        print(f"Strategy Used: {signal.get('strategy_used')}")

        # Test performance tracking
        performance = selector.get_strategy_performance()
        print(f"Performance: {performance}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

def test_strategy_factory():
    """Test the strategy factory function."""
    print("\n🏭 Testing Strategy Factory")
    print("=" * 50)

    strategy_types = ['trend_trading', 'breakout_retest', 'swing_trading', 'scalping', 'basic']

    for strategy_type in strategy_types:
        try:
            strategy = create_strategy(strategy_type)
            print(f"✅ Created {strategy_type}: {type(strategy).__name__}")
        except Exception as e:
            print(f"❌ Failed to create {strategy_type}: {str(e)}")

def test_regime_detection():
    """Test regime detection with different market conditions."""
    print("\n🌍 Testing Regime Detection")
    print("=" * 50)

    from strategies.regime_detector import RegimeDetector

    detector = RegimeDetector()

    # Test different market conditions
    conditions = [
        ('Trending Up', create_sample_data(200, trend_strength=1.0)),
        ('Trending Down', create_sample_data(200, trend_strength=-1.0)),
        ('Sideways', create_sample_data(200, trend_strength=0.1, volatility=0.01)),
        ('Volatile', create_sample_data(200, volatility=0.05))
    ]

    for condition_name, data in conditions:
        try:
            prepared_data = detector.prepare_data(data)
            regime_info = detector.detect_regime(prepared_data)
            recommended_strategy = detector.get_strategy_mapping(regime_info['regime'])

            print(f"{condition_name}:")
            print(f"  Regime: {regime_info['regime']} (Confidence: {regime_info['confidence']}%)")
            print(f"  Recommended Strategy: {recommended_strategy}")

        except Exception as e:
            print(f"❌ Error testing {condition_name}: {str(e)}")

def run_all_tests():
    """Run all strategy tests."""
    print("🚀 Running Complete Strategy Test Suite")
    print("=" * 60)

    start_time = datetime.now()

    try:
        test_individual_strategies()
        test_strategy_selector()
        test_strategy_factory()
        test_regime_detection()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n✅ All tests completed successfully!")
        print(f"⏱️  Total execution time: {duration:.2f} seconds")

    except Exception as e:
        print(f"\n❌ Test suite failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_all_tests()

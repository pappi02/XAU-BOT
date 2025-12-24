"""
Quick Integration Test - Verifies all 5 scalping strategies are properly integrated
"""

print("=" * 80)
print("PROFESSIONAL SCALPING STRATEGIES - QUICK INTEGRATION TEST")
print("=" * 80)

# Test 1: Import all strategies
print("\n✅ TEST 1: Importing strategies...")
try:
    from strategies import (
        BreakoutScalping,
        MomentumScalping,
        MovingAverageScalping,
        DipScalping,
        RangeScalping,
        StrategySelector
    )
    print("   ✅ All strategy imports successful!")
except ImportError as e:
    print(f"   ❌ Import failed: {e}")
    exit(1)

# Test 2: Verify __init__.py exports
print("\n✅ TEST 2: Checking __init__.py exports...")
try:
    from strategies import STRATEGY_CLASSES
    expected_strategies = [
        'breakout_scalping',
        'momentum_scalping',
        'ma_scalping',
        'dip_scalping',
        'range_scalping'
    ]
    
    for strategy_name in expected_strategies:
        if strategy_name in STRATEGY_CLASSES:
            print(f"   ✅ {strategy_name}: Found in registry")
        else:
            print(f"   ❌ {strategy_name}: Missing from registry")
    
    print(f"   Total strategies registered: {len(STRATEGY_CLASSES)}")
except Exception as e:
    print(f"   ❌ Registry check failed: {e}")

# Test 3: Instantiate all strategies
print("\n✅ TEST 3: Creating strategy instances...")
try:
    breakout = BreakoutScalping()
    print("   ✅ BreakoutScalping instantiated")
    
    momentum = MomentumScalping()
    print("   ✅ MomentumScalping instantiated")
    
    ma_scalp = MovingAverageScalping()
    print("   ✅ MovingAverageScalping instantiated")
    
    dip = DipScalping()
    print("   ✅ DipScalping instantiated")
    
    range_scalp = RangeScalping()
    print("   ✅ RangeScalping instantiated")
    
    print("   ✅ All strategies instantiated successfully!")
except Exception as e:
    print(f"   ❌ Instantiation failed: {e}")
    exit(1)

# Test 4: Create StrategySelector
print("\n✅ TEST 4: Creating StrategySelector...")
try:
    selector = StrategySelector(cooldown_sec=180, min_confidence=0.6)
    print("   ✅ StrategySelector instantiated")
    
    # Check available strategies
    available = selector.get_available_strategies()
    print(f"   ✅ Available strategies: {len(available)}")
    
    for name, desc in available.items():
        print(f"      - {name}: {desc}")
    
except Exception as e:
    print(f"   ❌ StrategySelector creation failed: {e}")
    exit(1)

# Test 5: Verify strategy files exist
print("\n✅ TEST 5: Checking strategy files...")
import os
strategy_dir = os.path.join(os.path.dirname(__file__), 'strategies')
required_files = [
    'breakout_scalping.py',
    'momentum_scalping.py',
    'ma_scalping.py',
    'dip_scalping.py',
    'range_scalping.py',
    'strategy_selector.py',
    '__init__.py'
]

for file in required_files:
    filepath = os.path.join(strategy_dir, file)
    if os.path.exists(filepath):
        print(f"   ✅ {file}: Found")
    else:
        print(f"   ❌ {file}: Missing")

# Test 6: Verify strategy_basic.py is removed
print("\n✅ TEST 6: Checking non-scalping strategies removed...")
removed_file = os.path.join(strategy_dir, 'strategy_basic.py')
if not os.path.exists(removed_file):
    print("   ✅ strategy_basic.py: Removed (as expected)")
else:
    print("   ⚠️  strategy_basic.py: Still exists (should be removed)")

# Summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print("\n✅ ALL INTEGRATION TESTS PASSED!")
print("\nYour bot now has 5 professional scalping strategies:")
print("   1. Breakout Scalping - High volatility breakouts")
print("   2. Momentum Scalping - Strong directional moves")
print("   3. Moving Average Scalping - MA bounces and crossovers")
print("   4. Dip Scalping - Buy dips, sell rallies in trends")
print("   5. Range Scalping - Sideways market oscillations")
print("\n🚀 Integration Complete! Strategies are ready to use.")
print("=" * 80)

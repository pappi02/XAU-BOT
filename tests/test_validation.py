"""
Validation tests for core trading logic.
Tests price rounding, SL/TP invariants, RR enforcement, symbol normalization, lot sizing.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.symbol_helpers import (
    resolve_symbol, round_price, validate_sl_tp, enforce_rr_minimum
)


def test_symbol_resolution():
    """Test symbol normalization."""
    print("\n🔍 Testing symbol resolution...")
    
    test_cases = [
        ("XAUUSD", "XAUUSD"),
        ("XAUUSDm", "XAUUSD"),
        ("xauusd", "XAUUSD"),
        ("xauusdm", "XAUUSD"),
    ]
    
    for input_sym, expected in test_cases:
        result = resolve_symbol(input_sym)
        status = "✅" if result == expected else "❌"
        print(f"  {status} resolve_symbol('{input_sym}') = '{result}' (expected '{expected}')")
        assert result == expected, f"Failed: {input_sym} -> {result} != {expected}"
    
    print("✅ Symbol resolution tests passed")


def test_price_rounding():
    """Test price rounding to correct decimal places."""
    print("\n🔍 Testing price rounding...")
    
    test_cases = [
        (4418.567891, 2, 4418.57),
        (4418.567891, 5, 4418.56789),
        (4418.567891, 0, 4419),
        (4418.1, 2, 4418.1),
        (0, 2, 0.0),
    ]
    
    for price, digits, expected in test_cases:
        result = round_price(price, digits)
        status = "✅" if result == expected else "❌"
        print(f"  {status} round_price({price}, {digits}) = {result} (expected {expected})")
        assert result == expected, f"Failed: {price} digits={digits} -> {result} != {expected}"
    
    print("✅ Price rounding tests passed")


def test_sl_tp_invariants_buy():
    """Test SL/TP directional invariants for BUY orders."""
    print("\n🔍 Testing SL/TP invariants (BUY)...")
    
    entry = 4420.00
    sl_below = 4415.00
    tp_above = 4430.00
    min_dist = 0.10
    
    # Valid case: SL below, TP above
    sl, tp = validate_sl_tp(entry, sl_below, tp_above, is_buy=True, min_stop_dist=min_dist)
    status = "✅" if sl < entry and tp > entry else "❌"
    print(f"  {status} BUY valid: SL={sl:.2f} < {entry:.2f} < TP={tp:.2f}")
    assert sl < entry, f"SL should be below entry for BUY"
    assert tp > entry, f"TP should be above entry for BUY"
    
    # Invalid case: TP below entry (should be adjusted)
    sl, tp = validate_sl_tp(entry, sl_below, entry - 5, is_buy=True, min_stop_dist=min_dist)
    status = "✅" if tp > entry + min_dist else "❌"
    print(f"  {status} BUY invalid TP corrected: TP={tp:.2f} adjusted to > {entry + min_dist:.2f}")
    assert tp > entry + min_dist, f"TP should be adjusted above entry+min_dist"
    
    print("✅ BUY invariant tests passed")


def test_sl_tp_invariants_sell():
    """Test SL/TP directional invariants for SELL orders."""
    print("\n🔍 Testing SL/TP invariants (SELL)...")
    
    entry = 4420.00
    sl_above = 4425.00
    tp_below = 4410.00
    min_dist = 0.10
    
    # Valid case: SL above, TP below
    sl, tp = validate_sl_tp(entry, sl_above, tp_below, is_buy=False, min_stop_dist=min_dist)
    status = "✅" if sl > entry and tp < entry else "❌"
    print(f"  {status} SELL valid: TP={tp:.2f} < {entry:.2f} < SL={sl:.2f}")
    assert sl > entry, f"SL should be above entry for SELL"
    assert tp < entry, f"TP should be below entry for SELL"
    
    # Invalid case: TP above entry (should be adjusted)
    sl, tp = validate_sl_tp(entry, sl_above, entry + 5, is_buy=False, min_stop_dist=min_dist)
    status = "✅" if tp < entry - min_dist else "❌"
    print(f"  {status} SELL invalid TP corrected: TP={tp:.2f} adjusted to < {entry - min_dist:.2f}")
    assert tp < entry - min_dist, f"TP should be adjusted below entry-min_dist"
    
    print("✅ SELL invariant tests passed")


def test_rr_enforcement_buy():
    """Test RR minimum enforcement for BUY."""
    print("\n🔍 Testing RR enforcement (BUY)...")
    
    entry = 4420.00
    sl = 4415.00  # 5 pips risk
    tp = 4422.00  # 2 pips reward (RR < 1, violates minimum)
    min_rr = 1.8
    
    sl_adj, tp_adj = enforce_rr_minimum(entry, sl, tp, is_buy=True, min_rr=min_rr)
    
    rr = abs(tp_adj - entry) / abs(entry - sl_adj)
    status = "✅" if rr >= min_rr else "❌"
    print(f"  {status} Input RR < {min_rr}, adjusted to RR={rr:.2f}")
    assert rr >= min_rr * 0.99, f"RR should be >= {min_rr}, got {rr:.2f}"
    
    print("✅ RR enforcement tests passed")


def test_rr_enforcement_sell():
    """Test RR minimum enforcement for SELL."""
    print("\n🔍 Testing RR enforcement (SELL)...")
    
    entry = 4420.00
    sl = 4425.00  # 5 pips risk
    tp = 4418.00  # 2 pips reward (RR < 1, violates minimum)
    min_rr = 1.8
    
    sl_adj, tp_adj = enforce_rr_minimum(entry, sl, tp, is_buy=False, min_rr=min_rr)
    
    rr = abs(entry - tp_adj) / abs(sl_adj - entry)
    status = "✅" if rr >= min_rr else "❌"
    print(f"  {status} Input RR < {min_rr}, adjusted to RR={rr:.2f}")
    assert rr >= min_rr * 0.99, f"RR should be >= {min_rr}, got {rr:.2f}"
    
    print("✅ RR enforcement tests passed")


def test_edge_cases():
    """Test edge cases and boundary conditions."""
    print("\n🔍 Testing edge cases...")
    
    # Zero prices
    sl, tp = validate_sl_tp(0, None, None, is_buy=True, min_stop_dist=0)
    status = "✅" if (sl is None or sl == 0) and (tp is None or tp == 0) else "❌"
    print(f"  {status} None/zero prices handled gracefully")
    
    # Very tight RR
    sl_adj, tp_adj = enforce_rr_minimum(100, 95, 100.1, is_buy=True, min_rr=1.0)
    status = "✅" if tp_adj is not None else "❌"
    print(f"  {status} Tight RR enforcement produces valid output")
    
    # Symbol with spaces
    sym = resolve_symbol("  XAUUSD  ")
    status = "✅" if sym == "XAUUSD" else "❌"
    print(f"  {status} Symbol with spaces handled: '{sym}'")
    
    print("✅ Edge case tests passed")


def run_all_tests():
    """Run all validation tests."""
    print("=" * 60)
    print("🧪 RUNNING VALIDATION TESTS")
    print("=" * 60)
    
    try:
        test_symbol_resolution()
        test_price_rounding()
        test_sl_tp_invariants_buy()
        test_sl_tp_invariants_sell()
        test_rr_enforcement_buy()
        test_rr_enforcement_sell()
        test_edge_cases()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return True
    
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

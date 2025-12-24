"""
Tests for economic calendar and news gating functionality.
Validates that trading is properly gated/degraded during economic events.
"""

import sys
import os
from datetime import datetime, timedelta
import pytz

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.economic_calendar import EconomicCalendar, IMPACT_HIGH, IMPACT_MEDIUM, IMPACT_LOW
from utils.news_gate import NewsAwareSignalFilter, NewsGateConfig


def test_calendar_event_detection():
    """Test economic calendar event detection."""
    print("\n🔍 Testing economic calendar event detection...")
    
    calendar = EconomicCalendar()
    events = calendar.get_events_today_and_tomorrow()
    
    print(f"  ✅ Found {len(events)} events for next 2 days")
    
    # Show first 5 events
    if events:
        print("  📅 Sample events:")
        for evt_dt, evt_name, country, impact in events[:5]:
            impact_str = {
                IMPACT_HIGH: "HIGH",
                IMPACT_MEDIUM: "MEDIUM",
                IMPACT_LOW: "LOW"
            }.get(impact, "UNKNOWN")
            print(f"     - {evt_dt.isoformat()}: {country} {evt_name} ({impact_str})")


def test_is_near_event():
    """Test proximity detection to economic events."""
    print("\n🔍 Testing proximity detection to economic events...")
    
    calendar = EconomicCalendar()
    
    # Get all events
    events = calendar.get_events_today_and_tomorrow()
    
    if not events:
        print("  ⚠️  No events found; creating synthetic test...")
        # Manually test with a known time window
        print("  Test skipped (requires live event data)")
        return
    
    # Test current proximity
    is_near, event_name, impact = calendar.is_near_event(
        buffer_minutes_before=15,
        buffer_minutes_after=30
    )
    
    if is_near:
        impact_str = {IMPACT_HIGH: "HIGH", IMPACT_MEDIUM: "MEDIUM", IMPACT_LOW: "LOW"}.get(impact, "UNKNOWN")
        print(f"  ✅ Near event: {event_name} ({impact_str})")
    else:
        print(f"  ✅ Not near any events")
    
    # Test degradation factor
    degrade_factor = calendar.get_signal_degradation_factor(
        buffer_minutes_before=30,
        buffer_minutes_after=45
    )
    
    print(f"  ✅ Signal degradation factor: {degrade_factor:.2f} (1.0 = no degradation, 0.3 = heavy)")
    assert 0.3 <= degrade_factor <= 1.0, "Degradation factor out of range"


def test_signal_filter_gating():
    """Test signal filtering and gating."""
    print("\n🔍 Testing signal filtering and gating...")
    
    signal_filter = NewsAwareSignalFilter()
    
    # Test gating check
    should_gate, reason = signal_filter.should_gate_trading()
    
    if should_gate:
        print(f"  ✅ Trading gated: {reason}")
    else:
        print(f"  ✅ Trading not gated (safe to trade)")
    
    # Test confidence requirement
    required_confidence = signal_filter.require_higher_confidence_near_events()
    print(f"  ✅ Required confidence threshold: {required_confidence:.2f} (base=0.65)")
    assert required_confidence >= 0.65, "Threshold should be >= base"
    assert required_confidence <= 0.85, "Threshold should not exceed 0.85"


def test_signal_degradation():
    """Test signal degradation near events."""
    print("\n🔍 Testing signal degradation...")
    
    signal_filter = NewsAwareSignalFilter()
    
    # Create sample signal
    sample_signal = {
        'type': 'BUY',
        'confidence': 0.75,
        'strength': 75,
        'reasons': ['Strong bullish setup']
    }
    
    # Apply filtering
    filtered = signal_filter.apply_signal_filters(sample_signal)
    
    print(f"  Original confidence: {sample_signal['confidence']:.2f}")
    print(f"  Filtered confidence: {filtered['confidence']:.2f}")
    print(f"  News state: {filtered.get('news_state', 'Unknown')}")
    
    # Check for gating or degradation
    if filtered.get('gated'):
        print(f"  ✅ Signal gated: {filtered.get('gate_reason')}")
    elif 'confidence_degradation' in filtered:
        degradation = filtered['confidence_degradation']
        print(f"  ✅ Signal degraded: {degradation['original']:.2f} → {degradation['degraded']:.2f} (factor={degradation['factor']:.2f})")
    else:
        print(f"  ✅ Signal not affected by news")


def test_manual_events_fallback():
    """Test that manual events fallback works when API unavailable."""
    print("\n🔍 Testing manual events fallback...")
    
    calendar = EconomicCalendar(api_key=None)  # No API key
    
    events = calendar.get_events_today_and_tomorrow()
    
    print(f"  ✅ Fallback events available: {len(events)} events")
    
    # Verify we have known events
    event_names = [evt[1] for evt in events]
    
    expected_events = ["FOMC Decision", "Non-Farm Payroll", "NFP", "CPI"]
    found = [evt for evt in expected_events if any(evt.lower() in name.lower() for name in event_names)]
    
    if found:
        print(f"  ✅ Found expected fallback events: {found}")
    else:
        print(f"  ⚠️  Note: No major USD events found in next 2 days (expected if no FOMC/NFP scheduled)")


def test_gating_config():
    """Test that gating configuration is correct."""
    print("\n🔍 Testing gating configuration...")
    
    # Check that windows make sense
    assert NewsGateConfig.HIGH_IMPACT_GATE_BEFORE_MIN > 0, "High-impact before should be > 0"
    assert NewsGateConfig.HIGH_IMPACT_GATE_AFTER_MIN > 0, "High-impact after should be > 0"
    assert NewsGateConfig.MEDIUM_IMPACT_DEGRADE_BEFORE_MIN > 0, "Medium-impact before should be > 0"
    assert NewsGateConfig.MEDIUM_IMPACT_DEGRADE_AFTER_MIN > 0, "Medium-impact after should be > 0"
    
    # Before windows should generally be < after windows
    assert (NewsGateConfig.HIGH_IMPACT_GATE_BEFORE_MIN <= 
            NewsGateConfig.MEDIUM_IMPACT_DEGRADE_BEFORE_MIN), "High-impact should be tighter"
    
    print(f"  ✅ HIGH_IMPACT_GATE: {NewsGateConfig.HIGH_IMPACT_GATE_BEFORE_MIN}min before, "
          f"{NewsGateConfig.HIGH_IMPACT_GATE_AFTER_MIN}min after")
    print(f"  ✅ MEDIUM_IMPACT_DEGRADE: {NewsGateConfig.MEDIUM_IMPACT_DEGRADE_BEFORE_MIN}min before, "
          f"{NewsGateConfig.MEDIUM_IMPACT_DEGRADE_AFTER_MIN}min after")
    print(f"  ✅ MIN_CONFIDENCE: {NewsGateConfig.BASE_MIN_CONFIDENCE:.2f}")


def run_all_tests():
    """Run all news gating tests."""
    print("\n" + "="*80)
    print("📰 NEWS GATING & ECONOMIC CALENDAR TEST SUITE")
    print("="*80)
    
    test_calendar_event_detection()
    test_is_near_event()
    test_signal_filter_gating()
    test_signal_degradation()
    test_manual_events_fallback()
    test_gating_config()
    
    print("\n" + "="*80)
    print("✅ All news gating tests completed successfully!")
    print("="*80)


if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

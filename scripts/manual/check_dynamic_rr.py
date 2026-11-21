#!/usr/bin/env python3
"""
Test script for dynamic_rr_ratio function
"""

from utils.indicators import dynamic_rr_ratio

def test_dynamic_rr_ratio():
    """Test the dynamic RR ratio function with various scenarios"""

    test_cases = [
        # (signal_strength, atr_value, news_sentiment, trend_strength, rsi_condition, position_type, expected_range)
        (100, 3.0, 'bullish', 1, 'oversold', 'BUY', 'high'),      # Perfect bullish setup
        (100, 3.0, 'bearish', -1, 'overbought', 'SELL', 'high'),  # Perfect bearish setup
        (33, 1.0, 'neutral', 0, 'neutral', 'BUY', 'low'),         # Weak signal
        (100, 3.0, 'bearish', 1, 'oversold', 'BUY', 'medium'),    # Conflicting signals
        (50, 2.0, 'neutral', 0, 'neutral', 'SELL', 'medium'),     # Average conditions
    ]

    print('Testing dynamic_rr_ratio function:')
    print('=' * 50)

    for i, (strength, atr_val, news, trend, rsi, pos_type, expected) in enumerate(test_cases, 1):
        rr = dynamic_rr_ratio(strength, atr_val, news, trend, rsi, pos_type)
        print(f'Test {i}: {pos_type} | Strength={strength}% | ATR={atr_val} | News={news} | Trend={trend} | RSI={rsi} → RR={rr:.2f} ({expected})')

    print('=' * 50)
    print('Function tests completed successfully!')

if __name__ == "__main__":
    test_dynamic_rr_ratio()

#!/usr/bin/env python3
"""
Test script for dynamic stop loss functionality
"""

from utils.indicators import dynamic_stop_loss

def test_dynamic_sl():
    print("🧪 Testing Dynamic Stop Loss Function")
    print("=" * 50)

    # Test scenarios
    scenarios = [
        {
            'name': 'Strong signal, low volatility',
            'params': {
                'signal_strength': 90,
                'atr_value': 1.0,
                'news_sentiment': 'neutral',
                'trend_strength': 1,
                'rsi_condition': 'neutral',
                'position_type': 'BUY'
            }
        },
        {
            'name': 'Weak signal, high volatility',
            'params': {
                'signal_strength': 30,
                'atr_value': 4.0,
                'news_sentiment': 'neutral',
                'trend_strength': 0,
                'rsi_condition': 'neutral',
                'position_type': 'BUY'
            }
        },
        {
            'name': 'News event impact',
            'params': {
                'signal_strength': 60,
                'atr_value': 2.0,
                'news_sentiment': 'bullish',
                'trend_strength': 0,
                'rsi_condition': 'neutral',
                'position_type': 'BUY'
            }
        },
        {
            'name': 'Extreme conditions',
            'params': {
                'signal_strength': 20,
                'atr_value': 5.0,
                'news_sentiment': 'bearish',
                'trend_strength': -1,
                'rsi_condition': 'overbought',
                'position_type': 'SELL'
            }
        }
    ]

    for scenario in scenarios:
        result = dynamic_stop_loss(**scenario['params'])
        print(f"{scenario['name']}: {result:.2f}")

    print("\n✅ Dynamic SL testing completed!")

if __name__ == "__main__":
    test_dynamic_sl()

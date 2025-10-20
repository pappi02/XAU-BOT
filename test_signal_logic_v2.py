import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import your actual signal generation function
from strategies.strategy_basic import BasicTradingStrategy

# ==============================
# Helper: Create synthetic OHLC data
# ==============================
def generate_fake_data(trend='sideways', candles=200):
    now = datetime.now()
    times = [now - timedelta(minutes=i) for i in range(candles)][::-1]
    base_price = 2400

    if trend == 'bullish':
        close = np.linspace(base_price, base_price + 20, candles)
    elif trend == 'bearish':
        close = np.linspace(base_price, base_price - 20, candles)
    else:
        close = base_price + np.random.normal(0, 1, candles)

    df = pd.DataFrame({
        'time': times,
        'open': close - np.random.normal(0.2, 0.1, candles),
        'high': close + np.random.normal(0.5, 0.2, candles),
        'low': close - np.random.normal(0.5, 0.2, candles),
        'close': close,
        'volume': np.random.randint(100, 1000, candles)
    })
    return df

# ==============================
# Test different market conditions
# ==============================
def test_signal_scenarios():
    strategy = BasicTradingStrategy()
    scenarios = {
        "Strong Bullish Trend": generate_fake_data('bullish', 200),
        "Strong Bearish Trend": generate_fake_data('bearish', 200),
        "Sideways Market": generate_fake_data('sideways', 200),
    }

    for name, data in scenarios.items():
        prepared_data = strategy.prepare_data(data)
        signal_info = strategy.generate_signal(prepared_data)
        signal = signal_info['signal']
        strength = signal_info['strength']
        print(f"\n📊 Scenario: {name}")
        print(f"➡️ Signal: {signal} | Strength: {strength:.2f}%")

        # Interpretation
        if signal == "BUY" and strength > 70:
            print("✅ Strong buy confirmation (expected in bullish trend).")
        elif signal == "SELL" and strength > 70:
            print("✅ Strong sell confirmation (expected in bearish trend).")
        elif signal == "HOLD":
            print("⚖️ No clear signal — expected in sideways conditions.")
        else:
            print("ℹ️ Moderate or weak signal — check indicator alignment.")

# ==============================
# Main Test
# ==============================
if __name__ == "__main__":
    print("🧪 Starting advanced signal logic test...")
    test_signal_scenarios()
    print("\n✅ Fuzzy logic signal testing completed successfully!")

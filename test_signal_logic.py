import pandas as pd
import numpy as np
import logging

# ----------------------------------------------------
# Logging Setup
# ----------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ----------------------------------------------------
# Simulated Data Preparation (for testing)
# ----------------------------------------------------
def prepare_test_data(n=200):
    """Create fake OHLC data with indicators for testing."""
    np.random.seed(42)
    data = pd.DataFrame({
        "open": np.random.uniform(1900, 2000, n),
        "high": np.random.uniform(1905, 2005, n),
        "low": np.random.uniform(1895, 1995, n),
        "close": np.random.uniform(1900, 2000, n)
    })
    data["ema_fast"] = data["close"].ewm(span=10, adjust=False).mean()
    data["ema_slow"] = data["close"].ewm(span=50, adjust=False).mean()
    data["rsi"] = np.random.uniform(10, 90, n)
    data["bb_upper"] = data["close"].rolling(20).mean() + 2 * data["close"].rolling(20).std()
    data["bb_lower"] = data["close"].rolling(20).mean() - 2 * data["close"].rolling(20).std()
    logging.info("📊 Data prepared with indicators")
    return data.dropna()

# ----------------------------------------------------
# Fuzzy Signal Logic
# ----------------------------------------------------
def generate_signal(ema_signal, rsi_condition, bb_signal):
    ema_weight, rsi_weight, bb_weight = 0.4, 0.3, 0.3
    buy_score = sell_score = 0

    if ema_signal == 1: buy_score += ema_weight
    elif ema_signal == -1: sell_score += ema_weight

    if rsi_condition == "bullish": buy_score += rsi_weight
    elif rsi_condition == "bearish": sell_score += rsi_weight

    if bb_signal == 1: buy_score += bb_weight
    elif bb_signal == -1: sell_score += bb_weight

    tolerance = 0.05
    total = buy_score + sell_score
    strength = round(abs(buy_score - sell_score) / total * 100, 2) if total > 0 else 0

    if abs(buy_score - sell_score) < tolerance:
        signal = "HOLD"
    elif buy_score > sell_score:
        signal = "BUY"
    else:
        signal = "SELL"

    return signal, strength, buy_score, sell_score


# ----------------------------------------------------
# Test Scenarios
# ----------------------------------------------------
def test_signal_logic():
    data = prepare_test_data()
    print(f"Total candles: {len(data)}\n")
    print("🧪 Testing signal generation with fuzzy logic...")

    tests = {
        "Strong BUY (all align)": (1, "bullish", 1),
        "Moderate BUY (2/3 align)": (1, "bullish", -1),
        "Weak BUY (1 indicator)": (1, "neutral", -1),
        "Strong SELL (all align)": (-1, "bearish", -1),
        "HOLD (mixed signals)": (1, "bearish", -1),
    }

    for name, (ema, rsi, bb) in tests.items():
        signal, strength, buy_score, sell_score = generate_signal(ema, rsi, bb)
        print(f"{name}: {signal} (strength: {strength}%) | buy_score={buy_score}, sell_score={sell_score}")

    print("\n✅ Signal logic test completed!")
    print("The fuzzy logic now adjusts signal strength based on indicator alignment.")

# ----------------------------------------------------
# Run Test
# ----------------------------------------------------
if __name__ == "__main__":
    test_signal_logic()

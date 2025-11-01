import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from execution.trade_executor import TradeExecutor

# Create executor with default mocks (None values trigger mock setup)
executor = TradeExecutor(mt5_module=None, config=None, risk_manager=None)

# Fake signal
fake_signal = {
    "signal": "BUY",
    "strength": 95.0,
    "components": {"ema_signal": 1, "rsi_condition": "bullish", "bb_signal": "bullish"}
}

# Execute trade
try:
    result = executor.execute_trade(fake_signal)
    print("Trade executed successfully:", result)
except Exception as e:
    print("Error:", e)


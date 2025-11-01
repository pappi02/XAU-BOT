"""
Base class for all chart patterns.
Each pattern must implement detect() and describe() methods.
"""

class BasePattern:
    """
    Base class for all chart patterns.
    Each pattern must implement detect() and describe() methods.
    """

    def __init__(self, candles):
        """
        Args:
            candles (list): List of candle data (OHLC).
                Example: [{"open":..., "high":..., "low":..., "close":..., "time":...}, ...]
        """
        self.candles = candles

    def detect(self):
        """
        Detects if pattern is forming.
        Returns:
            dict: {
                "detected": bool,
                "direction": "bullish" | "bearish" | None,
                "breakout_price": float | None,
                "confidence": float (0-1)
            }
        """
        raise NotImplementedError("detect() must be implemented in subclass.")

    def describe(self):
        """Returns a human-readable description of the pattern."""
        raise NotImplementedError("describe() must be implemented in subclass.")

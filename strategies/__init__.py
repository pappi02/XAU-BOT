# strategies/__init__.py - Strategy Module Initialization

from .scalping import ScalpingStrategy
from .regime_detector import RegimeDetector
from .strategy_selector import StrategySelector

__all__ = [
    'ScalpingStrategy',
    'RegimeDetector',
    'StrategySelector'
]

# Strategy mapping for easy access - only scalping for short-term focus
STRATEGY_CLASSES = {
    'scalping': ScalpingStrategy
}

def create_strategy(strategy_type, **kwargs):
    """
    Factory function to create trading strategies.

    Args:
        strategy_type (str): Type of strategy ('basic', 'trend_trading', etc.)
        **kwargs: Strategy parameters

    Returns:
        Strategy instance

    Raises:
        ValueError: If strategy type is unknown
    """
    if strategy_type not in STRATEGY_CLASSES:
        available = list(STRATEGY_CLASSES.keys())
        raise ValueError(f"Unknown strategy type: {strategy_type}. Available: {available}")

    return STRATEGY_CLASSES[strategy_type](**kwargs)

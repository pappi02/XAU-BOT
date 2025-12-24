# strategies/__init__.py - Professional Scalping Strategies Module

# Import all professional scalping strategies
from .breakout_scalping import BreakoutScalping
from .momentum_scalping import MomentumScalping
from .ma_scalping import MovingAverageScalping
from .dip_scalping import DipScalping
from .range_scalping import RangeScalping

# Legacy imports (kept for backward compatibility, but not recommended for new code)
from .scalping import ScalpingStrategy
from .regime_detector import RegimeDetector
from .strategy_selector import StrategySelector

__all__ = [
    # Professional scalping strategies (recommended)
    'BreakoutScalping',
    'MomentumScalping',
    'MovingAverageScalping',
    'DipScalping',
    'RangeScalping',
    # Legacy strategies
    'ScalpingStrategy',
    'RegimeDetector',
    'StrategySelector'
]

# Professional strategy mapping - 5 expert scalping strategies
STRATEGY_CLASSES = {
    'breakout_scalping': BreakoutScalping,
    'momentum_scalping': MomentumScalping,
    'ma_scalping': MovingAverageScalping,
    'dip_scalping': DipScalping,
    'range_scalping': RangeScalping,
    # Legacy
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

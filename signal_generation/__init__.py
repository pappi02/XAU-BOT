"""
Signal Generation Package - Professional modular signal generation system

This package consolidates all signal generation logic into focused, modular components.
Imports are intentionally lazy to avoid circular dependencies during package initialization.
"""

__all__ = [
    'TechnicalIndicatorAnalyzer',
    'PatternDetector',
    'NewsSentimentAnalyzer',
    'StrategyAnalyzer',
    'AdaptiveSignalAnalyzer',
    'SignalMaster'
]

__version__ = '2.0.0'
__description__ = 'Professional modular signal generation system for algorithmic trading'


def __getattr__(name):
    """Lazily import components to avoid circular imports."""
    if name == 'TechnicalIndicatorAnalyzer':
        from signal_generation.indicator_analyzer import TechnicalIndicatorAnalyzer
        return TechnicalIndicatorAnalyzer
    if name == 'PatternDetector':
        from signal_generation.pattern_detector import PatternDetector
        return PatternDetector
    if name == 'NewsSentimentAnalyzer':
        from signal_generation.news_sentiment_analyzer import NewsSentimentAnalyzer
        return NewsSentimentAnalyzer
    if name == 'StrategyAnalyzer':
        from signal_generation.strategy_analyzer import StrategyAnalyzer
        return StrategyAnalyzer
    if name == 'AdaptiveSignalAnalyzer':
        from signal_generation.adaptive_signal_analyzer import AdaptiveSignalAnalyzer
        return AdaptiveSignalAnalyzer
    if name == 'SignalMaster':
        from signal_generation.signal_master import SignalMaster
        return SignalMaster
    raise AttributeError(f"module 'signal_generation' has no attribute {name}")

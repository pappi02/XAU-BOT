"""
Pattern recognition module for trading bot.
Contains various chart pattern detection classes and functions.
"""

from .base_pattern import BasePattern
from .symmetrical_triangle import SymmetricalTriangle
from .bullish_flag import BullishFlag
from .bearish_flag import BearishFlag
from .wedge import RisingWedge, FallingWedge
from .double_top import detect_double_top
from .double_bottom import detect_double_bottom
from .channels import (
    detect_bullish_channel,
    detect_bearish_channel,
    detect_horizontal_channel
)
from .head_and_shoulders import detect_head_and_shoulders
from .triple_extrema import detect_triple_top, detect_triple_bottom, plot_pattern

__all__ = [
    'BasePattern',
    'SymmetricalTriangle',
    'BullishFlag',
    'BearishFlag',
    'RisingWedge',
    'FallingWedge',
    'detect_double_top',
    'detect_double_bottom',
    'detect_bullish_channel',
    'detect_bearish_channel',
    'detect_horizontal_channel',
    'detect_head_and_shoulders',
    'detect_triple_top',
    'detect_triple_bottom',
    'plot_pattern'
]

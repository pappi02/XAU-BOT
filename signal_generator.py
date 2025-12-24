"""
Legacy compatibility wrapper for the modular signal generation system.
All code now lives in signal_generator_new.py and signal_generation/ modules.
"""

from signal_generator_new import UnifiedSignalGenerator, create_signal_generator

__all__ = ["UnifiedSignalGenerator", "create_signal_generator"]

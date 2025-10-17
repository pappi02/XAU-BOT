"""
Compatibility shim for existing modules that import `utils.trade_logger`.
This re-exports the project's root-level `trade_logger.log_signal` function
and `trade_logger` instance so both import styles work.
"""
from trade_logger import log_signal, trade_logger

__all__ = ["log_signal", "trade_logger"]

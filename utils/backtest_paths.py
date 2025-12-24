"""
Utility functions to standardize backtest report folder structure.
New structure: reports/backtests/<symbol>/<timeframe>/<YYYY-MM-DD>/<run_id>/
Files: metrics.json, equity.csv, trades.csv
"""

import os
from datetime import datetime
from dataclasses import dataclass

@dataclass
class BacktestPaths:
    dir: str
    metrics_path: str
    equity_path: str
    trades_path: str
    run_id: str


def build_backtest_paths(symbol: str, timeframe: str, base_dir: str = "reports") -> BacktestPaths:
    """
    Build organized output paths for a backtest run.

    Args:
        symbol: Trading symbol (e.g., XAUUSD)
        timeframe: Timeframe (e.g., M5)
        base_dir: Base reports directory (default: reports)

    Returns:
        BacktestPaths with directory and file paths.
    """
    # Normalize
    symbol = str(symbol).upper()
    timeframe = str(timeframe).upper()

    # Run identifiers
    stamp = datetime.utcnow()
    date_str = stamp.strftime("%Y-%m-%d")
    run_id = stamp.strftime("%Y%m%d_%H%M%S")

    # Directory structure
    dir_path = os.path.join(base_dir, "backtests", symbol, timeframe, date_str, run_id)
    metrics_path = os.path.join(dir_path, "metrics.json")
    equity_path = os.path.join(dir_path, "equity.csv")
    trades_path = os.path.join(dir_path, "trades.csv")

    return BacktestPaths(
        dir=dir_path,
        metrics_path=metrics_path,
        equity_path=equity_path,
        trades_path=trades_path,
        run_id=run_id,
    )


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

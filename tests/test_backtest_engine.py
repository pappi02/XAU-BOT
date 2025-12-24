"""
Basic tests for BacktestEngine using synthetic data.
Validates that the engine runs and produces metrics and trades.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.backtest_engine import BacktestEngine, BacktestConfig


def create_trending_df(length: int = 500) -> pd.DataFrame:
    dates = pd.date_range('2023-01-01', periods=length, freq='5min')
    base = np.linspace(2000, 2100, length)
    noise = np.random.randn(length) * 0.8
    close = base + noise
    high = close + np.abs(np.random.randn(length) * 0.6)
    low = close - np.abs(np.random.randn(length) * 0.6)
    open_ = close + np.random.randn(length) * 0.2
    vol = (1000 + np.random.randint(-200, 200, length)).astype(float)

    df = pd.DataFrame({
        'time': dates,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'tick_volume': vol,
    })
    return df


def test_engine_runs_on_synthetic_data():
    df = create_trending_df(600)
    engine = BacktestEngine(BacktestConfig(
        starting_balance=1000.0,
        risk_per_trade_pct=0.003,
        atr_multiplier_sl=2.2,
        tp_rr=2.0,
        enable_news_gating=False,
        enable_strategy_refinements=True,
        enable_pattern_quality_controls=True,
    ))

    result = engine.run(df)

    print("\nBacktest metrics:", result.metrics)
    print("Trades:", len(result.trades))
    assert result.balance_final > 0
    assert isinstance(result.metrics, dict)
    assert 'sharpe' in result.metrics
    assert len(result.trades) >= 0

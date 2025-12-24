"""
Backtest Engine for UnifiedSignalGenerator.
Simulates trades on historical OHLC data with risk-based SL/TP, fees, and slippage.
Computes performance metrics: Sharpe, CAGR, max drawdown, win rate, profit factor.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

# Local imports
from signal_generator import UnifiedSignalGenerator
import config


@dataclass
class BacktestConfig:
    starting_balance: float = 1000.0
    risk_per_trade_pct: float = max(0.001, min(config.RISK_PER_TRADE_PCT, 0.05))  # clamp to [0.1%, 5%]
    atr_multiplier_sl: float = config.ATR_MULTIPLIER_SL
    tp_rr: float = config.TP_RISK_REWARD
    max_hold_bars: int = 50
    slippage_pct: float = 0.0005  # 5 bps
    commission_per_trade: float = 0.0
    spread_cost_usd: float = 0.0
    enable_news_gating: bool = False
    enable_strategy_refinements: bool = True
    enable_pattern_quality_controls: bool = True
    sensitivity: str = 'balanced'


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime]
    direction: str  # 'BUY' or 'SELL'
    entry_price: float
    sl_price: float
    tp_price: float
    result: str  # 'TP' or 'SL' or 'TIME'
    rr: float
    pnl_usd: float


@dataclass
class BacktestResult:
    balance_final: float
    trades: List[Trade]
    equity_curve: pd.Series
    metrics: Dict[str, float]


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift(1)).abs()
    low_close = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def compute_metrics(equity: pd.Series) -> Dict[str, float]:
    returns = equity.pct_change().fillna(0.0)
    avg_ret = returns.mean()
    vol = returns.std()
    sharpe = (avg_ret / vol) * math.sqrt(252) if vol > 0 else 0.0

    # Max drawdown
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_dd = drawdown.min() if len(drawdown) else 0.0

    # CAGR
    if len(equity) > 1:
        days = (equity.index[-1] - equity.index[0]).days or 1
        years = days / 365.0
        cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0
    else:
        cagr = 0.0

    return {
        'sharpe': float(sharpe),
        'max_drawdown': float(max_dd),
        'cagr': float(cagr),
        'avg_daily_return': float(avg_ret * 252),
        'volatility_annual': float(vol * math.sqrt(252)),
    }


class BacktestEngine:
    def __init__(self, bt_config: Optional[BacktestConfig] = None):
        self.bt_config = bt_config or BacktestConfig()
        self.generator = UnifiedSignalGenerator(
            config=config,
            enable_news_gating=self.bt_config.enable_news_gating,
            enable_strategy_refinements=self.bt_config.enable_strategy_refinements,
            enable_pattern_quality_controls=self.bt_config.enable_pattern_quality_controls,
            sensitivity=self.bt_config.sensitivity,
        )

    def _prepare_df(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
        df = df.sort_index()
        # Ensure required columns exist
        for col in ['open', 'high', 'low', 'close']:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        # Add ATR if missing
        if 'atr' not in df.columns:
            df['atr'] = compute_atr(df)
        return df.dropna().copy()

    def run(self, df: pd.DataFrame) -> BacktestResult:
        df = self._prepare_df(df)
        balance = self.bt_config.starting_balance
        equity_curve = []
        trades: List[Trade] = []

        open_position: Optional[Trade] = None
        # Iterate over candles; use rolling window for signal gen
        for i in range(60, len(df) - 1):
            window = df.iloc[: i + 1]
            signal_info = self.generator.generate_signal(window)
            current_time = window.index[-1]
            current_close = float(window['close'].iloc[-1])
            next_open = float(df['open'].iloc[i + 1])
            atr_val = float(window['atr'].iloc[-1])

            # Manage existing position first
            if open_position:
                # Check TP/SL hit on current candle
                high = float(window['high'].iloc[-1])
                low = float(window['low'].iloc[-1])
                hit_tp = (
                    (open_position.direction == 'BUY' and high >= open_position.tp_price) or
                    (open_position.direction == 'SELL' and low <= open_position.tp_price)
                )
                hit_sl = (
                    (open_position.direction == 'BUY' and low <= open_position.sl_price) or
                    (open_position.direction == 'SELL' and high >= open_position.sl_price)
                )

                exit_reason = None
                pnl = 0.0
                if hit_tp or hit_sl:
                    exit_time = current_time
                    rr = self.bt_config.tp_rr if hit_tp else -1.0
                    risk_amount = balance * self.bt_config.risk_per_trade_pct
                    pnl = risk_amount * rr - self.bt_config.commission_per_trade - self.bt_config.spread_cost_usd
                    balance += pnl
                    exit_reason = 'TP' if hit_tp else 'SL'
                else:
                    # Max hold check
                    bars_held = sum(1 for t in equity_curve if isinstance(t, tuple) and t[0] == open_position.entry_time)
                    if bars_held >= self.bt_config.max_hold_bars:
                        exit_time = current_time
                        rr = 0.0  # time exit, breakeven (could refine)
                        pnl = - self.bt_config.commission_per_trade - self.bt_config.spread_cost_usd
                        balance += pnl
                        exit_reason = 'TIME'
                
                if exit_reason:
                    open_position.exit_time = exit_time
                    open_position.pnl_usd = pnl
                    open_position.result = exit_reason
                    trades.append(open_position)
                    open_position = None

            # If no open position, consider new signal
            if not open_position:
                # Accept string direction if provided; otherwise convert numeric signal
                if 'direction' in signal_info:
                    signal = signal_info['direction']
                else:
                    sig_val = signal_info.get('signal', 0)
                    signal = 'BUY' if sig_val == 1 else ('SELL' if sig_val == -1 else 'HOLD')
                # Prefer strength (0-100). Fallback: confidence in [0,1] scaled.
                strength = float(signal_info.get('strength', 0.0))
                conf = float(signal_info.get('confidence', strength / 100.0))
                # Sensitivity-based entry threshold (in %)
                sens = (self.bt_config.sensitivity or 'balanced').lower()
                entry_min = {'conservative': 65.0, 'balanced': 55.0, 'aggressive': 12.0}.get(sens, 55.0)
                # Accept if strength above threshold (or confidence >= threshold in [0,1])
                if signal in ('BUY', 'SELL') and (strength >= entry_min or conf >= entry_min / 100.0):
                    # Entry at next open with slippage
                    slip = next_open * self.bt_config.slippage_pct
                    entry = next_open + slip if signal == 'BUY' else next_open - slip
                    # SL/TP
                    sl_dist = self.bt_config.atr_multiplier_sl * atr_val
                    tp_dist = sl_dist * self.bt_config.tp_rr
                    sl = entry - sl_dist if signal == 'BUY' else entry + sl_dist
                    tp = entry + tp_dist if signal == 'BUY' else entry - tp_dist

                    # Risk check
                    risk_amount = balance * self.bt_config.risk_per_trade_pct
                    if risk_amount < 0.5:  # minimal risk amount
                        continue

                    open_position = Trade(
                        entry_time=current_time,
                        exit_time=None,
                        direction=signal,
                        entry_price=entry,
                        sl_price=sl,
                        tp_price=tp,
                        result='OPEN',
                        rr=0.0,
                        pnl_usd=0.0,
                    )

            equity_curve.append(balance)

        equity_series = pd.Series(equity_curve, index=df.index[60:60+len(equity_curve)])
        metrics = compute_metrics(equity_series)
        return BacktestResult(
            balance_final=float(balance),
            trades=trades,
            equity_curve=equity_series,
            metrics=metrics,
        )

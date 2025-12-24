"""
CLI runner for BacktestEngine.
Fetches MT5 historical candles and runs the unified backtest, saving reports.
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



import os
import sys
import json
import argparse
from datetime import datetime
import io

# Fix Unicode encoding issues on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd

from data.connect_mt5 import connect_mt5, disconnect_mt5
from data.fetch_candles import get_candles
from utils.symbol_helpers import resolve_symbol
from utils.backtest_engine import BacktestEngine, BacktestConfig
from utils.backtest_paths import build_backtest_paths, ensure_dir
import config


def run_backtest(symbol: str, timeframe: str, candles: int, output_dir: str, sensitivity: str = 'balanced'):
    symbol = resolve_symbol(symbol)
    # Connect to MT5 using config credentials if available
    account = getattr(config, 'MT5_ACCOUNT', None)
    password = getattr(config, 'MT5_PASSWORD', None)
    server = getattr(config, 'MT5_SERVER', None)

    if not connect_mt5(account, password, server, getattr(config, 'MT5_TIMEOUT', 60000)):
        print("[ERROR] Failed to connect to MT5. Ensure credentials and terminal path are correct.")
        sys.exit(1)

    try:
        df = get_candles(symbol=symbol, timeframe=timeframe, num_candles=candles)
        if df is None or df.empty:
            print("[ERROR] No data fetched for backtest.")
            sys.exit(2)

        # Ensure required columns naming for BacktestEngine
        for col in ['open', 'high', 'low', 'close']:
            if col not in df.columns:
                raise RuntimeError(f"Missing column '{col}' in fetched data")

        engine = BacktestEngine(BacktestConfig(sensitivity=sensitivity))
        result = engine.run(df)

        # Organized folder structure under reports/backtests/<symbol>/<tf>/<YYYY-MM-DD>/<run_id>/
        paths = build_backtest_paths(symbol, timeframe, base_dir=output_dir)
        ensure_dir(paths.dir)
        metrics_path = paths.metrics_path
        equity_path = paths.equity_path
        trades_path = paths.trades_path

        # Save metrics and equity curve
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "starting_balance": float(BacktestConfig().starting_balance),
            "final_balance": float(result.balance_final),
            "metrics": result.metrics,
            "trade_count": len(result.trades)
        }
        with open(metrics_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)

        result.equity_curve.to_csv(equity_path, header=['equity'])

        # Save trades
        trades_df = pd.DataFrame([
            {
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'direction': t.direction,
                'entry_price': t.entry_price,
                'sl_price': t.sl_price,
                'tp_price': t.tp_price,
                'result': t.result,
                'rr': t.rr,
                'pnl_usd': t.pnl_usd
            }
            for t in result.trades
        ])
        trades_df.to_csv(trades_path, index=False)

        print("[OK] Backtest complete")
        print(f"Final balance: {result.balance_final:.2f}")
        print("Metrics:")
        for k, v in result.metrics.items():
            print(f"  - {k}: {v:.4f}")
        print(
            "Artifacts saved to: "
            f"{paths.dir}\n  - metrics.json\n  - equity.csv\n  - trades.csv"
        )

    finally:
        disconnect_mt5()


def main():
    parser = argparse.ArgumentParser(description="Run backtest using BacktestEngine")
    parser.add_argument('--symbol', default=getattr(config, 'SYMBOL', 'XAUUSD'), help='Trading symbol')
    parser.add_argument('--timeframe', default='M5', help='Timeframe (e.g., M5, M15, H1)')
    parser.add_argument('--candles', type=int, default=2000, help='Number of candles to fetch')
    parser.add_argument('--out', default='reports', help='Output directory for artifacts')
    parser.add_argument('--sensitivity', default='balanced', choices=['conservative', 'balanced', 'aggressive'], help='Signal sensitivity preset')
    args = parser.parse_args()

    run_backtest(args.symbol, args.timeframe, args.candles, args.out, args.sensitivity)


if __name__ == '__main__':
    main()
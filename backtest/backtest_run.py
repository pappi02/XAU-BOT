"""
Run a simple backtest using the BacktestEngine and UnifiedSignalGenerator.
Fetches candles via MT5 (data/fetch_candles.py) or from a CSV.
"""

import argparse
import pandas as pd
from typing import Optional

from utils.backtest_engine import BacktestEngine, BacktestConfig
from utils.backtest_paths import build_backtest_paths, ensure_dir
from data.fetch_candles import get_candles
from data.connect_mt5 import connect_mt5, disconnect_mt5
import config


def load_data(symbol: str, timeframe: str, candles: int, csv: Optional[str]) -> pd.DataFrame:
    if csv:
        df = pd.read_csv(csv)
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
        return df
    # Try MT5
    if connect_mt5():
        df = get_candles(symbol=symbol, timeframe=timeframe, num_candles=candles)
        disconnect_mt5()
        return df
    raise RuntimeError("Failed to connect to MT5 and no CSV provided.")


def main():
    parser = argparse.ArgumentParser(description="Run backtest for UnifiedSignalGenerator")
    parser.add_argument('--symbol', default=config.SYMBOL, help='Symbol to backtest')
    parser.add_argument('--timeframe', default='M5', help='Timeframe (e.g., M5, M15)')
    parser.add_argument('--candles', type=int, default=1500, help='Number of candles to fetch')
    parser.add_argument('--csv', default=None, help='Path to CSV with OHLC data')
    parser.add_argument('--balance', type=float, default=1000.0, help='Starting balance')
    parser.add_argument('--risk', type=float, default=config.RISK_PER_TRADE_PCT*100.0, help='Risk per trade %')
    parser.add_argument('--rr', type=float, default=config.TP_RISK_REWARD, help='TP risk-reward multiple')
    parser.add_argument('--atr', type=float, default=config.ATR_MULTIPLIER_SL, help='ATR multiplier for SL')

    args = parser.parse_args()

    df = load_data(args.symbol, args.timeframe, args.candles, args.csv)
    bt_conf = BacktestConfig(
        starting_balance=args.balance,
        risk_per_trade_pct=max(0.001, min(args.risk/100.0, 0.05)),
        atr_multiplier_sl=args.atr,
        tp_rr=args.rr,
        enable_news_gating=False,
        enable_strategy_refinements=True,
        enable_pattern_quality_controls=True,
    )

    engine = BacktestEngine(bt_conf)
    result = engine.run(df)

    print("\n=== Backtest Summary ===")
    print(f"Symbol: {args.symbol}  TF: {args.timeframe}  Candles: {len(df)}")
    print(f"Starting Balance: ${args.balance:.2f} → Final: ${result.balance_final:.2f}")
    print(f"Trades: {len(result.trades)}")
    print("Metrics:")
    for k, v in result.metrics.items():
        print(f"  - {k}: {v:.4f}")

    # Trade outcomes
    tp = sum(1 for t in result.trades if t.result == 'TP')
    sl = sum(1 for t in result.trades if t.result == 'SL')
    time = sum(1 for t in result.trades if t.result == 'TIME')
    win_rate = tp / len(result.trades) if result.trades else 0.0
    print(f"Wins: {tp}  Losses: {sl}  Time-outs: {time}  WinRate: {win_rate:.1%}")

    # Save artifacts in organized folder structure
    try:
        paths = build_backtest_paths(args.symbol, args.timeframe, base_dir='reports')
        ensure_dir(paths.dir)

        # Save metrics summary
        import json
        payload = {
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "starting_balance": float(bt_conf.starting_balance),
            "final_balance": float(result.balance_final),
            "metrics": result.metrics,
            "trade_count": len(result.trades),
        }
        with open(paths.metrics_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)

        # Save equity curve
        result.equity_curve.to_csv(paths.equity_path, header=['equity'])

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
                'pnl_usd': t.pnl_usd,
            }
            for t in result.trades
        ])
        trades_df.to_csv(paths.trades_path, index=False)

        print(f"Artifacts saved to: {paths.dir}\n  - metrics.json\n  - equity.csv\n  - trades.csv")
    except Exception as e:
        print(f"[WARN] Failed to save backtest artifacts: {e}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python
"""
Backtest Results Comparison Tool
Compares multiple backtest runs to validate professional enhancements
"""

import json
import os
from datetime import datetime
from pathlib import Path

def load_backtest_json(filepath):
    """Load backtest JSON results"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def compare_backtests(results_dir="reports"):
    """Compare all backtests in directory"""
    
    print("=" * 80)
    print("BACKTEST COMPARISON REPORT")
    print("=" * 80)
    print()
    
    # Find all backtest JSON files (support old flat and new organized structure)
    json_files = sorted(
        list(Path(results_dir).glob("backtest_*.json")) +
        list(Path(results_dir).glob("backtests/**/metrics.json"))
    )
    
    if not json_files:
        print("No backtest files found in reports directory")
        return
    
    backtests = []
    for filepath in json_files:
        data = load_backtest_json(filepath)
        if data:
            backtests.append({
                'file': filepath.name,
                'data': data,
                'timestamp': filepath.stat().st_mtime
            })
    
    if not backtests:
        print("No valid backtest files found")
        return
    
    # Sort by timestamp (oldest first)
    backtests.sort(key=lambda x: x['timestamp'])
    
    print(f"Found {len(backtests)} backtest(s)\n")
    
    # Display all backtests
    for i, bt in enumerate(backtests, 1):
        data = bt['data']
        metrics = data.get('metrics', {})
        
        print(f"Backtest #{i}: {bt['file']}")
        print("-" * 80)
        print(f"  Symbol:           {data.get('symbol', 'N/A')}")
        print(f"  Timeframe:        {data.get('timeframe', 'N/A')}")
        print(f"  Trade Count:      {data.get('trade_count', 0)}")
        print(f"  Starting Balance: ${data.get('starting_balance', 0):,.2f}")
        print(f"  Final Balance:    ${data.get('final_balance', 0):,.2f}")
        print(f"  Profit/Loss:      ${data.get('final_balance', 0) - data.get('starting_balance', 0):,.2f}")
        print(f"  Return %:         {((data.get('final_balance', 0) - data.get('starting_balance', 0)) / data.get('starting_balance', 1) * 100):.2f}%")
        print()
        print(f"  Metrics:")
        print(f"    Sharpe Ratio:   {metrics.get('sharpe', 0):.4f}")
        print(f"    CAGR:           {metrics.get('cagr', 0):.2f}%")
        print(f"    Max Drawdown:   {metrics.get('max_drawdown', 0):.2f}%")
        print(f"    Volatility:     {metrics.get('volatility_annual', 0):.4f}")
        print(f"    Daily Return:   {metrics.get('avg_daily_return', 0):.4f}")
        print()
    
    # Comparison
    if len(backtests) > 1:
        print("=" * 80)
        print("COMPARISON: Latest vs Oldest")
        print("=" * 80)
        print()
        
        first = backtests[0]['data']
        latest = backtests[-1]['data']
        
        first_return = ((first.get('final_balance', 0) - first.get('starting_balance', 0)) / 
                        first.get('starting_balance', 1) * 100)
        latest_return = ((latest.get('final_balance', 0) - latest.get('starting_balance', 0)) / 
                         latest.get('starting_balance', 1) * 100)
        
        print(f"{'Metric':<20} {'Initial':<15} {'Latest':<15} {'Change':<15}")
        print("-" * 65)
        
        # Trades
        first_trades = first.get('trade_count', 0)
        latest_trades = latest.get('trade_count', 0)
        trade_change = ((latest_trades - first_trades) / max(first_trades, 1) * 100) if first_trades else 0
        print(f"{'Trade Count':<20} {first_trades:<15} {latest_trades:<15} {trade_change:+.1f}%")
        
        # Returns
        print(f"{'Return %':<20} {first_return:<14.2f}% {latest_return:<14.2f}% {latest_return - first_return:+.2f}%")
        
        # Sharpe
        first_sharpe = first.get('metrics', {}).get('sharpe', 0)
        latest_sharpe = latest.get('metrics', {}).get('sharpe', 0)
        sharpe_change = latest_sharpe - first_sharpe
        print(f"{'Sharpe Ratio':<20} {first_sharpe:<15.4f} {latest_sharpe:<15.4f} {sharpe_change:+.4f}")
        
        # CAGR
        first_cagr = first.get('metrics', {}).get('cagr', 0)
        latest_cagr = latest.get('metrics', {}).get('cagr', 0)
        cagr_change = latest_cagr - first_cagr
        print(f"{'CAGR %':<20} {first_cagr:<14.2f}% {latest_cagr:<14.2f}% {cagr_change:+.2f}%")
        
        # Max Drawdown
        first_dd = first.get('metrics', {}).get('max_drawdown', 0)
        latest_dd = latest.get('metrics', {}).get('max_drawdown', 0)
        dd_change = latest_dd - first_dd
        print(f"{'Max Drawdown %':<20} {first_dd:<14.2f}% {latest_dd:<14.2f}% {dd_change:+.2f}%")
        
        print()
        print("=" * 80)
        print("INTERPRETATION")
        print("=" * 80)
        
        if latest_trades > first_trades:
            print(f"[+] Trading Opportunities: {latest_trades - first_trades:+d} more trades detected")
        
        if latest_return > first_return:
            print(f"[+] Return Improvement: {latest_return - first_return:+.2f}% better")
        
        if latest_sharpe > first_sharpe:
            print(f"[+] Risk-Adjusted Returns: Sharpe improved by {(latest_sharpe/first_sharpe - 1)*100:+.1f}%")
        
        if abs(latest_dd) <= abs(first_dd):
            print(f"[+] Drawdown Control: Improved from {first_dd:.2f}% to {latest_dd:.2f}%")
        
        print()

if __name__ == '__main__':
    import sys
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "reports"
    compare_backtests(results_dir)
    print("Done.")

#!/usr/bin/env python
"""
Real-time Backtest Monitoring
Tracks progress of running backtests
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path

def monitor_backtest(results_dir="reports", check_interval=10):
    """Monitor backtest progress"""
    
    print("[BACKTEST MONITOR] Started at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("[BACKTEST MONITOR] Checking for results every", check_interval, "seconds")
    print()
    
    last_files = set()
    
    while True:
        # Find JSON files (legacy flat and new organized)
        json_files = list(Path(results_dir).glob("backtest_*.json"))
        json_files += list(Path(results_dir).glob("backtests/**/metrics.json"))
        current_files = {f.name for f in json_files}
        
        # Check for new files
        new_files = current_files - last_files
        if new_files:
            for filename in sorted(new_files):
                # Build full path respecting nested dirs
                filepath = next((p for p in json_files if p.name == filename), Path(results_dir) / filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    print(f"[NEW BACKTEST] {filename}")
                    print(f"  Trades: {data.get('trade_count', 0)}")
                    print(f"  Final Balance: ${data.get('final_balance', 0):.2f}")
                    print(f"  Sharpe: {data.get('metrics', {}).get('sharpe', 0):.4f}")
                    print(f"  CAGR: {data.get('metrics', {}).get('cagr', 0):.2f}%")
                    print()
                except Exception as e:
                    print(f"[ERROR] Could not read {filename}: {e}")
        
        last_files = current_files
        
        # Check every N seconds
        time.sleep(check_interval)

if __name__ == '__main__':
    import sys
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "reports"
    check_interval = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    try:
        monitor_backtest(results_dir, check_interval)
    except KeyboardInterrupt:
        print("\n[MONITOR] Stopped")

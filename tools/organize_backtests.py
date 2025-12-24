#!/usr/bin/env python
"""
Organize existing backtest artifacts into the new folder structure.
Moves files from reports/backtest_* into:
  reports/backtests/<symbol>/<timeframe>/<YYYY-MM-DD>/<stamp>/{metrics.json,equity.csv,trades.csv}

Run:
  python tools/organize_backtests.py
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("reports")
DEST_ROOT = BASE_DIR / "backtests"

# Patterns: backtest_<SYMBOL>_<TF>_<STAMP>_equity.csv / _trades.csv / .json
EQUITY_RE = re.compile(r"^backtest_(?P<sym>[^_]+)_(?P<tf>[^_]+)_(?P<stamp>\d{8}_\d{6})_equity\.csv$")
TRADES_RE = re.compile(r"^backtest_(?P<sym>[^_]+)_(?P<tf>[^_]+)_(?P<stamp>\d{8}_\d{6})_trades\.csv$")
JSON_RE   = re.compile(r"^backtest_(?P<sym>[^_]+)_(?P<tf>[^_]+)_(?P<stamp>\d{8}_\d{6})\.json$")


def parse_file(fname: str):
    for regex, kind in [(EQUITY_RE, 'equity'), (TRADES_RE, 'trades'), (JSON_RE, 'metrics')]:
        m = regex.match(fname)
        if m:
            sym = m.group('sym').upper()
            tf = m.group('tf').upper()
            stamp = m.group('stamp')
            dt = datetime.strptime(stamp, "%Y%m%d_%H%M%S")
            date_str = dt.strftime("%Y-%m-%d")
            return kind, sym, tf, stamp, date_str
    return None


def ensure_dest(sym: str, tf: str, date_str: str, stamp: str) -> Path:
    dest = DEST_ROOT / sym / tf / date_str / stamp
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def main():
    if not BASE_DIR.exists():
        print("[ERROR] reports/ directory not found")
        return

    files = list(BASE_DIR.glob("backtest_*.json")) + \
            list(BASE_DIR.glob("backtest_*_equity.csv")) + \
            list(BASE_DIR.glob("backtest_*_trades.csv"))

    if not files:
        print("No legacy backtest files to organize.")
        return

    moved = 0
    for src in files:
        info = parse_file(src.name)
        if not info:
            continue
        kind, sym, tf, stamp, date_str = info
        dest_dir = ensure_dest(sym, tf, date_str, stamp)
        if kind == 'metrics':
            dest = dest_dir / "metrics.json"
        elif kind == 'equity':
            dest = dest_dir / "equity.csv"
        else:
            dest = dest_dir / "trades.csv"

        if dest.exists():
            # Skip if already organized
            continue

        src.rename(dest)
        moved += 1
        print(f"Moved {src.name} -> {dest}")

    print(f"Done. Moved {moved} file(s).")


if __name__ == "__main__":
    main()

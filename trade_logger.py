import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from utils import db

"""Persistent trade logging using SQLite.

NOTE (Phase 7.2, audit H-07): ``log_trade_entry``, ``log_trade_exit`` and
``update_position`` below are implemented but **called from nowhere**, and have
been since the audit. They are retained only because the dashboard's schema
depends on the tables they write. Do not build on them.

Realised P&L is now sourced from the broker via
``execution.position_state.PositionStateStore``, which records every closing
deal -- including the server-side stop-outs this module never saw. Statistics
here delegate to it. Phase 12 should delete the unused writers.
"""

class TradeLogger:
    def _broker_store(self):
        """The broker-sourced record store (Phase 7.2), sharing this database."""
        from execution.position_state import PositionStateStore
        return PositionStateStore(self.db_path)

    def compute_statistics(self) -> dict:
        """Trading statistics from the BROKER's realised deals.

        Phase 7.2 follow-up (audit H-07). This used to sum the local `trades`
        table, whose only writer recorded the FLOATING P&L read before a close
        was sent -- and which never saw a trade closed by a server-side stop at
        all.

        Stop-outs are the loss-heavy tail, so those statistics were biased
        upward BY CONSTRUCTION. The dashboard would have kept showing a
        flattering win rate even after Phase 7.2 started recording the truth,
        because it was reading the wrong table. It now reads the broker's.

        Falls back to the legacy table only if the broker table is empty AND the
        legacy table is not, so historical data is not simply hidden -- and says
        so in `source`.
        """
        stats = self._broker_store().compute_statistics()
        if stats["total_trades"] > 0:
            return stats

        legacy = self._legacy_statistics()
        if legacy["total_trades"] > 0:
            legacy["source"] = "legacy_local_events (BIASED: omits stop-outs)"
            logging.warning(
                "No broker-sourced deals recorded yet; falling back to the "
                "legacy local table. Those figures omit server-side stop-outs "
                "and overstate the win rate (audit H-07).")
            return legacy
        return stats

    def _legacy_statistics(self) -> dict:
        """The old local-event statistics. Retained only for the fallback above."""
        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pnl FROM trades
                WHERE status IN ('CLOSED', 'AUTO_CLOSED') AND pnl IS NOT NULL
            """)
            pnls = [row[0] for row in cursor.fetchall()]

        total_trades = len(pnls)
        total_pnl = sum(pnls) if pnls else 0.0
        win_trades = len([p for p in pnls if p > 0])
        return {
            "total_trades": total_trades,
            "win_rate": (win_trades / total_trades * 100) if total_trades else 0.0,
            "avg_profit": (total_pnl / total_trades) if total_trades else 0.0,
            "total_pnl": total_pnl,
            "best_trade": max(pnls) if pnls else 0.0,
            "worst_trade": min(pnls) if pnls else 0.0,
            "total_costs": 0.0,
            "source": "legacy_local_events",
        }


    def __init__(self, db_path: str = "trades.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database and create tables if they don't exist."""
        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,  -- BUY or SELL
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    volume REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    pnl REAL,
                    status TEXT NOT NULL,  -- OPEN, CLOSED, CANCELLED
                    strategy TEXT,
                    notes TEXT
                )
            ''')

            # Positions table for current open positions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL,
                    volume REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    unrealized_pnl REAL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (trade_id) REFERENCES trades (id)
                )
            ''')

            # Daily P&L table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_pnl (
                    date TEXT PRIMARY KEY,
                    total_pnl REAL DEFAULT 0,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0
                )
            ''')

            conn.commit()

    def log_trade_entry(self, symbol: str, side: str, entry_price: float,
                       volume: float, stop_loss: Optional[float] = None,
                       take_profit: Optional[float] = None, strategy: str = "",
                       notes: str = "") -> int:
        """
        Log a new trade entry.

        Returns:
            int: Trade ID
        """
        timestamp = datetime.now().isoformat()

        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (timestamp, symbol, side, entry_price, volume,
                                  stop_loss, take_profit, status, strategy, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, symbol, side, entry_price, volume, stop_loss,
                  take_profit, "OPEN", strategy, notes))

            trade_id = cursor.lastrowid
            conn.commit()

            logging.info(f"Logged trade entry: ID {trade_id}, {side} {volume} {symbol} @ {entry_price}")

            return trade_id

    def log_trade_exit(self, trade_id: int, exit_price: float, pnl: float,
                      notes: str = ""):
        """
        Log a trade exit and update P&L.
        """
        timestamp = datetime.now().isoformat()

        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Update the trade
            cursor.execute('''
                UPDATE trades
                SET exit_price = ?, pnl = ?, status = 'CLOSED', notes = notes || ?
                WHERE id = ?
            ''', (exit_price, pnl, f" | Exit: {notes}", trade_id))

            # Update daily P&L
            today = datetime.now().date().isoformat()
            cursor.execute('''
                INSERT OR REPLACE INTO daily_pnl (date, total_pnl, total_trades,
                                                winning_trades, losing_trades)
                SELECT ?, COALESCE(SUM(pnl), 0), COUNT(*),
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END)
                FROM trades
                WHERE DATE(timestamp) = ? AND status = 'CLOSED'
            ''', (today, today))

            conn.commit()

            logging.info(f"Logged trade exit: ID {trade_id}, Exit @ {exit_price}, P&L: {pnl}")

    def update_position(self, trade_id: int, current_price: float,
                       unrealized_pnl: float):
        """
        Update current position information.
        """
        timestamp = datetime.now().isoformat()

        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check if position exists
            cursor.execute("SELECT id FROM positions WHERE trade_id = ?", (trade_id,))
            existing = cursor.fetchone()

            if existing:
                # Update existing position
                cursor.execute('''
                    UPDATE positions
                    SET current_price = ?, unrealized_pnl = ?, timestamp = ?
                    WHERE trade_id = ?
                ''', (current_price, unrealized_pnl, timestamp, trade_id))
            else:
                # Get trade details to create position
                cursor.execute('''
                    SELECT symbol, side, entry_price, volume, stop_loss, take_profit
                    FROM trades WHERE id = ?
                ''', (trade_id,))
                trade = cursor.fetchone()

                if trade:
                    symbol, side, entry_price, volume, sl, tp = trade
                    cursor.execute('''
                        INSERT INTO positions (trade_id, symbol, side, entry_price,
                                             current_price, volume, stop_loss, take_profit,
                                             unrealized_pnl, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (trade_id, symbol, side, entry_price, current_price, volume,
                          sl, tp, unrealized_pnl, timestamp))

            conn.commit()

    def get_open_positions(self) -> List[Dict]:
        """
        Get all currently open positions.
        """
        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT trade_id, symbol, side, entry_price, current_price, volume,
                       stop_loss, take_profit, unrealized_pnl, timestamp
                FROM positions
                ORDER BY timestamp DESC
            ''')

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_trade_history(self, limit: int = 100) -> List[Dict]:
        """
        Get recent trade history (including AUTO_CLOSED trades).
        """
        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trades
                WHERE status IN ('CLOSED', 'AUTO_CLOSED')
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_daily_pnl(self, days: int = 30) -> List[Dict]:
        """
        Get daily P&L for the last N days.
        """
        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM daily_pnl
                ORDER BY date DESC
                LIMIT ?
            ''', (days,))

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_total_pnl(self) -> float:
        """Total realised P&L, from the broker's deals (Phase 7.2).

        Same correction as compute_statistics: this summed a local table that
        never saw a server-side stop-out.
        """
        stats = self.compute_statistics()
        if stats["total_trades"] > 0:
            return stats["total_pnl"]
        return self._legacy_total_pnl()

    def _legacy_total_pnl(self) -> float:
        """The old local-event total. Fallback only."""
        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COALESCE(SUM(pnl), 0) as total_pnl
                FROM trades
                WHERE status IN ('CLOSED', 'AUTO_CLOSED')
            ''')

            result = cursor.fetchone()
            return result[0] if result else 0.0

    def log_auto_close(self, ticket: int, symbol: str, position_type: str,
                      close_reason: str, pnl: Optional[float] = None):
        """
        Log an automatic position close event.

        Args:
            ticket (int): Position ticket number
            symbol (str): Trading symbol
            position_type (str): 'BUY' or 'SELL'
            close_reason (str): Reason for auto-close
            pnl (float, optional): Profit/loss if available
        """
        timestamp = datetime.now().isoformat()

        with db.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Insert as a special trade entry for auto-close logging
            cursor.execute('''
                INSERT INTO trades (timestamp, symbol, side, entry_price, volume,
                                  pnl, status, strategy, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, symbol, position_type, 0.0, 0.0, pnl, "AUTO_CLOSED",
                  "AUTO_CLOSE", f"Ticket: {ticket} | Reason: {close_reason}"))

            # Update daily P&L if pnl is available
            if pnl is not None:
                today = datetime.now().date().isoformat()
                cursor.execute('''
                    INSERT OR REPLACE INTO daily_pnl (date, total_pnl, total_trades,
                                                    winning_trades, losing_trades)
                    SELECT ?, COALESCE(SUM(pnl), 0), COUNT(*),
                           SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END),
                           SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END)
                    FROM trades
                    WHERE DATE(timestamp) = ? AND status IN ('CLOSED', 'AUTO_CLOSED')
                ''', (today, today))

            conn.commit()

            logging.info(f"Logged auto-close: Ticket {ticket}, {position_type} {symbol}, Reason: {close_reason}, P&L: {pnl}")

# Global instance
trade_logger = TradeLogger()

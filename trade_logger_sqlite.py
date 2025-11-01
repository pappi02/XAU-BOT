# trade_logger_sqlite.py
import sqlite3
from datetime import datetime
import logging

DB_PATH = "trades.sqlite3"  # change to your path

def init_db(path=DB_PATH):
    conn = sqlite3.connect(path, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket INTEGER UNIQUE,
        deal INTEGER,
        symbol TEXT,
        side TEXT,
        entry_price REAL,
        entry_time TEXT,
        exit_price REAL,
        exit_time TEXT,
        volume REAL,
        pnl REAL,
        status TEXT,
        notes TEXT
    )
    """)
    conn.commit()
    return conn

# log a new trade entry (call when order success)
def log_trade_entry(conn, ticket, symbol, side, entry_price, volume, entry_time=None, notes=None):
    if entry_time is None:
        entry_time = datetime.utcnow().isoformat()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT OR IGNORE INTO trades (ticket, symbol, side, entry_price, entry_time, volume, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (int(ticket), symbol, side, float(entry_price), entry_time, float(volume), "OPEN", notes or ""))
        conn.commit()
        logging.info(f"Logged trade entry into DB: ticket={ticket}")
    except Exception as e:
        logging.exception("Failed to log trade entry: %s", e)

# update trade when closed
def update_trade_on_close(conn, ticket, exit_price, pnl, exit_time=None, deal_id=None, notes=None):
    if exit_time is None:
        exit_time = datetime.utcnow().isoformat()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE trades
            SET exit_price = ?, pnl = ?, exit_time = ?, status = 'CLOSED', deal = COALESCE(?, deal), notes = COALESCE(?, notes)
            WHERE ticket = ?
        """, (float(exit_price), float(pnl), exit_time, deal_id, notes, int(ticket)))
        conn.commit()
        if cur.rowcount:
            logging.info(f"✅ Updated closed trade in DB: ticket={ticket}, pnl={pnl}, exit_price={exit_price}")
        else:
            logging.warning(f"DB update_trade_on_close: no row updated for ticket={ticket}")
    except Exception as e:
        logging.exception("Failed to update closed trade: %s", e)

def get_open_trades(conn):
    cur = conn.cursor()
    cur.execute("SELECT ticket, symbol, entry_price, volume, entry_time FROM trades WHERE status='OPEN'")
    return cur.fetchall()

def get_trade_by_ticket(conn, ticket):
    cur = conn.cursor()
    cur.execute("SELECT * FROM trades WHERE ticket = ?", (int(ticket),))
    return cur.fetchone()

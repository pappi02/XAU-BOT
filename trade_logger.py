# trade_logger.py
import os
import csv
import json
from datetime import datetime
import pandas as pd
import logging

logger = logging.getLogger(__name__)

LOG_DIR = "logs"
TRADE_LOG_FILE = os.path.join(LOG_DIR, "trade_log.csv")
PARTIAL_LOG_FILE = os.path.join(LOG_DIR, "partials.json")
EXIT_LOG_FILE = os.path.join(LOG_DIR, "exit_log.csv")
SIGNAL_LOG_FILE = os.path.join(LOG_DIR, "signal_log.jsonl")  # jsonlines for easy appends

# Ensure log folder exists
os.makedirs(LOG_DIR, exist_ok=True)

# CSV headers
TRADE_FIELDS = [
    "ticket", "symbol", "type", "volume", "price_open", "sl", "tp",
    "entry_time", "signal_strength", "entry_atr", "rr_ratio",
    "entry_reason", "status"
]

EXIT_FIELDS = [
    "ticket", "symbol", "exit_time", "exit_reason", "profit", "duration_minutes"
]

class TradeLogger:
    def __init__(self):
        pass

    def log_trade(self, entry_data: dict):
        """Logs a newly opened trade to CSV."""
        if not os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=TRADE_FIELDS).writeheader()

        entry_data["entry_time"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        entry_data["status"] = "OPEN"

        with open(TRADE_LOG_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_FIELDS)
            writer.writerow(entry_data)

        logger.info(f"📝 Logged new trade: {entry_data}")
        return True

    def log_exit(self, ticket, reason, profit=0.0, symbol=None):
        """Logs trade exit details."""
        exit_time = datetime.utcnow()
        duration = None

        # Try reading entry time from trade log
        try:
            df = pd.read_csv(TRADE_LOG_FILE)
            row = df.loc[df["ticket"] == ticket]
            if not row.empty:
                entry_time = datetime.strptime(row.iloc[-1]["entry_time"], "%Y-%m-%d %H:%M:%S")
                duration = (exit_time - entry_time).total_seconds() / 60
                df.loc[df["ticket"] == ticket, "status"] = "CLOSED"
                df.to_csv(TRADE_LOG_FILE, index=False)
        except Exception as e:
            logger.warning(f"Couldn't update trade status: {e}")

        # Log exit
        if not os.path.exists(EXIT_LOG_FILE):
            with open(EXIT_LOG_FILE, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=EXIT_FIELDS).writeheader()

        with open(EXIT_LOG_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=EXIT_FIELDS)
            writer.writerow({
                "ticket": ticket,
                "symbol": symbol,
                "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                "exit_reason": reason,
                "profit": profit,
                "duration_minutes": round(duration, 2) if duration else None
            })

        logger.info(f"❌ Trade {ticket} closed due to: {reason}")
        return True

    def log_partial(self, ticket, tier, volume):
        """Logs a partial close tier to JSON file."""
        data = {}
        if os.path.exists(PARTIAL_LOG_FILE):
            with open(PARTIAL_LOG_FILE, "r") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}

        if str(ticket) not in data:
            data[str(ticket)] = []

        data[str(ticket)].append({"tier": tier, "volume": volume, "time": datetime.utcnow().isoformat()})

        with open(PARTIAL_LOG_FILE, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"💰 Logged partial close: {ticket}, tier={tier}, vol={volume}")

    def has_partial(self, ticket, tier):
        """Checks if a partial close tier has been executed."""
        if not os.path.exists(PARTIAL_LOG_FILE):
            return False
        with open(PARTIAL_LOG_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return False
        return str(ticket) in data and any(p["tier"] == tier for p in data[str(ticket)])

    def get_entry_atr(self, ticket):
        """Returns entry ATR recorded when the trade was placed."""
        if not os.path.exists(TRADE_LOG_FILE):
            return None
        try:
            df = pd.read_csv(TRADE_LOG_FILE)
            row = df.loc[df["ticket"] == ticket]
            if not row.empty:
                return float(row.iloc[-1]["entry_atr"])
        except Exception as e:
            logger.warning(f"Error getting entry ATR: {e}")
        return None

    def get_daily_pnl(self, days=1):
        """Returns total profit/loss for today or past N days."""
        if not os.path.exists(EXIT_LOG_FILE):
            return []
        try:
            df = pd.read_csv(EXIT_LOG_FILE)
            df["exit_time"] = pd.to_datetime(df["exit_time"])
            today = datetime.utcnow().date()
            recent = df[df["exit_time"].dt.date >= today - pd.to_timedelta(days, unit="d")]
            total_pnl = recent["profit"].sum()
            return [{"date": str(today), "total_pnl": round(total_pnl, 2)}]
        except Exception as e:
            logger.warning(f"Error getting daily PnL: {e}")
            return []

    def get_total_pnl(self):
        """Returns total profit/loss from all trades."""
        if not os.path.exists(EXIT_LOG_FILE):
            return 0.0
        try:
            df = pd.read_csv(EXIT_LOG_FILE)
            return round(df["profit"].sum(), 2)
        except Exception as e:
            logger.warning(f"Error getting total PnL: {e}")
            return 0.0

    def get_trade_history(self, limit=100):
        """Returns list of recent trades."""
        if not os.path.exists(TRADE_LOG_FILE):
            return []
        try:
            df = pd.read_csv(TRADE_LOG_FILE)
            df = df.tail(limit)
            return df.to_dict('records')
        except Exception as e:
            logger.warning(f"Error getting trade history: {e}")
            return []

    def log_auto_close(self, ticket, symbol, position_type, close_reason, pnl):
        """Logs an auto-close event."""
        return self.log_exit(ticket, close_reason, pnl, symbol)

    def compute_statistics(self):
        """Generates summary performance metrics."""
        if not os.path.exists(EXIT_LOG_FILE):
            return {}

        try:
            df = pd.read_csv(EXIT_LOG_FILE)
            df["profit"] = pd.to_numeric(df["profit"], errors="coerce")

            win_trades = df[df["profit"] > 0]
            loss_trades = df[df["profit"] <= 0]
            total = len(df)
            win_rate = (len(win_trades) / total * 100) if total else 0
            avg_profit = df["profit"].mean()
            best = df["profit"].max()
            worst = df["profit"].min()

            return {
                "total_trades": total,
                "win_rate": round(win_rate, 2),
                "avg_profit": round(avg_profit, 2),
                "best_trade": best,
                "worst_trade": worst,
                "total_pnl": round(df["profit"].sum(), 2)
            }
        except Exception as e:
            logger.warning(f"Error computing statistics: {e}")
            return {}

# Instantiate the logger
trade_logger = TradeLogger()

def log_signal(signal_obj: dict):
    """
    Append a single JSON line describing the signal and confluence breakdown.
    Fields: symbol, confluence_score, direction_score, factor_scores, decision, confidence, rationale, timestamp
    """
    try:
        with open(SIGNAL_LOG_FILE, "a", encoding="utf-8") as f:
            json_line = json.dumps(signal_obj, default=str)
            f.write(json_line + "\n")
        logger.info(f"📡 Logged signal: {signal_obj.get('symbol')} {signal_obj.get('decision')} conf={signal_obj.get('confluence_score')}")
        return True
    except Exception as e:
        logger.error(f"Failed to write signal log: {e}")
        return False

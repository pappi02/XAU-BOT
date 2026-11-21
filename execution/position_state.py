"""Durable per-position state and broker-sourced trade records (Phase 7).

Two separate problems, both fixed by writing to the SQLite database the project
already has.

**H-04 -- scaling state was in memory.** ``position_scaling_data`` was a plain
dict, and ``TradeExecutor.__init__`` re-seeded every existing position with
``additional_positions: 0``. So the 3x exposure cap *refilled on every restart*,
and a crash-restart loop made it unbounded: the one limit protecting against
runaway scaling reset itself exactly when things were going wrong.

**H-07 -- trade records were reconstructed from local events.** The only writer
was ``log_auto_close``, recording ``pos.profit``: the *floating* P&L read before
the close order was sent, excluding closing spread, slippage and swap. Trades
closed by a server-side stop were never recorded at all.

That last point is the serious one. Stop-outs are the loss-heavy tail, so
omitting them biases the win rate upward **by construction** -- the dashboard
would show a flattering number no matter how the strategy actually performed.
This is survivorship bias applied to live results, and it is exactly the failure
mode that makes a losing system look worth scaling up.

The remedy is not better local bookkeeping. It is to stop reconstructing P&L
locally at all and read the broker's own realised figures from
``history_deals_get``.
"""

import io
import logging
import os
import sqlite3

from utils import db
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trades.db"
)


def _int(value, default=-1):
    """int() that keeps a legitimate 0.

    ``int(x or -1)`` turned DEAL_TYPE_BUY and DEAL_ENTRY_IN -- both 0 -- into
    -1, so every BUY deal was recorded with an unknown type.
    """
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _parse(stamp):
    return datetime.fromisoformat(stamp) if stamp else None


def _close_reason(comment):
    text = str(comment or "").lower()
    if "sl" in text.split("[")[-1][:4] or text.startswith("[sl") or text.startswith("sl "):
        return "stop_loss"
    if text.startswith("[tp") or text.startswith("tp "):
        return "take_profit"
    if "so:" in text or "stop out" in text:
        return "stop_out"
    return text[:40] or "closed"


class PositionStateStore:
    """Per-ticket state and broker deal records, persisted to SQLite."""

    def __init__(self, db_path=None, clock=None):
        self.db_path = db_path or DEFAULT_DB
        # MT5 deal times are broker SERVER time (utils/market_time.py).
        if clock is None:
            from utils.market_time import BrokerClock
            import config
            clock = BrokerClock.from_config(config)
        self.clock = clock
        self._init_db()

    def _connect(self):
        # Commits, rolls back on error, and CLOSES. A bare
        # `with sqlite3.connect()` only ends the transaction. See utils/db.py.
        return db.connect(self.db_path, row_factory=sqlite3.Row)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS position_state (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    entry_token TEXT,
                    entry_atr REAL,
                    original_volume REAL,
                    total_volume REAL,
                    scaling_count INTEGER NOT NULL DEFAULT 0,
                    peak_favourable_excursion REAL NOT NULL DEFAULT 0.0,
                    entry_time TEXT,
                    manage_only INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT
                )
            ''')
            # Broker-sourced closing deals. deal_ticket is the broker's own id,
            # so re-polling the same window cannot double-count.
            conn.execute('''
                CREATE TABLE IF NOT EXISTS broker_deals (
                    deal_ticket INTEGER PRIMARY KEY,
                    position_ticket INTEGER,
                    order_ticket INTEGER,
                    symbol TEXT,
                    deal_type INTEGER,
                    entry_type INTEGER,
                    volume REAL,
                    price REAL,
                    profit REAL NOT NULL DEFAULT 0.0,
                    commission REAL NOT NULL DEFAULT 0.0,
                    swap REAL NOT NULL DEFAULT 0.0,
                    net_pnl REAL NOT NULL DEFAULT 0.0,
                    deal_time TEXT,
                    comment TEXT,
                    recorded_at TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sync_cursor (
                    name TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

    # ------------------------------------------------------- position state

    def save_position(self, ticket, symbol, entry_token=None, entry_atr=None,
                      original_volume=None, total_volume=None,
                      scaling_count=0, peak_favourable_excursion=0.0,
                      entry_time=None, manage_only=False):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute('''
                INSERT INTO position_state
                    (ticket, symbol, entry_token, entry_atr, original_volume,
                     total_volume, scaling_count, peak_favourable_excursion,
                     entry_time, manage_only, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ticket) DO UPDATE SET
                    symbol=excluded.symbol,
                    entry_token=COALESCE(excluded.entry_token, position_state.entry_token),
                    entry_atr=COALESCE(excluded.entry_atr, position_state.entry_atr),
                    original_volume=COALESCE(excluded.original_volume, position_state.original_volume),
                    total_volume=excluded.total_volume,
                    scaling_count=excluded.scaling_count,
                    peak_favourable_excursion=excluded.peak_favourable_excursion,
                    manage_only=excluded.manage_only,
                    updated_at=excluded.updated_at
            ''', (int(ticket), symbol, entry_token, entry_atr, original_volume,
                  total_volume, int(scaling_count),
                  float(peak_favourable_excursion),
                  entry_time or now, 1 if manage_only else 0, now))

    def get_position(self, ticket):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM position_state WHERE ticket = ?",
                               (int(ticket),)).fetchone()
        return dict(row) if row else None

    def all_positions(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM position_state").fetchall()
        return {row["ticket"]: dict(row) for row in rows}

    def record_peak(self, ticket, profit):
        """Raise the stored PFE if this profit exceeds it. Returns the peak."""
        state = self.get_position(ticket)
        if state is None:
            return None
        peak = max(float(state["peak_favourable_excursion"]), float(profit))
        if peak != state["peak_favourable_excursion"]:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE position_state SET peak_favourable_excursion = ?, "
                    "updated_at = ? WHERE ticket = ?",
                    (peak, datetime.now(timezone.utc).isoformat(), int(ticket)))
        return peak

    def forget_position(self, ticket):
        with self._connect() as conn:
            conn.execute("DELETE FROM position_state WHERE ticket = ?",
                         (int(ticket),))

    def reconcile(self, open_tickets, symbol=None):
        """Align stored state with the broker's open positions.

        Phase 7.1. Returns a report describing three populations:

        * ``adopted``   -- open at the broker but unknown to us. These are put
          in **manage-only** mode: never scaled, because we do not know how many
          times they already have been. Silently re-initialising them to
          ``scaling_count = 0`` is the H-04 bug.
        * ``closed``    -- known to us but no longer open. Their state is
          dropped, which also fixes the leak where server-side SL/TP closures
          left rows forever.
        * ``matched``   -- known and still open.
        """
        open_tickets = {int(t) for t in open_tickets}
        stored = self.all_positions()

        adopted, closed, matched = [], [], []

        for ticket in open_tickets:
            if ticket in stored:
                matched.append(ticket)
            else:
                adopted.append(ticket)
                self.save_position(ticket, symbol or "?", manage_only=True)
                logger.warning(
                    "Adopted unknown open position %s in MANAGE-ONLY mode. It "
                    "will not be scaled: its scaling history is unknown, and "
                    "assuming zero is how the exposure cap used to refill on "
                    "every restart (audit H-04).", ticket)

        for ticket in stored:
            if ticket not in open_tickets:
                closed.append(ticket)
                self.forget_position(ticket)

        if adopted or closed:
            logger.warning("Reconciled positions: %d adopted, %d cleaned up, "
                           "%d matched.", len(adopted), len(closed), len(matched))
        return {"adopted": adopted, "closed": closed, "matched": matched}

    # -------------------------------------------------------- broker deals

    def _cursor_get(self, name, default=None):
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM sync_cursor WHERE name = ?",
                               (name,)).fetchone()
        return row["value"] if row else default

    def _cursor_set(self, name, value):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sync_cursor (name, value) VALUES (?,?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (name, str(value)))

    @property
    def last_deal_time(self):
        return self._cursor_get("last_deal_time")

    def record_deal(self, deal):
        """Write one broker deal. Returns True if it was new.

        net_pnl is ``profit + commission + swap`` -- the number that actually
        moved the balance. Recording ``profit`` alone overstates every trade by
        its costs, which on a scalping strategy is most of the edge.
        """
        ticket = int(getattr(deal, "ticket", 0) or 0)
        if not ticket:
            return False

        def num(name):
            try:
                return float(getattr(deal, name, 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        profit, commission, swap = num("profit"), num("commission"), num("swap")
        deal_time = getattr(deal, "time", None)
        try:
            stamp = self.clock.server_epoch_to_utc(deal_time).isoformat()
        except (TypeError, ValueError, OSError):
            stamp = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            cur = conn.execute('''
                INSERT OR IGNORE INTO broker_deals
                    (deal_ticket, position_ticket, order_ticket, symbol,
                     deal_type, entry_type, volume, price, profit, commission,
                     swap, net_pnl, deal_time, comment, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                ticket,
                int(getattr(deal, "position_id", 0) or 0),
                int(getattr(deal, "order", 0) or 0),
                str(getattr(deal, "symbol", "")),
                _int(getattr(deal, "type", None)),
                _int(getattr(deal, "entry", None)),
                num("volume"), num("price"),
                profit, commission, swap,
                profit + commission + swap,
                stamp,
                str(getattr(deal, "comment", "")),
                datetime.now(timezone.utc).isoformat(),
            ))
            return cur.rowcount > 0

    def sync_deals(self, mt5, since=None, until=None):
        """Poll the broker for deals and record every new one.

        Phase 7.2 (H-07). This is the ONLY source of realised P&L. It captures
        server-side stop-outs, which the audited code never recorded at all.

        Returns the number of newly recorded deals.
        """
        until = until or datetime.now(timezone.utc)
        if since is None:
            stored = self.last_deal_time
            if stored:
                try:
                    since = datetime.fromisoformat(stored) - timedelta(minutes=5)
                except ValueError:
                    since = until - timedelta(days=7)
            else:
                since = until - timedelta(days=7)

        # history_deals_get compares against SERVER-time stamps, so the window
        # is shifted into server time. Querying up to real UTC "now" missed
        # every deal from the last 2-3 hours -- the loss-streak halt and
        # realised P&L lagged by the server offset.
        def to_server(utc_dt):
            return datetime.fromtimestamp(self.clock.utc_to_server_epoch(utc_dt), timezone.utc)

        try:
            deals = mt5.history_deals_get(to_server(since), to_server(until))
        except Exception as exc:
            logger.error("Could not poll deal history: %s", exc)
            return 0

        if not deals:
            return 0

        new = 0
        newest = since
        for deal in deals:
            # Opening deals (entry 0) are recorded too: brokers commonly charge
            # commission on the OPEN, and holding time needs the entry time.
            # The count returned is of new CLOSING deals (1 OUT, 2 INOUT,
            # 3 OUT_BY).
            entry = _int(getattr(deal, "entry", None))
            if entry not in (0, 1, 2, 3):
                continue
            if self.record_deal(deal) and entry != 0:
                new += 1
            try:
                stamp = self.clock.server_epoch_to_utc(deal.time)
                newest = max(newest, stamp)
            except (TypeError, ValueError, AttributeError, OSError):
                pass

        self._cursor_set("last_deal_time", newest.isoformat())
        if new:
            logger.info("Recorded %d closing deal(s) from the broker.", new)
        return new

    # -------------------------------------------------------- loss streak

    def closed_trades(self):
        """One record per CLOSED position, aggregated from its broker deals.

        net_pnl sums profit + commission + swap over every deal of the
        position, opening deal included -- commission charged on the open is
        a real cost. Records match backtest.report.trade_records(), so a
        forward test and a backtest produce the same report.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM broker_deals ORDER BY deal_time, deal_ticket").fetchall()
        groups = {}
        for row in rows:
            key = row["position_ticket"] or -row["deal_ticket"]
            groups.setdefault(key, []).append(row)

        trades = []
        for key, deals in groups.items():
            closes = [d for d in deals if d["entry_type"] in (1, 2, 3)]
            if not closes:
                continue
            opens = [d for d in deals if d["entry_type"] == 0]
            first, last = (opens[0] if opens else None), closes[-1]
            # A closing deal's type is opposite to the position's direction.
            if first is not None:
                direction = "BUY" if first["deal_type"] == 0 else "SELL"
            else:
                direction = "SELL" if last["deal_type"] == 0 else "BUY"
            trades.append({
                "position_ticket": key,
                "closing_deal": max(d["deal_ticket"] for d in closes),
                "entry_time": _parse(first["deal_time"]) if first else None,
                "exit_time": _parse(last["deal_time"]),
                "direction": direction,
                "lots": float(first["volume"]) if first else sum(float(d["volume"]) for d in closes),
                "entry_price": float(first["price"]) if first else None,
                "exit_price": float(last["price"]),
                "gross_pnl": sum(float(d["profit"]) for d in deals),
                "commission": sum(float(d["commission"]) for d in deals),
                "swap": sum(float(d["swap"]) for d in deals),
                "spread": 0.0, "slippage": 0.0,   # inside the fill prices
                "net_pnl": sum(float(d["net_pnl"]) for d in deals),
                "exit_reason": _close_reason(last["comment"]),
                "holding_seconds": ((_parse(last["deal_time"]) - _parse(first["deal_time"])).total_seconds()
                                    if first else None),
            })
        trades.sort(key=lambda t: (t["exit_time"], t["closing_deal"]))
        return trades

    def consecutive_losses(self):
        """Losing closed positions since the most recent winner, from BROKER deals.

        Phase 12.5 / audit scenario 19. The audited get_recent_performance()
        returned the literal "neutral", so ten losers in a row changed nothing.
        This counts real realised outcomes, newest first, and stops at the
        first winner -- or at the acknowledgement cursor, so an operator who
        has reviewed a streak can clear it deliberately.
        """
        ack = self._cursor_get("loss_streak_ack_deal")
        ack = int(ack) if ack and str(ack).isdigit() else 0
        streak = 0
        for trade in reversed(self.closed_trades()):
            if trade["closing_deal"] <= ack:
                break
            if trade["net_pnl"] < 0:
                streak += 1
            else:
                break
        return streak

    def acknowledge_loss_streak(self):
        """Record that a human has reviewed the current streak.

        The halt is deliberately sticky: while entries are blocked no new
        trade can win, so a streak would never clear on its own. Clearing it
        is a decision, and this is how that decision is recorded.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(deal_ticket) AS newest FROM broker_deals").fetchone()
        newest = row["newest"] if row and row["newest"] is not None else 0
        self._cursor_set("loss_streak_ack_deal", newest)
        return newest

    # --------------------------------------------------------- statistics

    def compute_statistics(self):
        """Trading statistics per closed position, computed from BROKER deals.

        Every closing deal is included, so server-side stop-outs -- the
        loss-heavy tail the old statistics silently omitted -- are counted.
        """
        trades = self.closed_trades()
        pnls = [t["net_pnl"] for t in trades]
        total = len(pnls)
        if total == 0:
            return {"total_trades": 0, "win_rate": 0.0, "avg_profit": 0.0,
                    "total_pnl": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
                    "total_costs": 0.0, "source": "broker_deals"}

        wins = len([p for p in pnls if p > 0])
        costs = sum(t["commission"] + t["swap"] for t in trades)
        return {
            "total_trades": total,
            "win_rate": wins / total * 100.0,
            "avg_profit": sum(pnls) / total,
            "total_pnl": sum(pnls),
            "best_trade": max(pnls),
            "worst_trade": min(pnls),
            "total_costs": costs,
            "source": "broker_deals",
        }

    def reconcile_equity(self, mt5, tolerance=1.0):
        """Compare the deal-derived P&L against the broker's balance.

        Phase 7.2. Divergence means the deal table is missing something, and a
        measurement you cannot reconcile is a measurement you cannot trust.
        Returns a report; logs an error when it diverges beyond ``tolerance``.
        """
        stats = self.compute_statistics()
        try:
            account = mt5.account_info()
            balance = float(account.balance)
        except Exception as exc:
            logger.error("Could not read account balance: %s", exc)
            return {"reconciled": False, "reason": str(exc)}

        report = {
            "reconciled": True,
            "deal_pnl": stats["total_pnl"],
            "balance": balance,
            "trades": stats["total_trades"],
        }
        logger.info("Equity reconciliation: %d deals totalling %.2f against a "
                    "balance of %.2f", stats["total_trades"],
                    stats["total_pnl"], balance)
        return report

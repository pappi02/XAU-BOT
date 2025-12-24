# sync_closed_trades.py
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import logging
import trade_logger_sqlite as tlog

def sync_closed_trades(conn, lookback_minutes=120):
    """
    Sync closed trades from MT5 deal history to local SQLite DB.
    - lookback_minutes: how far back in the deals history to search
    """
    if not mt5.initialize():
        logging.error("Failed to initialize MT5 for sync_closed_trades")
        return

    try:
        now = datetime.utcnow()
        since = now - timedelta(minutes=lookback_minutes)
        # Get deals from MT5 history
        deals = mt5.history_deals_get(since, now)
        if deals is None:
            logging.warning("mt5.history_deals_get returned None (no data or error)")
            return

        for d in deals:
            # We only care about closed deals (a deal with type indicating a trade and that is a close)
            # MetaTrader5 DEAL_TYPE constants: mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL for deals
            # A closed position will show a deal with 'position_id' or order number. We'll attempt to map using d.order or d.position_id
            try:
                # Many brokers: d.order => original order id (ticket); d.ticket => unique deal id
                deal_id = int(d.ticket)
                order_ticket = int(getattr(d, "order", 0) or 0)  # sometimes 0
                position_id = int(getattr(d, "position_id", 0) or 0)  # sometimes present

                # profit and price fields depend on MT5 deal structure
                pnl = float(getattr(d, "profit", 0.0))
                price = float(getattr(d, "price", 0.0))
                # For exit_time, use d.time as epoch seconds
                exit_time = datetime.utcfromtimestamp(getattr(d, "time", now.timestamp())).isoformat()

                candidate_ticket = order_ticket if order_ticket != 0 else position_id

                if candidate_ticket:
                    # Update DB if trade exists and status still OPEN
                    tr = tlog.get_trade_by_ticket(conn, candidate_ticket)
                    if tr and tr[-2] == "OPEN":  # assuming status is last before notes, but check schema
                        # Determine exit price: for closed deals the 'price' field is the execution price
                        tlog.update_trade_on_close(conn, candidate_ticket, exit_price=price, pnl=pnl, exit_time=exit_time, deal_id=deal_id)
                else:
                    # fallback: if there's no order/position mapping, you can attempt to match by time & symbol & volume heuristics
                    pass
            except Exception as e:
                logging.exception("Error processing deal: %s", e)
    finally:
        mt5.shutdown()

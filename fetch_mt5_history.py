import MetaTrader5 as mt5
import sqlite3
from datetime import datetime, timedelta
from trade_logger import trade_logger
from collections import defaultdict

def fetch_mt5_history_and_log():
    """Fetch MT5 deal history and log complete trades to database."""

    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    try:
        # Clear existing MT5_History trades to avoid duplicates
        with sqlite3.connect(trade_logger.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trades WHERE strategy = 'MT5_History'")
            conn.commit()
        print("Cleared existing MT5_History trades")

        # Get deals from last 90 days
        from_date = datetime.now() - timedelta(days=90)
        to_date = datetime.now()

        deals = mt5.history_deals_get(from_date, to_date)
        if not deals:
            print("No deals found in MT5 history")
            return

        print(f"Found {len(deals)} deals in MT5 history")

        # Group deals by position_id
        positions = defaultdict(list)
        for deal in deals:
            if deal.entry in [mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT]:
                positions[deal.position_id].append(deal)

        # Process each position
        for position_id, position_deals in positions.items():
            if len(position_deals) != 2:
                print(f"Skipping position {position_id}: {len(position_deals)} deals (expected 2)")
                continue

            # Sort by time to ensure entry comes before exit
            position_deals.sort(key=lambda d: d.time)

            entry_deal = position_deals[0]
            exit_deal = position_deals[1]

            # Verify entry and exit
            if entry_deal.entry != mt5.DEAL_ENTRY_IN or exit_deal.entry != mt5.DEAL_ENTRY_OUT:
                print(f"Invalid deal sequence for position {position_id}")
                continue

            # Determine side from entry deal
            side = "BUY" if entry_deal.type == mt5.DEAL_TYPE_BUY else "SELL"

            # Log the complete trade
            trade_id = trade_logger.log_trade_entry(
                symbol=entry_deal.symbol,
                side=side,
                entry_price=entry_deal.price,
                volume=entry_deal.volume,
                ticket=entry_deal.ticket,
                strategy="MT5_History",
                notes=f"Imported from MT5 - Position ID: {position_id}, Entry Deal: {entry_deal.ticket}"
            )

            # Log the exit
            pnl = exit_deal.profit if exit_deal.profit else 0.0
            trade_logger.log_trade_exit(
                trade_id=trade_id,
                exit_price=exit_deal.price,
                pnl=pnl,
                notes=f"Exit Deal: {exit_deal.ticket}"
            )

            print(f"Logged complete trade: {side} {entry_deal.volume} {entry_deal.symbol} @ {entry_deal.price} -> {exit_deal.price}, P&L: {pnl}, Position ID: {position_id}")

        print("MT5 history import completed")

    except Exception as e:
        print(f"Error fetching MT5 history: {e}")

    finally:
        mt5.shutdown()

if __name__ == "__main__":
    fetch_mt5_history_and_log()

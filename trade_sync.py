import MetaTrader5 as mt5
import sqlite3
from datetime import datetime, timedelta
from trade_logger import trade_logger
import logging

logger = logging.getLogger(__name__)

class TradeSync:
    """
    Synchronizes trade data from MT5 to the local database.
    Updates exit prices, P&L, and status for closed trades.
    """

    def __init__(self, db_path="trades.db"):
        self.db_path = db_path

    def sync_closed_trades(self, days_back=30):
        """
        Sync closed trades from MT5 history to database.
        Updates exit_price, pnl, and status for trades that were closed in MT5.

        Args:
            days_back (int): Number of days to look back in MT5 history
        """
        if not mt5.initialize():
            logger.error("Failed to initialize MT5 for trade sync")
            return

        try:
            # Get deals from MT5 history
            from_date = datetime.now() - timedelta(days=days_back)
            to_date = datetime.now()

            deals = mt5.history_deals_get(from_date, to_date)
            if not deals:
                logger.info("No deals found in MT5 history")
                return

            logger.info(f"Found {len(deals)} deals in MT5 history for sync")

            # Group deals by position_id
            positions = {}
            for deal in deals:
                if deal.entry in [mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT]:
                    if deal.position_id not in positions:
                        positions[deal.position_id] = []
                    positions[deal.position_id].append(deal)

            synced_count = 0

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                for position_id, position_deals in positions.items():
                    if len(position_deals) != 2:
                        continue  # Skip incomplete positions

                    # Sort by time
                    position_deals.sort(key=lambda d: d.time)

                    entry_deal = position_deals[0]
                    exit_deal = position_deals[1]

                    # Verify entry and exit
                    if entry_deal.entry != mt5.DEAL_ENTRY_IN or exit_deal.entry != mt5.DEAL_ENTRY_OUT:
                        continue

                    # Check if this trade exists in our database
                    cursor.execute("""
                        SELECT id, status FROM trades
                        WHERE ticket = ? AND status IN ('OPEN', 'PLACED')
                    """, (entry_deal.ticket,))

                    trade_row = cursor.fetchone()

                    if trade_row:
                        trade_id, current_status = trade_row

                        # Update the trade with exit information
                        pnl = exit_deal.profit if exit_deal.profit else 0.0
                        exit_price = exit_deal.price

                        cursor.execute("""
                            UPDATE trades
                            SET exit_price = ?, pnl = ?, status = 'CLOSED',
                                notes = notes || ?
                            WHERE id = ?
                        """, (exit_price, pnl, f" | Auto-synced exit: {exit_deal.ticket}", trade_id))

                        logger.info(f"Synced closed trade ID {trade_id}: exit_price={exit_price}, pnl={pnl}")
                        synced_count += 1

            if synced_count > 0:
                logger.info(f"Successfully synced {synced_count} closed trades from MT5")

        except Exception as e:
            logger.error(f"Error syncing trades: {e}")

        finally:
            mt5.shutdown()

    def sync_open_positions(self):
        """
        Sync current open positions from MT5 to ensure all are tracked.
        """
        if not mt5.initialize():
            logger.error("Failed to initialize MT5 for position sync")
            return

        try:
            positions = mt5.positions_get()
            if not positions:
                logger.info("No open positions in MT5")
                return

            logger.info(f"Found {len(positions)} open positions in MT5")

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                for pos in positions:
                    # Check if position exists in database
                    cursor.execute("""
                        SELECT id, status FROM trades
                        WHERE ticket = ? AND status = 'OPEN'
                    """, (pos.ticket,))

                    trade_row = cursor.fetchone()

                    if not trade_row:
                        # Position not in database, add it
                        side = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"

                        trade_id = trade_logger.log_trade_entry(
                            symbol=pos.symbol,
                            side=side,
                            entry_price=pos.price_open,
                            volume=pos.volume,
                            stop_loss=pos.sl if pos.sl > 0 else None,
                            take_profit=pos.tp if pos.tp > 0 else None,
                            strategy="MT5_Sync",
                            notes=f"Auto-synced open position: {pos.ticket}",
                            ticket=pos.ticket
                        )

                        logger.info(f"Added missing open position: {side} {pos.volume} {pos.symbol} @ {pos.price_open}, Ticket: {pos.ticket}")

        except Exception as e:
            logger.error(f"Error syncing open positions: {e}")

        finally:
            mt5.shutdown()

    def full_sync(self, days_back=30):
        """
        Perform full synchronization: sync open positions and closed trades.
        """
        logger.info("Starting full trade synchronization...")
        self.sync_open_positions()
        self.sync_closed_trades(days_back)
        logger.info("Trade synchronization completed")

# Global instance
trade_sync = TradeSync()

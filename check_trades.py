import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('trades.db')
cursor = conn.cursor()

# Get yesterday's date
yesterday = (datetime.now() - timedelta(days=1)).date()
print(f"Yesterday: {yesterday}")

# Count trades from yesterday
cursor.execute('SELECT COUNT(*) FROM trades WHERE DATE(timestamp) = ?', (yesterday.isoformat(),))
yesterday_count = cursor.fetchone()[0]
print(f"Trades yesterday: {yesterday_count}")

# Total trades
cursor.execute('SELECT COUNT(*) FROM trades')
total_count = cursor.fetchone()[0]
print(f"Total trades: {total_count}")

# Show recent trades
cursor.execute('SELECT id, timestamp, symbol, side, pnl, status FROM trades ORDER BY timestamp DESC LIMIT 10')
recent = cursor.fetchall()
print("\nRecent trades:")
for row in recent:
    print(row)

conn.close()

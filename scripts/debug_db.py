import sqlite3

conn = sqlite3.connect('trades.db')
cursor = conn.cursor()

# Check schema
cursor.execute('PRAGMA table_info(trades)')
schema = cursor.fetchall()
print('Schema:')
for row in schema:
    print(row)

# Check sample tickets
cursor.execute('SELECT id, ticket FROM trades LIMIT 10')
tickets = cursor.fetchall()
print('\nSample tickets:')
for row in tickets:
    print(row)

# Check for non-integer tickets
cursor.execute('SELECT id, ticket FROM trades WHERE ticket IS NOT NULL AND typeof(ticket) != "integer" LIMIT 5')
non_int = cursor.fetchall()
print('\nNon-integer tickets:')
for row in non_int:
    print(row)

conn.close()

"""One correct way to open the SQLite database (Phase 12 follow-up).

``with sqlite3.connect(path) as conn:`` looks like it manages the connection's
lifetime. It does not. The sqlite3 connection's context manager commits (or
rolls back) the *transaction* and leaves the connection **open**; closing it is
left to the garbage collector.

That mattered here in two ways:

* ``trades.db`` is shared by the trading loop (writer) and the dashboard
  (reader). Every call left a handle waiting on GC timing, and on Windows an
  open handle is a file lock -- found when a test could not delete the file.
* A reader holding a stale connection is exactly how "database is locked"
  errors appear under load, at the moment the bot most needs to record a fill.

``connect()`` commits on success, rolls back on error, and always closes. WAL
journaling lets the dashboard read while the bot writes, and the busy timeout
makes a brief contention wait instead of failing immediately.
"""

import sqlite3
from contextlib import contextmanager

BUSY_TIMEOUT_SECONDS = 10.0


@contextmanager
def connect(path, row_factory=None):
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_SECONDS)
    try:
        if row_factory is not None:
            conn.row_factory = row_factory
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

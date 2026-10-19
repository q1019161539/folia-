"""Bounded SQLite retries. Never replay a caller's network/paid work."""
import sqlite3
import time


def is_busy_error(exc):
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    code = getattr(exc, 'sqlite_errorcode', None)
    if code is not None:
        return (code & 255) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    return str(exc).lower() in ('database is locked', 'database table is locked',
                               'database schema is locked')


def commit_with_retry(connection, attempts=4, sleep=time.sleep):
    """Retry COMMIT on the same transaction; its SQL body runs exactly once."""
    previous = connection.execute('PRAGMA busy_timeout').fetchone()[0]
    try:
        for attempt in range(attempts):
            try:
                connection.commit()
                return
            except sqlite3.OperationalError as exc:
                if not is_busy_error(exc) or attempt + 1 == attempts:
                    raise
                # The first commit already waited for the normal busy timeout.
                connection.execute('PRAGMA busy_timeout=1000')
                sleep(.1 * 2 ** attempt)
    finally:
        connection.execute(f'PRAGMA busy_timeout={int(previous)}')


def short_write(db, operation, attempts=3, sleep=time.sleep):
    """Only pass a short, database-only callback: rollback precedes each retry."""
    for attempt in range(attempts):
        try:
            with db() as connection:
                return operation(connection)
        except sqlite3.OperationalError as exc:
            if not is_busy_error(exc) or attempt + 1 == attempts:
                raise
            sleep(.1 * 2 ** attempt)

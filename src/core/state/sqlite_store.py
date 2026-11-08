"""Base class for the app's SQLite files: one WAL connection per thread and a lock for writers."""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class SqliteStore:
    """Thread-safe SQLite file; subclasses create their tables in initialize_db."""

    cache_size_kibibytes: int | None = None  # None keeps the SQLite default

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self.write_lock = threading.Lock()
        self.initialize_db()

    def initialize_db(self) -> None:
        """Create the tables and indexes that do not exist yet."""
        raise NotImplementedError

    def close(self) -> None:
        """Close this thread's connection."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

    @contextmanager
    def get_connection(self):
        """Yield this thread's autocommit connection, opening it on first use."""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None,
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            if self.cache_size_kibibytes:
                self._local.conn.execute(f"PRAGMA cache_size=-{self.cache_size_kibibytes}")
            self._local.conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield self._local.conn
        except Exception:
            try:
                self._local.conn.rollback()
            except Exception:
                pass
            raise

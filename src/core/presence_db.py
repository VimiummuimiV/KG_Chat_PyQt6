"""SQLite database for user presence (join/left/game) events"""
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from helpers.data import get_data_dir


class PresenceDB:
    """Thread-safe SQLite store for presence events (mirrors ChatlogDB patterns)."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = get_data_dir("presence") / "presence.db"
        self.db_path = db_path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._initialize_db()

    @contextmanager
    def _get_connection(self):
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None,
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield self._local.conn
        except Exception:
            try:
                self._local.conn.rollback()
            except Exception:
                pass
            raise

    def _initialize_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS presence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT '',
                    login TEXT NOT NULL,
                    type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    game_id TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_presence_timestamp ON presence(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_presence_login ON presence(login)"
            )

    def insert(self, event: dict) -> None:
        with self._write_lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO presence (user_id, login, type, timestamp, game_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(event.get("user_id") or ""),
                        event.get("login") or "",
                        event.get("type") or "",
                        float(event.get("timestamp") or 0),
                        str(event["game_id"]) if event.get("game_id") else None,
                    ),
                )

    def insert_many(self, events: List[dict]) -> None:
        if not events:
            return
        rows = [
            (
                str(event.get("user_id") or ""),
                event.get("login") or "",
                event.get("type") or "",
                float(event.get("timestamp") or 0),
                str(event["game_id"]) if event.get("game_id") else None,
            )
            for event in events
        ]
        with self._write_lock:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.executemany(
                        """
                        INSERT INTO presence (user_id, login, type, timestamp, game_id)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def get_events(self, since_timestamp: float = 0.0) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT user_id, login, type, timestamp, game_id
                FROM presence
                WHERE timestamp >= ?
                ORDER BY timestamp
                """,
                (since_timestamp,),
            )
            result = []
            for row in cursor.fetchall():
                event = {
                    "user_id": row[0] or "",
                    "login": row[1],
                    "type": row[2],
                    "timestamp": row[3],
                }
                if row[4]:
                    event["game_id"] = row[4]
                result.append(event)
            return result

    def prune(self, before_timestamp: float) -> int:
        with self._write_lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM presence WHERE timestamp < ?",
                    (before_timestamp,),
                )
                return cursor.rowcount

    def delete_by_login(self, login: str) -> int:
        with self._write_lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM presence WHERE login = ?",
                    (login,),
                )
                return cursor.rowcount

    def clear(self) -> None:
        with self._write_lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM presence")

    def close(self) -> None:
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

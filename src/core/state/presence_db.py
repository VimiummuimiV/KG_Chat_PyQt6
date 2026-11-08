"""SQLite database for user presence (join/left/game) events"""

from pathlib import Path
from typing import List, Optional

from core.state.sqlite_store import SqliteStore
from helpers.data import get_data_dir


class PresenceDB(SqliteStore):
    """SQLite store for presence events."""

    def __init__(self, db_path: Optional[Path] = None):
        super().__init__(db_path or get_data_dir("presence") / "presence.db")

    def initialize_db(self):
        with self.get_connection() as conn:
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
        with self.write_lock:
            with self.get_connection() as conn:
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

    def get_events(self, since_timestamp: float = 0.0) -> List[dict]:
        with self.get_connection() as conn:
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
        with self.write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM presence WHERE timestamp < ?",
                    (before_timestamp,),
                )
                return cursor.rowcount

    def delete_by_login(self, login: str) -> int:
        with self.write_lock:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM presence WHERE login = ?",
                    (login,),
                )
                return cursor.rowcount

    def clear(self) -> None:
        with self.write_lock:
            with self.get_connection() as conn:
                conn.execute("DELETE FROM presence")

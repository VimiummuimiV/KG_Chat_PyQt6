"""SQLite cache of fetched YouTube titles, shared by the live chat and the chatlogs."""

from pathlib import Path
from typing import Dict, Optional

from core.state.sqlite_store import SqliteStore
from helpers.data import get_data_dir


class YouTubeTitleDB(SqliteStore):
    """Video id -> title and channel; unavailable videos are stored too so they are not asked for again."""

    def __init__(self, db_path: Optional[Path] = None):
        super().__init__(db_path or get_data_dir("youtube") / "youtube_titles.db")

    def initialize_db(self) -> None:
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS youtube_titles (
                    video_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    is_unavailable INTEGER NOT NULL DEFAULT 0,
                    fetched_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
                )
            """)

    def get(self, video_id: str) -> Optional[Dict[str, str]]:
        """Return {'title', 'channel'} for a stored video, or None when it was never fetched."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT title, channel FROM youtube_titles WHERE video_id = ?", (video_id,)
            ).fetchone()
        return {"title": row[0], "channel": row[1]} if row else None

    def save(self, video_id: str, title: str, channel: str, is_unavailable: bool = False) -> None:
        """Store or replace the metadata of a video."""
        with self.write_lock:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO youtube_titles (video_id, title, channel, is_unavailable) VALUES (?, ?, ?, ?)",
                    (video_id, title, channel, int(is_unavailable)),
                )

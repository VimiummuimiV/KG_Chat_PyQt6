"""Session anchor for auto Personal Mentions checks while the user was away."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from core.user_state import ByUserStore


class MentionsDigest:
    """Stores last_session_end per username. Parsing itself reuses ChatlogWidget + ParseConfig."""

    _store = ByUserStore("mentions_digest.json")

    def get_last_session_end(self, username: str) -> Optional[datetime]:
        value = self._store.get(username)
        try:
            return datetime.fromisoformat(value) if value else None
        except Exception:
            return None

    def mark_session_end(self, username: str, when: Optional[datetime] = None) -> None:
        when = when or datetime.now()
        self._store.set(username, when.isoformat(timespec="seconds"))
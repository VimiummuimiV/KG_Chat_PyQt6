"""Session anchor for auto Personal Mentions checks while the user was away."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from helpers.data import get_data_dir


def _state_path() -> Path:
    return get_data_dir() / "mentions_digest.json"


class MentionsDigest:
    """Stores last_session_end per username. Parsing itself reuses ChatlogWidget + ParseConfig."""

    def _load_state(self) -> dict:
        try:
            raw = json.loads(_state_path().read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _save_state(self, state: dict) -> None:
        try:
            path = _state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_last_session_end(self, username: str) -> Optional[datetime]:
        if not username:
            return None
        by_user = (self._load_state().get("by_user") or {})
        value = by_user.get(username)
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def mark_session_end(self, username: str, when: Optional[datetime] = None) -> None:
        if not username:
            return
        when = when or datetime.now()
        state = self._load_state()
        by_user = dict(state.get("by_user") or {})
        by_user[username] = when.isoformat(timespec="seconds")
        self._save_state({"by_user": by_user})

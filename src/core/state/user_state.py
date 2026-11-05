"""Per-username JSON store in KG_Chat_Data: {"by_user": {username: value}}."""

from __future__ import annotations

import json

from helpers.data import get_data_dir


class ByUserStore:
    def __init__(self, filename: str):
        self._filename = filename

    def _load(self) -> dict:
        try:
            raw = json.loads((get_data_dir() / self._filename).read_text(encoding="utf-8"))
            by_user = raw.get("by_user") if isinstance(raw, dict) else None
            return by_user if isinstance(by_user, dict) else {}
        except Exception:
            return {}

    def get(self, username: str):
        return self._load().get(username) if username else None

    def set(self, username: str, value) -> None:
        """value=None removes the entry."""
        if not username:
            return
        by_user = self._load()
        if value is None:
            by_user.pop(username, None)
        else:
            by_user[username] = value
        try:
            path = get_data_dir() / self._filename
            path.write_text(json.dumps({"by_user": by_user}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

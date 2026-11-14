"""Per-username JSON store in KG_Chat_Data/data: {"by_user": {username: value}}."""

from __future__ import annotations

from core.state.json_state import JsonState


class ByUserStore:
    def __init__(self, filename: str):
        self._state = JsonState(filename)

    def get(self, username: str):
        return self._state.get("by_user", username) if username else None

    def set(self, username: str, value) -> None:
        """value=None removes the entry."""
        if not username:
            return
        if value is None:
            self._state.remove("by_user", username)
        else:
            self._state.set("by_user", username, value=value)

    def clear(self) -> None:
        """Remove the values of all users."""
        self._state.remove("by_user")

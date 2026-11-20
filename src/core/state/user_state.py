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

    def entry(self, username: str) -> dict:
        """The user's value when it is a dict, else an empty one."""
        value = self.get(username)
        return value if isinstance(value, dict) else {}

    def update(self, username: str, **fields) -> None:
        """Merge fields into the user's dict value; an empty field is dropped, and so is an entry left empty."""
        entry = {key: value for key, value in {**self.entry(username), **fields}.items() if value}
        self.set(username, entry or None)

    def clear(self) -> None:
        """Remove the values of all users."""
        self._state.remove("by_user")

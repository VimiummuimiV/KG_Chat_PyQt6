"""Extra words that count as a mention: local per account, global for every account."""

from __future__ import annotations

from typing import Optional, Pattern

from core.state.json_state import JsonState
from helpers.text.mention_parser import compile_mention_pattern


class MentionAliases:
    """One file, data/mention_aliases.json: {"local": {username: [...]}, "global": [...]}."""

    _state = JsonState("mention_aliases.json")

    def __init__(self):
        self._patterns: dict = {}

    def local_aliases(self, username: str) -> list:
        value = self._state.get("local", username) if username else None
        return list(value) if isinstance(value, list) else []

    def set_local_aliases(self, username: str, values: list) -> None:
        if not username:
            return
        self._state.set("local", username, value=list(values))
        self._patterns.clear()

    def global_aliases(self) -> list:
        value = self._state.get("global")
        return list(value) if isinstance(value, list) else []

    def set_global_aliases(self, values: list) -> None:
        self._state.set("global", value=list(values))
        self._patterns.clear()

    def pattern(self, username: str) -> Optional[Pattern]:
        """Pattern for the username plus its local and the global aliases (cached until an alias changes)."""
        if username not in self._patterns:
            self._patterns[username] = compile_mention_pattern(username, self.local_aliases(username), self.global_aliases())
        return self._patterns[username]


mention_aliases = MentionAliases()

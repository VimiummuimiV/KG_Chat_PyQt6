"""Extra words that count as a mention: local per account, global for every account."""

from __future__ import annotations

from typing import Optional, Pattern

from core.state.user_state import ByUserStore
from helpers.text.mention_parser import compile_mention_pattern


_GLOBAL_CONFIG_PATH = ("notification", "global_mention_aliases")


class MentionAliases:
    """Local aliases live in mention_aliases.json per username, global ones in the config."""

    _store = ByUserStore("mention_aliases.json")

    def __init__(self, config):
        self._config = config
        self._patterns: dict = {}

    def local_aliases(self, username: str) -> list:
        value = self._store.get(username)
        return list(value) if isinstance(value, list) else []

    def set_local_aliases(self, username: str, values: list) -> None:
        self._store.set(username, list(values))
        self._patterns.clear()

    def global_aliases(self) -> list:
        return list(self._config.get(*_GLOBAL_CONFIG_PATH) or [])

    def set_global_aliases(self, values: list) -> None:
        self._config.set(*_GLOBAL_CONFIG_PATH, value=list(values))
        self._patterns.clear()

    def pattern(self, username: str) -> Optional[Pattern]:
        """Pattern for the username plus its local and the global aliases (cached until an alias changes)."""
        if username not in self._patterns:
            keywords = [username, *self.local_aliases(username), *self.global_aliases()]
            self._patterns[username] = compile_mention_pattern(keywords)
        return self._patterns[username]

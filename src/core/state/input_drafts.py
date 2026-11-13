"""Text typed for the chat but not delivered: the draft in the input field and messages still unsent."""

from core.state.user_state import ByUserStore


class InputDrafts:
    """Per-username store; a crash or a failed send does not lose what the user wrote."""
    _store = ByUserStore("input_drafts.json")

    def draft(self, username: str) -> str:
        return self._entry(username).get("draft", "")

    def unsent(self, username: str) -> list:
        return list(self._entry(username).get("unsent", []))

    def set_draft(self, username: str, text: str):
        self._update(username, draft=text)

    def add_unsent(self, username: str, text: str):
        self._update(username, unsent=[*self.unsent(username), text])

    def remove_unsent(self, username: str, text: str):
        remaining = self.unsent(username)
        if text in remaining:
            remaining.remove(text)
            self._update(username, unsent=remaining)

    def restorable_text(self, username: str) -> str:
        """Unsent messages followed by the draft, as one text for the input field."""
        return " ".join([*self.unsent(username), self.draft(username)]).strip()

    def clear_unsent(self, username: str):
        self._update(username, unsent=[])

    def _entry(self, username: str) -> dict:
        entry = self._store.get(username)
        return entry if isinstance(entry, dict) else {}

    def _update(self, username: str, **changes):
        entry = {**self._entry(username), **changes}
        entry = {key: value for key, value in entry.items() if value}
        self._store.set(username, entry or None)

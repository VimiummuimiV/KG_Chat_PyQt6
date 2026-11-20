"""Text typed for the chat but not delivered: the draft in the input field, messages still unsent, and the queue."""

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

    def queued(self, username: str) -> list:
        """Messages that never left the client (no connection), as {"text", "at"}; they are sent again by themselves."""
        return list(self._entry(username).get("queued", []))

    def add_queued(self, username: str, text: str, queued_at: float):
        self._update(username, queued=[*self.queued(username), {"text": text, "at": queued_at}])

    def remove_queued(self, username: str, text: str):
        remaining = self.queued(username)
        for entry in remaining:
            if entry["text"] == text:
                remaining.remove(entry)
                self._update(username, queued=remaining)
                return

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

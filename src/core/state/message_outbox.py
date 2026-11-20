"""Messages handed to sending that the server has not confirmed yet, kept so that closing the chat loses none."""

from core.state.user_state import ByUserStore


class MessageOutbox:
    """Per-username store of two lists.

    unconfirmed: sent, no echo yet; after a restart they go back into the input field, as the server may have them.
    queued: the connection was down; sent again by themselves, as {"text", "at" (Unix seconds), "certain"}, where
    certain means the request could not have reached the server.
    """
    _store = ByUserStore("message_outbox.json")

    def unconfirmed(self, username: str) -> list:
        return list(self._store.entry(username).get("unconfirmed", []))

    def add_unconfirmed(self, username: str, text: str):
        self._store.update(username, unconfirmed=[*self.unconfirmed(username), text])

    def remove_unconfirmed(self, username: str, text: str):
        remaining = self.unconfirmed(username)
        if text in remaining:
            remaining.remove(text)
            self._store.update(username, unconfirmed=remaining)

    def clear_unconfirmed(self, username: str):
        self._store.update(username, unconfirmed=[])

    def queued(self, username: str) -> list:
        return list(self._store.entry(username).get("queued", []))

    def add_queued(self, username: str, text: str, queued_at: int, is_certain: bool):
        self._store.update(username, queued=[*self.queued(username), {"text": text, "at": queued_at, "certain": is_certain}])

    def remove_queued(self, username: str, text: str):
        remaining = self.queued(username)
        for entry in remaining:
            if entry["text"] == text:
                remaining.remove(entry)
                self._store.update(username, queued=remaining)
                return

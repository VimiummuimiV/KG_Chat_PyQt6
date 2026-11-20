"""The text typed in the chat input field, kept so that closing the chat loses none."""

from core.state.user_state import ByUserStore


class InputDrafts:
    """Per-username store of the draft in the input field."""
    _store = ByUserStore("input_drafts.json")

    def draft(self, username: str) -> str:
        return self._store.entry(username).get("draft", "")

    def set_draft(self, username: str, text: str):
        self._store.set(username, {"draft": text} if text else None)  # the whole entry: values of older versions go

"""Usernames the autocomplete inserted last, newest first (data/ui_state.json, key username_recent)."""

from typing import List, Optional

from core.state.ui_state import ui_state
from helpers.text.mention_parser import fold_nickname


MAX_STORED_RECENT = 10

_STATE_KEY = "username_recent"
_recent: Optional[List[str]] = None  # read from the file once; later changes only write it


def get_recent_usernames() -> List[str]:
    """Recently inserted usernames, newest first."""
    global _recent
    if _recent is None:
        stored = ui_state.get(_STATE_KEY)
        _recent = [username for username in stored if isinstance(username, str)] if isinstance(stored, list) else []
    return _recent


def remember_username(username: str) -> None:
    """Put a username first in the recent list."""
    recent = get_recent_usernames()
    folded = fold_nickname(username)
    recent[:] = [username, *(other for other in recent if fold_nickname(other) != folded)][:MAX_STORED_RECENT]
    ui_state.set(_STATE_KEY, value=recent)

"""Nickname suggestion options read from the config; the defaults and limits are shared with the settings page."""

from core.state.recent_mentions import MAX_STORED_RECENT
from helpers.config import read_bounded_int


DEFAULT_RECENT_LIMIT = 3
RECENT_LIMIT_RANGE = (1, MAX_STORED_RECENT)
DEFAULT_SUGGESTION_LIMIT = 8
SUGGESTION_LIMIT_RANGE = (1, 15)


def is_autocomplete_enabled(config) -> bool:
    """Whether nickname suggestions are on (on unless switched off in Settings)."""
    value = config.get("ui", "chat", "username_autocomplete")
    return True if value is None else bool(value)


def is_recent_shown(config) -> bool:
    """Whether a bare @ lists the recently inserted nicknames (on unless switched off in Settings)."""
    value = config.get("ui", "chat", "mention_recent")
    return True if value is None else bool(value)


def recent_limit(config) -> int:
    """How many recently inserted nicknames a bare @ lists."""
    return read_bounded_int(config, ("ui", "chat", "mention_recent_limit"), DEFAULT_RECENT_LIMIT, RECENT_LIMIT_RANGE)


def suggestion_limit(config) -> int:
    """How many suggested nicknames are shown."""
    return read_bounded_int(
        config, ("ui", "chat", "mention_suggestion_limit"), DEFAULT_SUGGESTION_LIMIT, SUGGESTION_LIMIT_RANGE
    )

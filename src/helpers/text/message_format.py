"""Plain-text line of a chat message for copying and exporting."""

from datetime import datetime


def format_message_line(
    username: str, body: str, timestamp: datetime, include_username: bool = True, include_timestamp: bool = True
) -> str:
    """Return "[HH:MM:SS] username: body"; the time and the username are left out on request, the username also when empty."""
    prefix = f"[{timestamp:%H:%M:%S}] " if include_timestamp else ""
    if include_username and username:
        prefix += f"{username}: "
    return f"{prefix}{body}"

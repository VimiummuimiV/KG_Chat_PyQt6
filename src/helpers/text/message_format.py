"""Plain-text line of a chat message for copying and exporting."""

from datetime import datetime


def message_line_parts(
    username: str, body: str, timestamp: datetime, include_username: bool = True, include_timestamp: bool = True
) -> tuple:
    """Return the ("[HH:MM:SS] ", "username: ", body) pieces of a message line; a piece that is left out is empty."""
    time_text = f"[{timestamp:%H:%M:%S}] " if include_timestamp else ""
    username_text = f"{username}: " if include_username and username else ""
    return time_text, username_text, body


def format_message_line(
    username: str, body: str, timestamp: datetime, include_username: bool = True, include_timestamp: bool = True
) -> str:
    """Return "[HH:MM:SS] username: body"; the time and the username are left out on request, the username also when empty."""
    return "".join(message_line_parts(username, body, timestamp, include_username, include_timestamp))

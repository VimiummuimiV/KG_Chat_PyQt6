"""Plain-text line of a chat message for copying and exporting."""

from datetime import datetime


RECIPIENT_ARROW = " → "  # between the sender and the recipient of an own private message


def message_line_parts(
    username: str, body: str, timestamp: datetime, include_username: bool = True, include_timestamp: bool = True,
    recipient: str = "",
) -> tuple:
    """Return the ("[HH:MM:SS] ", "username: ", " → ", "recipient: ", body) pieces of a message line; a piece that is left out is empty."""
    time_text = f"[{timestamp:%H:%M:%S}] " if include_timestamp else ""
    if not (include_username and username):
        return time_text, "", "", "", body
    if not recipient:
        return time_text, f"{username}: ", "", "", body
    return time_text, username, RECIPIENT_ARROW, f"{recipient}: ", body


def format_message_line(
    username: str, body: str, timestamp: datetime, include_username: bool = True, include_timestamp: bool = True
) -> str:
    """Return "[HH:MM:SS] username: body"; the time and the username are left out on request, the username also when empty."""
    return "".join(message_line_parts(username, body, timestamp, include_username, include_timestamp))

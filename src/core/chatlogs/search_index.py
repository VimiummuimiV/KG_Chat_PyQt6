"""Text index over a message list: finds the messages that contain a text without visiting every message."""

from array import array
from bisect import bisect_right
from itertools import accumulate
from typing import List, Optional

_KEY_BREAK = "\x00"
_NAME_BREAK = "\x01"


class MessageSearchIndex:
    """Lower-cased "username, body" of every message joined into one string, so a search is a few C-speed scans."""

    def __init__(self, messages: list):
        keys = [f"{message.username.lower()}{_NAME_BREAK}{message.body.lower()}" for message in messages]
        self._text = _KEY_BREAK.join(keys)
        self._starts = array("q", accumulate((len(key) + 1 for key in keys), initial=0))
        self.separator_rows = array("q", (row for row, message in enumerate(messages) if message.is_separator))

    def rows_containing(self, text: str) -> Optional[List[int]]:
        """Rows of the messages whose username or body contains the lower-cased text, in order; None if the text cannot be indexed."""
        if not text or _KEY_BREAK in text or _NAME_BREAK in text:
            return None
        rows = []
        position = self._text.find(text)
        while position != -1:
            row = bisect_right(self._starts, position) - 1
            rows.append(row)
            position = self._text.find(text, self._starts[row + 1])
        return rows

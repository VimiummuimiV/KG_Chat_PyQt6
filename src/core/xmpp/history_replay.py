"""Tells which messages of a history replay the chat already shows."""

from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable, Tuple


CLOCK_TOLERANCE = timedelta(seconds=60)  # live rows carry the local time, replayed ones the server's stamp


class HistoryReplayFilter:
    """After a reconnect the server replays its last messages; the ones already shown are dropped, not wiped and re-added."""

    def __init__(self, shown: Iterable[Tuple[str, str, datetime]]):
        entries = list(shown)
        self._remaining = Counter((username, body) for username, body, _ in entries)
        self._oldest = min((timestamp for _, _, timestamp in entries), default=None)

    def is_duplicate(self, username: str, body: str, timestamp: datetime) -> bool:
        """Whether a replayed message is already shown; every shown message is matched at most once."""
        if self._oldest is None:
            return False
        if timestamp < self._oldest - CLOCK_TOLERANCE:
            return True  # older than everything shown: it was cleared or scrolled out, not missed
        key = (username, body)
        if self._remaining[key] <= 0:
            return False
        self._remaining[key] -= 1
        return True

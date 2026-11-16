"""Tracker history data: the event model that applies the filters and the day separators itself."""

from datetime import datetime
from typing import List, Optional, Set

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt


def _event_day(event: dict) -> Optional[str]:
    """Local calendar day of an event, kept on the event after the first lookup."""
    day = event.get('day')
    if day is None:
        try:
            day = datetime.fromtimestamp(float(event.get('timestamp'))).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OverflowError, OSError):
            return None
        event['day'] = day
    return day


def _separator(day: str, event: dict) -> dict:
    return {'is_separator': True, 'date_str': day, 'timestamp': event.get('timestamp', 0)}


class TrackerEventModel(QAbstractListModel):
    """Join/left/game events as list rows: the events that pass the filters, with a separator before each day.

    The filters are applied here in one pass, so a change is a single model reset."""

    def __init__(self):
        super().__init__()
        self._source: List[dict] = []  # every event, oldest first
        self.stored_events: List[dict] = []  # the rows
        self.shown_count = 0  # events among the rows
        self._logins: Set[str] = set()
        self._types: Set[str] = set()
        self._days: Set[str] = set()
        self._last_day: Optional[str] = None

    @property
    def total_count(self) -> int:
        return len(self._source)

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.stored_events)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.stored_events):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.stored_events[index.row()]
        return None

    def set_events(self, events: List[dict]):
        self.beginResetModel()
        self._source = [event for event in events if not event.get('is_separator')]
        self._rebuild_rows()
        self.endResetModel()

    def set_filters(self, logins: Set[str], types: Set[str], days: Set[str] = None):
        """Show only the events of these logins, types and days; an empty set means no limit."""
        days = set(days or ())
        if (logins, types, days) == (self._logins, self._types, self._days):
            return
        self.beginResetModel()
        self._logins, self._types, self._days = set(logins), set(types), days
        self._rebuild_rows()
        self.endResetModel()

    def append_event(self, event: dict) -> Optional[int]:
        """Add a new event; returns its row, or None while a filter hides it."""
        self._source.append(event)
        if not self._matches(event):
            return None
        day = _event_day(event)
        added = [event]
        if day and day != self._last_day:
            added.insert(0, _separator(day, event))
            self._last_day = day
        first = len(self.stored_events)
        self.beginInsertRows(QModelIndex(), first, first + len(added) - 1)
        self.stored_events.extend(added)
        self.shown_count += 1
        self.endInsertRows()
        return first + len(added) - 1

    def remove_login(self, login: str) -> int:
        """Drop every event of the login; returns how many there were."""
        kept = [event for event in self._source if event.get('login') != login]
        removed = len(self._source) - len(kept)
        self.beginResetModel()
        self._source = kept
        self._rebuild_rows()
        self.endResetModel()
        return removed

    def find_row(self, login: str = None, event_ts: float = None) -> Optional[int]:
        target = None
        for row, event in enumerate(self.stored_events):
            if event.get('is_separator'):
                continue
            if login and event.get('login') != login:
                continue
            if event_ts is not None:
                ts = event.get('timestamp')
                if ts is None or abs(float(ts) - float(event_ts)) > 0.05:
                    continue
            target = row
            if event_ts is not None:
                break
        return target

    def clear(self):
        self.set_events([])

    def _matches(self, event: dict) -> bool:
        if self._logins and event.get('login') not in self._logins:
            return False
        if self._types and (event.get('type') or '') not in self._types:
            return False
        return not self._days or _event_day(event) in self._days

    def _rebuild_rows(self):
        rows = []
        last_day = None
        shown = 0
        for event in self._source:
            if not self._matches(event):
                continue
            day = _event_day(event)
            if day and day != last_day:
                rows.append(_separator(day, event))
                last_day = day
            rows.append(event)
            shown += 1
        self.stored_events = rows
        self.shown_count = shown
        self._last_day = last_day

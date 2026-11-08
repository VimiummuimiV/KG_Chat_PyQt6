"""Tracker history data: date helpers, event model and filter proxy."""

from datetime import datetime
from typing import List, Optional, Set

from PyQt6.QtCore import QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt


def _event_date_str(event: dict) -> Optional[str]:
    if event.get('is_separator'):
        return event.get('date_str')
    ts = event.get('timestamp')
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
    except Exception:
        return None


def _inject_date_separators(events: List[dict]) -> List[dict]:
    """Insert a DateSeparator row before each new calendar day."""
    result = []
    last_date = None
    for event in events:
        if event.get('is_separator'):
            continue
        date_str = _event_date_str(event)
        if date_str and date_str != last_date:
            result.append({
                'is_separator': True,
                'date_str': date_str,
                'timestamp': event.get('timestamp', 0),
            })
            last_date = date_str
        result.append(event)
    return result


class TrackerEventModel(QAbstractListModel):
    """Model for join/left/game tracker events - data only, no rendering"""

    def __init__(self):
        super().__init__()
        self._events: List[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._events)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._events):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._events[index.row()]
        return None

    def set_events(self, events: List[dict]):
        self.beginResetModel()
        self._events = _inject_date_separators(events)
        self.endResetModel()

    def append_event(self, event: dict) -> int:
        date_str = _event_date_str(event)
        last_date = None
        for existing in reversed(self._events):
            if existing.get('is_separator'):
                last_date = existing.get('date_str')
                break
            last_date = _event_date_str(existing)
            if last_date:
                break

        if date_str and date_str != last_date:
            separator = {
                'is_separator': True,
                'date_str': date_str,
                'timestamp': event.get('timestamp', 0),
            }
            row = len(self._events)
            self.beginInsertRows(QModelIndex(), row, row + 1)
            self._events.append(separator)
            self._events.append(event)
            self.endInsertRows()
            return row + 1

        row = len(self._events)
        self.beginInsertRows(QModelIndex(), row, row)
        self._events.append(event)
        self.endInsertRows()
        return row

    def remove_login(self, login: str) -> int:
        raw = [e for e in self._events
               if not e.get('is_separator') and e.get('login') != login]
        removed = sum(
            1 for e in self._events
            if not e.get('is_separator') and e.get('login') == login
        )
        self.beginResetModel()
        self._events = _inject_date_separators(raw)
        self.endResetModel()
        return removed

    def find_row(self, login: str = None, event_ts: float = None) -> Optional[int]:
        target = None
        for row, event in enumerate(self._events):
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

    def get_events(self) -> List[dict]:
        return list(self._events)


class TrackerEventFilterProxy(QSortFilterProxyModel):
    """Filters tracker events by login, event type and/or date without touching the source model"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filtered_logins: Set[str] = set()
        self._filtered_types: Set[str] = set()
        self.filtered_dates: Set[str] = set()

    def set_filters(self, logins: Set[str], types: Set[str], dates: Set[str] = None):
        self.filtered_logins = set(logins)
        self._filtered_types = set(types)
        self.filtered_dates = set(dates or ())
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self.sourceModel()
        event = source_model.data(
            source_model.index(source_row, 0, source_parent),
            Qt.ItemDataRole.DisplayRole,
        )
        if not event:
            return True

        date_str = _event_date_str(event)

        if event.get('is_separator'):
            if self.filtered_dates and date_str not in self.filtered_dates:
                return False
            # Hide separator when no real event of that day would remain visible
            for row in range(source_row + 1, source_model.rowCount()):
                sibling = source_model.data(
                    source_model.index(row, 0, source_parent),
                    Qt.ItemDataRole.DisplayRole,
                )
                if not sibling or sibling.get('is_separator'):
                    break
                if self._event_matches(sibling):
                    return True
            return False

        if self.filtered_dates and date_str not in self.filtered_dates:
            return False
        return self._event_matches(event)

    def _event_matches(self, event: dict) -> bool:
        if self.filtered_logins and event.get('login') not in self.filtered_logins:
            return False
        if self._filtered_types and (event.get('type') or '') not in self._filtered_types:
            return False
        return True

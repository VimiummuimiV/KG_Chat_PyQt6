"""Message data model for virtual scrolling"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt


@dataclass
class MessageData:
    """Lightweight message data structure"""
    timestamp: datetime
    username: str = ""
    body: str = ""
    background_color: Optional[str] = None
    login: Optional[str] = None
    is_private: bool = False
    is_separator: bool = False
    date_str: Optional[str] = None
    is_ban: bool = False
    is_system: bool = False
    is_competition: bool = False
    competition_game_id: Optional[int] = None
    competition_players: Optional[list] = None
    is_new_messages_marker: bool = False
    is_presence_log: bool = False
    presence_entries: Optional[list] = None
    joins_previous: bool = False  # Filtered chatlog: same user's previous shown message, nothing hidden between
    joins_next: bool = False
    delivery_id: Optional[int] = None  # own message followed by DeliveryTracker
    delivery: Optional[str] = None
    layout_cache: Optional[tuple] = field(default=None, compare=False, repr=False)  # (key, TextLayout) kept by MessageDelegate

    def get_time_str(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")


class MessageListModel(QAbstractListModel):
    """Model for storing messages - handles data only, no rendering"""

    def __init__(self, max_messages: int):
        super().__init__()
        self.stored_messages: List[MessageData] = []
        self.max_messages = max_messages

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.stored_messages)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.stored_messages):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.stored_messages[index.row()]
        return None

    def add_message(self, msg: MessageData):
        if len(self.stored_messages) >= self.max_messages:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self.stored_messages.pop(0)
            self.endRemoveRows()

        row = len(self.stored_messages)
        self.beginInsertRows(QModelIndex(), row, row)
        self.stored_messages.append(msg)
        self.endInsertRows()
        return row

    def set_delivery(self, delivery_id: int, state: str) -> bool:
        """Set the delivery state of the message with this id; True if it is in this model."""
        for row in range(len(self.stored_messages) - 1, -1, -1):
            msg = self.stored_messages[row]
            if msg.delivery_id == delivery_id:
                msg.delivery = state
                index = self.index(row)
                self.dataChanged.emit(index, index)
                return True
        return False

    def set_messages(self, messages: List[MessageData]):
        """Replace all messages in one model reset (bulk load)."""
        if len(messages) > self.max_messages:
            messages = messages[-self.max_messages:]
        self.beginResetModel()
        self.stored_messages = list(messages)
        self.endResetModel()

    def trim_to_limit(self):
        excess = len(self.stored_messages) - self.max_messages
        if excess > 0:
            self.beginRemoveRows(QModelIndex(), 0, excess - 1)
            del self.stored_messages[:excess]
            self.endRemoveRows()

    def clear(self):
        if self.stored_messages:
            self.beginResetModel()
            self.stored_messages.clear()
            self.endResetModel()

    def clear_private_messages(self):
        if not self.stored_messages:
            return
        private_indices = [i for i, msg in enumerate(self.stored_messages) if msg.is_private]
        for index in reversed(private_indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self.stored_messages.pop(index)
            self.endRemoveRows()

    def clear_competition_messages(self, game_id=None):
        if not self.stored_messages:
            return
        indices = [
            i for i, msg in enumerate(self.stored_messages)
            if msg.is_competition and (game_id is None or msg.competition_game_id == game_id)
        ]
        for index in reversed(indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self.stored_messages.pop(index)
            self.endRemoveRows()

    def clear_presence_messages(self):
        if not self.stored_messages:
            return
        indices = [i for i, msg in enumerate(self.stored_messages) if getattr(msg, 'is_presence_log', False)]
        for index in reversed(indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self.stored_messages.pop(index)
            self.endRemoveRows()

    def remove_messages_by_login(self, login: str, timestamp=None, from_timestamp=None, to_timestamp=None):
        if not login or not self.stored_messages:
            return
        indices = [i for i, m in enumerate(self.stored_messages)
                  if getattr(m, 'login', None) == login
                  and (timestamp       is not None and m.timestamp == timestamp
                    or from_timestamp  is not None and m.timestamp >= from_timestamp
                    or to_timestamp    is not None and m.timestamp <= to_timestamp
                    or timestamp is None and from_timestamp is None and to_timestamp is None)]
        for index in reversed(indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self.stored_messages.pop(index)
            self.endRemoveRows()

    def _find_competition_row(self, game_id: int) -> Optional[int]:
        for row in range(len(self.stored_messages) - 1, -1, -1):
            msg = self.stored_messages[row]
            if msg.is_competition and msg.competition_game_id == game_id:
                return row
        return None

    def update_message_by_game_id(self, game_id: int, body: str, players: Optional[List[str]] = None) -> Optional[int]:
        row = self._find_competition_row(game_id)
        if row is not None:
            msg = self.stored_messages[row]
            msg.body = body
            if players is not None:
                msg.competition_players = players
        return row

    def find_competition_message_row(self, game_id: int) -> Optional[int]:
        return self._find_competition_row(game_id)

    def get_open_presence_log_row(self) -> Optional[int]:
        if self.stored_messages and self.stored_messages[-1].is_presence_log:
            return len(self.stored_messages) - 1
        return None

    def get_message_at(self, row: int) -> Optional[MessageData]:
        return self.stored_messages[row] if 0 <= row < len(self.stored_messages) else None

    def update_presence_entries(self, row: int, entries: list, body: str) -> bool:
        if not (0 <= row < len(self.stored_messages)):
            return False
        msg = self.stored_messages[row]
        msg.presence_entries = entries
        msg.body = body
        msg.timestamp = datetime.now()
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
        return True

    def remove_message_at(self, row: int) -> bool:
        if not (0 <= row < len(self.stored_messages)):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        self.stored_messages.pop(row)
        self.endRemoveRows()
        return True

"""Message data model for virtual scrolling"""
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
from PyQt6.QtCore import QAbstractListModel, Qt, QModelIndex


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

    def get_time_str(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")


class MessageListModel(QAbstractListModel):
    """Model for storing messages - handles data only, no rendering"""

    def __init__(self, max_messages: int = 50000):
        super().__init__()
        self._messages: List[MessageData] = []
        self.max_messages = max_messages

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._messages)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._messages):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._messages[index.row()]
        return None

    def add_message(self, msg: MessageData):
        if len(self._messages) >= self.max_messages:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._messages.pop(0)
            self.endRemoveRows()

        row = len(self._messages)
        self.beginInsertRows(QModelIndex(), row, row)
        self._messages.append(msg)
        self.endInsertRows()
        return row

    def clear(self):
        if self._messages:
            self.beginResetModel()
            self._messages.clear()
            self.endResetModel()

    def clear_private_messages(self):
        if not self._messages:
            return
        private_indices = [i for i, msg in enumerate(self._messages) if msg.is_private]
        for index in reversed(private_indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self._messages.pop(index)
            self.endRemoveRows()

    def clear_competition_messages(self, game_id=None):
        if not self._messages:
            return
        indices = [
            i for i, msg in enumerate(self._messages)
            if msg.is_competition and (game_id is None or msg.competition_game_id == game_id)
        ]
        for index in reversed(indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self._messages.pop(index)
            self.endRemoveRows()

    def clear_presence_messages(self):
        if not self._messages:
            return
        indices = [i for i, msg in enumerate(self._messages) if getattr(msg, 'is_presence_log', False)]
        for index in reversed(indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self._messages.pop(index)
            self.endRemoveRows()

    def remove_messages_by_login(self, login: str, timestamp=None, from_timestamp=None, to_timestamp=None):
        if not login or not self._messages:
            return
        indices = [i for i, m in enumerate(self._messages)
                  if getattr(m, 'login', None) == login
                  and (timestamp       is not None and m.timestamp == timestamp
                    or from_timestamp  is not None and m.timestamp >= from_timestamp
                    or to_timestamp    is not None and m.timestamp <= to_timestamp
                    or timestamp is None and from_timestamp is None and to_timestamp is None)]
        for index in reversed(indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self._messages.pop(index)
            self.endRemoveRows()

    def _find_competition_row(self, game_id: int) -> Optional[int]:
        for row in range(len(self._messages) - 1, -1, -1):
            msg = self._messages[row]
            if msg.is_competition and msg.competition_game_id == game_id:
                return row
        return None

    def update_message_by_game_id(self, game_id: int, body: str, players: Optional[List[str]] = None) -> Optional[int]:
        row = self._find_competition_row(game_id)
        if row is not None:
            msg = self._messages[row]
            msg.body = body
            if players is not None:
                msg.competition_players = players
        return row

    def find_competition_message_row(self, game_id: int) -> Optional[int]:
        return self._find_competition_row(game_id)

    def get_open_presence_log_row(self) -> Optional[int]:
        if self._messages and self._messages[-1].is_presence_log:
            return len(self._messages) - 1
        return None

    def get_message_at(self, row: int) -> Optional[MessageData]:
        return self._messages[row] if 0 <= row < len(self._messages) else None

    def update_presence_entries(self, row: int, entries: list, body: str) -> bool:
        if not (0 <= row < len(self._messages)):
            return False
        msg = self._messages[row]
        msg.presence_entries = entries
        msg.body = body
        msg.timestamp = datetime.now()
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])
        return True

    def remove_message_at(self, row: int) -> bool:
        if not (0 <= row < len(self._messages)):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        self._messages.pop(row)
        self.endRemoveRows()
        return True

    def get_all_messages(self) -> List[MessageData]:
        return self._messages.copy()

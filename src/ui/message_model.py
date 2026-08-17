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
    date_str: Optional[str] = None  # For separators
    is_ban: bool = False
    is_system: bool = False
    is_competition: bool = False
    competition_game_id: Optional[int] = None
    competition_players: Optional[List[str]] = None
    is_new_messages_marker: bool = False
   
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
        """Add a new message"""
        if len(self._messages) >= self.max_messages:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._messages.pop(0)
            self.endRemoveRows()
       
        row = len(self._messages)
        self.beginInsertRows(QModelIndex(), row, row)
        self._messages.append(msg)
        self.endInsertRows()
   
    def clear(self):
        if self._messages:
            self.beginResetModel()
            self._messages.clear()
            self.endResetModel()
   
    def clear_private_messages(self):
        """Remove all private messages from the model"""
        if not self._messages:
            return
       
        # Find indices of private messages
        private_indices = [i for i, msg in enumerate(self._messages) if msg.is_private]
       
        if not private_indices:
            return
       
        # Remove in reverse order to maintain indices
        for index in reversed(private_indices):
            self.beginRemoveRows(QModelIndex(), index, index)
            self._messages.pop(index)
            self.endRemoveRows()


    def clear_competition_messages(self, game_id=None):
        """Remove rating competition messages.
        If game_id is set, only messages for that competition are removed.
        """
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

    def remove_messages_by_login(self, login: str, timestamp=None, from_timestamp=None, to_timestamp=None):
        """Remove messages by login.
        - timestamp:      only that exact message
        - from_timestamp: that message and everything after (same login)
        - to_timestamp:   that message and everything before (same login)
        - neither:        all messages from login
        """
        if not login or not self._messages:
            return
        
        indices = [i for i, m in enumerate(self._messages)
                  if getattr(m, 'login', None) == login
                  and (timestamp       is not None and m.timestamp == timestamp
                    or from_timestamp  is not None and m.timestamp >= from_timestamp
                    or to_timestamp    is not None and m.timestamp <= to_timestamp
                    or timestamp is None and from_timestamp is None and to_timestamp is None)]
        
        if not indices:
            return
        
        # Remove in reverse order to maintain indices
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
        """Update a competition message's body (and optionally its player chips) in place. Returns its row, or None."""
        row = self._find_competition_row(game_id)
        if row is not None:
            msg = self._messages[row]
            msg.body = body
            if players is not None:
                msg.competition_players = players
        return row

    def find_competition_message_row(self, game_id: int) -> Optional[int]:
        """Find row of a competition message by game_id. Returns row index or None."""
        return self._find_competition_row(game_id)

    def get_all_messages(self) -> List[MessageData]:
        return self._messages.copy()
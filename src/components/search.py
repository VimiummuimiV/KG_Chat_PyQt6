"""Reusable message search bar (field + clear, optional live filter with backup)."""
import re
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit
from PyQt6.QtCore import pyqtSignal

from helpers.create import create_icon_button
from helpers.fonts import get_font, FontType
from helpers.translate import tr

def parse_search_text(text: str):
    """Parse 'text' | 'U:Bob,Alice' | 'M:hello' | combined U:/M: prefixes.

    Returns (user_filter: set[str], message_filter: str, is_prefix_mode: bool).
    """
    if not text or not text.strip():
        return set(), "", False

    text = text.strip()
    has_u_prefix = re.search(r'[Uu]:', text)
    has_m_prefix = re.search(r'[Mm]:', text)
    if not (has_u_prefix or has_m_prefix):
        return set(), "", False

    user_filter = set()
    message_filter = ""

    if has_u_prefix:
        match = re.search(r'[Uu]:\s*(.+?)(?:\s+[Mm]:|$)', text)
        if match:
            users = [u.strip() for u in match.group(1).strip().split(',') if u.strip()]
            user_filter.update(users)

    if has_m_prefix:
        match = re.search(r'[Mm]:\s*(.+?)(?:\s+[Uu]:|$)', text)
        if match:
            message_filter = match.group(1).strip().lower()

    return user_filter, message_filter, True


def message_matches_search(msg_data, search_text: str) -> bool:
    """Match a message against plain text or U:/M: prefix query."""
    if not search_text:
        return True

    users, message_filter, is_prefix = parse_search_text(search_text)
    username = (msg_data.username or "").lower()
    body = (msg_data.body or "").lower()

    if is_prefix:
        if users and username not in {u.lower() for u in users}:
            return False
        if message_filter and message_filter not in body:
            return False
        return True

    search_lower = search_text.lower()
    return search_lower in username or search_lower in body


def highlight_from_search(search_text: str) -> str:
    """Text to highlight in the delegate for the current query."""
    users, message_filter, is_prefix = parse_search_text(search_text)
    if is_prefix:
        return message_filter
    return search_text


class MessageSearchBar(QWidget):
    """Search bar over a message list.

    With get_messages/set_messages: keeps a backup while a query is active and
    filters by plain text or U:/M: prefixes. Without them: UI + visibility only;
    the host reacts to text_changed / return_pressed (chatlog).
    """
    text_changed = pyqtSignal(str)
    return_pressed = pyqtSignal()

    def __init__(
        self,
        config,
        icons_path: Path,
        *,
        config_key: str = "chat_search_visible",
        get_messages=None,
        set_messages=None,
        placeholder: str = "",
        extra_widgets=None,
    ):
        super().__init__()
        self.config = config
        self._config_key = config_key
        self._get_messages = get_messages
        self._set_messages = set_messages
        self._filter_enabled = get_messages is not None and set_messages is not None
        self.search_text = ""
        self.visible_state = bool(config.get("ui", config_key) or False)
        self._backup = None

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(config.get("ui", "buttons", "spacing") or 8)
        self.setLayout(layout)

        self.field = QLineEdit()
        self.field.setPlaceholderText(placeholder)
        self.field.setFont(get_font(FontType.TEXT))
        self.field.setFixedHeight(config.get("ui", "input_height") or 48)
        self.field.textChanged.connect(self._on_text_changed)
        self.field.returnPressed.connect(self.return_pressed.emit)
        layout.addWidget(self.field, stretch=1)

        for widget in extra_widgets or ():
            layout.addWidget(widget)

        self.clear_btn = create_icon_button(
            icons_path, "trash.svg", "",
            size_type="large", config=config,
        )
        self.clear_btn.setToolTip(tr("Clear search", "Очистить поиск"))
        self.clear_btn.clicked.connect(self.clear)
        layout.addWidget(self.clear_btn)

        self.setVisible(self.visible_state)

    @property
    def active(self) -> bool:
        return self._backup is not None

    def toggle(self):
        self.visible_state = not self.visible_state
        self.setVisible(self.visible_state)
        self.config.set("ui", self._config_key, value=self.visible_state)
        if self.visible_state:
            self.field.setFocus()
        else:
            self.clear()

    def clear(self):
        self.field.blockSignals(True)
        self.field.clear()
        self.field.blockSignals(False)
        self.search_text = ""
        self.text_changed.emit("")
        if self._backup is not None and self._set_messages is not None:
            self._set_messages(self._backup)
            self._backup = None

    def reset(self):
        """Drop backup/query state without restoring the model (caller already cleared it)."""
        self._backup = None
        self.search_text = ""
        if self.visible_state:
            self.field.blockSignals(True)
            self.field.clear()
            self.field.blockSignals(False)
        self.text_changed.emit("")

    def matches(self, msg_data) -> bool:
        return message_matches_search(msg_data, self.search_text)

    def highlight_text(self) -> str:
        return highlight_from_search(self.search_text)

    def register_message(self, msg_data, max_messages: int) -> bool:
        """Sync backup with a new message; returns whether it should appear in the list now."""
        if self._backup is None:
            return True
        self._backup.append(msg_data)
        if len(self._backup) > max_messages:
            self._backup = self._backup[-max_messages:]
        return self.matches(msg_data)

    def filter_backup(self, predicate):
        """Remove backup entries for which predicate(msg) is True."""
        if self._backup is not None:
            self._backup = [m for m in self._backup if not predicate(m)]

    def _on_text_changed(self, text: str):
        self.search_text = text.strip()
        self.text_changed.emit(self.search_text)
        if not self._filter_enabled:
            return
        if not self.search_text:
            if self._backup is not None:
                self._set_messages(self._backup)
                self._backup = None
            return
        if self._backup is None:
            self._backup = list(self._get_messages())
        filtered = [m for m in self._backup if self.matches(m)]
        self._set_messages(filtered)

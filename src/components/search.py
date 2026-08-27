"""Reusable message search bar (field + clear, optional live filter with backup)."""
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit
from PyQt6.QtCore import pyqtSignal

from helpers.create import create_icon_button
from helpers.fonts import get_font, FontType


class MessageSearchBar(QWidget):
    """Search bar over a message list.

    With get_messages/set_messages: keeps a backup while a query is active and
    filters by username/body (messages chat). Without them: UI + visibility only;
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
            icons_path, "trash.svg", "Clear search",
            size_type="large", config=config,
        )
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
        if not self.search_text:
            return True
        search_lower = self.search_text.lower()
        return (
            search_lower in (msg_data.username or "").lower()
            or search_lower in (msg_data.body or "").lower()
        )

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
        search_lower = self.search_text.lower()
        filtered = [
            m for m in self._backup
            if search_lower in (m.username or "").lower()
            or search_lower in (m.body or "").lower()
        ]
        self._set_messages(filtered)

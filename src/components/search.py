"""Reusable message search bar (field + clear, optional live filter with backup)."""

import re
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import pyqtSignal, QEvent, Qt
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from components.button import create_icon_button, create_icon_entry
from components.mention_autocomplete.autocomplete import MentionAutocomplete
from helpers.fonts.fonts import FontType, set_font_role
from helpers.scroll.row_jump import announce_jump, describe_message, NEXT, PREVIOUS, RowJumpGroup
from helpers.translate import tr


_ENTER_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter)

# Previous first, then next
_MATCH_JUMP_ACTIONS = (
    ("line/chevron-up-line.svg",   "Previous match", "Предыдущее совпадение"),
    ("line/chevron-down-line.svg", "Next match",     "Следующее совпадение"),
)


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
            users = [u.strip().lstrip('@') for u in match.group(1).strip().split(',') if u.strip()]
            user_filter.update(users)

    if has_m_prefix:
        match = re.search(r'[Mm]:\s*(.+?)(?:\s+[Uu]:|$)', text)
        if match:
            message_filter = match.group(1).strip().lower()

    return user_filter, message_filter, True


class SearchQuery:
    """A search text parsed once: plain text, or U:/M: prefixes for the users and the message text.

    The one place that decides whether a message matches, for the live chat, the chatlog and the parser results."""

    def __init__(self, text: str):
        self.text = (text or "").strip()
        self.users, self.message_text, self.is_prefix_mode = parse_search_text(self.text)
        self._users_lower = {user.lower() for user in self.users}
        self.needle = self.message_text if self.is_prefix_mode else self.text.lower()  # lower-cased text a message must contain
        self.highlight_text = self.message_text if self.is_prefix_mode else self.text

    def matches(self, username: str, body: str) -> bool:
        """Whether a message of this user with this body passes the query (case-insensitive)."""
        if self.is_prefix_mode and self._users_lower and (username or "").lower() not in self._users_lower:
            return False
        if not self.needle:
            return True
        if self.is_prefix_mode:
            return self.needle in (body or "").lower()
        return self.needle in (username or "").lower() or self.needle in (body or "").lower()


class MessageSearchBar(QWidget):
    """Search bar over a message list.

    With get_messages/set_messages: keeps a backup while a query is active and
    filters by plain text or U:/M: prefixes. Without them: UI + visibility only;
    the host reacts to text_changed / return_pressed (chatlog).

    Enter / Shift+Enter jump to the next / previous match. While needs_confirmation() holds (live search over
    its limit) the first Enter only confirms the text and return_pressed fires; Enter jumps once the text is confirmed.
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
        needs_confirmation: Optional[Callable[[], bool]] = None,
    ):
        super().__init__()
        self.config = config
        self._config_key = config_key
        self._get_messages = get_messages
        self._set_messages = set_messages
        self._filter_enabled = get_messages is not None and set_messages is not None
        self.query = SearchQuery("")
        self.visible_state = bool(config.get("ui", config_key) or False)
        self._backup = None
        self._needs_confirmation = needs_confirmation
        self._confirmed_text: Optional[str] = None
        self._jump_group: Optional[RowJumpGroup] = None

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(config.get("ui", "buttons", "spacing") or 8)
        self.setLayout(layout)

        self.field = QLineEdit()
        self.field.setPlaceholderText(placeholder)
        set_font_role(self.field, FontType.TEXT)
        self.field.setFixedHeight(config.get("ui", "input_height") or 48)
        self.field.textChanged.connect(self._on_text_changed)
        self.field.installEventFilter(self)
        layout.addWidget(self.field, stretch=1)
        MentionAutocomplete(self.field, config, prefix_chars=":,", is_recorded=False)  # @nick, U:@nick, U:@a,@b

        self._jump_entries = [create_icon_entry(icons_path, icon, tr(en, ru), config) for icon, en, ru in _MATCH_JUMP_ACTIONS]
        for entry in self._jump_entries:
            entry["button"].setFocusPolicy(Qt.FocusPolicy.NoFocus)  # clicking it must not take focus from the field
            entry["button"].setVisible(False)  # shown by the jump group while some message matches
            layout.addWidget(entry["button"])

        for widget in extra_widgets or ():
            layout.addWidget(widget)

        self._clear_button = create_icon_button(
            icons_path, "fill/delete-bin-fill.svg", "",
            size_type="large", config=config,
        )
        self._clear_button.setToolTip(tr("Clear search", "Очистить поиск"))
        self._clear_button.clicked.connect(self.clear)
        layout.addWidget(self._clear_button)

        self.setVisible(self.visible_state)

    def attach_list_view(self, list_view):
        """Previous / next buttons that scroll the list to the messages the search text matches."""
        self._jump_group = RowJumpGroup(
            list_view, self._jump_entries, self._is_match,
            lambda row, position, total: announce_jump(list_view, row, position, total, tr("Match", "Совпадение")),
            describe=describe_message, scroll_mode="middle", starts_at_top=True, parent=self,
        )
        self._jump_group.rescan()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in _ENTER_KEYS:
            self._on_enter(is_backward=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            return True
        return super().eventFilter(watched, event)

    def _on_enter(self, is_backward: bool):
        is_confirmed = self.field.text() == self._confirmed_text
        is_confirmation_needed = self._needs_confirmation is not None and self._needs_confirmation()
        if is_confirmation_needed and not is_confirmed:
            self.confirm()
        elif self._jump_group is not None:
            self._jump_group.jump(PREVIOUS if is_backward else NEXT)

    def confirm(self):
        """Ask the host to apply the current text (the search button and the first Enter)."""
        self._confirmed_text = self.field.text()
        self.return_pressed.emit()

    def _is_match(self, message) -> bool:
        return bool(self.query.text) and not message.is_separator and self.query.matches(message.username, message.body)

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
        self._confirmed_text = None
        if not self.field.text() and self._backup is None:
            return
        self.field.blockSignals(True)
        self.field.clear()
        self.field.blockSignals(False)
        self.query = SearchQuery("")
        self.text_changed.emit("")
        if self._backup is not None and self._set_messages is not None:
            self._set_messages(self._backup)
            self._backup = None

    def reset(self):
        """Drop backup/query state without restoring the model (caller already cleared it)."""
        self._backup = None
        self._confirmed_text = None
        self.query = SearchQuery("")
        if self.visible_state:
            self.field.blockSignals(True)
            self.field.clear()
            self.field.blockSignals(False)
        self.text_changed.emit("")

    def _matches(self, msg_data) -> bool:
        return self.query.matches(msg_data.username, msg_data.body)

    def highlight_text(self) -> str:
        return self.query.highlight_text

    def register_message(self, msg_data, max_messages: int) -> bool:
        """Sync backup with a new message; returns whether it should appear in the list now."""
        if self._backup is None:
            return True
        self._backup.append(msg_data)
        if len(self._backup) > max_messages:
            self._backup = self._backup[-max_messages:]
        return self._matches(msg_data)

    def filter_backup(self, predicate):
        """Remove backup entries for which predicate(msg) is True."""
        if self._backup is not None:
            self._backup = [m for m in self._backup if not predicate(m)]

    def _on_text_changed(self, text: str):
        self.query = SearchQuery(text)
        self.text_changed.emit(self.query.text)
        if not self._filter_enabled:
            return
        if not self.query.text:
            if self._backup is not None:
                self._set_messages(self._backup)
                self._backup = None
            return
        if self._backup is None:
            self._backup = list(self._get_messages())
        filtered = [m for m in self._backup if self._matches(m)]
        self._set_messages(filtered)

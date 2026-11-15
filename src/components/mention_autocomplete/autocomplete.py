"""Nickname suggestions for a message input: type @ and a few letters, Tab inserts the nickname."""

import re
from typing import List, Optional, Tuple

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QAbstractItemView, QLineEdit, QListWidget, QListWidgetItem

from components.mention_autocomplete.options import (
    is_autocomplete_enabled,
    is_recent_shown,
    recent_limit,
    suggestion_limit,
)
from core.state.recent_mentions import get_recent_mentions, remember_mention
from helpers.cache import get_cache
from helpers.fonts.fonts import FontType, set_font_role


_POPUP_WIDTH = 260
_POPUP_GAP = 4
_MENTION_PATTERN = re.compile(r"(?<!\S)@([^\s@]*)$")
_ARROW_STEPS = {Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1}
_CTRL_STEP_KEYS = {Qt.Key.Key_N: 1, Qt.Key.Key_P: -1}


def find_mention(text: str, cursor: int) -> Optional[Tuple[int, str]]:
    """The @prefix that ends at the cursor as (index of the @, prefix), or None."""
    match = _MENTION_PATTERN.search(text, 0, cursor)
    return (match.start(), match.group(1)) if match else None


class MentionAutocomplete(QObject):
    """Suggestion list above a QLineEdit; while it is open it owns Tab, Up, Down, Ctrl+N, Ctrl+P and Esc.

    A bare @ lists the recently inserted nicknames, @ and some letters lists the matching nicknames.
    """

    _active: Optional["MentionAutocomplete"] = None  # only the focused input shows suggestions

    @classmethod
    def is_open(cls) -> bool:
        """Whether suggestions are on screen; the global hotkeys then leave the keys to the input."""
        return cls._active is not None

    def __init__(self, field: QLineEdit, config):
        super().__init__(field)
        self._field = field
        self._config = config
        self._list: Optional[QListWidget] = None
        self._query: Optional[Tuple[int, str]] = None
        field.installEventFilter(self)
        field.textEdited.connect(self._refresh)
        field.cursorPositionChanged.connect(self._refresh)

    def _refresh(self, *_):
        if not self._field.hasFocus():
            return
        query = find_mention(self._field.text(), self._field.cursorPosition())
        if query and not is_autocomplete_enabled(self._config):
            query = None
        if query == self._query:
            return
        self._query = query
        nicks = self._collect(query[1]) if query else []
        if nicks:
            self._show(nicks)
        else:
            self._close()

    def _collect(self, prefix: str) -> List[str]:
        if prefix:
            return get_cache().find_logins(prefix, suggestion_limit(self._config))
        return get_recent_mentions()[:recent_limit(self._config)] if is_recent_shown(self._config) else []

    def _show(self, nicks: List[str]):
        suggestions = self._ensure_list()
        suggestions.clear()
        suggestions.addItems(nicks)
        suggestions.setCurrentRow(0)  # the newest recent nickname is ready for Tab
        suggestions.setFixedSize(
            _POPUP_WIDTH, suggestions.sizeHintForRow(0) * len(nicks) + 2 * suggestions.frameWidth()
        )
        origin = self._field.mapTo(self._field.window(), QPoint(0, 0))
        suggestions.move(origin.x(), max(0, origin.y() - suggestions.height() - _POPUP_GAP))
        suggestions.show()
        suggestions.raise_()
        MentionAutocomplete._active = self

    def _ensure_list(self) -> QListWidget:
        if self._list is None:
            self._list = QListWidget(self._field.window())
            self._list.setObjectName("mentionList")
            set_font_role(self._list, FontType.TEXT)
            self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self._list.setMouseTracking(True)
            self._list.itemEntered.connect(self._list.setCurrentItem)
            self._list.itemClicked.connect(self._accept)
        return self._list

    def _close(self):
        self._query = None
        if self._list is not None:
            self._list.hide()
        if MentionAutocomplete._active is self:
            MentionAutocomplete._active = None

    def _step(self, step: int):
        self._list.setCurrentRow((self._list.currentRow() + step) % self._list.count())

    def _accept(self, item: Optional[QListWidgetItem] = None):
        item = item or self._list.currentItem()
        start = self._query[0]
        cursor = self._field.cursorPosition()
        text = self._field.text()
        separator = ", " if start == 0 else " "  # a nick at the very start addresses the message
        inserted = item.text() + separator
        remember_mention(item.text())
        self._field.setText(text[:start] + inserted + text[cursor:])
        self._field.setCursorPosition(start + len(inserted))
        self._close()
        self._field.setFocus()

    def _handle_key(self, event: QKeyEvent) -> bool:
        key = event.key()
        modifiers = event.modifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            step = _CTRL_STEP_KEYS.get(key) or _CTRL_STEP_KEYS.get(event.nativeVirtualKey())
            if not step:
                return False
            self._step(step)
        elif key == Qt.Key.Key_Backtab:
            self._step(-1)
        elif modifiers != Qt.KeyboardModifier.NoModifier:
            return False
        elif key == Qt.Key.Key_Tab:
            self._accept()
        elif key == Qt.Key.Key_Escape:
            self._close()
        elif key in _ARROW_STEPS:
            self._step(_ARROW_STEPS[key])
        else:
            return False
        return True

    def eventFilter(self, watched, event):
        event_type = event.type()
        if event_type == QEvent.Type.KeyPress and MentionAutocomplete._active is self:
            return self._handle_key(event)
        if event_type in (QEvent.Type.FocusOut, QEvent.Type.Hide):
            self._close()
        return False

"""ChatWindow: shared emoticon selector placement and insertion."""

from PyQt6.QtCore import QTimer

from ui.chat.ui_emoticon_selector import PANEL_WIDTH


class ChatEmoticonsMixin:
    """ChatWindow: shared emoticon selector placement and insertion."""

    def _reclaim_emoticon_selector(self):
        """Take back the selector from a popup that borrowed it, cleaning up that popup's layout."""
        self.emoticon_selector.attach(self, self.on_emoticon_selected)

    def toggle_emoticon_selector(self):
        """Toggle emoticon selector - reclaim from notification if borrowed, then toggle."""
        if not hasattr(self, 'emoticon_selector'):
            return
        if self.emoticon_selector.parent() is not self:
            self._reclaim_emoticon_selector()
        # _position_emoticon_selector resets fixedSize, clearing any height set by a notification
        self.emoticon_selector.toggle_visibility()
        self.position_emoticon_selector()

        # Take focus on ChatWindow so the selector's scroll area doesn't swallow arrow keys
        if self.emoticon_selector.isVisible():
            self.active_input_field().clearFocus()
            self.setFocus()

    def active_input_field(self):
        """Input that should receive typed/emoticon text."""
        room = self.current_room()
        if room is not None and getattr(room, 'input_field', None) is not None:
            if room.input_field.hasFocus() or not self.input_field.hasFocus():
                return room.input_field
        return self.input_field

    def active_emoticon_button(self):
        """Emoticon button of the active room (game tab or General)."""
        room = self.current_room()
        if room is not None and getattr(room, 'emoticon_button', None) is not None:
            return room.emoticon_button
        return self.emoticon_button

    def on_emoticon_selected(self, emoticon_name: str):
        """Insert emoticon into the active input field."""
        field = self.active_input_field()
        cursor_pos = field.cursorPosition()
        current_text = field.text() or ""
        emoticon_code = f":{emoticon_name}: "
        field.setText(current_text[:cursor_pos] + emoticon_code + current_text[cursor_pos:])
        field.setCursorPosition(cursor_pos + len(emoticon_code))
        QTimer.singleShot(0, self._refocus_if_selector_closed)

    def _refocus_if_selector_closed(self):
        if not (hasattr(self, 'emoticon_selector') and self.emoticon_selector.isVisible()):
            self.active_input_field().setFocus()

    def position_emoticon_selector(self):
        """Place selector aligned to the active room's emoticon button."""
        if not hasattr(self, 'emoticon_selector'):
            return

        # Moving a selector borrowed by a notification popup corrupts that popup layout
        if self.emoticon_selector.parent() is not self:
            return

        # Clamp size to available space
        available = max(200, self.height() - self.input_container.height() - 40)
        h = max(250, min(650, available))
        w = PANEL_WIDTH
        self.emoticon_selector.setFixedSize(w, h)

        # The General button sits in a hidden tab while a game room is active, so its geometry can be stale
        button = self.active_emoticon_button()
        button_top_right = self.mapFromGlobal(button.mapToGlobal(button.rect().topRight()))
        x = button_top_right.x() - w
        y = max(16, button_top_right.y() - h - 8)
        x = max(8, min(x, self.width() - w - 8))

        self.emoticon_selector.move(x, y)
        self.emoticon_selector.raise_()

    def on_room_emoticon_requested(self, widget=None):
        room = widget or self.current_room()
        if room and room.input_field:
            room.input_field.setFocus()
        self.toggle_emoticon_selector()

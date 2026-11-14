"""ChatWindow: font family and size changes."""

from PyQt6.QtCore import QTimer

from helpers.fonts.fonts import FontType, get_font, refresh_font_roles


class ChatFontsMixin:
    """ChatWindow: font family and size changes."""

    def on_font_family_changed(self):
        """Apply font family change immediately (no debounce)."""
        self._apply_font_size_change()
        tracker_widget = getattr(self, 'user_tracker_widget', None)
        if tracker_widget:
            tracker_widget.refresh_fonts()  # its row delegate paints with its own fonts

    def on_font_size_changed(self):
        """Handle font size changes from font scaler - refresh all text"""
        # Debounce: restart timer on every call so rapid slider moves only
        # trigger one full rebuild 80 ms after the last movement.
        if not hasattr(self, '_font_size_timer'):
            self._font_size_timer = QTimer(self)
            self._font_size_timer.setSingleShot(True)
            self._font_size_timer.timeout.connect(self._apply_font_size_change)
        self._font_size_timer.start(80)

    def _apply_font_size_change(self):
        """Push a changed font setting into the widgets that do not follow the application font."""
        # The UI font reaches every widget through the application font; role widgets (text, header) are refreshed here
        refresh_font_roles()

        # Message views paint with delegate fonts and cache row geometry
        text_font = get_font(FontType.TEXT)
        message_widgets = [
            self.messages_widget, self.presence_log_widget,
            self.chatlog_widget, self.chatlog_split_widget,
        ]
        message_widgets.extend(
            room.messages_widget for room in self.all_room_widgets() if room and room.messages_widget
        )
        for widget in message_widgets:
            if widget:
                widget.delegate.set_fonts(text_font)

        if getattr(self, 'settings_widget', None) and hasattr(self.settings_widget, 'update_font_preview'):
            self.settings_widget.update_font_preview()

        profile_widget = getattr(self, 'profile_widget', None)
        if profile_widget:
            if getattr(profile_widget, 'history_widget', None):
                profile_widget.history_widget.adjust_height()
            if hasattr(profile_widget, 'cards_data'):
                profile_widget.rebuild_card_layout(getattr(profile_widget, 'last_cols', 3))

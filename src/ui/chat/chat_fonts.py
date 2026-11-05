"""ChatWindow: font family and size changes."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTextEdit,
)

from helpers.fonts.fonts import FontType, get_font, get_userlist_width


class ChatFontsMixin:
    """ChatWindow: font family and size changes."""

    def on_font_family_changed(self):
        """Apply font family change immediately (no debounce)."""
        self._apply_font_size_change()

    def on_font_size_changed(self):
        """Handle font size changes from font scaler - refresh all text"""
        # Debounce: restart timer on every call so rapid slider moves only
        # trigger one full rebuild 80 ms after the last movement.
        if not hasattr(self, '_font_size_timer'):
            self._font_size_timer = QTimer(self)
            self._font_size_timer.setSingleShot(True)
            self._font_size_timer.timeout.connect(self._apply_font_size_change)
        self._font_size_timer.start(80)

    @staticmethod
    def _set_font_on_tree(root, font, header_font=None, text_font=None):
        """Apply font to root and children. Respects fontRole: header / text."""
        if root is None:
            return
        types = (QLabel, QCheckBox, QComboBox, QLineEdit, QSpinBox,
                 QTextEdit, QAbstractButton, QGroupBox)
        root.setFont(font)
        for w in root.findChildren(types):
            role = w.property("fontRole")
            if role == "header" and header_font is not None:
                w.setFont(header_font)
            elif role == "text" and text_font is not None:
                w.setFont(text_font)
            else:
                w.setFont(font)
        root.update()

    def _apply_font_size_change(self):
        """Actually apply font size / family change"""
        new_font = get_font(FontType.TEXT)
        ui_font = get_font(FontType.UI)

        # Update message delegates AND their renderers (general + chatlog + game rooms)
        message_widgets = [
            self.messages_widget, self.presence_log_widget,
            self.chatlog_widget, self.chatlog_split_widget,
        ]
        all_room_widgets = self._all_room_widgets()
        message_widgets.extend(
            room.messages_widget for room in all_room_widgets if room and room.messages_widget
        )
        for widget in message_widgets:
            if widget:
                widget.delegate.body_font = new_font
                widget.delegate.timestamp_font = new_font
                if widget.delegate.message_renderer:
                    widget.delegate.message_renderer.body_font = new_font
                widget.force_recalculate()

        # Update message input fields (general + game rooms + custom rooms)
        if self.input_field:
            self.input_field.setFont(new_font)
        for room in all_room_widgets:
            if room and room.input_field:
                room.input_field.setFont(new_font)

        # Update userlist widgets (general + game rooms + custom rooms)
        def _update_userlist_fonts(ul, fixed_width=False):
            if not ul:
                return
            ul.chat_label.setFont(new_font)
            ul.game_label.setFont(new_font)
            for user_widget in ul.user_widgets.values():
                user_widget.username_label.setFont(new_font)
                if user_widget.game_counter_label:
                    user_widget.game_counter_label.setFont(new_font)
            if fixed_width:
                ul.setFixedWidth(get_userlist_width())
            ul.update()

        _update_userlist_fonts(self.user_list_widget)

        for room in all_room_widgets:
            if room:
                _update_userlist_fonts(room.user_list_widget)

        if self.chatlog_userlist_widget:
            for user_widget in self.chatlog_userlist_widget.user_widgets.values():
                user_widget.username_label.setFont(new_font)
                user_widget.count_label.setFont(new_font)
            self.chatlog_userlist_widget.update()

        # Stacked pages
        header_font = get_font(FontType.HEADER)
        if getattr(self, 'settings_widget', None):
            self._set_font_on_tree(self.settings_widget, ui_font, header_font, new_font)
            if hasattr(self.settings_widget, 'update_font_preview'):
                self.settings_widget.update_font_preview()

        if getattr(self, 'ban_list_widget', None):
            self._set_font_on_tree(self.ban_list_widget, new_font, header_font)

        if getattr(self, 'user_tracker_widget', None):
            self._set_font_on_tree(self.user_tracker_widget, new_font, header_font)

        if getattr(self, 'pronunciation_widget', None):
            self._set_font_on_tree(self.pronunciation_widget, new_font, header_font)

        if getattr(self, 'profile_widget', None):
            self._set_font_on_tree(self.profile_widget, new_font, header_font)
            pw = self.profile_widget
            if getattr(pw, 'history_widget', None):
                pw.history_widget.adjust_height()
            if hasattr(pw, 'cards_data'):
                pw.rebuild_card_layout(getattr(pw, 'last_cols', 3))

        if getattr(self, 'parser_widget', None):
            self._set_font_on_tree(self.parser_widget, new_font, header_font)

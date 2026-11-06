"""ChatWindow: private conversation mode and input styling."""

from PyQt6.QtCore import QTimer

from components.button import create_icon_button
from helpers.colors.color_utils import (
    get_input_colors,
    get_private_message_colors,
    get_self_ban_colors,
)
from helpers.translate import tr
from ui.messages.messages_separator import NewMessagesSeparator


class ChatPrivateModeMixin:
    """ChatWindow: private conversation mode and input styling."""

    def enter_private_mode(self, jid: str, username: str, user_id: str):
        """Enter private chat mode with a user"""
        self._ensure_general_tab_visible()
        self.private_mode = True
        # Prefer explicit private recipient JID (user_id#username@domain/web) for private messages
        private_recipient_jid = jid
        if user_id and username:
            domain = None
            # Prefer XMPP client configured domain if available
            if hasattr(self, 'xmpp_client') and self.xmpp_client and getattr(self.xmpp_client, 'domain', None):
                domain = self.xmpp_client.domain
            else:
                # Fallback: try to extract domain from the provided jid
                if '@' in jid:
                    try:
                        domain = jid.split('@', 1)[1].split('/')[0]
                    except Exception:
                        domain = None
            if domain:
                private_recipient_jid = f"{user_id}#{username}@{domain}/web"

        self.private_chat_jid = private_recipient_jid
        self.private_chat_username = username
        self.private_chat_user_id = user_id

        # Clear input field
        self.input_field.clear()

        # Create exit button if it doesn't exist
        if self.exit_private_button is None:
            self.exit_private_button = create_icon_button(
                self.icons_path, "close.svg", "", config=self.config
            )
            self.tr_set(self.exit_private_button.setToolTip, "Exit Private Chat", "Выйти из приватного чата")
            self.exit_private_button.clicked.connect(self.exit_private_mode)

            # Insert after emoticon button
            emoticon_button_index = self.input_top_layout.indexOf(self.emoticon_button)
            self.input_top_layout.insertWidget(emoticon_button_index + 1, self.exit_private_button)
        else:
            self.exit_private_button.setVisible(True)

        # Update UI
        self.update_input_style()

        # Focus input for immediate typing — deferred so userlist click doesn't steal it back
        QTimer.singleShot(0, self.input_field.setFocus)

        # Update window title
        self.set_connection_status(self._connection_status)

        print(f"🔒 Entered private mode with {username}")

    def exit_private_mode(self):
        """Exit private chat mode"""
        if self.config.get("ui", "clear_private_messages_on_exit"):
            self._clear_private_messages()

        self.private_mode = False
        self.private_chat_jid = None
        self.private_chat_username = None
        self.private_chat_user_id = None

        # Remove and destroy exit button
        if self.exit_private_button is not None:
            # Remove from layout and destroy
            self.input_top_layout.removeWidget(self.exit_private_button)
            self.exit_private_button.deleteLater()
            self.exit_private_button = None

        # Update UI
        self.update_input_style()

        # Restore window title
        self.set_connection_status(self._connection_status)

        print("🔓 Exited private mode")
        self._restore_room_tab()

    def _clear_private_messages(self):
        """Clear all private messages from the messages widget"""
        self.messages_widget.clear_private_messages()

    def clear_new_messages_marker(self):
        if self.has_new_messages_marker:
            NewMessagesSeparator.remove_from_model(self.messages_widget.model)
            self.has_new_messages_marker = False

    def update_input_style(self):
        """Private mode (main input) > self-ban (every input) > default"""
        is_dark = self.theme_manager.is_dark()
        ban_left = self._self_ban_left()
        ban_style = (get_self_ban_colors(self.config, is_dark),
                     self.self_ban.placeholder(ban_left, self._self_ban_total)) if ban_left is not None else None

        default_style = (get_input_colors(self.config, is_dark), "")
        main_style = default_style
        if self.private_mode:
            main_style = (get_private_message_colors(self.config, is_dark),
                          tr(f"Private message to {self.private_chat_username}", f"Приватное сообщение для {self.private_chat_username}"))
        elif ban_style:
            main_style = ban_style

        self._style_input(self.input_field, main_style)
        for room in (*self.game_rooms.values(), *self.custom_rooms.values()):
            self._style_input(room.input_field, ban_style or default_style)

    @staticmethod
    def _style_input(field, style):
        colors, placeholder = style
        sheet = f"""
            QLineEdit {{
                background-color: {colors.get("input_bg_idle", colors["input_bg"])};
                color: {colors["text"]};
                border: 2px solid {colors["input_border"]};
                border-radius: 4px;
                padding: 8px;
                selection-background-color: {colors["selection_bg"]};
                selection-color: {colors["selection_text"]};
            }}
            QLineEdit:focus {{
                background-color: {colors["input_bg"]};
            }}
        """
        if field.styleSheet() != sheet:
            field.setStyleSheet(sheet)
        field.setPlaceholderText(placeholder)

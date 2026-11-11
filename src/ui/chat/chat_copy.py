"""ChatWindow: copy messages from the currently displayed message view."""

from PyQt6.QtWidgets import QApplication

from components.button import animate_button_bounce


class ChatCopyMixin:
    """ChatWindow: copy all messages of the active live chat, chatlog or parser view."""

    def copy_messages_from_current_view(self) -> None:
        """Copy every message of the current view to the clipboard and bounce the copy button."""
        if self.stacked_widget.currentWidget() == self.messages_splitter:
            source_widget = self.get_hovered_chatlog_widget() or self.active_messages_widget()
        else:
            source_widget = self.chatlog_for_hotkey()

        if source_widget is None:
            return

        text, message_count = source_widget.copy_all_messages_text()
        if message_count:
            QApplication.clipboard().setText(text)
            animate_button_bounce(self.button_panel.copy_messages_button)

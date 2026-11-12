"""ChatWindow: copy messages from the currently displayed message view."""

from PyQt6.QtWidgets import QApplication

from components.button import animate_button_bounce
from components.toast import ToastKind
from helpers.translate import tr


class ChatCopyMixin:
    """ChatWindow: copy all messages of the active live chat, chatlog or parser view."""

    def copy_messages_from_current_view(self) -> None:
        """Copy every message of the current view to the clipboard; confirm with a toast and a bounce of the copy button."""
        if self.stacked_widget.currentWidget() == self.messages_splitter:
            source_widget = self.get_hovered_chatlog_widget() or self.active_messages_widget()
        else:
            source_widget = self.chatlog_for_hotkey()

        text, message_count = source_widget.copy_all_messages_text() if source_widget else ("", 0)
        if not message_count:
            self.toast.show_message(tr("Nothing to copy", "Нечего копировать"), ToastKind.WARNING)
            return

        QApplication.clipboard().setText(text)
        animate_button_bounce(self.button_panel.copy_messages_button)
        self.toast.show_message(
            tr(f"Messages copied: {message_count}", f"Скопировано сообщений: {message_count}"), ToastKind.SUCCESS,
        )

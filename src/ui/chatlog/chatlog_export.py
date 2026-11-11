"""ChatlogWidget: copying and saving the shown messages."""

from datetime import datetime

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from helpers.data import get_data_dir
from helpers.text.message_format import format_message_line
from helpers.translate import tr


class ChatlogExportMixin:
    """ChatlogWidget: copying and saving the shown messages."""

    @staticmethod
    def count_messages(messages) -> int:
        return sum(1 for m in messages if not m.is_separator)

    def message_count(self) -> int:
        return self.count_messages(self.all_messages)

    def _messages_for_export(self):
        """Messages currently backing Copy/Save: filtered results if a search or
        filter is active, otherwise the full parsed log."""
        if not self.has_active_search_or_filter():
            return self.all_messages
        search_users, search_message, is_prefix_mode = self.parse_current_search_text()
        return self.filter_messages(self.all_messages, search_users, search_message, is_prefix_mode)

    def _format_messages_export(self, messages):
        text_lines = []
        message_count = 0
        for msg in messages:
            if msg.is_separator:
                if text_lines:
                    text_lines.append("")
                text_lines.append(f"{'='*60}")
                text_lines.append(f" {msg.date_str}")
                text_lines.append(f"{'='*60}")
                text_lines.append("")
            else:
                text_lines.append(format_message_line(msg.username, msg.body, msg.timestamp))
                message_count += 1
        while text_lines and text_lines[-1] == "":
            text_lines.pop()
        return '\n'.join(text_lines), message_count

    def update_copy_save_tooltips(self):
        kind = (
            tr("filtered results", "отфильтрованные результаты")
            if self.has_active_search_or_filter()
            else tr("results", "результаты")
        )
        self.parser_widget.copy_button.setToolTip(tr(
            f"Copy {kind} to clipboard (Ctrl+C)",
            f"Копировать {kind} в буфер (Ctrl+C)")
        )
        self.parser_widget.save_button.setToolTip(tr(
            f"Save {kind} to file (Ctrl+S)",
            f"Сохранить {kind} в файл (Ctrl+S)")
        )

    def copy_all_messages_text(self):
        """Return the text and count of messages currently shown in the chatlog or parser."""
        return self._format_messages_export(self._messages_for_export())

    def on_copy_results(self):
        messages = self._messages_for_export()
        if not messages:
            QMessageBox.information(self,
                tr("No Results", "Нет результатов"),
                tr("No messages to copy.", "Нет сообщений для копирования.")
            )
            return
        result, message_count = self._format_messages_export(messages)
        QApplication.clipboard().setText(result)
        QMessageBox.information(self,
            tr("Copied", "Скопировано"),
            tr(
                f"Copied {message_count} messages to clipboard.",
                f"Скопировано {message_count} сообщений в буфер.")
            )

    def on_save_results(self):
        messages = self._messages_for_export()
        if not messages:
            QMessageBox.information(self,
                tr("No Results", "Нет результатов"),
                tr("No messages to save.", "Нет сообщений для сохранения.")
            )
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_dir = get_data_dir("exports")
        default_filename = default_dir / f"chatlog_export_{timestamp}.txt"

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Chat Log",
            str(default_filename),
            "Text Files (*.txt);;All Files (*)"
        )
        if not filename:
            return

        try:
            result, message_count = self._format_messages_export(messages)
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(result)
            QMessageBox.information(self,
                tr("Saved", "Сохранено"),
                tr(
                    f"Saved {message_count} messages to:\n{filename}",
                    f"Сохранено {message_count} сообщений в:\n{filename}")
                )
        except Exception as e:
            QMessageBox.critical(self,
                tr("Error", "Ошибка"),
                tr(f"Failed to save file:\n{e}", f"Не удалось сохранить файл:\n{e}")
            )

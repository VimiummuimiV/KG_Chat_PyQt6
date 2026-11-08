"""ChatlogWidget: parser mode and parse progress handling."""

from datetime import datetime

from PyQt6.QtWidgets import QMessageBox

from components.button import set_button_icon
from core.chatlogs.range_parser import ParseConfig
from helpers.deferred import call_later
from helpers.scroll.scroll import scroll
from helpers.translate import tr
from ui.chatlog.parser_worker import ParserWorker
from ui.messages.message_model import MessageData
from ui.settings.settings_options import DEFAULTS


_LIMIT_EXCEEDED_SUFFIX_EN = "Rendering disabled. Use Copy/Save buttons."
_LIMIT_EXCEEDED_SUFFIX_RU = "Отрисовка отключена. Используйте кнопки Копировать/Сохранить."


class ChatlogParserControlsMixin:
    """ChatlogWidget: parser mode and parse progress handling."""

    def toggle_parser(self):
        """Toggle between normal view and parser config"""
        if self.parser_visible:
            # Hide parser, show list
            self.parser_visible = False
            self.stacked.setCurrentWidget(self.list_view)
            set_button_icon(self.parse_btn, "play.svg")
            self.parse_btn.setToolTip(
                tr(
                    "Parse all chatlogs (P | Ctrl+P from anywhere)",
                    "Парсить все чатлоги (P | Ctrl+P откуда угодно)"
                  )
            )
            # Parser results can span multiple dates, so keep "Parser" instead of a single stale date
            if self.is_parsing:
                self.date_label.setText(tr("Parser", "Парсер"))
            else:
                self.update_date_display()
        else:
            # Show parser, hide list
            self.parser_visible = True
            self.stacked.setCurrentWidget(self.parser_widget)
            set_button_icon(self.parse_btn, "list.svg")
            self.parse_btn.setToolTip(tr("Back to chat logs (P)", "Назад к чатлогам (P)"))
            self.date_label.setText(tr("Parser", "Парсер"))

        # The "Loaded N messages" status belongs to the chatlog list, not the parser config screen
        self.info_label.setVisible(not self.parser_visible)

    def set_parsing_mode(self, value: bool):
        self.is_parsing = value
        self.update_confirm_search_button()

    def _live_search_max_messages(self) -> int:
        value = self.config.get("ui", "chatlog", "live_search_max_messages")
        if value is None:
            return DEFAULTS["chatlog"]["live_search_max_messages"]
        return max(
            DEFAULTS["chatlog"]["live_search_max_messages_min"],
            min(DEFAULTS["chatlog"]["live_search_max_messages_max"], int(value)),
        )

    def requires_confirmed_search(self) -> bool:
        return self.message_count() > self._live_search_max_messages()

    def update_confirm_search_button(self):
        self.confirm_search_btn.setVisible(self.requires_confirmed_search())

    def max_messages_limit(self) -> int:
        value = self.config.get("ui", "chatlog", "max_messages")
        if value is None:
            return DEFAULTS["chatlog"]["max_messages"]
        return max(
            DEFAULTS["chatlog"]["max_messages_min"],
            min(DEFAULTS["chatlog"]["max_messages_max"], int(value)),
        )

    def apply_max_messages_limit(self):
        """Apply current config limit to the model; re-render if already loaded."""
        limit = self.max_messages_limit()
        self.model.max_messages = limit
        if self.is_parsing or not self.all_messages:
            return
        count = self.message_count()
        if count > limit:
            self.model.clear()
            self.info_label.setText(
                tr(
                    f"⚠️ {count:,} messages (limit: {limit:,}) - {_LIMIT_EXCEEDED_SUFFIX_EN}",
                    f"⚠️ {count:,} сообщений (лимит: {limit:,}) - {_LIMIT_EXCEEDED_SUFFIX_RU}"
                  )
            )
        else:
            self.apply_filter()

    def set_parser_youtube_off(self, off: bool):
        """Parser bulk views never expand YouTube links (config is ignored)."""
        renderer = getattr(self.delegate, "message_renderer", None)
        if renderer is not None:
            renderer.set_youtube_override(False if off else None)

    def on_parse_started(self, config: ParseConfig):
        """Start parsing with given config"""
        self.set_parsing_mode(True)
        self.exceeded_max_messages = False
        self.date_label.setText(tr("Parser", "Парсер"))
        if config.mode != 'syncdatabase':
            self.set_parser_youtube_off(True)

        # Only clear UI for non-sync modes
        if config.mode != 'syncdatabase':
            self.model.clear()
            self.all_messages = []
            self.temp_parsed_messages = []
            self.last_parsed_date = None
            self.update_confirm_search_button()
        else:
            self.info_label.setText(tr("Syncing database...", "Синхронизация базы..."))

        self.parser_worker = ParserWorker(config)
        self.parser_worker.progress.connect(self.parser_widget.update_progress)

        # Only connect messages_found for non-sync modes
        if config.mode != 'syncdatabase':
            self.parser_worker.messages_found.connect(self._on_parsed_messages)

        # Connect sync_stats signal
        self.parser_worker.sync_stats.connect(self._on_sync_complete)

        self.parser_worker.finished.connect(self._on_parse_finished)
        self.parser_worker.error.connect(self._on_parse_error)

        if self.parent_window:
            self.parser_worker.progress.connect(self.parent_window.update_parse_progress)
            self.parser_worker.finished.connect(lambda m: self.parent_window.on_parse_finished())
            self.parser_worker.error.connect(lambda e: self.parent_window.on_parse_error(e))

        self.parser_worker.start()

    def on_parse_cancelled(self):
        """Cancel parsing"""
        if self.parser_worker:
            self.parser_worker.stop()
            self.parser_worker = None
        self.parser_cancelled = True
        self.parser_widget.reset_ui()

        # Check if in sync mode
        is_sync = hasattr(self.parser_widget, 'is_sync_mode') and self.parser_widget.is_sync_mode

        if is_sync:
            self.info_label.setText(tr("Database sync cancelled", "Синхронизация базы отменена"))
        else:
            # Normal mode - add partial messages if any
            if self.temp_parsed_messages:
                self.list_view.setUpdatesEnabled(False)
                self.all_messages = self.temp_parsed_messages
                self.temp_parsed_messages = []
                self.model.set_messages(self.all_messages)
                self.list_view.setUpdatesEnabled(True)
                self.update_confirm_search_button()
                non_separator_messages = [m for m in self.all_messages if not m.is_separator]
                self.messages_loaded.emit(non_separator_messages)
                self.parser_widget.show_copy_save_buttons()
                self.update_copy_save_tooltips()
                call_later(self, 100, lambda: scroll(self.list_view, mode="top", delay=50))
                message_count = len(non_separator_messages)
                self.info_label.setText(tr(
                    f"Found {message_count} messages (partial)",
                    f"Найдено {message_count} сообщений (частично)")
                )
            else:
                self.info_label.setText(tr("Parsing cancelled", "Парсинг отменён"))
                self.set_parsing_mode(False)

        if self.parent_window:
            self.parent_window.stop_parse_status()

    def _on_parsed_messages(self, messages, date: str):
        """Handle incrementally parsed messages - ONLY update counter, not layout"""
        # Only add separator and messages if we actually have messages
        if not messages:
            return # Skip empty dates entirely

        # ALWAYS add separator when date changes OR when it's the first date
        if self.last_parsed_date is None or date != self.last_parsed_date:
            # Add separator to temp storage
            separator = MessageData(datetime.now(), "", "", is_separator=True, date_str=date)
            self.temp_parsed_messages.append(separator)
            self.last_parsed_date = date

        # Convert ChatMessage to MessageData - msg already has all fields
        for msg in messages:
            try:
                t = datetime.strptime(msg.timestamp, "%H:%M:%S").time()
                timestamp = datetime.combine(datetime.strptime(date, "%Y-%m-%d").date(), t)
                msg_data = MessageData(timestamp, msg.username, msg.message, None, msg.username)
                self.temp_parsed_messages.append(msg_data)
            except Exception as e:
                print(f"Error processing message: {e}")

        # Check if exceeded limit
        message_count = sum(1 for m in self.temp_parsed_messages if not m.is_separator)
        if message_count > self.model.max_messages and not self.exceeded_max_messages:
            self.exceeded_max_messages = True
            self.info_label.setText(tr(
                f"⚠️ Exceeded {self.model.max_messages:,} message limit - {_LIMIT_EXCEEDED_SUFFIX_EN}",
                f"⚠️ Превышен лимит {self.model.max_messages:,} сообщений - {_LIMIT_EXCEEDED_SUFFIX_RU}")
            )
        elif not self.exceeded_max_messages:
            self.info_label.setText(tr(
                f"Found {message_count:,} messages so far...",
                f"Найдено {message_count:,} сообщений...")
            )

    def _on_parse_finished(self, messages):
        """Handle parse completion - NOW add all messages to layout at once"""
        if self.parser_cancelled:
            self.parser_cancelled = False
            return

        self.parser_worker = None
        self.parser_widget.reset_ui()
        self.last_parsed_date = None

        # Check if this was a sync operation
        is_sync = hasattr(self.parser_widget, 'is_sync_mode') and self.parser_widget.is_sync_mode

        if is_sync:
            # Sync mode complete - info already updated in _on_sync_complete
            pass
        elif self.temp_parsed_messages:
            message_count = sum(1 for m in self.temp_parsed_messages if not m.is_separator)
            self.all_messages = self.temp_parsed_messages
            self.temp_parsed_messages = []
            self.update_confirm_search_button()

            # Skip rendering if exceeded limit
            if self.exceeded_max_messages:
                self.info_label.setText(tr(
                    f"⚠️ {message_count:,} messages found (limit: {self.model.max_messages:,}) - {_LIMIT_EXCEEDED_SUFFIX_EN}",
                    f"⚠️ Найдено {message_count:,} сообщений (лимит: {self.model.max_messages:,}) - {_LIMIT_EXCEEDED_SUFFIX_RU}")
                )
                self.exceeded_max_messages = False
            else:
                self.list_view.setUpdatesEnabled(False)
                self.model.set_messages(self.all_messages)
                self.list_view.setUpdatesEnabled(True)

                non_separator_messages = [m for m in self.all_messages if not m.is_separator]
                self.messages_loaded.emit(non_separator_messages)
                call_later(self, 100, lambda: scroll(self.list_view, mode="top", delay=50))

            self.parser_widget.show_copy_save_buttons()
            self.update_copy_save_tooltips()
        else:
            self.info_label.setText(tr("No messages found", "Сообщения не найдены"))

        if self.parent_window:
            self.parent_window.handle_parse_finished()

    def _on_sync_complete(self, fetched_count: int, db_stats: dict):
        """Handle sync database completion"""
        if fetched_count == 0:
            self.info_label.setText(tr(
                "✅ Database is already up to date",
                "✅ База уже актуальна")
            )
        else:
            self.info_label.setText(tr(
                f"✅ Synced {fetched_count} dates to database",
                f"✅ Синхронизировано {fetched_count} дат в базу")
            )

        # Show database stats
        QMessageBox.information(
            self,
            tr("Database Synced", "База синхронизирована"),
            tr(
                f"Successfully synced database!\n\n"
                f"Fetched: {fetched_count} dates\n"
                f"Total messages: {db_stats['total_messages']:,}\n"
                f"Cached dates: {db_stats['cached_dates']}\n"
                f"Database size: {db_stats['db_size_mb']} MB",
                f"База успешно синхронизирована!\n\n"
                f"Загружено: {fetched_count} дат\n"
                f"Всего сообщений: {db_stats['total_messages']:,}\n"
                f"Кэшированных дат: {db_stats['cached_dates']}\n"
                f"Размер базы: {db_stats['db_size_mb']} МБ"
            )
        )

    def _on_parse_error(self, error_msg: str):
        """Handle parse error"""
        if self.parser_cancelled:
            return
        self.parser_worker = None
        self.parser_widget.reset_ui()
        self.temp_parsed_messages = [] # Clear temp on error
        self.info_label.setText(tr(f"Error: {error_msg}", f"Ошибка: {error_msg}"))
        if self.parent_window:
            self.parent_window.stop_parse_status()

    def handle_error(self, error_msg: str):
        self.info_label.setText(error_msg)
        self.day_loaded.emit()

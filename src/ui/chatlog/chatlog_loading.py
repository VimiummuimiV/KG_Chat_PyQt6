"""ChatlogWidget: loading, displaying and navigating dates."""

import threading
from datetime import datetime, timedelta
from typing import Optional

from PyQt6.QtCore import QDate, Qt, QTimer
from PyQt6.QtWidgets import QCalendarWidget

from components.image_viewer.gallery import DayState
from core.chatlogs.fetch import ChatlogNotFoundError
from helpers.scroll.scroll import scroll
from helpers.translate import tr
from ui.messages.message_model import MessageData


class ChatlogLoadingMixin:
    """ChatlogWidget: loading, displaying and navigating dates."""

    def _on_repeat_timer(self):
        """Handle repeated navigation when button/mouse is held"""
        if self.repeat_direction is not None:
            self._navigate(self.repeat_direction)

    def navigate_hold(self, direction=None):
        """Start/stop hold navigation (None to stop, -1/1 to start)"""
        if direction is None:
            self.repeat_delay_timer.stop()
            self.repeat_timer.stop()
            self.repeat_direction = None
        else:
            self._navigate(direction)
            self.repeat_direction = direction
            self.repeat_delay_timer.start()  # Start delay before repeating

    def update_date_display(self):
        self.date_label.setText(self.current_date.strftime("%Y-%m-%d (%A)"))
        self.next_btn.setEnabled(self._can_navigate(1))
        self.prev_btn.setEnabled(self._can_navigate(-1))

    def _can_navigate(self, days: int) -> bool:
        return self.parser.MIN_DATE <= self.current_date + timedelta(days=days) <= datetime.now().date()

    def _day_state(self) -> Optional[DayState]:
        """Current day for the image viewer; None while parser results are shown."""
        if self.is_parsing:
            return None
        return DayState(self.current_date, self._can_navigate(-1), self._can_navigate(1))

    def load_date(self, date_str: str):
        try:
            self.current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            self.update_date_display()
            self.load_current_date()
        except Exception as e:
            self.info_label.setText(tr(f"Error: {e}", f"Ошибка: {e}"))

    def load_date_and_scroll(self, date_str: str, time_str: str = ""):
        """Load date_str, then, if time_str (HH:MM:SS) is given, scroll to and highlight that message"""
        current_date_str = self.current_date.strftime("%Y-%m-%d")
        if current_date_str == date_str and self.all_messages:
            if time_str:
                self._scroll_to_time(time_str)
            return

        if not time_str:
            self.load_date(date_str)
            return

        self.suppress_bottom_scroll = True

        def _on_loaded(stored_messages=None, t=time_str):
            self.messages_loaded.disconnect(_on_loaded)
            self._scroll_to_time(t)

        self.messages_loaded.connect(_on_loaded)
        self.load_date(date_str)

    def _scroll_to_time(self, time_str: str):
        """Scroll to and highlight the message matching time_str (HH:MM:SS) in the currently loaded date"""
        target_row = self._find_message_row(
            self.all_messages,
            lambda msg: msg.get_time_str() == time_str
        )
        if target_row is not None:
            self._scroll_and_highlight(target_row, scroll_delay=50, highlight_delay=200)

    def _scroll_to_bottom(self):
        """Scroll to bottom after a load, unless suppressed by a cross-date message search.
        Only auto-scrolls for today's log (where "latest" = bottom); for past dates the
        user reads top-to-bottom and scrolls down manually as needed."""
        if self.suppress_bottom_scroll:
            self.suppress_bottom_scroll = False
            return
        if self.current_date != datetime.now().date():
            return
        QTimer.singleShot(0, lambda: scroll(self.list_view, mode="bottom", delay=100))

    def load_current_date(self):
        """Load single date chatlog - this is NORMAL viewing"""
        self._set_parsing_mode(False)
        self._set_parser_youtube_off(False)
        self.model.clear()
        self.all_messages = []
        self._update_confirm_search_button()
        self.info_label.setText(tr("Loading...", "Загрузка..."))

        date_str = self.current_date.strftime("%Y-%m-%d")

        def _load():
            try:
                messages, was_truncated, from_cache = self.parser.get_messages(date_str)

                # Estimate size (no HTML to measure anymore)
                estimated_bytes = len(messages) * 100  # ~100 bytes per message average
                size_kb = estimated_bytes / 1024
                size_text = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"

                self._pending_data = (messages, size_text, was_truncated, from_cache)
                QTimer.singleShot(0, self._display_messages)
            except ChatlogNotFoundError:
                self._error_occurred.emit(f"No chatlog found for {date_str}")
            except ValueError as e:
                self._error_occurred.emit(str(e))
            except Exception as e:
                self._error_occurred.emit(f"Error: {e}")

        threading.Thread(target=_load, daemon=True).start()

    def _display_messages(self):
        """Display messages with ban filtering (except during parse mode)"""
        try:
            messages, size_text, was_truncated, from_cache = getattr(self, '_pending_data', ([], '', False, False))

            cache_marker = " 📁" if from_cache else ""
            filtered_ban_count = 0

            if not messages:
                self.info_label.setText(tr(
                    f"No messages · {size_text}{cache_marker}",
                    f"Нет сообщений · {size_text}{cache_marker}")
                )
                self.messages_loaded.emit([])
                self.list_view.setUpdatesEnabled(True)
                return

            # FILTER BANNED USERS if NOT in parse mode
            if self.ban_manager and not self.is_parsing:
                filtered_messages = []
                for msg in messages:
                    if not self.ban_manager.is_banned_by_username(msg.username):
                        filtered_messages.append(msg)
                    else:
                        filtered_ban_count += 1

                messages = filtered_messages

            # Batch operations
            self.list_view.setUpdatesEnabled(False)

            self.model.clear()
            self.all_messages = []

            if not messages:
                if filtered_ban_count > 0:
                    self.info_label.setText(tr(
                        f"No messages (all {filtered_ban_count} from banned users) · {size_text}{cache_marker}",
                        f"Нет сообщений (все {filtered_ban_count} от забаненных) · {size_text}{cache_marker}")
                    )
                else:
                    self.info_label.setText(tr(
                        f"No messages · {size_text}{cache_marker}",
                        f"Нет сообщений · {size_text}{cache_marker}")
                    )
                self.messages_loaded.emit([])
                self.list_view.setUpdatesEnabled(True)
                return

            message_data = []
            for msg in messages:
                try:
                    t = datetime.strptime(msg.timestamp, "%H:%M:%S").time()
                    timestamp = datetime.combine(self.current_date, t)
                    msg_data = MessageData(timestamp, msg.username, msg.message, None, msg.username)
                    message_data.append(msg_data)
                except Exception:
                    pass

            self.all_messages = message_data
            self._update_confirm_search_button()
            self._apply_filter()

            self.list_view.setUpdatesEnabled(True)

            # Update info label with ban filter info
            if was_truncated:
                info_text = tr(
                    f"⚠️ Loaded {len(messages)} messages (file truncated at {self.parser.MAX_FILE_SIZE_MB}MB limit) · {size_text}{cache_marker}",
                    f"⚠️ Загружено {len(messages)} сообщений (файл обрезан на {self.parser.MAX_FILE_SIZE_MB}МБ) · {size_text}{cache_marker}"
                )
            else:
                info_text = tr(
                    f"Loaded {len(messages)} messages · {size_text}{cache_marker}",
                    f"Загружено {len(messages)} сообщений · {size_text}{cache_marker}"
                )

            if filtered_ban_count > 0:
                info_text += tr(
                    f" · {filtered_ban_count} banned messages hidden",
                    f" · {filtered_ban_count} сообщений от забаненных скрыто"
                )

            if not (self.filtered_usernames or self.search_text):
                self.info_label.setText(info_text)

            self.messages_loaded.emit(message_data)
        except Exception as e:
            self.info_label.setText(tr(f"❌ Display error: {e}", f"❌ Ошибка отображения: {e}"))

    def _navigate(self, days):
        """Navigate by days offset (-1 for previous, +1 for next)"""
        if self._can_navigate(days):
            self.current_date += timedelta(days=days)
            self.update_date_display()
            self.load_timer.stop()
            self.load_timer.start(300)

    def show_calendar(self):
        calendar = QCalendarWidget()
        calendar.setWindowFlags(Qt.WindowType.Popup)
        calendar.setGridVisible(True)
        calendar.setMaximumDate(QDate.currentDate())

        min_qdate = QDate(self.parser.MIN_DATE.year, self.parser.MIN_DATE.month, self.parser.MIN_DATE.day)
        calendar.setMinimumDate(min_qdate)

        qdate = QDate(self.current_date.year, self.current_date.month, self.current_date.day)
        calendar.setSelectedDate(qdate)

        def on_date_selected(date: QDate):
            new_date = date.toPyDate()
            if new_date != self.current_date:
                self.current_date = new_date
                self.update_date_display()
                self.load_current_date()
            calendar.close()

        calendar.clicked.connect(on_date_selected)
        btn_pos = self.calendar_btn.mapToGlobal(self.calendar_btn.rect().bottomRight())
        x = btn_pos.x() - calendar.sizeHint().width()
        y = btn_pos.y() + (self.config.get("ui", "spacing", "widget_elements") or 6)
        calendar.move(x, y)
        calendar.show()

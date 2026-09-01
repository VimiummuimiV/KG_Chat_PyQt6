"""Chatlog viewer widget with virtual scrolling, search, and parser"""
from PyQt6.QtWidgets import(
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListView, QCalendarWidget, QLineEdit,
    QStackedWidget, QSplitter, QFileDialog, QMessageBox, QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, QDate, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import QFont
from datetime import datetime, timedelta
import threading
from pathlib import Path

from core.chatlogs import ChatlogsParser, ChatlogNotFoundError
from core.chatlogs_db import ChatMessage
from core.chatlogs_parser import ParseConfig, ChatlogsParserEngine
from helpers.mention_parser import parse_mentions
from helpers.create import create_icon_button, _render_svg_icon
from helpers.dates import parse_short_date, DATE_PLACEHOLDER
from helpers.emoticons import EmoticonManager
from helpers.scroll.scroll import scroll
from helpers.data import get_data_dir
from helpers.fonts import get_font, FontType
from helpers.scroll.scroll_buttons import ScrollButtonsPanel
from helpers.scroll.auto_scroll import AutoScroller
from helpers.scroll.scrollable_buttons import ScrollableButtonContainer
from helpers.message_interactions import MessageInteractions
from helpers.flash_highlight import FlashLabel
from ui.message_model import MessageListModel, MessageData
from ui.message_delegate import MessageDelegate
from ui.ui_chatlogs_parser import ChatlogsParserConfigWidget, ParserWorker
from ui.ui_settings import DEFAULTS
from components.search import MessageSearchBar, parse_search_text
from helpers.translate import tr, on_language_changed, TranslatableMixin

LIMIT_EXCEEDED_SUFFIX_EN = "Rendering disabled. Use Copy/Save buttons."
LIMIT_EXCEEDED_SUFFIX_RU = "Отрисовка отключена. Используйте кнопки Копировать/Сохранить."


class ChatlogWidget(TranslatableMixin, QWidget):
    """Chatlog viewer with virtual scrolling, search, and parser"""
    back_requested = pyqtSignal()
    messages_loaded = pyqtSignal(list)
    filter_changed = pyqtSignal(set)
    _error_occurred = pyqtSignal(str)

    def __init__(
        self,
        config,
        emoticon_manager,
        icons_path: Path,
        account=None,
        parent_window=None,
        ban_manager=None
        ):
        super().__init__()
        self._init_translatable()
        self.config = config
        self.emoticon_manager = emoticon_manager
        self.icons_path = icons_path
        self.account = account
        self.parent_window = parent_window
        self.ban_manager = ban_manager
        self.parser = ChatlogsParser()
        self.current_date = datetime.now().date()
        self.filtered_usernames = set()
        self.search_text = ""
        self.filter_mentions = False 
        self.all_messages = []
        self.last_parsed_date = None
        self.temp_parsed_messages = [] # Temp storage during parsing
        self.is_parsing = False  # Track if we're in parse mode
        self.exceeded_max_messages = False
        self.split_chatlog_widget = None  # Side pane showing full chatlog for a clicked date
        self.suppress_bottom_scroll = False  # Set before a load triggered by cross-date message search

        self.model = MessageListModel(max_messages=self._max_messages_limit())
        self.delegate = MessageDelegate(config, self.emoticon_manager)
        
        # Set username for mention highlighting if account is available
        if account and account.get('chat_username'):
            self.delegate.set_my_username(account.get('chat_username'))

        # Parser state
        self.parser_worker = None
        self.parser_visible = False
        self.parser_cancelled = False
        
        # Debounce timer for navigation
        self.load_timer = QTimer()
        self.load_timer.setSingleShot(True)
        self.load_timer.timeout.connect(self.load_current_date)
        
        # Repeat timer for holding mouse buttons
        self.repeat_timer = QTimer()
        self.repeat_timer.setInterval(100)  # Repeat every 100ms
        self.repeat_direction = None
        self.repeat_timer.timeout.connect(self._on_repeat_timer)
        
        # Delay timer before repeat starts
        self.repeat_delay_timer = QTimer()
        self.repeat_delay_timer.setSingleShot(True)
        self.repeat_delay_timer.setInterval(400)  # 400ms delay before repeat starts
        self.repeat_delay_timer.timeout.connect(self.repeat_timer.start)

        self._setup_ui()
        on_language_changed(self._retranslate)
    
        # Initialize auto-scroller after UI is set up
        self.auto_scroller = AutoScroller(self.list_view)
        
        # Connect message click handler
        self.delegate.message_clicked.connect(self._on_message_clicked)
        self.delegate.separator_clicked.connect(self._on_date_separator_clicked)
        self.delegate.timestamp_clicked.connect(lambda url: QApplication.clipboard().setText(url))
        self.delegate.chatlog_link_clicked.connect(self._on_chatlog_link_clicked)

        # Shared username click detection (same component MessagesWidget uses).
        # Timestamp clicks stay handled above via delegate.timestamp_clicked -
        # handle_timestamp=False keeps this component from also swallowing the
        # press for that region, which broke the copy-and-highlight behavior.
        # Exposed as self.interactions for callers to connect to directly.
        self.interactions = MessageInteractions(self.list_view, self.delegate, handle_timestamp=False)

    def set_account(self, account):
        """Update account for parser widget"""
        self.account = account
        if self.parser_widget:
            self.parser_widget.set_account(account)
        
        # Update delegate with new username for mention highlighting
        if account and account.get('chat_username'):
            self.delegate.set_my_username(account.get('chat_username'))

    def set_input_field(self, input_field, include_timestamp: bool = True):
        """Enable Reply and Paste options in message context menu"""
        if self.delegate:
            self.delegate.set_input_field(input_field, include_timestamp=include_timestamp)

    def _find_message_row(self, messages, predicate):
        return next(
            (i for i, msg in enumerate(messages)
             if not getattr(msg, 'is_separator', False) and predicate(msg)),
            None
        )

    def _scroll_and_highlight(self, target_row: int, scroll_delay: int = 50, highlight_delay: int = 200):
        """Scroll to target row and highlight it after a delay."""
        scroll(self.list_view, mode="middle", target_row=target_row, delay=scroll_delay)
        QTimer.singleShot(highlight_delay, lambda: self.delegate.highlight_row(target_row))

    def _highlight_in_split(self, timestamp):
        """Find a message by timestamp in the split pane (already showing the right date) and highlight it"""
        target_row = self._find_message_row(
            self.split_chatlog_widget.all_messages,
            lambda msg: msg.timestamp == timestamp
        )
        if target_row is not None:
            self.split_chatlog_widget._scroll_and_highlight(target_row, scroll_delay=50, highlight_delay=200)

    def _on_message_clicked(self, row: int):
        """Handle message click - reveal all messages and scroll to clicked message"""

        # Split view open → find message in the split chatlog and highlight it there,
        # loading that message's own date into the split pane first if it differs
        if self.split_chatlog_widget:
            clicked_msg = self.model.data(self.model.index(row, 0), Qt.ItemDataRole.DisplayRole)
            if clicked_msg and not getattr(clicked_msg, 'is_separator', False):
                if clicked_msg.timestamp.date() == self.split_chatlog_widget.current_date:
                    self._highlight_in_split(clicked_msg.timestamp)
                else:
                    def _on_loaded(_messages=None, ts=clicked_msg.timestamp):
                        self.split_chatlog_widget.messages_loaded.disconnect(_on_loaded)
                        self._highlight_in_split(ts)
                    self.split_chatlog_widget.messages_loaded.connect(_on_loaded)
                    self.split_chatlog_widget.suppress_bottom_scroll = True
                    self.split_chatlog_widget.load_date(clicked_msg.timestamp.strftime("%Y-%m-%d"))
            self.delegate.highlight_row(row)
            return
        
        # No active filters → simple direct scroll + highlight
        if not (self.filtered_usernames or self.search_text or self.filter_mentions):
            self._scroll_and_highlight(row, scroll_delay=50, highlight_delay=200)
            return

        # Filters are active → clear them and find message in full list
        clicked_msg = self.model.data(self.model.index(row, 0), Qt.ItemDataRole.DisplayRole)
        if not clicked_msg:
            return

        # Find corresponding row in unfiltered messages
        target_row = next((i for i, msg in enumerate(self.all_messages)
                        if not msg.is_separator 
                        and msg.username == clicked_msg.username
                        and msg.body == clicked_msg.body 
                        and msg.timestamp == clicked_msg.timestamp), None)

        if target_row is None:
            return

        # Clear filters
        self.filtered_usernames = set()
        self.search.clear()
    
        # Only update icon if it was actually active
        if self.filter_mentions:
            self.filter_mentions = False
            icon_name = "at-line.svg"
            self.mention_filter_btn._icon_name = icon_name
            icon = _render_svg_icon(self.mention_filter_btn._icon_path / icon_name, self.mention_filter_btn._icon_size)
            self.mention_filter_btn.setIcon(icon)

        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)

        # Scroll + highlight after the list has rebuilt
        QTimer.singleShot(100, lambda: self._scroll_and_highlight(
            target_row,
            scroll_delay=100,
            highlight_delay=250
        ))

    def _ensure_split_chatlog_widget(self):
        """Create (if needed) and return the split pane showing another date's chatlog"""
        if self.split_chatlog_widget is None:
            self.split_chatlog_widget = ChatlogWidget(
                self.config,
                self.emoticon_manager,
                self.icons_path,
                account=self.account,
                parent_window=self,
                ban_manager=self.ban_manager
            )
            self.split_chatlog_widget.back_btn.setToolTip(tr("Close split view", "Закрыть разделённый вид"))
            self.split_chatlog_widget.back_requested.connect(self._close_split_view)
            self.content_splitter.addWidget(self.split_chatlog_widget)
            self.content_splitter.setSizes([self.height() // 2, self.height() // 2])

            # Configure reply, compact mode, username clicks, etc.
            if self.parent_window:
                self.parent_window._configure_chatlog_widget(self.split_chatlog_widget)

        return self.split_chatlog_widget

    def _on_date_separator_clicked(self, date_str: str):
        """Open (or update) a split pane showing the full chatlog for the clicked date"""
        widget = self._ensure_split_chatlog_widget()
        if widget.current_date.strftime("%Y-%m-%d") == date_str and widget.all_messages:
            return
        widget.load_date(date_str)

    def _on_chatlog_link_clicked(self, date_str: str, time_str: str):
        """A chatlog URL inside a message body was clicked - open/update the split pane
        at that date, scrolling to and highlighting the linked message if a time was given"""
        self._ensure_split_chatlog_widget().load_date_and_scroll(date_str, time_str)

    def _on_info_label_clicked(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        text = self.info_label.text().strip()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.info_label.flash()
        event.accept()

    def _close_split_view(self):
        """Close the split pane showing a single date's full chatlog"""
        if not self.split_chatlog_widget:
            return
        widget = self.split_chatlog_widget
        self.split_chatlog_widget = None
        widget.cleanup()
        widget.setParent(None)
        widget.deleteLater()

    def _on_repeat_timer(self):
        """Handle repeated navigation when button/mouse is held"""
        if self.repeat_direction is not None:
            self._navigate(self.repeat_direction)
    
    def _navigate_hold(self, direction=None):
        """Start/stop hold navigation (None to stop, -1/1 to start)"""
        if direction is None:
            self.repeat_delay_timer.stop()
            self.repeat_timer.stop()
            self.repeat_direction = None
        else:
            self._navigate(direction)
            self.repeat_direction = direction
            self.repeat_delay_timer.start()  # Start delay before repeating
    
    def _setup_ui(self):
        spacing = self.config.get("ui", "spacing", "widget_elements") or 6
    
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        self.setLayout(layout)

        # Top bar container for responsive layout
        self.top_bar_container = QWidget()
        self.top_bar_layout = QVBoxLayout()
        self.top_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.top_bar_layout.setSpacing(spacing)
        self.top_bar_container.setLayout(self.top_bar_layout)
        layout.addWidget(self.top_bar_container)

        # Main horizontal bar (for wide screens)
        self.main_bar = QHBoxLayout()
        self.main_bar.setSpacing(spacing)
        self.main_bar.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.top_bar_layout.addLayout(self.main_bar)

        # Left side: Info block (date + status)
        self.info_block = QVBoxLayout()
        self.info_block.setSpacing(spacing)
        self.info_block.setAlignment(Qt.AlignmentFlag.AlignTop)
     
        # Date label
        self.date_label = QLabel()
        self.date_label.setFont(get_font(FontType.HEADER))
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_block.addWidget(self.date_label)
     
        # Info label
        self.info_label = FlashLabel(tr("Loading...", "Загрузка..."), is_dark_fn=lambda: self.delegate.is_dark_theme)
        self.info_label.setStyleSheet("color: #666666;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_label.setToolTip(tr("Copy to clipboard", "Скопировать в буфер обмена"))
        self.info_label.mousePressEvent = self._on_info_label_clicked
        self.info_block.addWidget(self.info_label)

        self.main_bar.addLayout(self.info_block, stretch=1)

        # Right side: Navigation buttons (horizontally scrollable, MMB drag supported)
        self.nav_buttons_container = ScrollableButtonContainer(
            Qt.Orientation.Horizontal, config=self.config
        )
        self.nav_buttons_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        self.back_btn = create_icon_button(self.icons_path, "go-back.svg", "",
                                          size_type="large", config=self.config)
        self._tr_set(self.back_btn.setToolTip, "Back to messages", "Назад к сообщениям")
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.nav_buttons_container.add_widget(self.back_btn)

        self.prev_btn = create_icon_button(self.icons_path, "arrow-left.svg", "",
                                          size_type="large", config=self.config)
        self._tr_set(self.prev_btn.setToolTip, "Previous day (H)", "Предыдущий день (H)")
        self.prev_btn.pressed.connect(lambda: self._navigate_hold(-1))
        self.prev_btn.released.connect(lambda: self._navigate_hold())
        self.nav_buttons_container.add_widget(self.prev_btn)

        self.next_btn = create_icon_button(self.icons_path, "arrow-right.svg", "",
                                          size_type="large", config=self.config)
        self._tr_set(self.next_btn.setToolTip, "Next day (L)", "Следующий день (L)")
        self.next_btn.pressed.connect(lambda: self._navigate_hold(1))
        self.next_btn.released.connect(lambda: self._navigate_hold())
        self.nav_buttons_container.add_widget(self.next_btn)

        self.calendar_btn = create_icon_button(self.icons_path, "calendar.svg", "",
                                              size_type="large", config=self.config)
        self._tr_set(self.calendar_btn.setToolTip, "Select date (D)", "Выбрать дату (D)")
        self.calendar_btn.clicked.connect(self._show_calendar)
        self.nav_buttons_container.add_widget(self.calendar_btn)

        self.search_toggle_btn = create_icon_button(self.icons_path, "search.svg", "",
                                                   size_type="large", config=self.config)
        self._tr_set(self.search_toggle_btn.setToolTip, "Toggle search (S / Ctrl+F)", "Поиск (S / Ctrl+F)")
        self.search_toggle_btn.clicked.connect(self._toggle_search)
        self.nav_buttons_container.add_widget(self.search_toggle_btn)

        self.mention_filter_btn = create_icon_button(self.icons_path, "at-line.svg", "",
                                                    size_type="large", config=self.config)
        self._tr_set(self.mention_filter_btn.setToolTip, "Filter mentions (M)", "Фильтр упоминаний (M)")
        self.mention_filter_btn.clicked.connect(self._toggle_mention_filter)
        self.nav_buttons_container.add_widget(self.mention_filter_btn)

        self.parse_btn = create_icon_button(self.icons_path, "play.svg", "",
                                           size_type="large", config=self.config)
        self._tr_set(self.parse_btn.setToolTip,
                     "Parse all chatlogs (P | Ctrl+P from anywhere)",
                     "Парсить все чатлоги (P | Ctrl+P откуда угодно)")
        self.parse_btn.clicked.connect(self._toggle_parser)
        self.nav_buttons_container.add_widget(self.parse_btn)

        self.main_bar.addWidget(self.nav_buttons_container)
    
        self.compact_layout = False

        # Search bar (MessageSearchBar; confirm button is chatlog-specific)
        self.confirm_search_btn = create_icon_button(self.icons_path, "search.svg", "",
                                                     size_type="large", config=self.config)
        self._tr_set(self.confirm_search_btn.setToolTip, "Search (Enter)", "Поиск (Enter)")
        self.confirm_search_btn.clicked.connect(self._on_search_enter)
        self.confirm_search_btn.setVisible(False)

        self.search = MessageSearchBar(
            self.config, self.icons_path,
            config_key="chatlog_search_visible",
            extra_widgets=(self.confirm_search_btn,),
        )
        self._tr_set(
            self.search.field.setPlaceholderText,
            f"Search: 'text' or 'U:Bob' or 'U:Bob,Alice' or 'M:hello' or 'D:{DATE_PLACEHOLDER}' (Enter)",
            f"Поиск: 'текст' или 'U:Вася' или 'U:Петя,Маша' или 'M:привет' или 'D:{DATE_PLACEHOLDER}' (Enter)"
        )
        self.search.text_changed.connect(self._on_search_changed)
        self.search.return_pressed.connect(self._on_search_enter)
        layout.addWidget(self.search)

        # Stacked widget: List view OR Parser config
        self.stacked = QStackedWidget()

        # Splitter holds the main view and, when opened, a split pane showing
        # the full chatlog for a date clicked in the parsed results
        self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        self.content_splitter.addWidget(self.stacked)
        layout.addWidget(self.content_splitter, stretch=1)

        # List view page
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.delegate.set_list_view(self.list_view)
    
        self.list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.list_view.setUniformItemSizes(False)
        self.list_view.setSpacing(0)
    
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_view.setMouseTracking(True)
        self.list_view.viewport().setMouseTracking(True)
    
        self.stacked.addWidget(self.list_view)
       
        # Add scroll buttons panel for quick navigation (date_jump: MessageData carries is_separator)
        self.scroll_buttons = ScrollButtonsPanel(self.list_view, parent=self, date_jump=True)
       
        # Parser config page
        self.parser_widget = ChatlogsParserConfigWidget(self.config, self.icons_path, self.account)
        self.parser_widget.parse_started.connect(self._on_parse_started)
        self.parser_widget.parse_cancelled.connect(self._on_parse_cancelled)
     
        # Connect copy/save buttons
        self.parser_widget.copy_button.clicked.connect(self._on_copy_results)
        self.parser_widget.save_button.clicked.connect(self._on_save_results)
     
        self.stacked.addWidget(self.parser_widget)

        # Show list view by default
        self.stacked.setCurrentWidget(self.list_view)

        self._update_date_display()
        self._error_occurred.connect(self._handle_error)

    def _has_active_search_or_filter(self) -> bool:
        return bool(
            self.search_text
            or self.filtered_usernames
            or self.filter_mentions
        )

    @staticmethod
    def _count_messages(messages) -> int:
        return sum(1 for m in messages if not m.is_separator)

    def _message_count(self) -> int:
        return self._count_messages(self.all_messages)

    def _messages_for_export(self):
        """Messages currently backing Copy/Save: filtered results if a search or
        filter is active, otherwise the full parsed log."""
        if not self._has_active_search_or_filter():
            return self.all_messages
        search_users, search_message, is_prefix_mode = self._parse_search_text()
        return self._filter_messages(self.all_messages, search_users, search_message, is_prefix_mode)

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
                timestamp = msg.timestamp.strftime("%H:%M:%S")
                text_lines.append(f"[{timestamp}] {msg.username}: {msg.body}")
                message_count += 1
        while text_lines and text_lines[-1] == "":
            text_lines.pop()
        return '\n'.join(text_lines), message_count

    def _update_copy_save_tooltips(self):
        kind = (
            tr("filtered results", "отфильтрованные результаты")
            if self._has_active_search_or_filter()
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

    def _on_copy_results(self):
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

    def _on_save_results(self):
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

    def _toggle_parser(self):
        """Toggle between normal view and parser config"""
        if self.parser_visible:
            # Hide parser, show list
            self.parser_visible = False
            self.stacked.setCurrentWidget(self.list_view)
            self.parse_btn.setIcon(_render_svg_icon(self.icons_path / "play.svg", self.parse_btn._icon_size))
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
                self._update_date_display()
        else:
            # Show parser, hide list
            self.parser_visible = True
            self.stacked.setCurrentWidget(self.parser_widget)
            self.parse_btn.setIcon(_render_svg_icon(self.icons_path / "list.svg", self.parse_btn._icon_size))
            self.parse_btn.setToolTip(tr("Back to chat logs (P)", "Назад к чатлогам (P)"))
            self.date_label.setText(tr("Parser", "Парсер"))

        # The "Loaded N messages" status belongs to the chatlog list, not the parser config screen
        self.info_label.setVisible(not self.parser_visible)

    def _set_parsing_mode(self, value: bool):
        self.is_parsing = value
        self._update_confirm_search_button()

    def _live_search_max_messages(self) -> int:
        value = self.config.get("ui", "chatlog", "live_search_max_messages")
        if value is None:
            return DEFAULTS["chatlog"]["live_search_max_messages"]
        return max(
            DEFAULTS["chatlog"]["live_search_max_messages_min"],
            min(DEFAULTS["chatlog"]["live_search_max_messages_max"], int(value)),
        )

    def _requires_confirmed_search(self) -> bool:
        return self._message_count() > self._live_search_max_messages()

    def _update_confirm_search_button(self):
        self.confirm_search_btn.setVisible(self._requires_confirmed_search())

    def _max_messages_limit(self) -> int:
        value = self.config.get("ui", "chatlog", "max_messages")
        if value is None:
            return DEFAULTS["chatlog"]["max_messages"]
        return max(
            DEFAULTS["chatlog"]["max_messages_min"],
            min(DEFAULTS["chatlog"]["max_messages_max"], int(value)),
        )

    def apply_max_messages_limit(self):
        """Apply current config limit to the model; re-render if already loaded."""
        limit = self._max_messages_limit()
        self.model.max_messages = limit
        if self.is_parsing or not self.all_messages:
            return
        count = self._message_count()
        if count > limit:
            self.model.clear()
            self.info_label.setText(
                tr(
                    f"⚠️ {count:,} messages (limit: {limit:,}) - {LIMIT_EXCEEDED_SUFFIX_EN}",
                    f"⚠️ {count:,} сообщений (лимит: {limit:,}) - {LIMIT_EXCEEDED_SUFFIX_RU}"
                  )
            )
        else:
            self._apply_filter()

    def _set_parser_youtube_off(self, off: bool):
        """Parser bulk views never expand YouTube links (config is ignored)."""
        renderer = getattr(self.delegate, "message_renderer", None)
        if renderer is not None:
            renderer.set_youtube_override(False if off else None)

    def _on_parse_started(self, config: ParseConfig):
        """Start parsing with given config"""
        self._set_parsing_mode(True)
        self.exceeded_max_messages = False
        self.date_label.setText(tr("Parser", "Парсер"))
        if config.mode != 'syncdatabase':
            self._set_parser_youtube_off(True)
        
        # Only clear UI for non-sync modes
        if config.mode != 'syncdatabase':
            self.model.clear()
            self.all_messages = []
            self.temp_parsed_messages = []
            self.last_parsed_date = None
            self._update_confirm_search_button()
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

    def _on_parse_cancelled(self):
        """Cancel parsing"""
        if self.parser_worker:
            self.parser_worker.stop()
            self.parser_worker = None
        self.parser_cancelled = True
        self.parser_widget._reset_ui()
        
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
                self._update_confirm_search_button()
                non_separator_messages = [m for m in self.all_messages if not m.is_separator]
                self.messages_loaded.emit(non_separator_messages)
                self.parser_widget.show_copy_save_buttons()
                self._update_copy_save_tooltips()
                QTimer.singleShot(100, lambda: scroll(self.list_view, mode="top", delay=50))
                message_count = len(non_separator_messages)
                self.info_label.setText(tr(
                    f"Found {message_count} messages (partial)",
                    f"Найдено {message_count} сообщений (частично)")
                )
            else:
                self.info_label.setText(tr("Parsing cancelled", "Парсинг отменён"))
                self._set_parsing_mode(False)
        
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
                f"⚠️ Exceeded {self.model.max_messages:,} message limit - {LIMIT_EXCEEDED_SUFFIX_EN}",
                f"⚠️ Превышен лимит {self.model.max_messages:,} сообщений - {LIMIT_EXCEEDED_SUFFIX_RU}")
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
        self.parser_widget._reset_ui()
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
            self._update_confirm_search_button()
            
            # Skip rendering if exceeded limit
            if self.exceeded_max_messages:
                self.info_label.setText(tr(
                    f"⚠️ {message_count:,} messages found (limit: {self.model.max_messages:,}) - {LIMIT_EXCEEDED_SUFFIX_EN}",
                    f"⚠️ Найдено {message_count:,} сообщений (лимит: {self.model.max_messages:,}) - {LIMIT_EXCEEDED_SUFFIX_RU}")
                )
                self.exceeded_max_messages = False
            else:
                self.list_view.setUpdatesEnabled(False)
                self.model.set_messages(self.all_messages)
                self.list_view.setUpdatesEnabled(True)
                
                non_separator_messages = [m for m in self.all_messages if not m.is_separator]
                self.messages_loaded.emit(non_separator_messages)
                QTimer.singleShot(100, lambda: scroll(self.list_view, mode="top", delay=50))
            
            self.parser_widget.show_copy_save_buttons()
            self._update_copy_save_tooltips()
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
        self.parser_widget._reset_ui()
        self.temp_parsed_messages = [] # Clear temp on error
        self.info_label.setText(tr(f"Error: {error_msg}", f"Ошибка: {error_msg}"))
        if self.parent_window:
            self.parent_window.stop_parse_status()

    def _handle_error(self, error_msg: str):
        self.info_label.setText(error_msg)

    @property
    def search_visible(self) -> bool:
        return self.search.visible_state

    @property
    def search_field(self):
        return self.search.field

    def _toggle_search(self):
        self.search.toggle()

    def _toggle_mention_filter(self):
        """Toggle mention filter on/off"""
        self.filter_mentions = not self.filter_mentions
        
        # Update icon based on state
        icon_name = "at-fill.svg" if self.filter_mentions else "at-line.svg"
        self.mention_filter_btn._icon_name = icon_name  # Update the attribute for theme consistency
        icon = _render_svg_icon(self.mention_filter_btn._icon_path / icon_name, self.mention_filter_btn._icon_size)
        self.mention_filter_btn.setIcon(icon)
        
        # Reapply filter to show/hide messages
        self._apply_filter()

    def _on_search_changed(self, text: str):
        self.search_text = text
        if not self._requires_confirmed_search():
            self._apply_filter()

    def _on_search_enter(self):
        """Enter/search button - jump to date for a 'D:<date>' entry, otherwise apply the search."""
        import re
        match = re.match(r'^[Dd]:\s*(\S+)', self.search_text)
        if match:
            date_str = parse_short_date(match.group(1))
            try:
                target = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.info_label.setText(tr(f"Invalid date: {match.group(1)}", f"Неверная дата: {match.group(1)}"))
                return

            if not (self.parser.MIN_DATE <= target <= datetime.now().date()):
                self.info_label.setText(tr(f"Date out of range: {date_str}", f"Дата вне диапазона: {date_str}"))
                return

            self._clear_search()
            self.load_date(date_str)
            return

        self._apply_filter()

    def _parse_search_text(self):
        return parse_search_text(self.search_text)


    def _clear_search(self):
        self.search.clear()
        self._apply_filter()

    def _update_date_display(self):
        self.date_label.setText(self.current_date.strftime("%Y-%m-%d (%A)"))
        self.next_btn.setEnabled(self.current_date < datetime.now().date())
        self.prev_btn.setEnabled(self.current_date > self.parser.MIN_DATE)

    def set_compact_layout(self, compact: bool):
        """Handle responsive layout for < 1000px width"""
        if compact == self.compact_layout:
            return
    
        if compact:
            # Remove items from main_bar (widget at index 1, layout at index 0)
            self.main_bar.takeAt(1)  # nav_buttons_container widget item
            self.main_bar.takeAt(0)  # info_block item
            # Remove main_bar from top_bar_layout
            self.top_bar_layout.takeAt(0)
            # Add nav_buttons_container (widget) and info_block (layout) to top_bar_layout
            self.top_bar_layout.addWidget(self.nav_buttons_container)
            self.top_bar_layout.addLayout(self.info_block)
            self.compact_layout = True
        else:
            # Remove items from top_bar_layout
            self.top_bar_layout.takeAt(1)  # info_block item
            self.top_bar_layout.takeAt(0)  # nav_buttons_container widget item
            # Add main_bar back
            self.top_bar_layout.addLayout(self.main_bar)
            # Add sub-items to main_bar
            self.main_bar.addLayout(self.info_block, stretch=1)
            self.main_bar.addWidget(self.nav_buttons_container)

            self.compact_layout = False

    def set_compact_mode(self, compact: bool):
        self.delegate.set_compact_mode(compact)
        self._force_recalculate()

    def update_theme(self):
        self.delegate.update_theme()
        self._force_recalculate()

    def _force_recalculate(self):
        self.list_view.setUpdatesEnabled(False)
        self.list_view.reset()
        self.list_view.clearSelection()
        self.list_view.scheduleDelayedItemsLayout()
        self.model.layoutChanged.emit()
        self.list_view.setUpdatesEnabled(True)
        self.list_view.viewport().update()
        QTimer.singleShot(10, lambda: self.list_view.viewport().update())

    def load_date(self, date_str: str):
        try:
            self.current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            self._update_date_display()
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

        def _on_loaded(_messages=None, t=time_str):
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

    def set_username_filter(self, usernames: set):
        self.filtered_usernames = usernames
        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)

    def clear_filter(self):
        self.filtered_usernames = set()
        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)

    def _message_matches_filters(self, msg, search_users, search_message, is_prefix_mode) -> bool:
        if self.filter_mentions and self.account and self.account.get('chat_username'):
            my_username = self.account.get('chat_username')
            if not any(is_mention for is_mention, _ in parse_mentions(msg.body, my_username)):
                return False

        if is_prefix_mode:
            if search_users and msg.username.lower() not in search_users:
                return False
            if search_message and search_message not in msg.body.lower():
                return False
        else:
            if self.filtered_usernames and msg.username not in self.filtered_usernames:
                return False
            if self.search_text:
                search_lower = self.search_text.lower()
                if search_lower not in msg.username.lower() and search_lower not in msg.body.lower():
                    return False
        return True

    def _filter_messages(self, messages, search_users, search_message, is_prefix_mode):
        """Keep matching messages together with the date separator that precedes them.
        search_users/search_message/is_prefix_mode come from _parse_search_text(),
        parsed once by the caller and shared - never re-parsed here."""
        if not self._has_active_search_or_filter():
            return list(messages)

        search_users_lower = {u.lower() for u in search_users} if search_users else set()
        result = []
        pending_separator = None
        for msg in messages:
            if msg.is_separator:
                pending_separator = msg
                continue
            if self._message_matches_filters(msg, search_users_lower, search_message, is_prefix_mode):
                if pending_separator is not None:
                    result.append(pending_separator)
                    pending_separator = None
                result.append(msg)
        return result

    def _apply_filter(self):
        self.list_view.setUpdatesEnabled(False)
        self.model.clear()

        if not self.all_messages:
            self.list_view.setUpdatesEnabled(True)
            self._update_copy_save_tooltips()
            return

        search_users, search_message, is_prefix_mode = self._parse_search_text()
        self.delegate.set_highlight_text(search_message if is_prefix_mode else self.search_text)
        messages_to_show = self._filter_messages(self.all_messages, search_users, search_message, is_prefix_mode)
        self.model.set_messages(messages_to_show)
        self.list_view.setUpdatesEnabled(True)
        self._update_copy_save_tooltips()

        total = self._message_count()
        shown = self._count_messages(messages_to_show)

        filters = []
        if self.filter_mentions:
            filters.append("mentions only")
        if is_prefix_mode:
            if search_users:
                filters.append(f"users: {', '.join(sorted(search_users))}")
            if search_message:
                filters.append(f"message: '{search_message}'")
        else:
            if self.filtered_usernames:
                filters.append(f"users: {', '.join(sorted(self.filtered_usernames))}")
            if self.search_text:
                filters.append(f"search: '{self.search_text}'")

        if filters:
            self.info_label.setText(tr(
                f"Showing {shown}/{total} messages ({' | '.join(filters)})",
                f"Показано {shown}/{total} сообщений ({' | '.join(filters)})")
            )
        else:
            if hasattr(self, '_pending_data'):
                _, size_text, was_truncated, from_cache = self._pending_data
                cache_marker = " 📁" if from_cache else ""
                if was_truncated:
                    self.info_label.setText(tr(
                        f"⚠️ Loaded {total} messages (file truncated at {self.parser.MAX_FILE_SIZE_MB}MB limit) · {size_text}{cache_marker}",
                        f"⚠️ Загружено {total} сообщений (файл обрезан на {self.parser.MAX_FILE_SIZE_MB}МБ) · {size_text}{cache_marker}")
                    )
                else:
                    self.info_label.setText(tr(
                        f"Loaded {total} messages · {size_text}{cache_marker}",
                        f"Загружено {total} сообщений · {size_text}{cache_marker}")
                    )
            else:
                self.info_label.setText(tr(f"Loaded {total} messages", f"Загружено {total} сообщений"))

        self._scroll_to_bottom()

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
                except:
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

    def _retranslate(self, _code=None):
        self._retranslate_all()

    def _navigate(self, days):
        """Navigate by days offset (-1 for previous, +1 for next)"""
        new_date = self.current_date + timedelta(days=days)
        if self.parser.MIN_DATE <= new_date <= datetime.now().date():
            self.current_date = new_date
            self._update_date_display()
            self.load_timer.stop()
            self.load_timer.start(300)

    def _show_calendar(self):
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
                self._update_date_display()
                self.load_current_date()
            calendar.close()
    
        calendar.clicked.connect(on_date_selected)
        btn_pos = self.calendar_btn.mapToGlobal(self.calendar_btn.rect().bottomRight())
        x = btn_pos.x() - calendar.sizeHint().width()
        y = btn_pos.y() + (self.config.get("ui", "spacing", "widget_elements") or 6)
        calendar.move(x, y)
        calendar.show()

    def cleanup(self):
        if self.delegate:
            self.delegate.cleanup()
        if hasattr(self, 'scroll_buttons'):
            self.scroll_buttons.cleanup()
        if hasattr(self, 'auto_scroller'):
            self.auto_scroller.cleanup()
        if hasattr(self.parser, 'db'):
            self.parser.db.close()
        if self.split_chatlog_widget:
            self.split_chatlog_widget.cleanup()
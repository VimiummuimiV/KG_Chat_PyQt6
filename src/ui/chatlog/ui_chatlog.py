"""Chatlog viewer widget with virtual scrolling, search, and parser"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListView,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from components.button import create_icon_button
from components.flash_highlight import FlashLabel
from components.image_viewer.gallery import DayNavigation
from components.search import MessageSearchBar
from core.chatlogs.fetch import ChatlogsParser
from helpers.dates import DATE_PLACEHOLDER
from helpers.fonts.fonts import FontType, get_font
from helpers.scroll.auto_scroll import AutoScroller
from helpers.scroll.scroll_buttons import ScrollButtonsPanel
from helpers.scroll.scrollable_buttons import ScrollableButtonContainer
from helpers.translate import on_language_changed, tr, TranslatableMixin
from ui.chatlog.chatlog_export import ChatlogExportMixin
from ui.chatlog.chatlog_images import ChatlogImagesMixin
from ui.chatlog.chatlog_loading import ChatlogLoadingMixin
from ui.chatlog.chatlog_parser_controls import ChatlogParserControlsMixin
from ui.chatlog.chatlog_search import ChatlogSearchMixin
from ui.chatlog.chatlog_split_view import ChatlogSplitViewMixin
from ui.chatlog.ui_chatlogs_parser import ChatlogsParserConfigWidget
from ui.messages.message_delegate import MessageDelegate
from ui.messages.message_interactions import MessageInteractions
from ui.messages.message_model import MessageListModel


class ChatlogWidget(
    TranslatableMixin,
    ChatlogExportMixin,
    ChatlogImagesMixin,
    ChatlogLoadingMixin,
    ChatlogParserControlsMixin,
    ChatlogSearchMixin,
    ChatlogSplitViewMixin,
    QWidget,
):
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
        self.init_translatable()
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
        self.delegate.set_marker_gutter(True)
        self.delegate.anchor_frame_enabled = self._anchor_frame_active
        self.delegate.day_navigation = DayNavigation(self._navigate, self._day_state)

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
        self.model.modelReset.connect(self._update_image_button)
        self._update_image_button()
        on_language_changed(self._retranslate)

        # Initialize auto-scroller after UI is set up
        self.auto_scroller = AutoScroller(self.list_view)

        # Connect message click handler
        self.delegate.message_clicked.connect(self._on_message_clicked)
        self.delegate.separator_clicked.connect(self._on_date_separator_clicked)
        self.delegate.chatlog_link_clicked.connect(self._on_chatlog_link_clicked)

        # Timestamp clicks stay in MessageDelegate.editorEvent, so handle_timestamp=False
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
        self.info_label = FlashLabel(tr("Loading...", "Загрузка..."), is_dark_fn=lambda: self.delegate.is_dark_theme, config=self.config, duration_kind="copy")
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
        self.tr_set(self.back_btn.setToolTip, "Back to messages", "Назад к сообщениям")
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.nav_buttons_container.add_widget(self.back_btn)

        self.prev_btn = create_icon_button(self.icons_path, "arrow-left.svg", "",
                                          size_type="large", config=self.config)
        self.tr_set(self.prev_btn.setToolTip, "Previous day (H)", "Предыдущий день (H)")
        self.prev_btn.pressed.connect(lambda: self.navigate_hold(-1))
        self.prev_btn.released.connect(lambda: self.navigate_hold())
        self.nav_buttons_container.add_widget(self.prev_btn)

        self.next_btn = create_icon_button(self.icons_path, "arrow-right.svg", "",
                                          size_type="large", config=self.config)
        self.tr_set(self.next_btn.setToolTip, "Next day (L)", "Следующий день (L)")
        self.next_btn.pressed.connect(lambda: self.navigate_hold(1))
        self.next_btn.released.connect(lambda: self.navigate_hold())
        self.nav_buttons_container.add_widget(self.next_btn)

        self.calendar_btn = create_icon_button(self.icons_path, "calendar.svg", "",
                                              size_type="large", config=self.config)
        self.tr_set(self.calendar_btn.setToolTip, "Select date (D)", "Выбрать дату (D)")
        self.calendar_btn.clicked.connect(self.show_calendar)
        self.nav_buttons_container.add_widget(self.calendar_btn)

        self.search_toggle_btn = create_icon_button(self.icons_path, "search.svg", "",
                                                   size_type="large", config=self.config)
        self.tr_set(self.search_toggle_btn.setToolTip, "Toggle search (S / Ctrl+F)", "Поиск (S / Ctrl+F)")
        self.search_toggle_btn.clicked.connect(self.toggle_search)
        self.nav_buttons_container.add_widget(self.search_toggle_btn)

        self.mention_filter_btn = create_icon_button(self.icons_path, "at-line.svg", "",
                                                    size_type="large", config=self.config)
        self.tr_set(self.mention_filter_btn.setToolTip, "Filter mentions (M)", "Фильтр упоминаний (M)")
        self.mention_filter_btn.clicked.connect(self.toggle_mention_filter)
        self.nav_buttons_container.add_widget(self.mention_filter_btn)

        self.image_button = create_icon_button(self.icons_path, "gallery-line.svg", "",
                                               size_type="large", config=self.config)
        self.tr_set(self.image_button.setToolTip, "View images", "Просмотр изображений")
        self.image_button.clicked.connect(lambda: self.delegate.open_first_image())
        self.nav_buttons_container.add_widget(self.image_button)

        self.parse_btn = create_icon_button(self.icons_path, "play.svg", "",
                                           size_type="large", config=self.config)
        self.tr_set(self.parse_btn.setToolTip,
                     "Parse all chatlogs (P | Ctrl+P from anywhere)",
                     "Парсить все чатлоги (P | Ctrl+P откуда угодно)")
        self.parse_btn.clicked.connect(self.toggle_parser)
        self.nav_buttons_container.add_widget(self.parse_btn)

        self.main_bar.addWidget(self.nav_buttons_container)

        self.compact_layout = False

        # Search bar (MessageSearchBar; confirm button is chatlog-specific)
        self.confirm_search_btn = create_icon_button(self.icons_path, "search.svg", "",
                                                     size_type="large", config=self.config)
        self.tr_set(self.confirm_search_btn.setToolTip, "Search (Enter)", "Поиск (Enter)")
        self.confirm_search_btn.clicked.connect(self._on_search_enter)
        self.confirm_search_btn.setVisible(False)

        self.search = MessageSearchBar(
            self.config, self.icons_path,
            config_key="chatlog_search_visible",
            extra_widgets=(self.confirm_search_btn,),
        )
        self.tr_set(
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
        self.parser_widget.parse_started.connect(self.on_parse_started)
        self.parser_widget.parse_cancelled.connect(self.on_parse_cancelled)

        # Connect copy/save buttons
        self.parser_widget.copy_button.clicked.connect(self.on_copy_results)
        self.parser_widget.save_button.clicked.connect(self.on_save_results)

        self.stacked.addWidget(self.parser_widget)

        # Show list view by default
        self.stacked.setCurrentWidget(self.list_view)

        self.update_date_display()
        self._error_occurred.connect(self._handle_error)

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
        self.force_recalculate()

    def update_theme(self):
        self.delegate.update_theme()
        self.force_recalculate()

    def force_recalculate(self):
        self.list_view.setUpdatesEnabled(False)
        self.list_view.reset()
        self.list_view.clearSelection()
        self.list_view.scheduleDelayedItemsLayout()
        self.model.layoutChanged.emit()
        self.list_view.setUpdatesEnabled(True)
        self.list_view.viewport().update()
        QTimer.singleShot(10, lambda: self.list_view.viewport().update())

    def _retranslate(self, _code=None):
        self.retranslate_all()

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

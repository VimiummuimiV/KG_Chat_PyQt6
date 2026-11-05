"""User Tracker UI — tracked users + join/left history"""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from components.button import create_icon_button
from components.presence_badge import TypeFilterBar
from helpers.fonts.fonts import FontType, get_font, get_userlist_width
from helpers.scroll.auto_scroll import AutoScroller
from helpers.scroll.scroll_buttons import ScrollButtonsPanel
from helpers.translate import on_language_changed, tr, TranslatableMixin
from helpers.users.user_tracker import UserTracker
from ui.tracker.tracker_delegate import TrackerEventDelegate
from ui.tracker.tracker_events import TrackerEventFilterProxy, TrackerEventModel
from ui.tracker.tracker_filters import TrackerFiltersMixin
from ui.tracker.tracker_history import TrackerHistoryMixin
from ui.tracker.tracker_selection import TrackerSelectionMixin


class UserTrackerWidget(
    TranslatableMixin,
    TrackerFiltersMixin,
    TrackerHistoryMixin,
    TrackerSelectionMixin,
    QWidget,
):
    back_requested = pyqtSignal()
    tracked_users_changed = pyqtSignal()

    def __init__(self, config, icons_path: Path, user_tracker: UserTracker, font_scaler=None):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.user_tracker = user_tracker
        self.font_scaler = font_scaler
        self.user_items = []
        self.filtered_logins = set()
        self.filtered_types = set()
        self.filtered_dates = set()
        self.chip_widgets = {}
        userlist_visible = config.get("ui", "userlist", "tracker")
        self.userlist_visible = True if userlist_visible is None else bool(userlist_visible)
        self._setup_ui()
        self._load_selected()
        self._rebuild_events()
        self._apply_default_tab()
        self._on_tab_changed(self.tabs.currentIndex())
        if self.font_scaler is not None:
            self.font_scaler.font_size_committed.connect(self._on_font_size_committed)

    def _on_font_size_committed(self):
        self.filter_panel.setFixedWidth(get_userlist_width())
        for item in self.user_items:
            item.update_font_scale()
        if self.user_items:
            self.recalculate_layout()
        self.history_delegate.update_fonts()

    def _setup_ui(self):
        window_margin = self.config.get("ui", "margins", "window") or 10
        window_spacing = self.config.get("ui", "spacing", "window_content") or 10

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(window_margin, window_margin, window_margin, window_margin)
        main_layout.setSpacing(window_spacing)
        self.setLayout(main_layout)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        main_layout.addLayout(header_layout)

        self.back_button = create_icon_button(
            self.icons_path, "go-back.svg", "", config=self.config
        )
        self.tr_set(self.back_button.setToolTip, "Back to Messages", "Назад к сообщениям")
        self.back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.back_button)

        title_label = QLabel()
        title_label.setFont(get_font(FontType.HEADER))
        self.tr_set(title_label.setText, "User Tracker", "Трекер пользователей")
        header_layout.addWidget(title_label)

        self.info_label = QLabel("")
        self.info_label.setFont(get_font(FontType.UI))
        self.info_label.setStyleSheet("color: #888;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_label.setVisible(False)
        header_layout.addWidget(self.info_label, stretch=1)

        self.add_user_button = create_icon_button(
            self.icons_path, "add.svg", "", config=self.config
        )
        self.tr_set(self.add_user_button.setToolTip, "Add user", "Добавить пользователя")
        self.add_user_button.clicked.connect(self._add_new_item)
        header_layout.addWidget(self.add_user_button)

        self.clear_filter_button = create_icon_button(
            self.icons_path, "filter.svg", tr("Clear history filter", "Сбросить фильтр истории"), config=self.config
        )
        self.clear_filter_button.clicked.connect(self._clear_filter)
        self.clear_filter_button.setVisible(False)
        header_layout.addWidget(self.clear_filter_button)

        self.clear_history_button = create_icon_button(
            self.icons_path, "trash.svg", "", config=self.config
        )
        self.tr_set(self.clear_history_button.setToolTip, "Clear History", "Очистить историю")
        self.clear_history_button.clicked.connect(self._clear_history)
        header_layout.addWidget(self.clear_history_button)

        self.tabs = QTabWidget()
        self.tabs.setFont(get_font(FontType.UI))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs, stretch=1)

        list_spacing = self.config.get("ui", "spacing", "list_items") or 2

        # --- Tracked tab ---
        tracked_page = QWidget()
        tracked_layout = QVBoxLayout(tracked_page)
        tracked_layout.setContentsMargins(4, 4, 4, 4)
        tracked_layout.setSpacing(6)

        self.users_scroll = QScrollArea()
        self.users_scroll.setWidgetResizable(True)
        self.users_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.users_container = QWidget()
        self.users_grid = QGridLayout()
        self.users_grid.setContentsMargins(0, 0, 0, 0)
        self.users_grid.setSpacing(list_spacing)
        self.users_grid.setVerticalSpacing(list_spacing * 2)
        self.users_grid.setHorizontalSpacing(list_spacing * 4)
        self.users_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.users_container.setLayout(self.users_grid)
        self.users_scroll.setWidget(self.users_container)
        tracked_layout.addWidget(self.users_scroll, stretch=1)

        tracked_tab_index = self.tabs.addTab(tracked_page, "")
        self.tr_set(lambda text, i=tracked_tab_index: self.tabs.setTabText(i, text), "Tracked", "Отслеживаемые")

        # --- History tab ---
        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(4, 4, 4, 4)
        history_layout.setSpacing(6)

        history_row = QHBoxLayout()
        history_row.setSpacing(6)
        history_layout.addLayout(history_row, stretch=1)

        self.history_model = TrackerEventModel()
        self.history_proxy = TrackerEventFilterProxy()
        self.history_proxy.setSourceModel(self.history_model)
        self.history_delegate = TrackerEventDelegate(self.config)

        self.history_list_view = QListView()
        self.history_list_view.setModel(self.history_proxy)
        self.history_list_view.setItemDelegate(self.history_delegate)
        self.history_delegate.set_list_view(self.history_list_view)
        self.history_list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.history_list_view.setUniformItemSizes(False)
        self.history_list_view.setSpacing(0)
        self.history_list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_list_view.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.history_list_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.history_list_view.setMouseTracking(True)
        self.history_list_view.viewport().setMouseTracking(True)
        self.history_delegate.filter_clicked.connect(self._handle_filter_click)
        self.history_delegate.type_filter_clicked.connect(self._handle_type_filter_click)
        self.history_delegate.date_filter_clicked.connect(self._handle_date_filter_click)

        self._empty_history_label = QLabel()
        self._empty_history_label.setFont(get_font(FontType.UI))
        self._empty_history_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_history_label.setStyleSheet("color: #888;")
        self.tr_set(self._empty_history_label.setText, "No events", "Нет событий")

        self.history_stack = QStackedWidget()
        self.history_stack.addWidget(self.history_list_view)
        self.history_stack.addWidget(self._empty_history_label)
        history_row.addWidget(self.history_stack, stretch=1)

        self.history_scroll_buttons = ScrollButtonsPanel(self.history_list_view, parent=self, date_jump=True)
        self.history_auto_scroller = AutoScroller(self.history_list_view)

        self.filter_panel = QWidget()
        self.filter_panel.setFixedWidth(get_userlist_width())
        self.filter_panel.setVisible(False)
        filter_panel_layout = QVBoxLayout(self.filter_panel)
        filter_panel_layout.setContentsMargins(0, 0, 0, 0)
        filter_panel_layout.setSpacing(4)

        self.filter_scroll = QScrollArea()
        self.filter_scroll.setWidgetResizable(True)
        self.filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        filter_container = QWidget()
        self.filter_chips_layout = QVBoxLayout()
        self.filter_chips_layout.setContentsMargins(4, 4, 4, 4)
        self.filter_chips_layout.setSpacing(2)
        filter_container.setLayout(self.filter_chips_layout)
        self.filter_chips_layout.addStretch()
        self.filter_scroll.setWidget(filter_container)
        filter_panel_layout.addWidget(self.filter_scroll, stretch=1)

        theme = self.config.get("ui", "theme") or "dark"
        self.type_filter_bar = TypeFilterBar(empty_means_all=True, is_dark=(theme == "dark"))
        self.type_filter_bar.changed.connect(self._on_type_filter_changed)
        filter_panel_layout.addWidget(self.type_filter_bar)

        history_row.addWidget(self.filter_panel)

        self.filter_auto_scroller = AutoScroller(self.filter_scroll)

        history_tab_index = self.tabs.addTab(history_page, "")
        self.tr_set(lambda text, i=history_tab_index: self.tabs.setTabText(i, text), "History", "История")
        on_language_changed(self.retranslate_all)

    def toggle_userlist(self) -> bool:
        self.userlist_visible = not self.userlist_visible
        self.config.set("ui", "userlist", "tracker", value=self.userlist_visible)
        self._update_filter_panel_visibility()
        return self.userlist_visible

    def _on_tab_changed(self, index: int):
        is_tracked = index == 0
        self.add_user_button.setVisible(is_tracked)
        self.clear_history_button.setVisible(not is_tracked)
        self.clear_filter_button.setVisible(not is_tracked and self._has_active_filters())
        self.info_label.setVisible(not is_tracked)
        if not is_tracked:
            self._update_info_label()
        if is_tracked and self.user_items:
            QTimer.singleShot(0, self.recalculate_layout)

    def recalculate_layout(self):
        if not self.user_items:
            return

        available_width = self.users_scroll.viewport().width()
        h_spacing = self.users_grid.horizontalSpacing()
        if h_spacing == -1:
            h_spacing = self.users_grid.spacing()

        margins = self.users_grid.contentsMargins()
        available_for_items = available_width - (margins.left() + margins.right())
        max_item_width = max(item.width() for item in self.user_items)
        columns = max(1, (available_for_items + h_spacing) // (max_item_width + h_spacing))

        for i in reversed(range(self.users_grid.count())):
            widget = self.users_grid.itemAt(i).widget()
            if widget:
                self.users_grid.removeWidget(widget)

        for idx, item in enumerate(self.user_items):
            row = idx // columns
            col = idx % columns
            self.users_grid.addWidget(item, row, col)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(50, self.recalculate_layout)

    def showEvent(self, event):
        super().showEvent(event)
        if self.user_items:
            QTimer.singleShot(0, self.recalculate_layout)

    def update_theme(self):
        self.history_delegate.update_theme()
        self.history_list_view.viewport().update()
        for item in self.user_items:
            if hasattr(item, "apply_theme"):
                item.apply_theme()
        theme = self.config.get("ui", "theme") or "dark"
        self.type_filter_bar.update_theme(theme == "dark")
        self._rebuild_filter_chips()

    def _apply_default_tab(self):
        tab = self.config.get("user_tracker", "default_tab") or "tracked"
        self.tabs.setCurrentIndex(1 if tab == "history" else 0)

    def refresh(self):
        self._load_selected()
        self._rebuild_events()
        self._apply_default_tab()
        self._on_tab_changed(self.tabs.currentIndex())

    def cleanup(self):
        for item in self.user_items:
            item.cleanup()
        if getattr(self, "history_delegate", None):
            self.history_delegate.cleanup()
        if getattr(self, "history_scroll_buttons", None):
            self.history_scroll_buttons.cleanup()
        if getattr(self, "history_auto_scroller", None):
            self.history_auto_scroller.cleanup()
        if getattr(self, "filter_auto_scroller", None):
            self.filter_auto_scroller.cleanup()

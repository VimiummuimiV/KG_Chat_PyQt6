"""User Tracker UI — tracked users + join/left history"""
from pathlib import Path
from datetime import datetime
from collections import Counter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QMessageBox, QFrame, QTabWidget, QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QPixmap, QPainter

from helpers.create import create_icon_button, set_visual_active
from helpers.fonts import (
    get_font,
    FontType,
    get_userlist_width,
    get_scaled_width
)
from helpers.user_tracker import UserTracker
from helpers.cache import get_cache
from helpers.flash_highlight import FlashHighlight
from helpers.scroll.auto_scroll import AutoScroller
from helpers.scroll.scroll_buttons import ScrollButtonsPanel
from core.api_data import validate_username_and_get_id
from components.presence_badge import make_presence_badge, make_game_id_label
from components.user_count_row import UserCountRow


class TrackedUserItem(QWidget):
    remove_requested = pyqtSignal(object)

    USERNAME_BASE_WIDTH = 220
    USER_ID_BASE_WIDTH = 125
    ARROW_WIDTH = 26
    BUTTON_WIDTH = 48  # freeze + remove buttons

    def __init__(self, config, icons_path: Path, username="", user_id=""):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.user_id = user_id
        self.frozen = False
        self.parent_widget = None
        self.username_valid = True

        spacing = config.get("ui", "spacing", "widget_elements") or 6
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        self.setLayout(layout)

        input_height = config.get("ui", "input_height") or 44

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setText(username)
        self.username_input.setFont(get_font(FontType.TEXT))
        self.username_input.setFixedHeight(input_height)
        self._username_width = get_scaled_width(self.USERNAME_BASE_WIDTH)
        self.username_input.setFixedWidth(self._username_width)
        self.username_input.editingFinished.connect(self._validate)
        layout.addWidget(self.username_input)

        arrow_label = QLabel()
        arrow_svg = icons_path / "arrow-right.svg"
        if arrow_svg.exists():
            with open(arrow_svg, 'r') as f:
                svg_content = f.read().replace('fill="currentColor"', 'fill="#888888"')
            renderer = QSvgRenderer()
            renderer.load(svg_content.encode('utf-8'))
            pixmap = QPixmap(26, 26)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            arrow_label.setPixmap(pixmap)
            arrow_label.setFixedSize(26, 26)
        layout.addWidget(arrow_label)

        self.user_id_input = QLineEdit()
        self.user_id_input.setPlaceholderText("User ID")
        self.user_id_input.setText(user_id)
        self.user_id_input.setFont(get_font(FontType.TEXT))
        self.user_id_input.setFixedHeight(input_height)
        self._user_id_width = get_scaled_width(self.USER_ID_BASE_WIDTH)
        self.user_id_input.setFixedWidth(self._user_id_width)
        self.user_id_input.setReadOnly(True)
        layout.addWidget(self.user_id_input)

        self.freeze_button = create_icon_button(
            icons_path, "snowflake.svg", "Freeze tracking",
            size_type="large", config=config
        )
        self.freeze_button.clicked.connect(self._toggle_freeze)
        layout.addWidget(self.freeze_button)

        self.remove_button = create_icon_button(
            icons_path, "trash.svg", "Remove",
            size_type="large", config=config
        )
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self.remove_button)

        self._spacing = spacing
        self._update_total_width()
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        if username and not user_id:
            self._validate()

    def _update_total_width(self):
        total_width = (
            self._username_width + self.ARROW_WIDTH + self._user_id_width
            + self.BUTTON_WIDTH * 2 + self._spacing * 4
        )
        self.setFixedWidth(total_width)

    def update_font_scale(self):
        """Re-scale fixed-width fields when text font size changes (called on font_size_committed)."""
        self._username_width = get_scaled_width(self.USERNAME_BASE_WIDTH)
        self._user_id_width = get_scaled_width(self.USER_ID_BASE_WIDTH)
        self.username_input.setFixedWidth(self._username_width)
        self.user_id_input.setFixedWidth(self._user_id_width)
        self._update_total_width()

    def _validate(self):
        username = self.username_input.text().strip()
        if not username:
            self.username_valid = True
            self.user_id = ""
            self.user_id_input.clear()
            self._update_input_style()
            if self.parent_widget:
                self.parent_widget._save_selected()
            return

        user_id = validate_username_and_get_id(username)
        self.username_valid = user_id is not None
        if self.username_valid:
            self.user_id = user_id
            self.user_id_input.setText(self.user_id)
        else:
            self.user_id = ""
            self.user_id_input.clear()

        self._update_input_style()
        if self.parent_widget:
            self.parent_widget._save_selected()

    def _update_input_style(self, highlight_empty=False):
        if highlight_empty and not self.username_input.text().strip():
            self.username_input.setStyleSheet("QLineEdit { border: 2px solid #ffb84d; }")
            self.username_input.setToolTip("Fill username before adding new item")
        elif self.username_input.text().strip() and not self.username_valid:
            self.username_input.setStyleSheet("QLineEdit { border: 2px solid #ff4444; }")
            self.username_input.setToolTip("User not found")
        else:
            self.username_input.setStyleSheet("")
            self.username_input.setToolTip("")

    def set_frozen(self, frozen: bool):
        self.frozen = bool(frozen)
        # Dim identity fields when frozen (parent opacity would dim buttons too)
        set_visual_active(self.username_input, not self.frozen)
        set_visual_active(self.user_id_input, not self.frozen)
        set_visual_active(self.freeze_button, not self.frozen)
        self.freeze_button.setToolTip(
            "Unfreeze tracking" if self.frozen else "Freeze tracking"
        )

    def _toggle_freeze(self):
        if not self.user_id:
            return
        self.set_frozen(not self.frozen)
        if self.parent_widget:
            self.parent_widget.user_tracker.set_frozen(self.user_id, self.frozen)

    def is_empty(self):
        return not self.username_input.text().strip()

    def get_data(self):
        return self.username_input.text().strip(), self.user_id

    def cleanup(self):
        pass


class EventRow(QFrame):
    filter_clicked = pyqtSignal(str, bool)

    def __init__(self, config, event: dict):
        super().__init__()
        self.setObjectName("trackerEventRow")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setStyleSheet("QFrame#trackerEventRow { background: transparent; border: none; }")
        self.config = config
        self.login = event.get('login', '')
        self.event_ts = event.get('ts')
        # Overlay above children so flash is a full fill (like chat rows), not an outline
        self._hl_overlay = QWidget(self)
        self._hl_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._hl_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._hl_overlay.setStyleSheet("background: transparent;")
        self._flash = FlashHighlight(
            self._hl_overlay, lambda: (config.get("ui", "theme") == "dark")
        )
        self._hl_overlay.paintEvent = self._paint_hl_overlay  # type: ignore

        layout = QHBoxLayout(self)
        spacing = config.get("ui", "spacing", "widget_elements") or 6
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(spacing)

        ts = event.get('ts', 0)
        try:
            time_text = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        except Exception:
            time_text = "—"
        time_label = QLabel(time_text)
        time_label.setFont(get_font(FontType.UI))
        time_label.setStyleSheet("color: #888;")
        time_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout.addWidget(time_label)

        event_type = event.get('type', '')
        layout.addWidget(make_presence_badge(event_type))

        self.name_label = QLabel(self.login)
        self.name_label.setFont(get_font(FontType.TEXT))
        self.name_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.name_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name_label.mousePressEvent = self._on_name_click  # type: ignore
        self._apply_name_color()
        layout.addWidget(self.name_label)

        gid_label = make_game_id_label(event_type, event.get('game_id'))
        if gid_label is not None:
            layout.addWidget(gid_label)

        layout.addStretch(1)

    def _apply_name_color(self):
        is_dark = self.config.get("ui", "theme") == "dark"
        color = get_cache().get_username_color(self.login, is_dark)
        self.name_label.setStyleSheet(f"color: {color}; background: transparent;")

    def apply_theme(self):
        self._apply_name_color()
        self._flash.is_dark_fn = lambda: (self.config.get("ui", "theme") == "dark")

    def _on_name_click(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.login:
            ctrl_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.filter_clicked.emit(self.login, ctrl_pressed)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            event.ignore()
            return
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._hl_overlay.setGeometry(self.rect())
        self._hl_overlay.raise_()

    def flash(self):
        self._hl_overlay.setGeometry(self.rect())
        self._hl_overlay.raise_()
        self._flash.start()

    def _paint_hl_overlay(self, event):
        painter = QPainter(self._hl_overlay)
        self._flash.paint_overlay(painter, self._hl_overlay.rect())


class TrackerUserChip(UserCountRow):
    """History filter chip: avatar + login + event count, orange highlight when filtered"""

    delete_requested = pyqtSignal(str)  # login

    def __init__(self, config, icons_path: Path, login: str, count: int, user_id: str = None):
        super().__init__(login, count, config, icons_path, user_id,
                          margins=(2, 0, 2, 0), filter_radius=6)
        self.login = login  # alias kept for readability at call sites (== self.username)
        self.delete_button = create_icon_button(
            icons_path, "trash.svg", "Remove history for this user",
            size_type="small", config=config
        )
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.login))
        self.layout().addWidget(self.delete_button)


class UserTrackerWidget(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, config, icons_path: Path, user_tracker: UserTracker, font_scaler=None):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.user_tracker = user_tracker
        self.font_scaler = font_scaler
        self.user_items = []
        self._empty_label = None
        self.filtered_logins = set()
        self.chip_widgets = {}  # login -> TrackerUserChip
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
        self.filter_scroll.setFixedWidth(get_userlist_width())
        for item in self.user_items:
            item.update_font_scale()
        if self.user_items:
            self._recalculate_layout()

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
            self.icons_path, "go-back.svg", "Back to Messages", config=self.config
        )
        self.back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.back_button)

        title_label = QLabel("User Tracker")
        title_label.setFont(get_font(FontType.HEADER))
        header_layout.addWidget(title_label, stretch=1)

        self.add_user_button = create_icon_button(
            self.icons_path, "add.svg", "Add user", config=self.config
        )
        self.add_user_button.clicked.connect(self._add_new_item)
        header_layout.addWidget(self.add_user_button)

        self.clear_filter_button = create_icon_button(
            self.icons_path, "filter.svg", "Clear history filter", config=self.config
        )
        self.clear_filter_button.clicked.connect(self._clear_filter)
        self.clear_filter_button.setVisible(False)
        header_layout.addWidget(self.clear_filter_button)

        self.clear_history_button = create_icon_button(
            self.icons_path, "trash.svg", "Clear History", config=self.config
        )
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

        self.tabs.addTab(tracked_page, "Tracked")

        # --- History tab ---
        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(4, 4, 4, 4)
        history_layout.setSpacing(6)

        history_row = QHBoxLayout()
        history_row.setSpacing(6)
        history_layout.addLayout(history_row, stretch=1)

        self.events_scroll = QScrollArea()
        self.events_scroll.setWidgetResizable(True)
        self.events_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.events_container = QWidget()
        self.events_layout = QVBoxLayout()
        self.events_layout.setContentsMargins(0, 0, 0, 0)
        self.events_layout.setSpacing(1)
        self.events_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.events_container.setLayout(self.events_layout)
        self.events_scroll.setWidget(self.events_container)
        history_row.addWidget(self.events_scroll, stretch=1)

        self.history_scroll_buttons = ScrollButtonsPanel(self.events_scroll, parent=self.events_scroll)
        self.history_auto_scroller = AutoScroller(self.events_scroll)

        self.filter_scroll = QScrollArea()
        self.filter_scroll.setWidgetResizable(True)
        self.filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.filter_scroll.setVisible(False)
        self.filter_scroll.setFixedWidth(get_userlist_width())
        filter_container = QWidget()
        self.filter_chips_layout = QVBoxLayout()
        self.filter_chips_layout.setContentsMargins(4, 4, 4, 4)
        self.filter_chips_layout.setSpacing(2)
        filter_container.setLayout(self.filter_chips_layout)
        self.filter_chips_layout.addStretch()
        self.filter_scroll.setWidget(filter_container)
        history_row.addWidget(self.filter_scroll)

        self.filter_auto_scroller = AutoScroller(self.filter_scroll)

        self.tabs.addTab(history_page, "History")

    def toggle_userlist(self) -> bool:
        """Toggle the history filter sidebar; returns new visibility state."""
        self.userlist_visible = not self.userlist_visible
        self.config.set("ui", "userlist", "tracker", value=self.userlist_visible)
        self.filter_scroll.setVisible(self.userlist_visible and bool(self.chip_widgets))
        set_visual_active(self.userlist_toggle_button, self.userlist_visible)
        return self.userlist_visible

    def _on_tab_changed(self, index: int):
        is_tracked = index == 0
        self.add_user_button.setVisible(is_tracked)
        self.clear_history_button.setVisible(not is_tracked)
        self.clear_filter_button.setVisible(not is_tracked and bool(self.filtered_logins))
        if is_tracked and self.user_items:
            QTimer.singleShot(0, self._recalculate_layout)

    def _load_selected(self):
        for item in list(self.user_items):
            self.users_grid.removeWidget(item)
            item.cleanup()
            item.deleteLater()
        self.user_items.clear()

        for user_id, username in self.user_tracker.get_selected().items():
            self._add_item(username, user_id, recalculate=False)
            item = self.user_items[-1]
            if self.user_tracker.is_frozen(user_id=user_id):
                item.set_frozen(True)

        if self.user_items:
            QTimer.singleShot(50, self._recalculate_layout)

    def _add_item(self, username="", user_id="", recalculate=True):
        item = TrackedUserItem(self.config, self.icons_path, username, user_id)
        item.parent_widget = self
        item.remove_requested.connect(self._remove_item)
        self.user_items.append(item)
        if recalculate:
            self._recalculate_layout()

    def _add_new_item(self):
        for item in self.user_items:
            if item.is_empty():
                item._update_input_style(highlight_empty=True)
                item.username_input.setFocus()
                return
        self._add_item()

    def _remove_item(self, item: TrackedUserItem):
        if item in self.user_items:
            self.user_items.remove(item)
            self.users_grid.removeWidget(item)
            item.cleanup()
            item.deleteLater()
            self._save_selected()
            self._recalculate_layout()

    def _save_selected(self):
        self.user_tracker.clear_selected()
        for item in self.user_items:
            username, user_id = item.get_data()
            if username and user_id and item.username_valid:
                self.user_tracker.add_selected(user_id, username)

    def _recalculate_layout(self):
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
        QTimer.singleShot(50, self._recalculate_layout)

    def showEvent(self, event):
        super().showEvent(event)
        if self.user_items:
            QTimer.singleShot(0, self._recalculate_layout)

    def _clear_events_layout(self):
        while self.events_layout.count():
            child = self.events_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()
        self._empty_label = None

    def _show_empty(self):
        self._empty_label = QLabel("No events yet")
        self._empty_label.setFont(get_font(FontType.UI))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888;")
        self._empty_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.events_layout.addWidget(self._empty_label)

    def _scroll_history_to_bottom(self):
        sb = self.events_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _make_event_row(self, event: dict) -> EventRow:
        row = EventRow(self.config, event)
        row.filter_clicked.connect(self._handle_filter_click)
        return row

    def _handle_filter_click(self, login: str, ctrl_pressed: bool):
        if ctrl_pressed:
            if login in self.filtered_logins:
                self.filtered_logins.discard(login)
            else:
                self.filtered_logins.add(login)
        else:
            if self.filtered_logins == {login}:
                self.filtered_logins = set()
            else:
                self.filtered_logins = {login}
        self._update_filter_button()
        self._apply_event_filter()
        self._update_chip_highlights()

    def _clear_filter(self):
        self.filtered_logins.clear()
        self._update_filter_button()
        self._apply_event_filter()
        self._update_chip_highlights()

    def _update_filter_button(self):
        active = bool(self.filtered_logins)
        on_history = self.tabs.currentIndex() == 1
        self.clear_filter_button.setVisible(on_history and active)
        if active:
            names = ", ".join(sorted(self.filtered_logins))
            self.clear_filter_button.setToolTip(f"Clear filter: {names}")
        else:
            self.clear_filter_button.setToolTip("Clear history filter")

    def _rebuild_events(self):
        """Full teardown/rebuild - use only when the whole event list needs reloading
        (open/refresh, clear history). Everything else updates widgets in place."""
        self._clear_events_layout()
        events = self.user_tracker.get_events()
        for event in events:
            self.events_layout.addWidget(self._make_event_row(event))
        self._apply_event_filter()
        if events:
            QTimer.singleShot(0, self._scroll_history_to_bottom)
        self._rebuild_filter_chips()

    def _apply_event_filter(self):
        """Show/hide existing event rows in place - no widget recreation."""
        has_visible = False
        for i in range(self.events_layout.count()):
            widget = self.events_layout.itemAt(i).widget()
            if isinstance(widget, EventRow):
                visible = not self.filtered_logins or widget.login in self.filtered_logins
                widget.setVisible(visible)
                has_visible = has_visible or visible

        if self._empty_label is not None:
            self.events_layout.removeWidget(self._empty_label)
            self._empty_label.deleteLater()
            self._empty_label = None
        if not has_visible:
            self._show_empty()

    def _update_chip_highlights(self):
        """Update filter highlight on existing chips - no widget recreation."""
        for login, chip in self.chip_widgets.items():
            chip.set_filtered(login in self.filtered_logins)

    def _rebuild_filter_chips(self):
        while self.filter_chips_layout.count() > 1:
            item = self.filter_chips_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.chip_widgets = {}

        events = self.user_tracker.get_events()
        counts = Counter(e.get('login') for e in events if e.get('login'))
        user_ids = {}
        for e in events:
            login = e.get('login')
            if login and login not in user_ids and e.get('user_id'):
                user_ids[login] = e['user_id']

        self.filter_scroll.setVisible(self.userlist_visible and bool(counts))
        for login, count in sorted(counts.items(), key=lambda x: (-x[1], x[0].lower())):
            chip = TrackerUserChip(self.config, self.icons_path, login, count, user_ids.get(login))
            chip.set_filtered(login in self.filtered_logins)
            chip.clicked.connect(self._handle_filter_click)
            chip.delete_requested.connect(self._handle_chip_delete_requested)
            self.filter_chips_layout.insertWidget(self.filter_chips_layout.count() - 1, chip)
            self.chip_widgets[login] = chip

    def _handle_chip_delete_requested(self, login: str):
        reply = QMessageBox.question(
            self, "Remove History",
            f"Remove all history for {login}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.user_tracker.remove_user_events(login)
        self.filtered_logins.discard(login)
        self._update_filter_button()
        self._remove_login_from_view(login)

    def _remove_login_from_view(self, login: str):
        """Remove only this login's rows/chip in place - no rebuild of the rest."""
        has_visible = False
        for i in reversed(range(self.events_layout.count())):
            widget = self.events_layout.itemAt(i).widget()
            if isinstance(widget, EventRow):
                if widget.login == login:
                    self.events_layout.removeWidget(widget)
                    widget.deleteLater()
                elif widget.isVisible():
                    has_visible = True
        if not has_visible and self._empty_label is None:
            self._show_empty()

        chip = self.chip_widgets.pop(login, None)
        if chip is not None:
            self.filter_chips_layout.removeWidget(chip)
            chip.deleteLater()
        self.filter_scroll.setVisible(self.userlist_visible and bool(self.chip_widgets))

    def append_event(self, event: dict):
        if self._empty_label is not None:
            self.events_layout.removeWidget(self._empty_label)
            self._empty_label.deleteLater()
            self._empty_label = None
        row = self._make_event_row(event)
        row.setVisible(not self.filtered_logins or row.login in self.filtered_logins)
        self.events_layout.addWidget(row)
        if row.isVisible():
            QTimer.singleShot(0, self._scroll_history_to_bottom)
        self._bump_chip_count(event)

    def _bump_chip_count(self, event: dict):
        """Update or create the one affected chip in place - no rebuild of the rest.
        New/updated chips aren't re-sorted live; order settles on the next full rebuild."""
        login = event.get('login')
        if not login:
            return
        chip = self.chip_widgets.get(login)
        if chip is not None:
            chip.count_label.setText(str(int(chip.count_label.text()) + 1))
            return
        chip = TrackerUserChip(self.config, self.icons_path, login, 1, event.get('user_id') or None)
        chip.set_filtered(login in self.filtered_logins)
        chip.clicked.connect(self._handle_filter_click)
        chip.delete_requested.connect(self._handle_chip_delete_requested)
        self.filter_chips_layout.insertWidget(0, chip)
        self.chip_widgets[login] = chip
        self.filter_scroll.setVisible(self.userlist_visible and bool(self.chip_widgets))

    def _clear_history(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Clear all join/left history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.user_tracker.clear_events()
            self._rebuild_events()


    def update_theme(self):
        for i in range(self.events_layout.count()):
            w = self.events_layout.itemAt(i).widget()
            if isinstance(w, EventRow):
                w.apply_theme()
        for item in self.user_items:
            if hasattr(item, "apply_theme"):
                item.apply_theme()
        self._rebuild_filter_chips()

    def reveal_event(self, login: str, event_ts: float = None):
        """Switch to History, scroll to matching event, flash highlight."""
        self.tabs.setCurrentIndex(1)
        # Clear filter so the row is visible
        if self.filtered_logins:
            self.filtered_logins.clear()
            self._update_filter_button()
            self._apply_event_filter()
            self._update_chip_highlights()

        target = None
        for i in range(self.events_layout.count()):
            w = self.events_layout.itemAt(i).widget()
            if not isinstance(w, EventRow):
                continue
            if login and w.login != login:
                continue
            if event_ts is not None and w.event_ts is not None:
                if abs(float(w.event_ts) - float(event_ts)) > 0.05:
                    continue
            target = w
            # prefer exact ts match; keep last matching login if no ts
            if event_ts is not None:
                break

        if target is None:
            return

        self.events_scroll.ensureWidgetVisible(target, 0, 40)
        # same timing idea as chatlog _scroll_and_highlight
        QTimer.singleShot(50, lambda: self.events_scroll.ensureWidgetVisible(target, 0, 40))
        QTimer.singleShot(200, target.flash)

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
        if getattr(self, "history_scroll_buttons", None):
            self.history_scroll_buttons.cleanup()
        if getattr(self, "history_auto_scroller", None):
            self.history_auto_scroller.cleanup()
        if getattr(self, "filter_auto_scroller", None):
            self.filter_auto_scroller.cleanup()
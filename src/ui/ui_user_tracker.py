"""User Tracker UI — tracked users + join/left history"""
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Dict, List, Optional, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListView,
    QScrollArea, QMessageBox, QTabWidget, QSizePolicy, QGridLayout, QStackedWidget,
    QStyledItemDelegate, QStyleOptionViewItem
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QAbstractListModel, QSortFilterProxyModel,
    QModelIndex, QSize, QRect, QEvent
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QPixmap, QPainter, QPen, QFontMetrics, QColor, QCursor

from helpers.create import create_icon_button, set_visual_active
from helpers.fonts import (
    get_font,
    FontType,
    get_userlist_width,
    get_scaled_width
)
from helpers.user_tracker import UserTracker
from helpers.cache import get_cache
from helpers.flash_highlight import highlight_fill_color
from helpers.scroll.auto_scroll import AutoScroller
from helpers.scroll.scroll_buttons import ScrollButtonsPanel
from helpers.scroll.scroll import scroll
from core.api_data import validate_username_and_get_id
from components.presence_badge import (
    TypeFilterBar,
    toggle_filter_value,
    presence_badge_style
)
from components.user_count_row import UserCountRow
from components.messages_separator import DateSeparator



def event_date_str(event: dict) -> Optional[str]:
    if event.get('is_separator'):
        return event.get('date_str')
    ts = event.get('timestamp')
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
    except Exception:
        return None


def inject_date_separators(events: List[dict]) -> List[dict]:
    """Insert a DateSeparator row before each new calendar day."""
    result = []
    last_date = None
    for event in events:
        if event.get('is_separator'):
            continue
        date_str = event_date_str(event)
        if date_str and date_str != last_date:
            result.append({
                'is_separator': True,
                'date_str': date_str,
                'timestamp': event.get('timestamp', 0),
            })
            last_date = date_str
        result.append(event)
    return result


class TrackerEventModel(QAbstractListModel):
    """Model for join/left/game tracker events - data only, no rendering"""

    def __init__(self):
        super().__init__()
        self._events: List[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._events)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._events):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._events[index.row()]
        return None

    def set_events(self, events: List[dict]):
        self.beginResetModel()
        self._events = inject_date_separators(events)
        self.endResetModel()

    def append_event(self, event: dict) -> int:
        date_str = event_date_str(event)
        last_date = None
        for existing in reversed(self._events):
            if existing.get('is_separator'):
                last_date = existing.get('date_str')
                break
            last_date = event_date_str(existing)
            if last_date:
                break

        if date_str and date_str != last_date:
            separator = {
                'is_separator': True,
                'date_str': date_str,
                'timestamp': event.get('timestamp', 0),
            }
            row = len(self._events)
            self.beginInsertRows(QModelIndex(), row, row + 1)
            self._events.append(separator)
            self._events.append(event)
            self.endInsertRows()
            return row + 1

        row = len(self._events)
        self.beginInsertRows(QModelIndex(), row, row)
        self._events.append(event)
        self.endInsertRows()
        return row

    def remove_login(self, login: str) -> int:
        raw = [e for e in self._events
               if not e.get('is_separator') and e.get('login') != login]
        removed = sum(
            1 for e in self._events
            if not e.get('is_separator') and e.get('login') == login
        )
        self.beginResetModel()
        self._events = inject_date_separators(raw)
        self.endResetModel()
        return removed

    def find_row(self, login: str = None, event_ts: float = None) -> Optional[int]:
        target = None
        for row, event in enumerate(self._events):
            if event.get('is_separator'):
                continue
            if login and event.get('login') != login:
                continue
            if event_ts is not None:
                ts = event.get('timestamp')
                if ts is None or abs(float(ts) - float(event_ts)) > 0.05:
                    continue
            target = row
            if event_ts is not None:
                break
        return target

    def clear(self):
        self.set_events([])

    def get_events(self) -> List[dict]:
        return list(self._events)


class TrackerEventFilterProxy(QSortFilterProxyModel):
    """Filters tracker events by login, event type and/or date without touching the source model"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filtered_logins: Set[str] = set()
        self.filtered_types: Set[str] = set()
        self.filtered_dates: Set[str] = set()

    def set_filters(self, logins: Set[str], types: Set[str], dates: Set[str] = None):
        self.filtered_logins = set(logins)
        self.filtered_types = set(types)
        self.filtered_dates = set(dates or ())
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self.sourceModel()
        event = source_model.data(
            source_model.index(source_row, 0, source_parent),
            Qt.ItemDataRole.DisplayRole,
        )
        if not event:
            return True

        date_str = event_date_str(event)

        if event.get('is_separator'):
            if self.filtered_dates and date_str not in self.filtered_dates:
                return False
            # Hide separator when no real event of that day would remain visible
            for row in range(source_row + 1, source_model.rowCount()):
                sibling = source_model.data(
                    source_model.index(row, 0, source_parent),
                    Qt.ItemDataRole.DisplayRole,
                )
                if not sibling or sibling.get('is_separator'):
                    break
                if self._event_matches(sibling):
                    return True
            return False

        if self.filtered_dates and date_str not in self.filtered_dates:
            return False
        return self._event_matches(event)

    def _event_matches(self, event: dict) -> bool:
        if self.filtered_logins and event.get('login') not in self.filtered_logins:
            return False
        if self.filtered_types and (event.get('type') or '') not in self.filtered_types:
            return False
        return True


class TrackerEventDelegate(QStyledItemDelegate):
    """Renders tracker events (time, type badge, username, game id) with virtual scrolling"""

    filter_clicked = pyqtSignal(str, bool)       # login, ctrl_pressed
    type_filter_clicked = pyqtSignal(str, bool)  # event_type, ctrl_pressed
    date_filter_clicked = pyqtSignal(str, bool)  # date_str, ctrl_pressed

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        theme = config.get("ui", "theme") or "dark"
        self.is_dark_theme = (theme == "dark")

        self.padding = 8
        self.spacing = config.get("ui", "spacing", "widget_elements") or 6

        self.click_rects: Dict[int, Dict] = {}
        self.list_view = None

        self.highlighted_row = None
        self.highlight_opacity = 0.0
        self.highlight_timer = QTimer()
        self.highlight_timer.timeout.connect(self.highlight_row)
        self.highlight_timer.setInterval(50)

        self._reload_fonts()

    def _reload_fonts(self):
        self.time_font = get_font(FontType.TEXT)
        self.badge_font = get_font(FontType.TEXT)
        self.name_font = get_font(FontType.TEXT)
        self.gid_font = get_font(FontType.TEXT)

    def set_list_view(self, list_view):
        self.list_view = list_view

    def cleanup(self):
        self.highlight_timer.stop()
        self.list_view = None
        self.click_rects.clear()

    def clear_click_rects(self):
        self.click_rects.clear()

    def update_theme(self):
        theme = self.config.get("ui", "theme") or "dark"
        self.is_dark_theme = (theme == "dark")
        self._reload_fonts()

    def update_fonts(self):
        """Call after text font size change so row heights and paint use the new size."""
        self._reload_fonts()
        self.click_rects.clear()
        if self.list_view is not None:
            try:
                self.list_view.scheduleDelayedItemsLayout()
                self.list_view.viewport().update()
            except RuntimeError:
                pass

    def _row_height(self) -> int:
        name_h = QFontMetrics(self.name_font).height()
        badge_h = QFontMetrics(self.badge_font).height() + 6
        return max(name_h, badge_h) + 4

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        width = option.rect.width()
        if width <= 0 and self.list_view is not None:
            try:
                width = self.list_view.viewport().width()
            except RuntimeError:
                width = 0
        if width <= 0:
            width = 800
        event = index.data(Qt.ItemDataRole.DisplayRole) or {}
        if event.get('is_separator'):
            return QSize(width, DateSeparator.get_height())
        return QSize(width, self._row_height())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        event = index.data(Qt.ItemDataRole.DisplayRole)
        if not event:
            return

        row = index.row()
        self.click_rects[row] = {'username': QRect(), 'badge': QRect(), 'separator': QRect()}

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if row == self.highlighted_row and self.highlight_opacity > 0:
            painter.fillRect(option.rect, highlight_fill_color(self.is_dark_theme, self.highlight_opacity))

        if event.get('is_separator'):
            DateSeparator.render(
                painter,
                option.rect,
                event.get('date_str') or '',
                self.time_font,
                self.is_dark_theme,
            )
            self.click_rects[row]['separator'] = QRect(option.rect)
            painter.restore()
            return

        x = option.rect.x() + self.padding
        y = option.rect.y()
        h = option.rect.height()

        ts = event.get('timestamp', 0)
        try:
            time_text = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        except Exception:
            time_text = "—"
        painter.setFont(self.time_font)
        painter.setPen(QColor("#888888"))
        ts_fm = QFontMetrics(self.time_font)
        ts_width = ts_fm.horizontalAdvance(time_text)
        painter.drawText(
            QRect(x, y, ts_width, h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            time_text,
        )
        x += ts_width + self.spacing

        event_type = event.get('type', '') or ''
        badge_text, badge_bg, badge_fg, badge_border = presence_badge_style(
            event_type, self.is_dark_theme
        )
        painter.setFont(self.badge_font)
        badge_fm = QFontMetrics(self.badge_font)
        badge_width = badge_fm.horizontalAdvance(badge_text) + 12
        badge_height = badge_fm.height() + 6
        badge_rect = QRect(x, y + (h - badge_height) // 2, badge_width, badge_height)
        border_width = 2
        inset = border_width // 2
        pen = QPen(QColor(badge_border))
        pen.setWidth(border_width)
        painter.setPen(pen)
        painter.setBrush(QColor(badge_bg))
        painter.drawRoundedRect(
            badge_rect.adjusted(inset, inset, -inset, -inset), 4, 4
        )
        painter.setPen(QColor(badge_fg))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        self.click_rects[row]['badge'] = badge_rect
        x += badge_width + self.spacing

        login = event.get('login', '') or ''
        painter.setFont(self.name_font)
        name_fm = QFontMetrics(self.name_font)
        name_color = get_cache().get_username_color(login, self.is_dark_theme)
        painter.setPen(QColor(name_color))
        name_width = name_fm.horizontalAdvance(login)
        name_rect = QRect(x, y, name_width, h)
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            login,
        )
        self.click_rects[row]['username'] = name_rect
        x += name_width + self.spacing

        game_id = event.get('game_id')
        if game_id and event_type == 'game':
            gid_text = f"#{game_id}"
            painter.setFont(self.gid_font)
            painter.setPen(QColor("#888888"))
            gid_width = QFontMetrics(self.gid_font).horizontalAdvance(gid_text)
            painter.drawText(
                QRect(x, y, gid_width, h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                gid_text,
            )

        painter.restore()

    def editorEvent(self, event: QEvent, model, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        row = index.row()
        rects = self.click_rects.get(row)

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton or not rects:
                return super().editorEvent(event, model, option, index)
            data = index.data(Qt.ItemDataRole.DisplayRole) or {}
            ctrl_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            pos = event.pos()
            if data.get('is_separator') and rects.get('separator') and rects['separator'].contains(pos):
                date_str = data.get('date_str') or ''
                if date_str:
                    self.date_filter_clicked.emit(date_str, ctrl_pressed)
                return True
            if rects['username'].contains(pos) and data.get('login'):
                self.filter_clicked.emit(data['login'], ctrl_pressed)
                return True
            if rects['badge'].contains(pos) and data.get('type'):
                self.type_filter_clicked.emit(data['type'], ctrl_pressed)
                return True

        elif event.type() == QEvent.Type.MouseMove:
            if rects and self.list_view:
                pos = event.pos()
                is_over_clickable = (
                    rects['username'].contains(pos)
                    or rects['badge'].contains(pos)
                    or (rects.get('separator') and rects['separator'].contains(pos))
                )
                cursor = Qt.CursorShape.PointingHandCursor if is_over_clickable else Qt.CursorShape.ArrowCursor
                self.list_view.setCursor(QCursor(cursor))

        return super().editorEvent(event, model, option, index)

    def highlight_row(self, row: int = None):
        if row is not None:
            self.highlighted_row = row
            self.highlight_opacity = 1.0
            if not self.highlight_timer.isActive():
                self.highlight_timer.start()
        else:
            self.highlight_opacity -= 0.05
            if self.highlight_opacity <= 0:
                self.highlight_opacity = 0.0
                self.highlighted_row = None
                self.highlight_timer.stop()

        if self.highlighted_row is not None and self.list_view and self.list_view.model():
            index = self.list_view.model().index(self.highlighted_row, 0)
            self.list_view.viewport().update(self.list_view.visualRect(index))


class TrackedUserItem(QWidget):
    remove_requested = pyqtSignal(object)

    USERNAME_BASE_WIDTH = 220
    USER_ID_BASE_WIDTH = 125
    ARROW_WIDTH = 26
    BUTTON_WIDTH = 48

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
        self._username_width = get_scaled_width(self.USERNAME_BASE_WIDTH)
        self._user_id_width = get_scaled_width(self.USER_ID_BASE_WIDTH)
        self.username_input.setFont(get_font(FontType.TEXT))
        self.user_id_input.setFont(get_font(FontType.TEXT))
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


class TrackerUserChip(UserCountRow):
    """History filter chip: avatar + login + event count, orange highlight when filtered"""

    delete_requested = pyqtSignal(str)

    def __init__(self, config, icons_path: Path, login: str, count: int, user_id: str = None):
        super().__init__(
            login, count, config, icons_path, user_id,
            margins=(2, 0, 2, 0), filter_radius=6,
        )
        self.login = login
        self.delete_button = create_icon_button(
            icons_path, "trash.svg", "Remove history for this user",
            size_type="small", config=config
        )
        self.delete_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.login))
        self.layout().addWidget(self.delete_button)


class UserTrackerWidget(QWidget):
    back_requested = pyqtSignal()
    tracked_users_changed = pyqtSignal()

    def __init__(self, config, icons_path: Path, user_tracker: UserTracker, font_scaler=None):
        super().__init__()
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
            self._recalculate_layout()
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
            self.icons_path, "go-back.svg", "Back to Messages", config=self.config
        )
        self.back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.back_button)

        title_label = QLabel("User Tracker")
        title_label.setFont(get_font(FontType.HEADER))
        header_layout.addWidget(title_label)

        self.info_label = QLabel("")
        self.info_label.setFont(get_font(FontType.UI))
        self.info_label.setStyleSheet("color: #888;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_label.setVisible(False)
        header_layout.addWidget(self.info_label, stretch=1)

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

        self._empty_history_label = QLabel("No events")
        self._empty_history_label.setFont(get_font(FontType.UI))
        self._empty_history_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_history_label.setStyleSheet("color: #888;")

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

        self.tabs.addTab(history_page, "History")

    def toggle_userlist(self) -> bool:
        self.userlist_visible = not self.userlist_visible
        self.config.set("ui", "userlist", "tracker", value=self.userlist_visible)
        self._update_filter_panel_visibility()
        return self.userlist_visible

    def _update_filter_panel_visibility(self):
        self.filter_panel.setVisible(self.userlist_visible and bool(self.chip_widgets))

    def _make_chip(self, login: str, count: int, user_id: str = None) -> "TrackerUserChip":
        chip = TrackerUserChip(self.config, self.icons_path, login, count, user_id)
        chip.set_filtered(login in self.filtered_logins)
        chip.clicked.connect(self._handle_filter_click)
        chip.delete_requested.connect(self._handle_chip_delete_requested)
        self.chip_widgets[login] = chip
        return chip

    def _on_tab_changed(self, index: int):
        is_tracked = index == 0
        self.add_user_button.setVisible(is_tracked)
        self.clear_history_button.setVisible(not is_tracked)
        self.clear_filter_button.setVisible(not is_tracked and self._has_active_filters())
        self.info_label.setVisible(not is_tracked)
        if not is_tracked:
            self._update_info_label()
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
        self.tracked_users_changed.emit()

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

    def _update_history_empty_state(self):
        self.history_stack.setCurrentIndex(1 if self.history_proxy.rowCount() == 0 else 0)

    def _scroll_history_to_bottom(self):
        scroll(self.history_list_view, mode="bottom", delay=10)

    def _update_info_label(self):
        total = sum(
            1 for e in self.history_model.get_events() if not e.get('is_separator')
        )
        if total == 0:
            self.info_label.setText("No events")
            return
        shown = 0
        for row in range(self.history_proxy.rowCount()):
            event = self.history_proxy.data(
                self.history_proxy.index(row, 0), Qt.ItemDataRole.DisplayRole
            )
            if event and not event.get('is_separator'):
                shown += 1
        desc = self._filter_description()
        if desc:
            self.info_label.setText(f"Showing {shown}/{total} events ({desc})")
        else:
            self.info_label.setText(f"{total} events")

    def _toggle_filter_set(self, attr: str, value: str, ctrl_pressed: bool, on_changed=None):
        if not value:
            return
        setattr(self, attr, toggle_filter_value(getattr(self, attr), value, ctrl_pressed))
        if on_changed:
            on_changed()
        self._update_filter_button()
        self._apply_event_filter()

    def _handle_filter_click(self, login: str, ctrl_pressed: bool):
        self._toggle_filter_set('filtered_logins', login, ctrl_pressed, self._update_chip_highlights)

    def _handle_type_filter_click(self, event_type: str, ctrl_pressed: bool):
        self._toggle_filter_set(
            'filtered_types', event_type, ctrl_pressed,
            lambda: self.type_filter_bar.set_active_types(self.filtered_types)
        )

    def _handle_date_filter_click(self, date_str: str, ctrl_pressed: bool):
        self._toggle_filter_set('filtered_dates', date_str, ctrl_pressed)

    def _on_type_filter_changed(self, types):
        self.filtered_types = set(types)
        self._update_filter_button()
        self._apply_event_filter()

    def _clear_filter(self):
        self.filtered_logins.clear()
        self.filtered_types.clear()
        self.filtered_dates.clear()
        self.type_filter_bar.set_active_types(())
        self._update_filter_button()
        self._apply_event_filter()
        self._update_chip_highlights()

    def _filter_description(self) -> str:
        parts = []
        if self.filtered_dates:
            parts.append(", ".join(sorted(self.filtered_dates)))
        if self.filtered_logins:
            parts.append(", ".join(sorted(self.filtered_logins)))
        if self.filtered_types:
            parts.append("/".join(t.upper() for t in sorted(self.filtered_types)))
        return " · ".join(parts)

    def _has_active_filters(self) -> bool:
        return bool(self.filtered_logins) or bool(self.filtered_types) or bool(self.filtered_dates)

    def _update_filter_button(self):
        active = self._has_active_filters()
        on_history = self.tabs.currentIndex() == 1
        self.clear_filter_button.setVisible(on_history and active)
        self.clear_filter_button.setToolTip(
            f"Clear filter: {self._filter_description()}" if active else "Clear history filter"
        )

    def _rebuild_events(self):
        events = self.user_tracker.get_events()
        self.history_model.set_events(events)
        self.history_delegate.clear_click_rects()
        self._apply_event_filter()
        if events:
            QTimer.singleShot(0, self._scroll_history_to_bottom)
        self._rebuild_filter_chips()
        self._update_info_label()

    def _apply_event_filter(self):
        self.history_proxy.set_filters(self.filtered_logins, self.filtered_types, self.filtered_dates)
        self.history_delegate.clear_click_rects()
        self._update_history_empty_state()
        self._update_info_label()

    def _update_chip_highlights(self):
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

        for login, count in sorted(counts.items(), key=lambda x: (-x[1], x[0].lower())):
            chip = self._make_chip(login, count, user_ids.get(login))
            self.filter_chips_layout.insertWidget(self.filter_chips_layout.count() - 1, chip)
        self._update_filter_panel_visibility()

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
        self.history_model.remove_login(login)
        self.history_delegate.clear_click_rects()
        self._update_history_empty_state()

        chip = self.chip_widgets.pop(login, None)
        if chip is not None:
            self.filter_chips_layout.removeWidget(chip)
            chip.deleteLater()
        self._update_filter_panel_visibility()
        self._update_info_label()

    def append_event(self, event: dict):
        sb = self.history_list_view.verticalScrollBar()
        at_bottom = (sb.maximum() - sb.value()) <= 100
        self.history_model.append_event(event)
        self._update_history_empty_state()
        if at_bottom:
            QTimer.singleShot(0, lambda: scroll(self.history_list_view, mode="bottom", delay=50))
        self._bump_chip_count(event)
        self._update_info_label()

    def _bump_chip_count(self, event: dict):
        login = event.get('login')
        if not login:
            return
        chip = self.chip_widgets.get(login)
        if chip is not None:
            chip.count_label.setText(str(int(chip.count_label.text()) + 1))
            return
        chip = self._make_chip(login, 1, event.get('user_id') or None)
        self.filter_chips_layout.insertWidget(0, chip)
        self._update_filter_panel_visibility()

    def _clear_history(self):
        if not self.user_tracker.get_events():
            return
        reply = QMessageBox.question(
            self, "Clear History",
            "Clear all join/left history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.user_tracker.clear_events()
            self._rebuild_events()

    def update_theme(self):
        self.history_delegate.update_theme()
        self.history_list_view.viewport().update()
        for item in self.user_items:
            if hasattr(item, "apply_theme"):
                item.apply_theme()
        theme = self.config.get("ui", "theme") or "dark"
        self.type_filter_bar.update_theme(theme == "dark")
        self._rebuild_filter_chips()

    def reveal_event(self, login: str, event_ts: float = None):
        self.tabs.setCurrentIndex(1)
        if self._has_active_filters():
            self._clear_filter()

        source_row = self.history_model.find_row(login, event_ts)
        if source_row is None:
            return
        proxy_index = self.history_proxy.mapFromSource(self.history_model.index(source_row, 0))
        if not proxy_index.isValid():
            return
        row = proxy_index.row()

        scroll(self.history_list_view, mode="middle", target_row=row, delay=100)
        QTimer.singleShot(250, lambda: self.history_delegate.highlight_row(row))

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
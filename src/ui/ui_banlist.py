"""Ban List Management UI Widget"""

import time
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from components.button import create_icon_button
from components.toast import show_toast, ToastKind
from components.user_entry_row import UserEntryRow
from helpers.fonts.fonts import FontType, set_font_role
from helpers.translate import on_language_changed, tr, TranslatableMixin
from helpers.users.ban_manager import BanManager
from ui.dialogs.duration_dialog import DurationDialog

_DURATION_MIN_WIDTH = 110
_DURATION_TEXT_PADDING = 40
_COUNTDOWN_TICK_MS = 1000


def _format_time_remaining(seconds: int) -> str:
    """Format remaining seconds into full format display

    Shows all relevant units based on magnitude:
    - >= 1 week: shows weeks, days, hours, minutes (e.g., "2w 0d 0h 0m")
    - >= 1 day: shows days, hours, minutes (e.g., "2d 5h 30m")
    - >= 1 hour: shows hours, minutes (e.g., "3h 45m")
    - >= 1 minute: shows minutes (e.g., "25m")
    - < 1 minute: shows seconds (e.g., "45s")
    """
    if seconds <= 0:
        return tr("Expired", "Истекло")

    w = seconds // 604800
    d = (seconds % 604800) // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    # Show all units from highest non-zero down to minutes
    if w > 0:
        return f"{w}w {d}d {h}h {m}m"
    elif d > 0:
        return f"{d}d {h}h {m}m"
    elif h > 0:
        return f"{h}h {m}m"
    elif m > 0:
        return f"{m}m"
    else:
        return f"{s}s"


class _BanItemWidget(UserEntryRow):
    """Ban row: the shared user row, with a countdown button that changes the duration of a temporary ban."""
    expired = pyqtSignal(object)  # Signal when temporary ban expires

    def __init__(self, config, icons_path: Path, username="", user_id="", expires_at=None, is_temporary=False):
        super().__init__(config, icons_path, username, user_id)
        self.expires_at = expires_at
        self.is_temporary = is_temporary

        if is_temporary:
            self._duration_button = QPushButton()
            set_font_role(self._duration_button, FontType.TEXT)
            self._duration_button.setFixedHeight(self.input_height)
            self._duration_button.setMinimumWidth(_DURATION_MIN_WIDTH)
            self._duration_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._duration_button.clicked.connect(self._change_duration)
            self.add_action(self._duration_button)

            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(self._update_duration_text)
            self._update_timer.start(_COUNTDOWN_TICK_MS)
            self._update_duration_text()

    def _update_duration_text(self):
        """Show the time left; an expired ban asks the list to remove it."""
        if not self.expires_at:
            return
        remaining = max(0, self.expires_at - int(time.time()))
        if remaining == 0:
            self._update_timer.stop()
            self.expired.emit(self)
            return
        self._duration_button.setText(_format_time_remaining(remaining))
        text_width = QFontMetrics(self._duration_button.font()).horizontalAdvance(self._duration_button.text())
        self._duration_button.setFixedWidth(max(_DURATION_MIN_WIDTH, text_width + _DURATION_TEXT_PADDING))
        self.fit_width()

    def _change_duration(self):
        """Show dialog to change duration for temporary ban"""
        current_remaining = max(60, self.expires_at - int(time.time())) if self.expires_at else 3600

        # The dialog keeps the unit of the current remaining time when it can
        seconds, ok = DurationDialog.get_duration(self, current_remaining)
        if ok and seconds > 0:
            self.expires_at = int(time.time()) + seconds
            self._update_duration_text()
            self.changed.emit()

    def get_values(self):
        """Get username, user_id, and expires_at"""
        username, user_id = self.get_data()
        return username, user_id, self.expires_at

    def cleanup(self):
        """Stop the countdown"""
        if self.is_temporary:
            self._update_timer.stop()


class BanListWidget(TranslatableMixin, QWidget):
    """Widget for managing banned users with separate permanent/temporary sections"""

    back_requested = pyqtSignal()

    def __init__(self, config, icons_path: Path, ban_manager: BanManager):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.ban_manager = ban_manager
        self._perm_items = []  # Permanent ban items
        self._temp_items = []  # Temporary ban items

        self._setup_ui()
        self.load_bans()

    def _create_section(self, title_en: str, title_ru: str, tooltip_en: str, tooltip_ru: str, is_temporary: bool):
        """Helper to create a section (avoid code duplication)"""
        section = QWidget()
        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(4, 4, 4, 4)
        section_layout.setSpacing(6)
        section.setLayout(section_layout)

        # Header with title and add button
        header = QHBoxLayout()
        label = QLabel()
        set_font_role(label, FontType.HEADER)
        self.tr_set(label.setText, title_en, title_ru)
        header.addWidget(label, stretch=1)

        count_label = QLabel()
        count_label.setObjectName("mutedHint")
        header.addWidget(count_label)

        add_button = create_icon_button(self.icons_path, "line/add-large-line.svg", "", config=self.config)
        self.tr_set(add_button.setToolTip, tooltip_en, tooltip_ru)
        add_button.clicked.connect(lambda: self._add_new_item(is_temporary))
        header.addWidget(add_button)
        section_layout.addLayout(header)

        # Grid layout for items
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(self.config.get("ui", "spacing", "list_items") or 2)
        grid.setVerticalSpacing((self.config.get("ui", "spacing", "list_items") or 2) * 2)
        grid.setHorizontalSpacing((self.config.get("ui", "spacing", "list_items") or 2) * 4)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        section_layout.addLayout(grid)

        return section, grid, count_label

    def _setup_ui(self):
        """Setup UI with separate sections"""
        window_margin = self.config.get("ui", "margins", "window") or 10
        window_spacing = self.config.get("ui", "spacing", "window_content") or 10

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(window_margin, window_margin, window_margin, window_margin)
        main_layout.setSpacing(window_spacing)
        self.setLayout(main_layout)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        main_layout.addLayout(header_layout)

        self._back_button = create_icon_button(
            self.icons_path, "line/arrow-go-back-line.svg", "", config=self.config
        )
        self.tr_set(self._back_button.setToolTip, "Back to Messages", "Назад к сообщениям")
        self._back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self._back_button)

        title_label = QLabel()
        set_font_role(title_label, FontType.HEADER)
        self.tr_set(title_label.setText, "Ban List", "Список забаненных")
        header_layout.addWidget(title_label, stretch=1)

        self._total_count_label = QLabel()
        self._total_count_label.setObjectName("mutedHint")
        header_layout.addWidget(self._total_count_label)

        self._clear_all_button = create_icon_button(
            self.icons_path, "fill/delete-bin-fill.svg", "", config=self.config
        )
        self.tr_set(self._clear_all_button.setToolTip, "Clear All", "Очистить всё")
        self._clear_all_button.clicked.connect(self._clear_all)
        header_layout.addWidget(self._clear_all_button)

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(self.scroll, stretch=1)

        # Container with sections
        self._items_container = QWidget()
        sections_layout = QVBoxLayout()
        sections_layout.setContentsMargins(0, 0, 0, 0)
        sections_layout.setSpacing(self.config.get("ui", "spacing", "list_items") or 6)
        sections_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._items_container.setLayout(sections_layout)

        # Create permanent section
        perm_section, self._perm_layout, self._perm_count_label = self._create_section(
            "Permanent", "Постоянные", "Add to Permanent", "Добавить в постоянные", is_temporary=False
        )
        sections_layout.addWidget(perm_section)

        # Create temporary section
        temp_section, self._temp_layout, self._temp_count_label = self._create_section(
            "Temporary", "Временные", "Add to Temporary", "Добавить во временные", is_temporary=True
        )
        sections_layout.addWidget(temp_section)

        self.scroll.setWidget(self._items_container)
        on_language_changed(self.retranslate_all)

    def load_bans(self):
        """Load existing bans into appropriate sections"""
        # Only clear if items already exist
        if self._perm_items:
            for item in list(self._perm_items):
                self._perm_layout.removeWidget(item)
                item.cleanup()
                item.deleteLater()
            self._perm_items.clear()

        if self._temp_items:
            for item in list(self._temp_items):
                self._temp_layout.removeWidget(item)
                item.cleanup()
                item.deleteLater()
            self._temp_items.clear()

        # Load bans from manager
        all_bans = self.ban_manager.get_all_bans()
        for user_id, ban_data in all_bans.items():
            is_temporary = ban_data.get('is_temporary', False)
            self._add_item(
                ban_data['username'], 
                user_id, 
                ban_data.get('expires_at'),
                is_temporary=is_temporary
            )

        # Don't create empty items - users can click [+] button to add
        if all_bans:  # Only recalculate if we loaded something
            QTimer.singleShot(100, self.recalculate_layout)
        self._update_counts()

    def _add_item(self, username="", user_id="", expires_at=None, is_temporary=False):
        """Add ban item to appropriate section"""
        item = _BanItemWidget(
            self.config, 
            self.icons_path, 
            username, 
            user_id, 
            expires_at,
            is_temporary=is_temporary
        )
        item.remove_requested.connect(self._remove_item)
        item.changed.connect(self._save_bans)

        if is_temporary:
            item.expired.connect(self._on_expired)
            self._temp_items.append(item)
        else:
            self._perm_items.append(item)

        self.recalculate_layout()

    def _add_new_item(self, is_temporary: bool):
        """Add new empty item to specified section"""
        # Check for empty items in the target section
        items_to_check = self._temp_items if is_temporary else self._perm_items
        for item in items_to_check:
            if item.is_empty():
                item.update_input_style(highlight_empty=True)
                item.username_input.setFocus()
                return

        # Show duration dialog for temporary bans
        if is_temporary:
            seconds, ok = DurationDialog.get_duration(self, default_seconds=3600)
            if not ok:
                return
            expires_at = int(time.time()) + seconds
            self._add_item("", "", expires_at, is_temporary=True)
        else:
            self._add_item("", "", None, is_temporary=False)

    def _remove_item(self, item: _BanItemWidget):
        """Remove item from appropriate section"""
        if item in self._perm_items:
            self._perm_items.remove(item)
            self._perm_layout.removeWidget(item)
        elif item in self._temp_items:
            self._temp_items.remove(item)
            self._temp_layout.removeWidget(item)

        item.cleanup()
        item.deleteLater()
        self._save_bans()
        self.recalculate_layout()

    def _on_expired(self, item: _BanItemWidget):
        """Handle expired temporary ban - remove it completely"""
        if item in self._temp_items:
            print(f"⏱️ Temporary ban expired for {item.username_input.text()}")
            self._remove_item(item)

    def _save_bans(self):
        """Save all bans"""
        self.ban_manager.clear_all()

        # Save permanent bans
        for item in self._perm_items:
            username, user_id, _ = item.get_values()
            if username and user_id and item.username_valid:
                self.ban_manager.add_user(user_id, username, duration=None)

        # Save temporary bans
        for item in self._temp_items:
            username, user_id, expires_at = item.get_values()
            if username and user_id and item.username_valid and expires_at:
                duration = max(0, expires_at - int(time.time()))
                if duration > 0:  # Only save if not expired
                    self.ban_manager.add_user(user_id, username, duration=duration)
        self._update_counts()

    def _update_counts(self):
        """Counts of the filled rows: permanent and temporary beside their headers, the total beside the title."""
        permanent = sum(1 for item in self._perm_items if not item.is_empty())
        temporary = sum(1 for item in self._temp_items if not item.is_empty())
        self._perm_count_label.setText(str(permanent))
        self._temp_count_label.setText(str(temporary))
        total = permanent + temporary
        self._total_count_label.setText(tr(f"Total: {total}", f"Всего: {total}"))

    def update_theme(self):
        is_dark = (self.config.get("ui", "theme") or "dark") == "dark"
        for item in self._perm_items + self._temp_items:
            item.update_theme(is_dark)

    def _clear_all(self):
        """Clear all bans from both sections"""
        if not any(not item.is_empty() for item in self._perm_items + self._temp_items):
            show_toast(self, tr("Ban list is already empty", "Список забаненных уже пуст"), ToastKind.INFO)
            return

        reply = QMessageBox.question(
            self, tr("Confirm Clear All", "Подтвердите очистку"),
                  tr("Remove all users from ban list?", "Удалить всех пользователей из списка забаненных?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Clear permanent items
            for item in list(self._perm_items):
                self._perm_layout.removeWidget(item)
                item.cleanup()
                item.deleteLater()
            self._perm_items.clear()

            # Clear temporary items
            for item in list(self._temp_items):
                self._temp_layout.removeWidget(item)
                item.cleanup()
                item.deleteLater()
            self._temp_items.clear()

            self.ban_manager.clear_all()
            self._update_counts()
            # Don't create empty item - users can click [+] to add

    def recalculate_layout(self):
        """Recalculate grid layout for both sections"""
        def _layout_section(grid_layout, items_list):
            if not items_list:
                return

            available_width = self.scroll.viewport().width()
            h_spacing = grid_layout.horizontalSpacing()
            if h_spacing == -1:
                h_spacing = grid_layout.spacing()

            available_for_items = available_width - (grid_layout.contentsMargins().left() + 
                                                     grid_layout.contentsMargins().right())

            # Find max item width (temp items may have different widths due to duration)
            max_item_width = max(item.width() for item in items_list)

            columns = max(1, (available_for_items + h_spacing) // (max_item_width + h_spacing))

            # Clear layout
            for i in reversed(range(grid_layout.count())):
                widget = grid_layout.itemAt(i).widget()
                if widget:
                    grid_layout.removeWidget(widget)

            # Re-add items in grid
            for idx, item in enumerate(items_list):
                row = idx // columns
                col = idx % columns
                grid_layout.addWidget(item, row, col)

        # Layout both sections independently
        _layout_section(self._perm_layout, self._perm_items)
        _layout_section(self._temp_layout, self._temp_items)

    def resizeEvent(self, event):
        """Handle resize"""
        super().resizeEvent(event)
        QTimer.singleShot(50, self.recalculate_layout)

    def cleanup(self):
        """Cleanup all items"""
        for item in self._perm_items + self._temp_items:
            item.cleanup()

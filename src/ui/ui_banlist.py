"""Ban List Management UI Widget"""

import time
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from components.button import create_icon_button
from components.toast import show_toast, ToastKind
from components.user_row.model import COLUMN_BUTTON, ExtraColumn, UserRow
from components.user_row.view import UserRowView
from helpers.fonts.fonts import FontType, set_font_role
from helpers.scroll.auto_scroll import AutoScroller
from helpers.translate import on_language_changed, tr, TranslatableMixin
from helpers.users.ban_manager import BanManager
from ui.dialogs.duration_dialog import DurationDialog

_DURATION_MIN_WIDTH = 110
_COUNTDOWN_TICK_MS = 1000
_EXPIRES = "expires_at"


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


def _seconds_left(row: UserRow) -> int:
    return max(0, row.extras[_EXPIRES] - int(time.time()))


_DURATION_COLUMN = ExtraColumn(
    _EXPIRES, COLUMN_BUTTON, base_width=_DURATION_MIN_WIDTH, text_of=lambda row: _format_time_remaining(_seconds_left(row))
)


class BanListWidget(TranslatableMixin, QWidget):
    """Widget for managing banned users with separate permanent/temporary sections"""

    back_requested = pyqtSignal()

    def __init__(self, config, icons_path: Path, ban_manager: BanManager):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.ban_manager = ban_manager
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)

        self._setup_ui()
        self.load_bans()
        self._countdown_timer.start(_COUNTDOWN_TICK_MS)

    def _create_section(self, title_en: str, title_ru: str, tooltip_en: str, tooltip_ru: str, is_temporary: bool):
        """A section: its header with the count and add button, and the rows of its bans."""
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
        header.addWidget(label)

        count_label = QLabel()
        count_label.setObjectName("mutedHint")
        count_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(count_label, stretch=1)

        add_button = create_icon_button(self.icons_path, "line/add-large-line.svg", "", config=self.config)
        self.tr_set(add_button.setToolTip, tooltip_en, tooltip_ru)
        add_button.clicked.connect(lambda: self._add_new_item(is_temporary))
        header.addWidget(add_button)
        section_layout.addLayout(header)

        view = UserRowView(self.config, self.icons_path, (_DURATION_COLUMN,) if is_temporary else ())
        view.changed.connect(self._save_bans)
        section_layout.addWidget(view)

        return section, view, count_label

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
        self.tr_set(self._back_button.setToolTip, "Back to messages", "Назад к сообщениям")
        self._back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self._back_button)

        title_label = QLabel()
        set_font_role(title_label, FontType.HEADER)
        self.tr_set(title_label.setText, "Ban List", "Список забаненных")
        header_layout.addWidget(title_label)

        self._total_count_label = QLabel()
        self._total_count_label.setObjectName("mutedHint")
        self._total_count_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(self._total_count_label, stretch=1)

        self._clear_all_button = create_icon_button(
            self.icons_path, "fill/delete-bin-fill.svg", "", config=self.config
        )
        self.tr_set(self._clear_all_button.setToolTip, "Remove all bans", "Удалить все баны")
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
        perm_section, self._perm_view, self._perm_count_label = self._create_section(
            "Permanent", "Постоянные", "Add permanent ban", "Добавить постоянный бан", is_temporary=False
        )
        sections_layout.addWidget(perm_section)

        # Create temporary section
        temp_section, self._temp_view, self._temp_count_label = self._create_section(
            "Temporary", "Временные", "Add temporary ban", "Добавить временный бан", is_temporary=True
        )
        sections_layout.addWidget(temp_section)
        self._temp_view.extra_clicked.connect(self._change_duration)

        self.scroll.setWidget(self._items_container)
        self.auto_scroller = AutoScroller(self.scroll)
        for view in (self._perm_view, self._temp_view):
            view.editor_shown.connect(self.scroll.ensureWidgetVisible)
        on_language_changed(self.retranslate_all)

    def load_bans(self):
        """Show the bans of the manager: permanent and temporary ones in their sections."""
        permanent, temporary = [], []
        for user_id, ban_data in self.ban_manager.get_all_bans().items():
            expires_at = ban_data.get('expires_at')
            if ban_data.get('is_temporary', False):
                temporary.append(UserRow(ban_data['username'], user_id, {_EXPIRES: expires_at}))
            else:
                permanent.append(UserRow(ban_data['username'], user_id))
        self._perm_view.set_rows(permanent)
        self._temp_view.set_rows(temporary)
        self._update_counts()

    def _add_new_item(self, is_temporary: bool):
        """Edit the empty row of the section, or add a row (a temporary ban asks for its duration first)."""
        view = self._temp_view if is_temporary else self._perm_view
        if view.edit_empty_row():
            return
        if not is_temporary:
            view.add_row()
            return
        seconds, ok = DurationDialog.get_duration(self, default_seconds=3600)
        if ok:
            view.add_row(UserRow(extras={_EXPIRES: int(time.time()) + seconds}))

    def _change_duration(self, row: UserRow, _key: str):
        """Ask for a new duration of a temporary ban; the dialog keeps the unit of the time left when it can."""
        seconds, ok = DurationDialog.get_duration(self, max(60, _seconds_left(row)))
        if ok and seconds > 0:
            row.extras[_EXPIRES] = int(time.time()) + seconds
            self._temp_view.refresh()
            self._save_bans()

    def _tick_countdown(self):
        """Remove the bans that ran out and show the time that is left in the others."""
        for row in [row for row in self._temp_view.rows if _seconds_left(row) == 0]:
            self._temp_view.remove_row(row)
        self._temp_view.refresh()

    def _save_bans(self):
        """Save all bans"""
        self.ban_manager.clear_all()
        for row in self._perm_view.rows:
            if row.is_confirmed:
                self.ban_manager.add_user(row.user_id, row.username, duration=None)
        for row in self._temp_view.rows:
            if row.is_confirmed and _seconds_left(row) > 0:
                self.ban_manager.add_user(row.user_id, row.username, duration=_seconds_left(row))
        self._update_counts()

    def _update_counts(self):
        """Counts of the filled rows: permanent and temporary beside their headers, the total beside the title."""
        permanent = self._perm_view.filled_count()
        temporary = self._temp_view.filled_count()
        self._perm_count_label.setText(str(permanent))
        self._temp_count_label.setText(str(temporary))
        total = permanent + temporary
        self._total_count_label.setText(tr(f"Total: {total}", f"Всего: {total}"))

    def retranslate_all(self, _code=None):
        super().retranslate_all(_code)
        self._update_counts()

    def update_theme(self):
        for view in (self._perm_view, self._temp_view):
            view.update_theme()

    def _clear_all(self):
        """Remove all bans from both sections"""
        if not (self._perm_view.filled_count() or self._temp_view.filled_count()):
            show_toast(self, tr("Ban list is already empty", "Список забаненных уже пуст"), ToastKind.INFO)
            return

        reply = QMessageBox.question(
            self, tr("Remove all bans", "Удалить все баны"),
                  tr("Remove all bans?", "Удалить все баны?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._perm_view.clear()
            self._temp_view.clear()
            self.ban_manager.clear_all()
            self._update_counts()

    def cleanup(self):
        """Stop the countdown"""
        self._countdown_timer.stop()

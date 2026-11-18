"""Username Pronunciation Management Widget"""

from functools import partial
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
from components.user_row.model import COLUMN_FIELD, ExtraColumn, UserRow
from components.user_row.view import UserRowView
from helpers.fonts.fonts import FontType, set_font_role
from helpers.scroll.auto_scroll import AutoScroller
from helpers.scroll.scroll import scroll
from helpers.translate import on_language_changed, tr, TranslatableMixin


_SAVE_DELAY_MS = 500
_REVEAL_DELAY_MS = 50


_PRONUNCIATION = "pronunciation"
_PRONUNCIATION_COLUMN = ExtraColumn(
    _PRONUNCIATION, COLUMN_FIELD, placeholder=("Pronunciation", "Произношение"), base_width=200
)


def _is_row_empty(row: UserRow) -> bool:
    return not row.username and not row.extras[_PRONUNCIATION].strip()


class PronunciationWidget(TranslatableMixin, QWidget):
    """Widget for managing username pronunciations"""
    back_requested = pyqtSignal()

    def __init__(self, config, icons_path: Path, pronunciation_manager):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.pronunciation_manager = pronunciation_manager
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(_SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self._save_mappings)

        self._setup_ui()
        self._load_mappings()

    def _setup_ui(self):
        """Setup the pronunciation management UI"""
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

        # Back button
        self._back_button = create_icon_button(
            self.icons_path, "line/arrow-go-back-line.svg", "", config=self.config
        )
        self.tr_set(self._back_button.setToolTip, "Back to messages", "Назад к сообщениям")
        self._back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self._back_button)

        # Title
        title_label = QLabel()
        set_font_role(title_label, FontType.HEADER)
        self.tr_set(title_label.setText, "Username Pronunciation", "Произношение имён")
        header_layout.addWidget(title_label)

        self._total_count_label = QLabel()
        self._total_count_label.setObjectName("mutedHint")
        self._total_count_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(self._total_count_label, stretch=1)

        # Add button
        self._add_button = create_icon_button(
            self.icons_path, "line/add-large-line.svg", "", config=self.config
        )
        self.tr_set(self._add_button.setToolTip, "Add mapping", "Добавить соответствие")
        self._add_button.clicked.connect(self._add_new_item)
        header_layout.addWidget(self._add_button)

        # Clear All button
        self._clear_all_button = create_icon_button(
            self.icons_path, "fill/delete-bin-fill.svg", "", config=self.config
        )
        self.tr_set(self._clear_all_button.setToolTip, "Remove all mappings", "Удалить все соответствия")
        self._clear_all_button.clicked.connect(self._clear_all)
        header_layout.addWidget(self._clear_all_button)

        # Scroll area for items
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(self.scroll, stretch=1)

        items_margin = self.config.get("ui", "margins", "widget") or 5
        self.users_view = UserRowView(self.config, self.icons_path, (_PRONUNCIATION_COLUMN,))
        self.users_view.changed.connect(self._save_mappings)
        self.users_view.extra_changed.connect(self._schedule_save)
        self.users_view.editor_shown.connect(self.scroll.ensureWidgetVisible)
        self._items_container = QWidget()
        container_layout = QVBoxLayout(self._items_container)
        container_layout.setContentsMargins(items_margin, items_margin, items_margin, items_margin)
        container_layout.addWidget(self.users_view)
        container_layout.addStretch()

        self.users_view.row_added.connect(partial(scroll, self.scroll, mode="bottom", delay=_REVEAL_DELAY_MS))
        self.scroll.setWidget(self._items_container)
        self.auto_scroller = AutoScroller(self.scroll)
        on_language_changed(self.retranslate_all)

    def _load_mappings(self):
        """Show the saved mappings, or one empty row when there are none."""
        rows = [
            UserRow(entry["username"], user_id, {_PRONUNCIATION: entry["pronunciation"]})
            for user_id, entry in self.pronunciation_manager.get_entries().items()
        ]
        self.users_view.set_rows(rows or [UserRow(extras={_PRONUNCIATION: ""})])
        self._update_count()

    def refresh(self):
        """Reload mappings after adding, editing, or removing one from the context menu."""
        self._load_mappings()

    def _add_new_item(self):
        """Edit the empty row, or add one"""
        if not self.users_view.edit_empty_row():
            self.users_view.add_row(UserRow(extras={_PRONUNCIATION: ""}))

    def _save_mappings(self):
        """Save the complete rows with one write"""
        entries = {}
        for row in self.users_view.rows:
            pronunciation = row.extras[_PRONUNCIATION].strip()
            if row.is_confirmed and pronunciation:
                entries[row.user_id] = {"username": row.username, "pronunciation": pronunciation}
        self.pronunciation_manager.replace_all(entries)
        self._update_count()

    def _schedule_save(self, *_):
        self._save_timer.start()

    def hideEvent(self, event):
        """Save at once what is still waiting when the panel is left or the window closes."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_mappings()
        super().hideEvent(event)

    def _update_count(self):
        count = sum(1 for row in self.users_view.rows if not _is_row_empty(row))
        self._total_count_label.setText(tr(f"Total: {count}", f"Всего: {count}"))

    def retranslate_all(self, _code=None):
        super().retranslate_all(_code)
        self._update_count()

    def update_theme(self):
        self.users_view.update_theme()

    def _clear_all(self):
        """Clear all pronunciation mappings"""
        if all(_is_row_empty(row) for row in self.users_view.rows):
            show_toast(self, tr("Pronunciation list is already empty", "Список произношений уже пуст"), ToastKind.INFO)
            return

        reply = QMessageBox.question(
            self,
            tr("Remove all mappings", "Удалить все соответствия"),
            tr("Remove all mappings?", "Удалить все соответствия?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.pronunciation_manager.replace_all({})
            self._load_mappings()

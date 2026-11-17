"""Username Pronunciation Management Widget"""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from components.button import create_icon_button
from components.toast import show_toast, ToastKind
from components.user_entry_row import UserEntryRow
from helpers.cache import get_cache
from helpers.fonts.fonts import FontType, set_font_role
from helpers.translate import on_language_changed, tr, TranslatableMixin


class _PronunciationItemWidget(UserEntryRow):
    """Pronunciation row: the shared user row with a field for how the name is spoken."""

    PRONUNCIATION_BASE_WIDTH = 200

    def __init__(self, config, icons_path: Path, original: str = "", pronunciation: str = "", user_id: str = ""):
        super().__init__(config, icons_path, original, user_id, check_on_load=False)  # saved names are not looked up one by one
        self.pronunciation_input = QLineEdit()
        self.tr_set(self.pronunciation_input.setPlaceholderText, "Pronunciation", "Произношение")
        self.pronunciation_input.setText(pronunciation)
        set_font_role(self.pronunciation_input, FontType.TEXT)
        self.pronunciation_input.setFixedHeight(self.input_height)
        self.add_action(self.pronunciation_input, self.PRONUNCIATION_BASE_WIDTH)
        self.setTabOrder(self.username_input, self.pronunciation_input)

    def get_values(self):
        """Get original and pronunciation values"""
        return self.username_input.text().strip(), self.pronunciation_input.text().strip()

    def is_empty(self):
        """Check if both inputs are empty"""
        return super().is_empty() and not self.pronunciation_input.text().strip()


class PronunciationWidget(TranslatableMixin, QWidget):
    """Widget for managing username pronunciations"""
    back_requested = pyqtSignal()

    def __init__(self, config, icons_path: Path, pronunciation_manager):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.pronunciation_manager = pronunciation_manager
        self.items = []
        self._current_columns = 1

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
        self.tr_set(self._back_button.setToolTip, "Back to Messages", "Назад к сообщениям")
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
        self.tr_set(self._add_button.setToolTip, "Add Mapping", "Добавить соответствие")
        self._add_button.clicked.connect(self._add_new_item)
        header_layout.addWidget(self._add_button)

        # Clear All button
        self._clear_all_button = create_icon_button(
            self.icons_path, "fill/delete-bin-fill.svg", "", config=self.config
        )
        self.tr_set(self._clear_all_button.setToolTip, "Clear All", "Очистить всё")
        self._clear_all_button.clicked.connect(self._clear_all)
        header_layout.addWidget(self._clear_all_button)

        # Scroll area for items
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(self.scroll, stretch=1)

        # Container for items with limited width
        self._items_container = QWidget()
        # Don't set fixed width - let it be flexible but items will wrap

        items_margin = self.config.get("ui", "margins", "widget") or 5
        items_spacing = self.config.get("ui", "spacing", "list_items") or 2

        # Use grid layout for adaptive columns
        self._items_layout = QGridLayout()
        self._items_layout.setContentsMargins(items_margin, items_margin, items_margin, items_margin)
        self._items_layout.setSpacing(items_spacing)
        # Add vertical spacing between rows
        self._items_layout.setVerticalSpacing(items_spacing * 2)
        # Increase horizontal spacing significantly
        self._items_layout.setHorizontalSpacing(items_spacing * 4)
        self._items_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._items_container.setLayout(self._items_layout)

        self.scroll.setWidget(self._items_container)
        on_language_changed(self.retranslate_all)

    def _load_mappings(self):
        """Load existing pronunciation mappings"""
        mappings = self.pronunciation_manager.get_all_mappings()
        for original, pronunciation in mappings.items():
            self._add_item(original, pronunciation)

        # Add one empty item if no mappings exist
        if not mappings:
            self._add_item("", "")

        # Initial layout calculation
        QTimer.singleShot(100, self.recalculate_layout)
        self._update_count()

    def _add_item(self, original: str = "", pronunciation: str = ""):
        """Add a pronunciation item to the list"""
        user_id = get_cache().get_user_id(original) if original else None
        item = _PronunciationItemWidget(self.config, self.icons_path, original, pronunciation, str(user_id or ""))
        item.remove_requested.connect(self._remove_item)

        # Auto-save: after the name is checked and while the pronunciation is typed
        item.changed.connect(self._save_mappings)
        item.pronunciation_input.textChanged.connect(self._save_mappings)

        self.items.append(item)
        self.recalculate_layout()

    def refresh(self):
        """Reload mappings after adding, editing, or removing one from the context menu."""
        for item in self.items:
            self._items_layout.removeWidget(item)
            item.deleteLater()
        self.items.clear()
        self._load_mappings()

    def _add_new_item(self):
        """Add a new empty pronunciation item"""
        self._add_item("", "")

    def _remove_item(self, item: _PronunciationItemWidget):
        """Remove a pronunciation item"""
        if item in self.items:
            self.items.remove(item)
            self._items_layout.removeWidget(item)
            item.deleteLater()
            self._save_mappings()
            self.recalculate_layout()

    def _save_mappings(self):
        """Save all pronunciation mappings"""
        # Clear existing mappings
        self.pronunciation_manager.clear_all()

        # Save only valid, non-empty mappings
        for item in self.items:
            original, pronunciation = item.get_values()
            # Only save if both fields filled AND username is valid
            if original and pronunciation and item.username_valid:
                self.pronunciation_manager.add_mapping(original, pronunciation)
        self._update_count()

    def _update_count(self):
        count = sum(1 for item in self.items if not item.is_empty())
        self._total_count_label.setText(tr(f"Total: {count}", f"Всего: {count}"))

    def retranslate_all(self, _code=None):
        super().retranslate_all(_code)
        self._update_count()

    def update_theme(self):
        is_dark = (self.config.get("ui", "theme") or "dark") == "dark"
        for item in self.items:
            item.update_theme(is_dark)

    def _clear_all(self):
        """Clear all pronunciation mappings"""
        if not any(not item.is_empty() for item in self.items):
            show_toast(self, tr("Pronunciation list is already empty", "Список произношений уже пуст"), ToastKind.INFO)
            return

        reply = QMessageBox.question(
            self,
            tr("Confirm Clear All", "Подтвердите очистку"),
            tr("Remove all pronunciation mappings?", "Удалить все соответствия произношения?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Remove all items
            for item in list(self.items):
                self._items_layout.removeWidget(item)
                item.deleteLater()
            self.items.clear()

            # Clear pronunciation manager
            self.pronunciation_manager.clear_all()

            # Add one empty item
            self._add_item("", "")
            self._update_count()

    def recalculate_layout(self):
        """Recalculate grid layout based on available width"""
        if not self.items:
            return

        # Get available width
        available_width = self.scroll.viewport().width()

        # Each item has fixed width, calculate from first item
        if self.items:
            item_width = self.items[0].width()
            # Get horizontal spacing
            h_spacing = self._items_layout.horizontalSpacing()
            if h_spacing == -1:  # Use default if not set
                h_spacing = self._items_layout.spacing()

            # Calculate how many columns can fit
            # Need to account for spacing between items
            available_for_items = available_width - (self._items_layout.contentsMargins().left() + 
                                                     self._items_layout.contentsMargins().right())
            columns = max(1, (available_for_items + h_spacing) // (item_width + h_spacing))

            # Clear layout
            for i in reversed(range(self._items_layout.count())):
                widget = self._items_layout.itemAt(i).widget()
                if widget:
                    self._items_layout.removeWidget(widget)

            # Re-add items in grid
            for index, item in enumerate(self.items):
                row = index // columns
                col = index % columns
                self._items_layout.addWidget(item, row, col)

            self._current_columns = columns

    def resizeEvent(self, event):
        """Handle resize to recalculate grid layout"""
        super().resizeEvent(event)
        QTimer.singleShot(50, self.recalculate_layout)

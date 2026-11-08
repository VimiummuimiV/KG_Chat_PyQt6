"""Username Pronunciation Management Widget"""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
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
from core.web.api_data import get_exact_user_id_by_name
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import on_language_changed, tr, TranslatableMixin


class _PronunciationItemWidget(TranslatableMixin, QWidget):
    """Single pronunciation mapping item"""
    remove_requested = pyqtSignal(object)  # Emits self

    def __init__(self, config, icons_path: Path, original: str = "", pronunciation: str = ""):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.username_valid = True  # Track validation state

        spacing = self.config.get("ui", "spacing", "widget_elements") or 6

        # Use horizontal layout
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        self.setLayout(layout)

        # Original username input
        self._original_input = QLineEdit()
        self.tr_set(self._original_input.setPlaceholderText, "Username", "Имя пользователя")
        self._original_input.setText(original)
        self._original_input.setFont(get_font(FontType.TEXT))
        input_height = self.config.get("ui", "input_height") or 48
        self._original_input.setFixedHeight(input_height)
        self._original_input.setFixedWidth(250)

        # Connect to validation on focus out
        self._original_input.editingFinished.connect(self._validate_username)

        layout.addWidget(self._original_input)

        # Arrow icon label (SVG as QLabel)
        arrow_label = QLabel()
        arrow_svg_path = self.icons_path / "arrow-right.svg"
        if arrow_svg_path.exists():
            # Get icon size from config
            icon_size = 30  # Default large icon size
            btn_cfg = config.get("ui", "buttons")
            if btn_cfg and isinstance(btn_cfg, dict):
                large_btn = btn_cfg.get("large_button", {})
                if isinstance(large_btn, dict):
                    icon_size = large_btn.get("icon_size", 30)

            # Render SVG to pixmap with gray color
            with open(arrow_svg_path, 'r') as f:
                svg_content = f.read()

            # Use gray color for arrow (works on both light and dark backgrounds)
            svg_content = svg_content.replace('fill="currentColor"', 'fill="#888888"')

            renderer = QSvgRenderer()
            renderer.load(svg_content.encode('utf-8'))
            pixmap = QPixmap(icon_size, icon_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()

            arrow_label.setPixmap(pixmap)
            arrow_label.setFixedSize(icon_size, icon_size)

        layout.addWidget(arrow_label)

        # Pronunciation input
        self._pronunciation_input = QLineEdit()
        self.tr_set(self._pronunciation_input.setPlaceholderText, "Pronunciation", "Произношение")
        self._pronunciation_input.setText(pronunciation)
        self._pronunciation_input.setFont(get_font(FontType.TEXT))
        self._pronunciation_input.setFixedHeight(input_height)
        self._pronunciation_input.setFixedWidth(250)
        layout.addWidget(self._pronunciation_input)

        # Set tab order: Username -> Pronunciation
        self.setTabOrder(self._original_input, self._pronunciation_input)

        # Remove button
        self._remove_button = create_icon_button(
            self.icons_path, "trash.svg", "", 
            size_type="large", config=self.config
        )
        self.tr_set(self._remove_button.setToolTip, "Remove", "Удалить")
        self._remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self._remove_button)

        # Set fixed width for the whole item
        # 250 + 30 + 250 + 48 + spacing*3
        total_width = 250 + icon_size + 250 + 48 + (spacing * 3)
        self.setFixedWidth(total_width)
        on_language_changed(self.retranslate_all)

    def _validate_username(self):
        """Validate username exists using API"""
        username = self._original_input.text().strip()

        # If empty, reset to valid state
        if not username:
            self.username_valid = True
            self.update_input_style()
            return

        # Check if user exists
        try:
            user_id = get_exact_user_id_by_name(username)
            self.username_valid = (user_id is not None)
        except Exception:
            self.username_valid = False

        self.update_input_style()

    def update_input_style(self):
        """Update input styling based on validation state"""
        if not self.username_valid:
            # Invalid username - show red border
            self._original_input.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #ff4444;
                }
            """)
            self._original_input.setToolTip(tr("User not found", "Пользователь не найден"))
        else:
            # Valid or empty - remove custom styling
            self._original_input.setStyleSheet("")
            self._original_input.setToolTip("")

    def get_values(self):
        """Get original and pronunciation values"""
        return self._original_input.text().strip(), self._pronunciation_input.text().strip()

    def is_empty(self):
        """Check if both inputs are empty"""
        original, pronunciation = self.get_values()
        return not original and not pronunciation

    def is_valid(self):
        """Check if username is valid"""
        return self.username_valid


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
            self.icons_path, "go-back.svg", "", config=self.config
        )
        self.tr_set(self._back_button.setToolTip, "Back to Messages", "Назад к сообщениям")
        self._back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self._back_button)

        # Title
        title_label = QLabel()
        title_label.setFont(get_font(FontType.HEADER))
        self.tr_set(title_label.setText, "Username Pronunciation", "Произношение имён")
        header_layout.addWidget(title_label, stretch=1)

        # Clear All button
        self._clear_all_button = create_icon_button(
            self.icons_path, "trash.svg", "", config=self.config
        )
        self.tr_set(self._clear_all_button.setToolTip, "Clear All", "Очистить всё")
        self._clear_all_button.clicked.connect(self._clear_all)
        header_layout.addWidget(self._clear_all_button)

        # Add button
        self._add_button = create_icon_button(
            self.icons_path, "add.svg", "", config=self.config
        )
        self.tr_set(self._add_button.setToolTip, "Add Mapping", "Добавить соответствие")
        self._add_button.clicked.connect(self._add_new_item)
        header_layout.addWidget(self._add_button)

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

    def _add_item(self, original: str = "", pronunciation: str = ""):
        """Add a pronunciation item to the list"""
        item = _PronunciationItemWidget(self.config, self.icons_path, original, pronunciation)
        item.remove_requested.connect(self._remove_item)

        # Connect inputs to auto-save
        item._original_input.textChanged.connect(self._save_mappings)
        item._pronunciation_input.textChanged.connect(self._save_mappings)

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
            if original and pronunciation and item.is_valid():
                self.pronunciation_manager.add_mapping(original, pronunciation)

    def _clear_all(self):
        """Clear all pronunciation mappings"""
        if not any(not item.is_empty() for item in self.items):
            QMessageBox.information(
                self,
                tr("Empty", "Пусто"),
                tr("Pronunciation list is already empty", "Список произношений уже пуст")
            )
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
            for idx, item in enumerate(self.items):
                row = idx // columns
                col = idx % columns
                self._items_layout.addWidget(item, row, col)

            self._current_columns = columns

    def resizeEvent(self, event):
        """Handle resize to recalculate grid layout"""
        super().resizeEvent(event)
        QTimer.singleShot(50, self.recalculate_layout)

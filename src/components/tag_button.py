"""Reusable tag/chip UI components (e.g. saved-value quick-access buttons)."""
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QLayout
from PyQt6.QtCore import QSize, QRect, QTimer, Qt, pyqtSignal
from PyQt6 import sip

from helpers import create as icon_helpers

_tag_registry = []

# Tag chip colors: (background, text, border)
_TAG_COLORS_DARK = ("#333333", "#dddddd", "#454545")
_TAG_COLORS_LIGHT = ("#eceef0", "#222222", "#d5d8db")
_TAG_BORDER_RADIUS = 6 

# Close (x) button
_CLOSE_BTN_SIZE = 22
_CLOSE_BTN_RADIUS = 4
_CLOSE_ICON_SIZE = 12 
_CLOSE_ICON_COLOR = "#999999"
_CLOSE_ICON_STROKE_WIDTH = 2 
_CLOSE_HOVER_BG_DARK = "#4a4a4a"
_CLOSE_HOVER_BG_LIGHT = "#d5d8db"


class TagButton(QWidget):
    """Pill-shaped tag with a label and a small remove (x) icon, themed for dark/light."""

    clicked = pyqtSignal(str)
    double_clicked = pyqtSignal(str)
    removed = pyqtSignal(str)

    def __init__(self, text: str, icons_path: Path, close_icon: str = "close.svg"):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.text_value = text
        self.icons_path = icons_path
        self.close_icon = close_icon

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(6)

        self.label = QLabel(text)
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.mousePressEvent = lambda e: self.clicked.emit(self.text_value)
        self.label.mouseDoubleClickEvent = lambda e: self.double_clicked.emit(self.text_value)
        layout.addWidget(self.label)

        self.close_btn = QPushButton()
        self.close_btn.setFlat(True)
        self.close_btn.setFixedSize(_CLOSE_BTN_SIZE, _CLOSE_BTN_SIZE)
        self.close_btn.setIconSize(QSize(_CLOSE_ICON_SIZE, _CLOSE_ICON_SIZE))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(lambda: self.removed.emit(self.text_value))
        layout.addWidget(self.close_btn)

        self.setLayout(layout)
        _tag_registry.append(self)
        self._update_style()

    def _update_style(self):
        """Re-apply colors for the current theme (read live from helpers.create)"""
        is_dark = icon_helpers._is_dark_theme
        bg, fg, border = _TAG_COLORS_DARK if is_dark else _TAG_COLORS_LIGHT
        close_hover_bg = _CLOSE_HOVER_BG_DARK if is_dark else _CLOSE_HOVER_BG_LIGHT

        self.setStyleSheet(
            f"background-color: {bg}; border: 1px solid {border}; border-radius: {_TAG_BORDER_RADIUS}px;"
        )
        self.label.setStyleSheet(f"color: {fg}; background: transparent; border: none;")
        self.close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: {_CLOSE_BTN_RADIUS}px; }}"
            f"QPushButton:hover {{ background-color: {close_hover_bg}; }}"
        )
        self.close_btn.setIcon(icon_helpers._render_svg_icon(
            self.icons_path / self.close_icon, _CLOSE_ICON_SIZE,
            color=_CLOSE_ICON_COLOR, stroke_width=_CLOSE_ICON_STROKE_WIDTH
        ))


def update_all_tag_buttons():
    """Refresh all registered TagButton instances. Call alongside update_all_icons() on theme change."""
    global _tag_registry
    _tag_registry = [tag for tag in _tag_registry if not sip.isdeleted(tag)]
    for tag in _tag_registry:
        tag._update_style()


class FlowLayout(QLayout):
    """Horizontal layout that wraps to a new line when it runs out of width."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)
        self._items = []
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if index < len(self._items) else None

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):
        return QSize(self.geometry().width(), self.height_for_width(self.geometry().width()))

    def height_for_width(self, width):
        """Required height to lay out all items within the given width"""
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def _arrange(self, rect, apply):
        """Place items left-to-right, wrapping rows as needed. Shared by setGeometry
        (actually moves items) and height_for_width (just measures)."""
        spacing = self.spacing()
        x, y, line_height = rect.x(), rect.y(), 0

        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() and line_height:
                x, y, line_height = rect.x(), y + line_height + spacing, 0
            if apply:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x += hint.width() + spacing
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y()


class SavedValuesBar(QWidget):
    """Row of removable chips backed by a config list, e.g. saved usernames.
    Owns loading/saving/rebuilding; the parent widget only reacts to chip clicks."""

    value_selected = pyqtSignal(str)
    value_double_clicked = pyqtSignal(str)

    def __init__(self, config, config_path: tuple, icons_path: Path):
        super().__init__()
        self.config = config
        self.config_path = config_path
        self.icons_path = icons_path
        self.values = self.config.get(*config_path) or []
        self._tags = {}

        self._layout = FlowLayout(self)
        self._rebuild()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.values:
            self.setFixedHeight(self._layout.height_for_width(event.size().width()))

    def add_values(self, values: list):
        """Add any values not already saved, and persist"""
        new_values = [v for v in values if v not in self.values]
        if new_values:
            self.values.extend(new_values)
            self._save()
            for value in new_values:
                self._add_tag(value)
            self._update_size()

    def _remove_value(self, value: str):
        if value not in self.values:
            return
        self.values.remove(value)
        self._save()
        tag = self._tags.pop(value, None)
        if tag:
            self._layout.removeWidget(tag)
            tag.deleteLater()
        self._update_size()

    def _save(self):
        self.config.set(*self.config_path, value=self.values)

    def _add_tag(self, value: str):
        """Create a chip for one value and add it to the layout, without touching existing chips"""
        tag = TagButton(value, self.icons_path)
        tag.clicked.connect(self.value_selected.emit)
        tag.double_clicked.connect(self.value_double_clicked.emit)
        tag.removed.connect(self._remove_value)
        self._tags[value] = tag
        self._layout.addWidget(tag)

    def _rebuild(self):
        """Full teardown/recreate - only needed for the initial load from config"""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tags.clear()

        for value in self.values:
            self._add_tag(value)

        self._update_size()

    def _update_size(self):
        self.setVisible(bool(self.values))
        if self.values:
            QTimer.singleShot(0, self._apply_content_height)

    def _apply_content_height(self):
        """Measure and apply height after Qt has settled the layout (deferred - see _update_size)"""
        self.setFixedHeight(self._layout.height_for_width(self.width() or self.sizeHint().width()))
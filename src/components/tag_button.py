"""Reusable tag/chip UI components (e.g. saved-value quick-access buttons)."""
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QLayout
from PyQt6.QtCore import QSize, QRect, Qt, pyqtSignal
from PyQt6 import sip

from helpers import create as icon_helpers

_tag_registry = []


class TagButton(QWidget):
    """Pill-shaped tag with a label and a small remove (x) icon, themed for dark/light."""

    clicked = pyqtSignal(str)
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
        layout.addWidget(self.label)

        self.close_btn = QPushButton()
        self.close_btn.setFlat(True)
        self.close_btn.setFixedSize(14, 14)
        self.close_btn.setIconSize(QSize(10, 10))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("background: transparent; border: none;")
        self.close_btn.clicked.connect(lambda: self.removed.emit(self.text_value))
        layout.addWidget(self.close_btn)

        self.setLayout(layout)
        _tag_registry.append(self)
        self._update_style()

    def _update_style(self):
        """Re-apply colors for the current theme (read live from helpers.create)"""
        bg, fg, border = ("#333333", "#dddddd", "#454545") if icon_helpers._is_dark_theme \
            else ("#eceef0", "#222222", "#d5d8db")

        self.setStyleSheet(f"background-color: {bg}; border: 1px solid {border}; border-radius: 11px;")
        self.label.setStyleSheet(f"color: {fg}; background: transparent; border: none;")
        self.close_btn.setIcon(icon_helpers._render_svg_icon(self.icons_path / self.close_icon, 10, color="#999999"))


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

    def __init__(self, config, config_path: tuple, icons_path: Path):
        super().__init__()
        self.config = config
        self.config_path = config_path
        self.icons_path = icons_path
        self.values = self.config.get(*config_path) or []

        self._layout = FlowLayout(self)
        self._rebuild()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setFixedHeight(self._layout.height_for_width(event.size().width()))

    def add_values(self, values: list):
        """Add any values not already saved, and persist"""
        new_values = [v for v in values if v not in self.values]
        if new_values:
            self.values.extend(new_values)
            self._save()
            self._rebuild()

    def _remove_value(self, value: str):
        if value in self.values:
            self.values.remove(value)
            self._save()
            self._rebuild()

    def _save(self):
        self.config.set(*self.config_path, value=self.values)

    def _rebuild(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for value in self.values:
            tag = TagButton(value, self.icons_path)
            tag.clicked.connect(self.value_selected.emit)
            tag.removed.connect(self._remove_value)
            self._layout.addWidget(tag)

        self.setVisible(bool(self.values))
        self.setFixedHeight(self._layout.height_for_width(self.width() or self.sizeHint().width()))
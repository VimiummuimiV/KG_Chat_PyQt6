"""Reusable tag/chip UI components (e.g. saved-value quick-access buttons)."""

from pathlib import Path
from typing import Callable

from PyQt6.QtCore import pyqtSignal, QMimeData, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLayout, QPushButton, QWidget

from components import button as icon_helpers


# Close (x) button
_CLOSE_BUTTON_SIZE = 22
_CLOSE_ICON_SIZE = 12 
_CLOSE_ICON_COLOR = "#999999"
_CLOSE_ICON_STROKE_WIDTH = 2 

# Drag-to-reorder insertion line
_DROP_LINE_WIDTH = 6


class _TagButton(QWidget):
    """Pill-shaped tag with a label and a small remove (x) icon; colors come from the stylesheet."""

    clicked = pyqtSignal(str)
    _double_clicked = pyqtSignal(str)
    removed = pyqtSignal(str)

    def __init__(self, text: str, icons_path: Path, close_icon: str = "line/close-large-line.svg"):
        super().__init__()
        self.setObjectName("tagButton")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._text_value = text
        self.icons_path = icons_path
        self._close_icon = close_icon
        self._drag_start_pos = None

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(6)

        self.label = QLabel(text)
        self.label.setObjectName("tagLabel")
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.mousePressEvent = self._on_label_press
        self.label.mouseMoveEvent = self._on_label_move
        self.label.mouseReleaseEvent = self._on_label_release
        self.label.mouseDoubleClickEvent = lambda e: self._double_clicked.emit(self._text_value)
        layout.addWidget(self.label)

        self.close_btn = QPushButton()
        self.close_btn.setObjectName("tagClose")
        self.close_btn.setFlat(True)
        self.close_btn.setFixedSize(_CLOSE_BUTTON_SIZE, _CLOSE_BUTTON_SIZE)
        self.close_btn.setIconSize(QSize(_CLOSE_ICON_SIZE, _CLOSE_ICON_SIZE))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(lambda: self.removed.emit(self._text_value))
        layout.addWidget(self.close_btn)

        self.setLayout(layout)
        self.close_btn.setIcon(icon_helpers.render_svg_icon(
            self.icons_path / self._close_icon, _CLOSE_ICON_SIZE,
            color=_CLOSE_ICON_COLOR, stroke_width=_CLOSE_ICON_STROKE_WIDTH
        ))

    def _on_label_press(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = e.position().toPoint()

    def _on_label_move(self, e):
        if self._drag_start_pos is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if (e.position().toPoint() - self._drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
            self._start_drag()

    def _on_label_release(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            self.clicked.emit(self._text_value)
        self._drag_start_pos = None

    def _start_drag(self):
        """Reorder drag: carries this tag's text so the container can reposition it."""
        self._drag_start_pos = None
        mime = QMimeData()
        mime.setText(self._text_value)

        drag = QDrag(self.label)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self.rect().center())
        drag.exec(Qt.DropAction.MoveAction)


class _FlowLayout(QLayout):
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
        return QSize(self.geometry().width(), self._height_for_width(self.geometry().width()))

    def _height_for_width(self, width):
        """Required height to lay out all items within the given width"""
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def _reorder(self, widgets):
        """Reorder existing items to match the given widget order (no add/remove/recreate)."""
        by_widget = {item.widget(): item for item in self._items}
        self._items = [by_widget[w] for w in widgets if w in by_widget]
        self.invalidate()

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
    """Row of removable, draggable chips backed by any list storage, e.g. saved usernames or aliases.
    Owns loading/saving/rebuilding; the parent widget only reacts to chip clicks."""

    value_selected = pyqtSignal(str)
    value_double_clicked = pyqtSignal(str)

    def __init__(self, icons_path: Path, load_values: Callable[[], list], save_values: Callable[[list], None]):
        super().__init__()
        self.icons_path = icons_path
        self._save_values = save_values
        self.values = load_values()
        self._tags = {}

        self._layout = _FlowLayout(self)
        self._drop_indicator = QWidget(self)
        self._drop_indicator.setObjectName("tagDropLine")
        self._drop_indicator.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drop_indicator.hide()
        self._drop_target = (None, False)
        self.setAcceptDrops(True)
        self._rebuild()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.values:
            self.setFixedHeight(self._layout._height_for_width(event.size().width()))

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
        self._save_values(self.values)

    def _tag_at(self, pos):
        """Which tag (if any) a point is over, and whether pos is past its midpoint."""
        widget = self.childAt(pos)
        while widget is not None and widget not in self._tags.values():
            widget = widget.parentWidget()
        after = widget is not None and pos.x() > widget.geometry().center().x()
        return widget, after

    def _update_drop_indicator(self, pos):
        """Single place that owns the drop indicator: resolves the target tag,
        remembers it for dropEvent, and positions/shows or hides the indicator."""
        widget, after = self._tag_at(pos)
        self._drop_target = (widget, after)
        if widget is None:
            self._drop_indicator.hide()
            return

        g, gap = widget.geometry(), self._layout.spacing()
        x = (g.right() + gap / 2) if after else (g.left() - gap / 2)
        self._drop_indicator.setGeometry(round(x - _DROP_LINE_WIDTH / 2), g.top(), _DROP_LINE_WIDTH, g.height())
        self._drop_indicator.raise_()
        self._drop_indicator.show()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            self._update_drop_indicator(event.position().toPoint())
            event.acceptProposedAction()

    dragEnterEvent = dragMoveEvent

    def dragLeaveEvent(self, event):
        self._drop_indicator.hide()

    def dropEvent(self, event):
        """Move the dragged tag next to whichever tag it was dropped on."""
        self._update_drop_indicator(event.position().toPoint())
        self._drop_indicator.hide()

        dragged_value = event.mimeData().text()
        widget, after = self._drop_target
        if dragged_value not in self.values or widget is self._tags.get(dragged_value):
            event.acceptProposedAction()
            return

        new_values = [v for v in self.values if v != dragged_value]
        if widget is None:
            new_values.append(dragged_value)
        else:
            target_value = next(v for v, w in self._tags.items() if w is widget)
            new_values.insert(new_values.index(target_value) + after, dragged_value)

        self.values = new_values
        self._save()
        self._layout._reorder([self._tags[v] for v in self.values])
        event.acceptProposedAction()

    def _add_tag(self, value: str):
        """Create a chip for one value and add it to the layout, without touching existing chips"""
        tag = _TagButton(value, self.icons_path)
        tag.clicked.connect(self.value_selected.emit)
        tag._double_clicked.connect(self.value_double_clicked.emit)
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
        self.setFixedHeight(self._layout._height_for_width(self.width() or self.sizeHint().width()))

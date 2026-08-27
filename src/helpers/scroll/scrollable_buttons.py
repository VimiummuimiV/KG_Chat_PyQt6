"""Reusable scrollable button container with wheel and MMB drag scroll support"""
from PyQt6.QtWidgets import QWidget, QScrollArea, QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt, QEvent


class ScrollableButtonContainer(QWidget):
    """Orientation-aware scrollable container for icon buttons (wheel + MMB drag)."""

    def __init__(self, orientation=Qt.Orientation.Horizontal, config=None, parent=None):
        super().__init__(parent)
        self._orientation = orientation
        self._is_dragging = False
        self._drag_start_pos = None
        self._scroll_start_value = None
        spacing = (config.get("ui", "buttons", "spacing") if config else None) or 8
        self._init_ui(spacing)

    def _init_ui(self, spacing: int):
        is_vertical = self._orientation == Qt.Orientation.Vertical

        outer = QVBoxLayout() if is_vertical else QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setLayout(outer)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(is_vertical)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if not is_vertical:
            self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.container = QWidget()
        self._layout = QVBoxLayout() if is_vertical else QHBoxLayout()
        if is_vertical:
            self._layout.addStretch()
        else:
            self._layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._layout.setSpacing(spacing)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.container.setLayout(self._layout)

        self.scroll_area.setWidget(self.container)
        outer.addWidget(self.scroll_area)
        self.scroll_area.viewport().installEventFilter(self)

    def _sync_content_size(self):
        if self._orientation != Qt.Orientation.Horizontal:
            return
        self.container.adjustSize()
        hint = self.container.sizeHint()
        self.container.setFixedSize(hint)
        self.setMinimumHeight(hint.height())

    def add_widget(self, widget: QWidget):
        if self._orientation == Qt.Orientation.Vertical:
            self._layout.insertWidget(self._layout.count() - 1, widget)
        else:
            self._layout.addWidget(widget)
            self._sync_content_size()

    def remove_widget(self, widget: QWidget):
        self._layout.removeWidget(widget)
        widget.setParent(None)
        self._sync_content_size()

    def clear_widgets(self):
        keep = 1 if self._orientation == Qt.Orientation.Vertical else 0
        while self._layout.count() > keep:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._sync_content_size()

    def _scrollbar(self):
        if self._orientation == Qt.Orientation.Vertical:
            return self.scroll_area.verticalScrollBar()
        return self.scroll_area.horizontalScrollBar()

    def eventFilter(self, obj, event):
        if obj != self.scroll_area.viewport():
            return super().eventFilter(obj, event)

        t = event.type()
        if t == QEvent.Type.Wheel:
            delta = event.angleDelta().x() or event.angleDelta().y()
            if self._orientation == Qt.Orientation.Vertical:
                delta = event.angleDelta().y()
            self._scrollbar().setValue(self._scrollbar().value() + (-delta // 2))
            return True

        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.MiddleButton:
            self._is_dragging = True
            self._drag_start_pos = event.pos()
            self._scroll_start_value = self._scrollbar().value()
            self.scroll_area.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return True

        if t == QEvent.Type.MouseMove and self._is_dragging and self._drag_start_pos is not None:
            delta = event.pos() - self._drag_start_pos
            offset = delta.y() if self._orientation == Qt.Orientation.Vertical else delta.x()
            self._scrollbar().setValue(self._scroll_start_value - offset)
            return True

        if t == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.MiddleButton and self._is_dragging:
            self._is_dragging = False
            self._drag_start_pos = None
            self._scroll_start_value = None
            self.scroll_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            return True

        return super().eventFilter(obj, event)

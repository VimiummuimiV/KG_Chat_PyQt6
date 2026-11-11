"""RMB drag over several message rows: a band follows the drag, releasing opens the copy overlay over the rows."""

from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QPersistentModelIndex, QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from components.flash_highlight import highlight_color, HIGHLIGHT_RADIUS


_AUTOSCROLL_INTERVAL_MS = 30
_AUTOSCROLL_MAX_STEP = 40  # pixels per tick
_BAND_FILL_ALPHA = 40
_BAND_BORDER_ALPHA = 160
_BAND_BORDER_WIDTH = 1


class _SelectionBand(QWidget):
    """Mouse-transparent translucent frame over the rows being selected."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._color = QColor()
        self.hide()

    def set_color(self, color_hex: str):
        self._color = QColor(color_hex)

    def paintEvent(self, event):
        fill, border = QColor(self._color), QColor(self._color)
        fill.setAlpha(_BAND_FILL_ALPHA)
        border.setAlpha(_BAND_BORDER_ALPHA)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(border, _BAND_BORDER_WIDTH))
        painter.setBrush(fill)
        half = _BAND_BORDER_WIDTH / 2
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(half, half, -half, -half), HIGHLIGHT_RADIUS, HIGHLIGHT_RADIUS)


class MessageRangeSelector(QObject):
    """RMB drag across the rows of a message list view; on release the delegate opens its copy overlay over them."""

    def __init__(self, list_view, delegate):
        super().__init__(list_view)
        self._list_view = list_view
        self._delegate = delegate
        self._anchor: Optional[QPersistentModelIndex] = None  # row the drag started on; survives rows being added or trimmed
        self._press_position = QPoint()
        self._pointer = QPoint()
        self._is_dragging = False
        self._band = _SelectionBand(list_view.viewport())
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(_AUTOSCROLL_INTERVAL_MS)
        self._autoscroll_timer.timeout.connect(self._autoscroll)
        list_view.viewport().installEventFilter(self)
        list_view.verticalScrollBar().valueChanged.connect(self._update_band)

    def eventFilter(self, watched, event):
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.RightButton:
            self._begin(event.pos())
        elif event_type == QEvent.Type.MouseMove and self._anchor is not None:
            self._move(event)
        elif event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.RightButton:
            return self._finish()
        return False

    def _begin(self, position: QPoint):
        index = self._list_view.indexAt(position)
        self._anchor = QPersistentModelIndex(index) if index.isValid() else None
        self._press_position = self._pointer = position
        self._is_dragging = False

    def _move(self, event):
        if not event.buttons() & Qt.MouseButton.RightButton:  # the release went to another window
            self._reset()
            return
        self._pointer = event.pos()
        if not self._is_dragging:
            if (self._pointer - self._press_position).manhattanLength() < QApplication.startDragDistance():
                return
            self._is_dragging = True
            self._band.set_color(highlight_color(self._delegate.is_dark_theme))
            self._autoscroll_timer.start()
        self._update_band()

    def _finish(self) -> bool:
        """Open the overlay for a drag over several rows; a plain click is left to the delegate."""
        rows = self._rows() if self._is_dragging else None
        rect = self._rows_rect(*rows) if rows else QRect()
        self._reset()
        if rows is None or rows[0] == rows[1]:
            return False
        model = self._list_view.model()
        messages = [model.index(row, 0).data(Qt.ItemDataRole.DisplayRole) for row in range(rows[0], rows[1] + 1)]
        self._delegate.show_text_selector(messages, rect)
        return True

    def _reset(self):
        self._anchor = None
        self._is_dragging = False
        self._autoscroll_timer.stop()
        self._band.hide()

    def _rows(self) -> Optional[tuple[int, int]]:
        """First and last row between the drag start and the pointer; None when the start row is gone."""
        if self._anchor is None or self._anchor.row() < 0:
            return None
        viewport = self._list_view.viewport()
        index = self._list_view.indexAt(QPoint(
            max(0, min(self._pointer.x(), viewport.width() - 1)),
            max(0, min(self._pointer.y(), viewport.height() - 1)),
        ))
        current = index.row() if index.isValid() else self._list_view.model().rowCount() - 1
        return min(self._anchor.row(), current), max(self._anchor.row(), current)

    def _rows_rect(self, first: int, last: int) -> QRect:
        """Viewport area covered by the rows, cut to what is in view."""
        model = self._list_view.model()
        rect = self._list_view.visualRect(model.index(first, 0)).united(self._list_view.visualRect(model.index(last, 0)))
        return rect.intersected(self._list_view.viewport().rect())

    def _update_band(self):
        rows = self._rows() if self._is_dragging else None
        if rows is None or rows[0] == rows[1]:
            self._band.hide()
            return
        self._band.setGeometry(self._rows_rect(*rows))
        self._band.show()
        self._band.raise_()

    def _autoscroll(self):
        """Scroll while the pointer is held above or below the view; the band follows through the scroll bar signal."""
        y = self._pointer.y()
        overshoot = min(y, 0) + max(y - self._list_view.viewport().height(), 0)
        if overshoot:
            scroll_bar = self._list_view.verticalScrollBar()
            scroll_bar.setValue(scroll_bar.value() + max(-_AUTOSCROLL_MAX_STEP, min(_AUTOSCROLL_MAX_STEP, overshoot)))

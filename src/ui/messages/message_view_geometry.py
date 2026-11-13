"""Keeps the row heights of a message list in step with its width, fonts and layout mode."""

from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, QTimer
from PyQt6.QtWidgets import QListView

from ui.messages.message_delegate import MessageDelegate

_BOTTOM_TOLERANCE = 4  # px from the end of the list that still count as scrolled to the bottom


class MessageViewGeometry(QObject):
    """Measures the rows again once per burst of changes and keeps the reader at the same place in the log."""

    def __init__(self, list_view: QListView, delegate: MessageDelegate):
        super().__init__(list_view)
        self._list_view = list_view
        self._anchor: Optional[tuple] = None  # (row, offset of its top) or None for "stay at the bottom"
        self._at_bottom = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._relayout)
        list_view.viewport().installEventFilter(self)
        delegate.geometry_changed.connect(self.schedule)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and event.size().width() != event.oldSize().width():
            self.schedule()
        return False

    def schedule(self):
        """Ask for a relayout; calls within one event loop pass collapse into a single one."""
        if self._timer.isActive():
            return
        self._capture_position()
        self._timer.start(0)

    def _capture_position(self):
        scroll_bar = self._list_view.verticalScrollBar()
        self._at_bottom = scroll_bar.maximum() - scroll_bar.value() <= _BOTTOM_TOLERANCE
        index = self._list_view.indexAt(QPoint(1, 0))
        self._anchor = (index.row(), self._list_view.visualRect(index).top()) if index.isValid() else None

    def _relayout(self):
        view = self._list_view
        view.doItemsLayout()
        scroll_bar = view.verticalScrollBar()
        if self._at_bottom:
            scroll_bar.setValue(scroll_bar.maximum())
        elif self._anchor is not None:
            row, offset = self._anchor
            model = view.model()
            if row < model.rowCount():
                scroll_bar.setValue(scroll_bar.value() + view.visualRect(model.index(row, 0)).top() - offset)
        view.viewport().update()

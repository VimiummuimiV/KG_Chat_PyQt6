"""Keeps the row heights of a message list in step with its width, fonts and layout mode."""

import time
from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, QTimer
from PyQt6.QtWidgets import QListView

from ui.messages.message_delegate import MessageDelegate

_BOTTOM_TOLERANCE = 4  # px from the end of the list that still count as scrolled to the bottom
_BUSY_SHARE = 2.0  # a relayout may take at most 1 / _BUSY_SHARE of the time, so the window stays responsive while dragged
_MAX_INTERVAL_MS = 100
_DRAFT_MIN_ROWS = 1000  # from this size on, a resize measures only the rows near the screen until it settles
_SETTLE_MS = 120


class MessageViewGeometry(QObject):
    """Measures the rows again once per burst of changes and keeps the reader at the same place in the log."""

    def __init__(self, list_view: QListView, delegate: MessageDelegate):
        super().__init__(list_view)
        self._list_view = list_view
        self._delegate = delegate
        self._anchor: Optional[tuple] = None  # (row, offset of its top) or None for "stay at the bottom"
        self._at_bottom = False
        self._is_exact_needed = False  # a change other than the width needs every row measured right now
        self._interval_ms = 0.0  # pause that keeps the relayouts within their share of the time
        self._finished_at = 0.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._relayout)
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._measure_all_rows)
        list_view.viewport().installEventFilter(self)
        delegate.geometry_changed.connect(self._measure_all_rows)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and event.size().width() != event.oldSize().width():
            self._schedule()
        return False

    def _measure_all_rows(self):
        self._is_exact_needed = True
        self._schedule()

    def _schedule(self):
        """Ask for a relayout. While the width keeps changing the relayouts are spaced by their own cost, the last one always runs."""
        if self._timer.isActive():
            return
        self._capture_position()
        pause_ms = self._interval_ms - (time.perf_counter() - self._finished_at) * 1000
        self._timer.start(max(0, round(pause_ms)))

    def _capture_position(self):
        scroll_bar = self._list_view.verticalScrollBar()
        self._at_bottom = scroll_bar.maximum() - scroll_bar.value() <= _BOTTOM_TOLERANCE
        index = self._list_view.indexAt(QPoint(1, 0))
        self._anchor = (index.row(), self._list_view.visualRect(index).top()) if index.isValid() else None

    def _rows_near_screen(self) -> Optional[tuple]:
        """First and last row within one screen above and below the visible ones, or None if nothing is shown."""
        view = self._list_view
        first = view.indexAt(QPoint(1, 0))
        if not first.isValid():
            return None
        last = view.indexAt(QPoint(1, view.viewport().height() - 1))
        last_row = last.row() if last.isValid() else view.model().rowCount() - 1
        span = last_row - first.row() + 1
        return first.row() - span, last_row + span

    def _relayout(self):
        started = time.perf_counter()
        view = self._list_view
        is_draft = not self._is_exact_needed and view.model().rowCount() >= _DRAFT_MIN_ROWS
        self._delegate.exact_rows = self._rows_near_screen() if is_draft else None
        try:
            view.doItemsLayout()
        finally:
            self._delegate.exact_rows = None
        scroll_bar = view.verticalScrollBar()
        if self._at_bottom:
            scroll_bar.setValue(scroll_bar.maximum())
        elif self._anchor is not None:
            row, offset = self._anchor
            model = view.model()
            if row < model.rowCount():
                scroll_bar.setValue(scroll_bar.value() + view.visualRect(model.index(row, 0)).top() - offset)
        view.viewport().update()
        self._finished_at = time.perf_counter()
        self._interval_ms = min((self._finished_at - started) * 1000 * (_BUSY_SHARE - 1), _MAX_INTERVAL_MS)
        if is_draft:
            self._settle_timer.start(_SETTLE_MS)  # the rows far from the screen keep their old height until the resize stops
        else:
            self._is_exact_needed = False
            self._settle_timer.stop()

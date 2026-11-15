"""Message list that measures only the rows around the viewport, so a log of any length opens at once."""

from bisect import bisect_right
from itertools import accumulate
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QPainter, QRegion
from PyQt6.QtWidgets import QAbstractItemView, QStyleOptionViewItem

_BLOCK_ROWS = 256  # rows per block; a block keeps one running height, so a position costs one block, not the whole log
_SAMPLE_ROWS = 48  # rows measured to guess the height of the rows nobody has measured yet
_FIT_PASSES = 4  # measuring rows can move the rows below them; a few passes settle it
_MIN_PREFETCH_ROWS = 8
_SCROLL_STEP = 24
_FALLBACK_HEIGHT = 40


class MessageListView(QAbstractItemView):
    """List of MessageListModel rows drawn by a MessageDelegate.

    Rows nobody has seen keep an estimated height, so a model reset, a filter or a resize costs the same for ten
    rows and for millions. Rows near the viewport are measured exactly, and the first visible row stays in place
    while the rows above it are measured."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_count = 0
        self._estimate = _FALLBACK_HEIGHT
        self._measured_width = 0
        self._block_rows: List[Optional[Dict[int, int]]] = []  # per block: row -> measured height
        self._block_heights: List[int] = []
        self._block_tops: List[int] = [0]  # height of everything before each block, the total at the end
        self._is_tops_dirty = False
        self._is_fitting = False
        self._has_estimate = False
        self._pending_anchor: Optional[Tuple[int, int]] = None  # anchor taken before the model inserts or removes rows
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(_SCROLL_STEP)

    def setModel(self, model):
        super().setModel(model)
        model.modelReset.connect(self._on_model_reset)
        model.rowsAboutToBeInserted.connect(self._remember_anchor)
        model.rowsAboutToBeRemoved.connect(self._remember_anchor)
        model.rowsInserted.connect(self._on_rows_inserted)
        model.rowsRemoved.connect(self._on_rows_removed)
        model.dataChanged.connect(self._on_data_changed)

    def setItemDelegate(self, delegate):
        super().setItemDelegate(delegate)
        geometry_changed = getattr(delegate, "geometry_changed", None)
        if geometry_changed is not None:
            geometry_changed.connect(self._on_geometry_changed)

    def doItemsLayout(self):
        self._restart(self._anchor(), resample=True)

    def sizeHintForRow(self, row: int) -> int:
        return self._size_hint(row) if 0 <= row < self._row_count else -1

    def visualRect(self, index: QModelIndex) -> QRect:
        if not index.isValid() or index.row() >= self._row_count:
            return QRect()
        row = index.row()
        return QRect(0, self._row_top(row) - self.verticalScrollBar().value(), self.viewport().width(), self._row_height(row))

    def indexAt(self, point) -> QModelIndex:
        y = point.y() + self.verticalScrollBar().value()
        if not self._row_count or y < 0 or y >= self._current_tops()[-1]:
            return QModelIndex()
        return self.model().index(self._row_at(y), 0)

    def scrollTo(self, index: QModelIndex, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        if not index.isValid() or index.row() >= self._row_count:
            return
        row = index.row()
        scroll_bar = self.verticalScrollBar()
        for _ in range(_FIT_PASSES):
            self._measure_rows(row, row)
            self._update_range()
            value = self._target_value(row, hint)
            scroll_bar.setValue(value)  # scrollContentsBy measures the rows that came into view
            if self._target_value(row, hint) == value:
                break
        self.viewport().update()

    def horizontalOffset(self) -> int:
        return 0

    def verticalOffset(self) -> int:
        return self.verticalScrollBar().value()

    def moveCursor(self, cursor_action, modifiers) -> QModelIndex:
        return QModelIndex()

    def isIndexHidden(self, index: QModelIndex) -> bool:
        return False

    def setSelection(self, rect, flags):
        """Rows are never selected; the delegate handles clicks."""

    def visualRegionForSelection(self, selection) -> QRegion:
        return QRegion()

    def scrollContentsBy(self, dx: int, dy: int):
        self._fit_rows()
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.viewport().width() != self._measured_width:
            self._restart(self._anchor(), resample=True)
        else:
            self._fit_rows()

    def paintEvent(self, event):
        model = self.model()
        if not model or not self._row_count:
            return
        painter = QPainter(self.viewport())
        delegate = self.itemDelegate()
        option = QStyleOptionViewItem()
        self.initViewItemOption(option)
        width, view_height = self.viewport().width(), self.viewport().height()
        value = self.verticalScrollBar().value()
        row = self._row_at(value)
        y = self._row_top(row) - value
        while row < self._row_count and y < view_height:
            height = self._row_height(row)
            option.rect = QRect(0, y, width, height)
            delegate.paint(painter, option, model.index(row, 0))
            y += height
            row += 1

    def _on_model_reset(self):
        self._restart(None, resample=True)

    def _remember_anchor(self, *_):
        self._pending_anchor = self._anchor()

    def _on_rows_inserted(self, _parent, first: int, last: int):
        anchor = self._pending_anchor
        if anchor is not None and first <= anchor[0]:
            anchor = (anchor[0] + last - first + 1, anchor[1])
        self._restart(anchor, resample=False)

    def _on_rows_removed(self, _parent, first: int, last: int):
        anchor = self._pending_anchor
        if anchor is not None and anchor[0] > last:
            anchor = (anchor[0] - (last - first + 1), anchor[1])
        elif anchor is not None and anchor[0] >= first:
            anchor = (first, 0)
        self._restart(anchor, resample=False)

    def _on_geometry_changed(self):
        self._restart(self._anchor(), resample=True)

    def _on_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, *_):
        anchor = self._anchor()
        for row in range(top_left.row(), min(bottom_right.row(), self._row_count - 1) + 1):
            self._forget_height(row)
        self._fit_rows(anchor)
        self.viewport().update()

    def _restart(self, anchor: Optional[Tuple[int, int]], resample: bool):
        """Forget the measured rows and measure those on screen; the anchor row keeps its place, no anchor means the top.
        resample guesses the height of the unseen rows again, which only a new width, font or log needs."""
        model = self.model()
        self._row_count = model.rowCount() if model else 0
        self._measured_width = self.viewport().width()
        if resample or not self._has_estimate:
            self._estimate = self._sample_estimate()
        self._has_estimate = self._row_count > 0
        if anchor is not None and self._row_count:
            anchor = (min(anchor[0], self._row_count - 1), anchor[1])
        block_count = -(-self._row_count // _BLOCK_ROWS)
        self._block_rows = [None] * block_count
        self._block_heights = [_BLOCK_ROWS * self._estimate] * block_count
        if block_count:
            self._block_heights[-1] = (self._row_count - (block_count - 1) * _BLOCK_ROWS) * self._estimate
        self._is_tops_dirty = True
        if anchor is None:
            self._update_range()
            self.verticalScrollBar().setValue(0)
        self._fit_rows(anchor)
        self.viewport().update()

    def _anchor(self) -> Optional[Tuple[int, int]]:
        """The first visible row and the distance from its top to the top of the viewport."""
        if not self._row_count:
            return None
        value = self.verticalScrollBar().value()
        row = self._row_at(value)
        return row, self._row_top(row) - value

    def _fit_rows(self, anchor: Optional[Tuple[int, int]] = None):
        """Measure the rows around the viewport and keep the anchor row where it was."""
        if self._is_fitting:
            return
        self._is_fitting = True
        try:
            if not self._row_count:
                self._update_range()
                return
            anchor = anchor or self._anchor()
            for _ in range(_FIT_PASSES):
                value = self._place(anchor)
                if not self._measure_rows(*self._rows_to_measure(value)):
                    break
            else:
                self._place(anchor)
        finally:
            self._is_fitting = False

    def _place(self, anchor: Tuple[int, int]) -> int:
        """Update the scroll range and put the anchor row at its offset; returns the new scroll value."""
        self._update_range()
        scroll_bar = self.verticalScrollBar()
        value = min(max(self._row_top(anchor[0]) - anchor[1], 0), scroll_bar.maximum())
        scroll_bar.setValue(value)
        return value

    def _rows_to_measure(self, value: int) -> Tuple[int, int]:
        """The visible rows plus as many above and below, so the next scroll steps find them measured."""
        first = self._row_at(value)
        last = self._row_at(value + self.viewport().height())
        padding = max(last - first + 1, _MIN_PREFETCH_ROWS)
        return max(first - padding, 0), min(last + padding, self._row_count - 1)

    def _update_range(self):
        scroll_bar = self.verticalScrollBar()
        page = self.viewport().height()
        scroll_bar.setRange(0, max(self._current_tops()[-1] - page, 0))
        scroll_bar.setPageStep(page)

    def _target_value(self, row: int, hint) -> int:
        top, height = self._row_top(row), self._row_height(row)
        view_height = self.viewport().height()
        scroll_bar = self.verticalScrollBar()
        if hint == QAbstractItemView.ScrollHint.PositionAtTop:
            value = top
        elif hint == QAbstractItemView.ScrollHint.PositionAtBottom:
            value = top + height - view_height
        elif hint == QAbstractItemView.ScrollHint.PositionAtCenter:
            value = top + (height - view_height) // 2
        elif top < scroll_bar.value():
            value = top
        elif top + height > scroll_bar.value() + view_height:
            value = top + height - view_height
        else:
            value = scroll_bar.value()
        return min(max(value, 0), scroll_bar.maximum())

    def _size_hint(self, row: int) -> int:
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, self.viewport().width(), 0)
        size: QSize = self.itemDelegate().sizeHint(option, self.model().index(row, 0))
        return max(size.height(), 1)

    def _sample_estimate(self) -> int:
        if not self._row_count:
            return _FALLBACK_HEIGHT
        step = max(self._row_count // _SAMPLE_ROWS, 1)
        heights = [self._size_hint(row) for row in range(0, self._row_count, step)]
        return max(round(sum(heights) / len(heights)), 1)

    def _measure_rows(self, first: int, last: int) -> bool:
        """Measure the rows nobody measured yet; True if any height differs from the estimate it replaced."""
        is_changed = False
        for row in range(first, last + 1):
            rows = self._block_rows[row // _BLOCK_ROWS]
            if rows is None or row not in rows:
                is_changed |= self._set_height(row, self._size_hint(row))
        return is_changed

    def _set_height(self, row: int, height: int) -> bool:
        block = row // _BLOCK_ROWS
        rows = self._block_rows[block]
        if rows is None:
            rows = self._block_rows[block] = {}
        difference = height - rows.get(row, self._estimate)
        rows[row] = height
        if difference:
            self._block_heights[block] += difference
            self._is_tops_dirty = True
        return bool(difference)

    def _forget_height(self, row: int):
        """Drop a measured height, the row is estimated until it is measured again."""
        block = row // _BLOCK_ROWS
        rows = self._block_rows[block]
        if rows is None or row not in rows:
            return
        self._block_heights[block] += self._estimate - rows.pop(row)
        self._is_tops_dirty = True

    def _current_tops(self) -> List[int]:
        if self._is_tops_dirty:
            self._block_tops = [0, *accumulate(self._block_heights)]
            self._is_tops_dirty = False
        return self._block_tops

    def _row_height(self, row: int) -> int:
        rows = self._block_rows[row // _BLOCK_ROWS]
        return rows.get(row, self._estimate) if rows else self._estimate

    def _row_top(self, row: int) -> int:
        block, offset = divmod(row, _BLOCK_ROWS)
        top = self._current_tops()[block] + offset * self._estimate
        rows = self._block_rows[block]
        if rows:
            top += sum(height - self._estimate for measured, height in rows.items() if measured < row)
        return top

    def _row_at(self, y: int) -> int:
        """The row that contains the content position y; positions outside the log give the first or last row."""
        tops = self._current_tops()
        block = min(max(bisect_right(tops, y) - 1, 0), len(self._block_rows) - 1)
        offset = y - tops[block]
        row = block * _BLOCK_ROWS
        last = min(row + _BLOCK_ROWS, self._row_count) - 1
        rows = self._block_rows[block]
        if not rows:
            return min(row + max(offset, 0) // self._estimate, last)
        while row < last:
            height = rows.get(row, self._estimate)
            if offset < height:
                break
            offset -= height
            row += 1
        return row

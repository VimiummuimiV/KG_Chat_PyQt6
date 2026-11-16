"""Previous / next buttons that move a list view to the nearest row picked by a predicate"""

from bisect import bisect_left, bisect_right
from typing import Callable, Iterable, Optional

from PyQt6.QtCore import pyqtSignal, QObject, Qt, QTimer

from helpers.scroll.scroll import scroll, visible_rows


_DIRECTIONS = (-1, 1)  # previous, next


def set_entry_enabled(entry: dict, enabled: bool) -> None:
    """Enable or disable a panel button together with its normal or dimmed icon."""
    button = entry["button"]
    if enabled != button.isEnabled():
        button.setEnabled(enabled)
        button.setIcon(entry["icon_normal"] if enabled else entry["icon_dimmed"])


def _find_row(rows: list, reference: int, direction: int) -> Optional[int]:
    """Nearest of the sorted rows strictly before (direction < 0) or after (direction > 0) the reference row."""
    position = bisect_right(rows, reference) if direction > 0 else bisect_left(rows, reference) - 1
    return rows[position] if 0 <= position < len(rows) else None


class RowJumpGroup(QObject):
    """Previous / next buttons that scroll to the nearest row accepted by is_target; hidden while there is none."""
    visibility_changed = pyqtSignal(bool)

    def __init__(self, list_view, entries: list, is_target: Callable, on_jump: Optional[Callable] = None,
                 rescan_signals: Iterable = (), describe: Optional[Callable] = None, parent=None):
        """entries: the two panel buttons (previous, next) as dicts with button, icon_normal, icon_dimmed.
        on_jump(row, position, total) runs after a jump; describe(row data) names the target in a button tooltip."""
        super().__init__(parent)
        self._list_view = list_view
        self._entries = entries
        self._is_target = is_target
        self._on_jump = on_jump
        self._describe = describe
        self._tooltips = [entry["button"].toolTip() for entry in entries]
        self._rows: list = []
        self._cursor: Optional[int] = None  # row of the last jump; the next one starts there while it stays on screen
        self._is_visible = False

        self._signals = list(rescan_signals)
        model = list_view.model()
        if model:
            self._signals += [model.modelReset, model.rowsInserted, model.rowsRemoved]
        self._timer = QTimer(self)  # one rescan per event loop pass, however many signals fired
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.rescan)
        for signal in self._signals:
            signal.connect(self._schedule_rescan)

        for direction, entry in zip(_DIRECTIONS, entries):
            entry["button"].clicked.connect(lambda _checked=False, step=direction: self._jump(step))

    def _schedule_rescan(self, *_args) -> None:
        self._timer.start()

    def rescan(self) -> None:
        """Collect the accepted rows and show the buttons only when there are some."""
        model = self._list_view.model()
        count = model.rowCount() if model else 0
        rows_data = getattr(model, "stored_messages", None) or getattr(model, "stored_events", None)  # a plain list is far cheaper to walk than model.data per row
        if rows_data is None:
            rows_data = (self._row_data(row) for row in range(count))
        self._rows = [row for row, data in enumerate(rows_data) if self._is_target(data)]
        self._cursor = None
        is_visible = bool(self._rows)
        for entry in self._entries:
            entry["button"].setVisible(is_visible)
        if is_visible != self._is_visible:
            self._is_visible = is_visible
            self.visibility_changed.emit(is_visible)
        self.update_enabled()

    def update_enabled(self) -> None:
        """Dim a button when no accepted row lies in its direction."""
        if not self._rows:
            return
        reference = self._reference_row()
        for direction, entry, tooltip in zip(_DIRECTIONS, self._entries, self._tooltips):
            target = _find_row(self._rows, reference, direction)
            set_entry_enabled(entry, target is not None)
            if self._describe:
                target_data = None if target is None else self._row_data(target)  # None while the rows are stale
                entry["button"].setToolTip(tooltip if target_data is None else f"{tooltip}\n{self._describe(target_data)}")

    def _row_data(self, row: int):
        model = self._list_view.model()
        return model.data(model.index(row, 0), Qt.ItemDataRole.DisplayRole)

    def _reference_row(self) -> int:
        """The last jump target while it is on screen (a target in the last page cannot reach the top), else the top row."""
        top_row, bottom_row = visible_rows(self._list_view)
        cursor = self._cursor
        return cursor if cursor is not None and top_row <= cursor <= bottom_row else top_row

    def _jump(self, direction: int) -> None:
        target = _find_row(self._rows, self._reference_row(), direction)
        if target is None:
            return
        self._cursor = target
        scroll(self._list_view, mode="top", target_row=target, delay=0)
        self.update_enabled()
        if self._on_jump:
            self._on_jump(target, bisect_left(self._rows, target) + 1, len(self._rows))

    def cleanup(self) -> None:
        """Stop the timer and disconnect from the model and the extra signals."""
        self._timer.stop()
        for signal in self._signals:
            try:
                signal.disconnect(self._schedule_rescan)
            except (RuntimeError, TypeError):
                pass

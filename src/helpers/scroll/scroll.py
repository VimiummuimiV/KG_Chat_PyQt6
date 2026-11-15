from PyQt6.QtCore import QPoint, QTimer
from PyQt6.QtWidgets import QAbstractItemView, QListView, QScrollArea


def is_separator_row(data) -> bool:
    """Default separator check: works for MessageData (attribute) and tracker events (dict)."""
    if data is None:
        return False
    if isinstance(data, dict):
        return bool(data.get('is_separator'))
    return bool(getattr(data, 'is_separator', False))


def visible_rows(view) -> tuple[int, int]:
    """First and last row at least partly visible in a QListView; an empty or short view reports row 0 and the last row."""
    viewport = view.viewport()
    top_index = view.indexAt(viewport.rect().topLeft())
    bottom_index = view.indexAt(QPoint(1, viewport.height() - 1))
    last_row = max(view.model().rowCount() - 1, 0)
    return (top_index.row() if top_index.isValid() else 0), (bottom_index.row() if bottom_index.isValid() else last_row)


def scroll(widget, mode="bottom", pos=0.0, delay=10, target_row=None):
    def _scroll():
        # Check if widget is still valid (not deleted)
        try:
            if widget is None or not hasattr(widget, 'isVisible'):
                return
            # This call will raise RuntimeError if widget has been deleted
            widget.isVisible()
        except RuntimeError:
            return  # Widget has been deleted, skip scroll

        # Get scrollbar - works for both widget types
        try:
            sb = getattr(widget, "verticalScrollBar", lambda: None)()
            if not sb:
                return
        except RuntimeError:
            return  # Widget deleted during access

        # QListView - use model-based scrolling when possible
        if isinstance(widget, QListView):
            try:
                m = widget.model()
                if not m or not m.rowCount():
                    return

                hints = {
                    "top": QAbstractItemView.ScrollHint.PositionAtTop,
                    "bottom": QAbstractItemView.ScrollHint.PositionAtBottom,
                    "middle": QAbstractItemView.ScrollHint.PositionAtCenter,
                }
                if mode in hints:
                    # Explicit target_row wins; otherwise "top"/"bottom" fall back to the
                    # first/last row (a bare "middle" has no default and falls through below)
                    if target_row is not None:
                        row = target_row
                    elif mode == "top":
                        row = 0
                    elif mode == "bottom":
                        row = m.rowCount() - 1
                    else:
                        row = None
                    if row is not None and 0 <= row < m.rowCount():
                        widget.scrollTo(m.index(row, 0), hints[mode])
                        return
            except RuntimeError:
                return  # Widget or model deleted during access

        # QScrollArea - refresh geometry
        if isinstance(widget, QScrollArea):
            try:
                if widget.widget():
                    widget.widget().updateGeometry()
                    widget.updateGeometry()
            except RuntimeError:
                return  # Widget deleted during access

        # Common scrollbar-based scrolling for both types
        try:
            if mode == "top":
                sb.setValue(0)
            elif mode == "bottom":
                sb.setValue(sb.maximum())
            elif mode == "middle":
                sb.setValue(sb.maximum() // 2)
            else:  # relative
                sb.setValue(int(sb.maximum() * max(0.0, min(1.0, pos))))
        except RuntimeError:
            return  # Scrollbar deleted during access

    if delay > 0:
        QTimer.singleShot(delay, _scroll)
        if mode == "bottom" and delay < 50:
            QTimer.singleShot(50, _scroll)
    else:
        _scroll()

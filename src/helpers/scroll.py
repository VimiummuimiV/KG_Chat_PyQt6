from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QScrollArea, QListView, QAbstractItemView

def scroll(widget, mode="bottom", pos=0.0, delay=10):
    def _scroll():
        # QListView → model-based scrolling
        if isinstance(widget, QListView):
            m = widget.model()
            if not m or not m.rowCount():
                return
            if mode == "relative":
                sb = widget.verticalScrollBar()
                sb.setValue(int(sb.maximum() * max(0.0, min(1.0, pos))))
            else:
                i = 0 if mode == "top" else m.rowCount() - 1
                hint = (
                    QAbstractItemView.ScrollHint.PositionAtTop
                    if mode == "top"
                    else QAbstractItemView.ScrollHint.PositionAtBottom
                )
                widget.scrollTo(m.index(i, 0), hint)
            return
        # QScrollArea geometry refresh (only if needed, but harmless)
        if isinstance(widget, QScrollArea):
            if widget.widget():
                widget.widget().updateGeometry()
            widget.updateGeometry()
        sb = getattr(widget, "verticalScrollBar", None)
        sb = sb() if callable(sb) else None
        if not sb:
            return
        if mode == "top":
            sb.setValue(0)
        elif mode == "bottom":
            sb.setValue(sb.maximum())
        else:  # relative
            sb.setValue(int(sb.maximum() * max(0.0, min(1.0, pos))))
    if delay > 0:
        QTimer.singleShot(delay, _scroll)
        if mode == "bottom" and delay < 50:
            QTimer.singleShot(50, _scroll)
    else:
        _scroll()

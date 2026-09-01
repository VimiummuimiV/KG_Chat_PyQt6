"""Shared fade-out row/widget highlight (chatlog rows, tracker history, …)."""
from PyQt6.QtCore import QTimer, QObject, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget, QLabel

HIGHLIGHT_RADIUS = 4


def highlight_fill_color(is_dark: bool, opacity: float) -> QColor:
    color = QColor("#4DA6FF" if is_dark else "#0066CC")
    color.setAlphaF(max(0.0, min(1.0, opacity)) * 0.15)
    return color


def paint_highlight(painter: QPainter, rect, is_dark: bool, opacity: float):
    if opacity <= 0:
        return
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(highlight_fill_color(is_dark, opacity))
    painter.drawRoundedRect(rect, HIGHLIGHT_RADIUS, HIGHLIGHT_RADIUS)


class FlashHighlight(QObject):
    """Attach to a QWidget: start() fades a blue overlay via paint_overlay()."""

    def __init__(self, widget: QWidget, is_dark_fn, interval_ms: int = 50, step: float = 0.05):
        super().__init__(widget)
        self.widget = widget
        self.is_dark_fn = is_dark_fn
        self.opacity = 0.0
        self.step = step
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._tick)

    def start(self):
        self.opacity = 1.0
        if not self.timer.isActive():
            self.timer.start()
        self.widget.update()

    def _tick(self):
        self.opacity -= self.step
        if self.opacity <= 0:
            self.opacity = 0.0
            self.timer.stop()
        self.widget.update()

    def paint_overlay(self, painter: QPainter, rect):
        paint_highlight(painter, rect, bool(self.is_dark_fn()), self.opacity)


class FlashLabel(QLabel):
    """QLabel that flashes a fade-out highlight overlay via flash()."""

    def __init__(self, *args, is_dark_fn, **kwargs):
        super().__init__(*args, **kwargs)
        self.flash_highlight = FlashHighlight(self, is_dark_fn)

    def flash(self):
        self.flash_highlight.start()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        self.flash_highlight.paint_overlay(painter, self.rect())
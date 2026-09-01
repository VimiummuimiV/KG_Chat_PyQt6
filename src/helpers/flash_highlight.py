"""Shared fade-out row/widget highlight (chatlog rows, tracker history, …)."""
from PyQt6.QtCore import QTimer, QObject, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget, QLabel

HIGHLIGHT_RADIUS = 4

DEFAULTS = {
    "highlight": {"dark": "#4DA6FF", "light": "#0066CC"},
    "link": {
        "normal": {"dark": "#4DA6FF", "light": "#0066CC"},
        "media": {"dark": "#4DFF88", "light": "#00AA44"},
        "chatlog": {"dark": "#FFD24D", "light": "#CC6600"},
    },
    "timestamp": {"dark": "#999999", "light": "#999999"},
}


def _theme_color(entry: dict, is_dark: bool) -> str:
    return entry["dark"] if is_dark else entry["light"]


def highlight_fill_color(is_dark: bool, opacity: float) -> QColor:
    color = QColor(_theme_color(DEFAULTS["highlight"], is_dark))
    color.setAlphaF(max(0.0, min(1.0, opacity)) * 0.15)
    return color


def link_colors(is_dark: bool) -> dict:
    return {kind: _theme_color(entry, is_dark) for kind, entry in DEFAULTS["link"].items()}


def timestamp_color(is_dark: bool) -> str:
    return _theme_color(DEFAULTS["timestamp"], is_dark)


def draw_rounded_fill(painter: QPainter, rect, color: QColor, radius: int = HIGHLIGHT_RADIUS):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(rect, radius, radius)
    painter.restore()


def paint_highlight(painter: QPainter, rect, is_dark: bool, opacity: float):
    if opacity <= 0:
        return
    draw_rounded_fill(painter, rect, highlight_fill_color(is_dark, opacity))


class FlashFade(QObject):
    """Drives an opacity fade from 1.0 to 0.0, calling on_tick after each step."""

    def __init__(self, on_tick, parent=None, interval_ms: int = 50, step: float = 0.05):
        super().__init__(parent)
        self.opacity = 0.0
        self.step = step
        self.on_tick = on_tick
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._tick)

    def start(self):
        self.opacity = 1.0
        if not self.timer.isActive():
            self.timer.start()
        self.on_tick()

    def _tick(self):
        self.opacity -= self.step
        if self.opacity <= 0:
            self.opacity = 0.0
            self.timer.stop()
        self.on_tick()


class FlashHighlight(FlashFade):
    """Attach to a QWidget: start() fades an overlay via paint_overlay()."""

    def __init__(self, widget: QWidget, is_dark_fn, interval_ms: int = 50, step: float = 0.05):
        super().__init__(widget.update, parent=widget, interval_ms=interval_ms, step=step)
        self.widget = widget
        self.is_dark_fn = is_dark_fn

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
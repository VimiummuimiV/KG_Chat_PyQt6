"""Shared fade-out highlight: one FlashFade drives opacity, callers supply color+rect."""
from PyQt6.QtCore import QTimer, QObject, Qt, QEasingCurve
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget, QLabel

HIGHLIGHT_RADIUS = 4

# Timing functions offered for the flash fade, keyed by the value stored in config.
TIMING_FUNCTIONS = {
    "linear": QEasingCurve.Type.Linear,
    "ease_out": QEasingCurve.Type.OutQuad,
    "ease_in_out": QEasingCurve.Type.InOutQuad,
    "ease_out_cubic": QEasingCurve.Type.OutCubic,
    "ease_in_out_cubic": QEasingCurve.Type.InOutCubic,
    "ease_elastic_in_out": QEasingCurve.Type.InOutElastic,
    "ease_elastic_out_in": QEasingCurve.Type.OutInElastic,
    "ease_back_in": QEasingCurve.Type.InBack,
    "ease_back_out": QEasingCurve.Type.OutBack,
    "ease_back_in_out": QEasingCurve.Type.InOutBack,
    "ease_back_out_in": QEasingCurve.Type.OutInBack,
    "ease_bounce_in": QEasingCurve.Type.InBounce,
    "ease_bounce_out": QEasingCurve.Type.OutBounce,
}
DEFAULT_FLASH_DURATION_MS = 1000
DEFAULT_FLASH_EASING = "linear"


def flash_duration_ms(config) -> int:
    value = config.get("ui", "chat", "flash_duration_ms") if config else None
    return int(value) if value else DEFAULT_FLASH_DURATION_MS


def flash_easing(config) -> QEasingCurve.Type:
    name = config.get("ui", "chat", "flash_easing") if config else None
    return TIMING_FUNCTIONS.get(name, TIMING_FUNCTIONS[DEFAULT_FLASH_EASING])

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


def highlight_color(is_dark: bool) -> str:
    return _theme_color(DEFAULTS["highlight"], is_dark)


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


def paint_flash(painter: QPainter, rect, color: str, opacity: float, alpha: float = 0.15, radius: int = HIGHLIGHT_RADIUS):
    if opacity <= 0:
        return
    fill = QColor(color)
    fill.setAlphaF(max(0.0, min(1.0, opacity)) * alpha)
    draw_rounded_fill(painter, rect, fill, radius)


class FlashFade(QObject):
    """Drives an opacity fade from 1.0 to 0.0 over config-driven duration/easing, calling on_tick after each step."""

    def __init__(self, on_tick, parent=None, config=None, interval_ms: int = 50):
        super().__init__(parent)
        self.opacity = 0.0
        self.config = config
        self.on_tick = on_tick
        self._elapsed_ms = 0
        self._duration_ms = DEFAULT_FLASH_DURATION_MS
        self._easing = QEasingCurve(TIMING_FUNCTIONS[DEFAULT_FLASH_EASING])
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._tick)

    def start(self):
        self.opacity = 1.0
        self._elapsed_ms = 0
        self._duration_ms = flash_duration_ms(self.config)
        self._easing = QEasingCurve(flash_easing(self.config))
        if not self.timer.isActive():
            self.timer.start()
        self.on_tick()

    def _tick(self):
        self._elapsed_ms += self.timer.interval()
        progress = min(1.0, self._elapsed_ms / self._duration_ms)
        self.opacity = 1.0 - self._easing.valueForProgress(progress)
        if progress >= 1.0:
            self.opacity = 0.0
            self.timer.stop()
        self.on_tick()

    def paint(self, painter: QPainter, rect, color: str, alpha: float = 0.15, radius: int = HIGHLIGHT_RADIUS):
        paint_flash(painter, rect, color, self.opacity, alpha, radius)


class FlashHighlight(FlashFade):
    """Attach to a QWidget: start() fades the shared highlight color via paint_overlay()."""

    def __init__(self, widget: QWidget, is_dark_fn, config=None, interval_ms: int = 50):
        super().__init__(widget.update, parent=widget, config=config, interval_ms=interval_ms)
        self.widget = widget
        self.is_dark_fn = is_dark_fn

    def paint_overlay(self, painter: QPainter, rect):
        self.paint(painter, rect, highlight_color(bool(self.is_dark_fn())))


class FlashLabel(QLabel):
    """QLabel that flashes a fade-out highlight overlay via flash()."""

    def __init__(self, *args, is_dark_fn, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.flash_highlight = FlashHighlight(self, is_dark_fn, config=config)

    def flash(self):
        self.flash_highlight.start()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        self.flash_highlight.paint_overlay(painter, self.rect())
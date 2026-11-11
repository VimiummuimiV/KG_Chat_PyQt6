"""Smooth fade of a whole widget through the opacity of the widget as one picture."""

from PyQt6.QtCore import QEasingCurve, QObject, QVariantAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget


class WidgetFader(QObject):
    """Fades a widget out and back in as a whole: one animation, however many items it holds.

    The opacity effect exists only while the widget is not fully visible.
    """

    def __init__(self, widget: QWidget):
        super().__init__(widget)
        self._widget = widget
        self._effect: QGraphicsOpacityEffect | None = None
        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.valueChanged.connect(self._apply)
        self._animation.finished.connect(self._finish)

    def fade_to(self, opacity: float, duration_ms: int) -> None:
        """Move the opacity of the widget to the given value, from where it is now."""
        if self._effect is None:
            if opacity >= 1.0:
                return
            self._effect = QGraphicsOpacityEffect(self._widget)
            self._effect.setOpacity(1.0)
            self._widget.setGraphicsEffect(self._effect)
        self._animation.stop()
        self._animation.setStartValue(self._effect.opacity())
        self._animation.setEndValue(opacity)
        self._animation.setDuration(duration_ms)
        self._animation.start()

    def restore(self) -> None:
        """Show the widget fully at once."""
        self._animation.stop()
        self._remove_effect()

    def _apply(self, opacity: float) -> None:
        if self._effect is not None:
            self._effect.setOpacity(opacity)

    def _finish(self) -> None:
        if self._effect is not None and self._effect.opacity() >= 1.0:
            self._remove_effect()

    def _remove_effect(self) -> None:
        if self._effect is not None:
            self._effect = None
            self._widget.setGraphicsEffect(None)

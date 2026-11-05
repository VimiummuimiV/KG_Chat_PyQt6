from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSlider, QWidget

from helpers.fonts.font_scaler import FontScaler


class _SliderWheelFilter(QObject):
    """Intercepts wheel on slider — enforces exactly +1/-1 per notch."""

    def __init__(self, font_scaler: FontScaler, parent=None):
        super().__init__(parent)
        self.font_scaler = font_scaler

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if event.angleDelta().y() > 0:
                self.font_scaler.scale_up()
            else:
                self.font_scaler.scale_down()
            event.accept()
            return True
        return False


class FontScaleSlider(QWidget):
    """
    Horizontal slider for adjusting text font size. Shows current value in a label.
    Dimmed to 0.5 opacity at rest, smoothly reveals to 1.0 on hover.
    """

    def __init__(self, font_scaler: FontScaler, parent=None):
        super().__init__(parent)
        self.font_scaler = font_scaler
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        self.setLayout(layout)

        # Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(FontScaler.TEXT_MIN)
        self.slider.setMaximum(FontScaler.TEXT_MAX)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setValue(font_scaler.get_text_size())
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.sliderReleased.connect(font_scaler.font_size_committed.emit)
        self._wheel_filter = _SliderWheelFilter(font_scaler, self.slider)
        self.slider.installEventFilter(self._wheel_filter)
        layout.addWidget(self.slider, stretch=1)

        # Value label
        self.value_label = QLabel(str(font_scaler.get_text_size()))
        self.value_label.setFont(QFont("Roboto", 12))
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setFixedWidth(24)
        layout.addWidget(self.value_label)

        font_scaler.font_size_changed.connect(self._sync_from_scaler)

        # Opacity effect
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0)
        self.setGraphicsEffect(self._opacity_effect)

        self._anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def _fade_to(self, opacity: float):
        self._anim.stop()
        self._anim.setStartValue(self._opacity_effect.opacity())
        self._anim.setEndValue(opacity)
        self._anim.start()

    def enterEvent(self, event):
        self._fade_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._fade_to(0)
        super().leaveEvent(event)

    def _on_slider_changed(self, value: int):
        self.value_label.setText(str(value))
        self.font_scaler.set_size(value, is_dragging=self.slider.isSliderDown())

    def _sync_from_scaler(self):
        value = self.font_scaler.get_text_size()
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.value_label.setText(str(value))

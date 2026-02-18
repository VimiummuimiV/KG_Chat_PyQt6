from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt, QEvent
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSlider
from PyQt6.QtGui import QFont


class FontScaler(QObject):
    """
    Manages text font size. Emits font_size_changed on every size update.
    Disk writes are debounced to avoid excessive I/O.
    """

    font_size_changed = pyqtSignal()

    TEXT_MIN = 12
    TEXT_MAX = 24

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._text_size = max(
            self.TEXT_MIN,
            min(self.TEXT_MAX, self.config.get("ui", "text_font_size") or 17)
        )

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

    def get_text_size(self) -> int:
        return self._text_size

    def set_size(self, size: int):
        size = max(self.TEXT_MIN, min(self.TEXT_MAX, size))
        if size != self._text_size:
            self._text_size = size
            self._notify()

    def scale_up(self):
        self.set_size(self._text_size + 1)

    def scale_down(self):
        self.set_size(self._text_size - 1)

    def _notify(self):
        self.font_size_changed.emit()
        self._save_timer.start(300)

    def _do_save(self):
        self.config.set("ui", "text_font_size", value=self._text_size)


class _SliderWheelFilter(QObject):
    """
    Event filter installed on the slider widget.
    Intercepts wheel events and enforces exactly +1/-1 per scroll notch,
    bypassing Qt's native slider wheel acceleration entirely.
    """

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
            return True  # Stop event — do not let slider process it natively
        return False


class FontScaleSlider(QWidget):
    """
    Horizontal slider for adjusting font size.
    Layout: small A — slider — big A — value label
    """

    def __init__(self, font_scaler: FontScaler, parent=None):
        super().__init__(parent)
        self.font_scaler = font_scaler

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        self.setLayout(layout)

        # Small "A"
        small_label = QLabel("A")
        small_label.setFont(QFont("Roboto", 10))
        small_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(small_label)

        # Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(FontScaler.TEXT_MIN)
        self.slider.setMaximum(FontScaler.TEXT_MAX)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setValue(font_scaler.get_text_size())
        self.slider.valueChanged.connect(self._on_slider_changed)

        # Event filter intercepts wheel before Qt's native handler
        self._wheel_filter = _SliderWheelFilter(font_scaler, self.slider)
        self.slider.installEventFilter(self._wheel_filter)

        layout.addWidget(self.slider, stretch=1)

        # Large "A"
        big_label = QLabel("A")
        big_label.setFont(QFont("Roboto", 16))
        big_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(big_label)

        # Value label — always visible to the right of big A
        self.value_label = QLabel(str(font_scaler.get_text_size()))
        self.value_label.setFont(QFont("Roboto", 12))
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setFixedWidth(24)
        layout.addWidget(self.value_label)

        font_scaler.font_size_changed.connect(self._sync_from_scaler)

    def _on_slider_changed(self, value: int):
        self.value_label.setText(str(value))
        self.font_scaler.set_size(value)

    def _sync_from_scaler(self):
        """Keep slider and label in sync when changed via Ctrl+Scroll or keyboard."""
        value = self.font_scaler.get_text_size()
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.value_label.setText(str(value))
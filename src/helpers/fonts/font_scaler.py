from PyQt6.QtCore import pyqtSignal, QObject, QTimer


class FontScaler(QObject):
    font_size_changed = pyqtSignal()  # Fires immediately on any change (drag/wheel/keyboard)
    font_size_committed = pyqtSignal()  # Fires on release (drag) or after idle (wheel/keyboard)

    TEXT_MIN = 12
    TEXT_MAX = 24

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._text_size = max(
            self.TEXT_MIN,
            min(self.TEXT_MAX, self.config.get("font", "text", "size") or 12)
        )

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.timeout.connect(self.font_size_committed.emit)

    def get_text_size(self) -> int:
        return self._text_size

    def set_size(self, size: int, is_dragging: bool = False):
        size = max(self.TEXT_MIN, min(self.TEXT_MAX, size))
        if size != self._text_size:
            self._text_size = size
            self._notify(is_dragging)

    def scale_up(self):
        self.set_size(self._text_size + 1)

    def scale_down(self):
        self.set_size(self._text_size - 1)

    def _notify(self, is_dragging: bool = False):
        self.font_size_changed.emit()
        self._save_timer.start(300)
        if not is_dragging:
            self._commit_timer.start(150)

    def _do_save(self):
        self.config.set("font", "text", "size", value=self._text_size)

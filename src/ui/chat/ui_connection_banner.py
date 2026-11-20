"""ChatWindow: the strip above the input that shows a lost or restoring connection."""

from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

from helpers.translate import on_language_changed, tr, TranslatableMixin
from themes.stylesheet import set_style_property


_COUNTDOWN_INTERVAL_MS = 1000
_PADDING_HORIZONTAL = 10
_PADDING_VERTICAL = 4


class ConnectionBanner(TranslatableMixin, QFrame):
    """Hidden while online; otherwise says what the connection is doing and what waits for it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_translatable()
        self.setObjectName("connectionBanner")
        self._status = "online"
        self._retry_seconds: Optional[int] = None
        self._attempt = 0
        self._queued_count = 0

        self._text_label = QLabel()
        self._text_label.setObjectName("connectionBannerText")
        self._text_label.setWordWrap(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PADDING_HORIZONTAL, _PADDING_VERTICAL, _PADDING_HORIZONTAL, _PADDING_VERTICAL)
        layout.addWidget(self._text_label)

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(_COUNTDOWN_INTERVAL_MS)
        self._countdown_timer.timeout.connect(self._tick)
        on_language_changed(self.retranslate_all)
        self.hide()

    def set_connection(self, status: str, retry_seconds: Optional[int] = None, attempt: int = 0):
        """Show the connection state; retry_seconds is the wait before the next attempt while offline."""
        self._status = status
        self._retry_seconds = retry_seconds if status == "offline" else None
        self._attempt = attempt
        self._render()

    def set_queued(self, count: int):
        """Show how many messages wait for the connection."""
        self._queued_count = count
        self._render()

    def retranslate_all(self, code=None):
        super().retranslate_all(code)
        self._render()

    def _tick(self):
        self._retry_seconds = max(0, self._retry_seconds - 1)
        self._render()

    def _render(self):
        is_visible = self._status != "online"
        self.setVisible(is_visible)
        if not is_visible:
            self._countdown_timer.stop()
            return
        set_style_property(self, "state", self._status)
        set_style_property(self._text_label, "state", self._status)  # a rule on the banner does not restyle its child
        if self._retry_seconds is None:
            self._countdown_timer.stop()
        elif not self._countdown_timer.isActive():
            self._countdown_timer.start()
        self._text_label.setText(self._text())

    def _text(self) -> str:
        """State, attempt number, countdown and the queue, as short parts joined by a middle dot."""
        parts = [tr("No connection", "Нет соединения") if self._status == "offline" else tr("Connecting…", "Подключение…")]
        if self._attempt:
            parts.append(tr(f"attempt {self._attempt}", f"попытка {self._attempt}"))
        if self._retry_seconds is not None:
            parts.append(tr(f"retry in {self._retry_seconds} s", f"через {self._retry_seconds} с"))
        if self._queued_count:
            parts.append(tr(f"Queued: {self._queued_count}", f"В очереди: {self._queued_count}"))
        return " · ".join(parts)

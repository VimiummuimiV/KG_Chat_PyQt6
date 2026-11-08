"""Delayed calls that die together with the widget they touch."""

from typing import Callable

from PyQt6.QtCore import QObject, QTimer


def call_later(owner: QObject, delay_ms: int, callback: Callable[[], None]) -> None:
    """Run callback after delay_ms on the main thread; skipped when owner is destroyed first."""
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.timeout.connect(callback)
    timer.timeout.connect(timer.deleteLater)
    timer.start(delay_ms)

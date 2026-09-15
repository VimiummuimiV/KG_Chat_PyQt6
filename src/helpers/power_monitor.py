"""Cross-platform system sleep/wake detector.

Works on Windows, macOS and Linux without any platform-specific APIs: a QTimer
"heartbeat" ticks on a fixed interval, driven by Qt's event loop. When the OS
suspends, the event loop (and this timer) freezes along with it; on resume the
timer fires again after an abnormally long gap in wall-clock time. That gap is
the signal that the system just woke up.
"""
import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

HEARTBEAT_INTERVAL_MS = 2000
SUSPEND_GAP_THRESHOLD_SECONDS = 8.0


class PowerMonitor(QObject):
    """Emits `resumed` shortly after the system wakes from sleep/hibernation."""

    resumed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(HEARTBEAT_INTERVAL_MS)
        self._timer.timeout.connect(self._on_heartbeat)
        self._last_tick = None

    def start(self):
        self._last_tick = time.monotonic()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _on_heartbeat(self):
        now = time.monotonic()
        gap = now - self._last_tick
        self._last_tick = now
        if gap > SUSPEND_GAP_THRESHOLD_SECONDS:
            print(f"⚡ System wake detected (idle gap: {gap:.1f}s)")
            self.resumed.emit()


power_monitor = PowerMonitor()

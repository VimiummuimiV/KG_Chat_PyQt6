"""Hold-to-repeat: runs an action on press, then keeps repeating it while the button stays down."""

from PyQt6.QtCore import QObject, QTimer


HOLD_DELAY_MS = 400  # pause before the repeating starts
HOLD_INTERVAL_MS = 100


class HoldRepeater(QObject):
    """Calls an action on press and, after a delay, again at an interval until release."""

    def __init__(self, action, parent: QObject):
        super().__init__(parent)
        self._action = action
        self._arguments = ()
        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.setInterval(HOLD_DELAY_MS)
        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(HOLD_INTERVAL_MS)
        self._delay_timer.timeout.connect(self._repeat_timer.start)
        self._repeat_timer.timeout.connect(self._repeat)

    def press(self, *arguments) -> None:
        """Run the action now and start repeating it with the same arguments."""
        self.release()
        self._arguments = arguments
        self._action(*arguments)
        self._delay_timer.start()

    def release(self) -> None:
        """Stop repeating."""
        self._delay_timer.stop()
        self._repeat_timer.stop()

    def _repeat(self) -> None:
        self._action(*self._arguments)

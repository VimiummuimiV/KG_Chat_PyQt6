"""Shared physics of bodies on the pet line: held by the mouse, thrown, falling and landing."""

import math
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QPixmap


GRAVITY = 2400  # device pixels per second squared
_MAXIMUM_THROW_SPEED = 1500  # device pixels per second
_DRAG_THRESHOLD = 4  # device pixels; a shorter press is a click
_STALE_VELOCITY_MS = 80  # a body held still this long before release is dropped, not thrown
_VELOCITY_WINDOW_MS = 100  # the hand speed is measured over this much of the latest movement
_THROW_DEAD_SPEED = 600  # device pixels per second; a hand moving slower than this only drops the body
_THROW_GAIN = 0.6  # share of the hand speed beyond the dead speed that the body leaves with


@dataclass
class _Grab:
    """A body held by the mouse."""

    offset: QPoint  # grab point inside the body's pixmap
    start: QPoint
    samples: deque  # (timestamp in ms, point) of the latest mouse positions
    _moved: bool = False


class Throwable(ABC):
    """A body standing on the line of an area measured in device pixels that the mouse can pick up and throw."""

    def __init__(self):
        self.x = 0.0
        self.lift = 0.0  # height above the line
        self.is_flying = False
        self.hold: _Grab | None = None
        self.velocity = [0.0, 0.0]  # right, up

    @property
    @abstractmethod
    def pixmap(self) -> QPixmap:
        """The picture drawn now."""

    @property
    def is_held(self) -> bool:
        return self.hold is not None

    @property
    def can_be_held(self) -> bool:
        return True

    @abstractmethod
    def _maximum_lift(self, area_height: int) -> float:
        """Return the highest lift that keeps the body inside the area."""

    def click(self) -> None:
        """React to being pressed and released without a drag."""

    def land(self, impact_speed: float) -> None:
        """React to touching the line after a flight."""

    def position(self, area_height: int) -> QPoint:
        """Return where the pixmap's top left corner is drawn."""
        return QPoint(round(self.x), round(area_height - self.lift - self.pixmap.height()))

    def grab(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        """Pick the body up at point."""
        self.hold = _Grab(point - self.position(area_height), point, deque([(timestamp_ms, point)]))
        self.is_flying = False
        self.velocity = [0.0, 0.0]

    def drag_to(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        """Carry the held body to point, remembering the latest hand positions."""
        grab = self.hold
        if not grab._moved and (point - grab.start).manhattanLength() < _DRAG_THRESHOLD:
            return
        grab._moved = True
        self.x = point.x() - grab.offset.x()
        top = point.y() - grab.offset.y()
        self.lift = max(0.0, min(area_height - self.pixmap.height() - top, self._maximum_lift(area_height)))
        grab.samples.append((timestamp_ms, point))
        while len(grab.samples) > 1 and grab.samples[0][0] < timestamp_ms - _VELOCITY_WINDOW_MS:
            grab.samples.popleft()

    def release(self, timestamp_ms: int) -> None:
        """Let go: a click only calls click(), a drag throws the body."""
        grab, self.hold = self.hold, None
        if not grab._moved:
            self.is_flying = self.lift > 0
            self.click()
            return
        self.velocity = self._throw_velocity(grab, timestamp_ms)
        self.is_flying = True

    @staticmethod
    def _throw_velocity(grab: _Grab, timestamp_ms: int) -> list[float]:
        """Turn the recent hand movement into a launch speed: slow movement drops the body, a real swing throws it."""
        (oldest_ms, oldest), (newest_ms, newest) = grab.samples[0], grab.samples[-1]
        if timestamp_ms - newest_ms > _STALE_VELOCITY_MS or newest_ms == oldest_ms:
            return [0.0, 0.0]
        seconds = (newest_ms - oldest_ms) / 1000
        right, up = (newest.x() - oldest.x()) / seconds, (oldest.y() - newest.y()) / seconds
        hand_speed = math.hypot(right, up)
        launch_speed = min((hand_speed - _THROW_DEAD_SPEED) * _THROW_GAIN, _MAXIMUM_THROW_SPEED)
        if launch_speed <= 0:
            return [0.0, 0.0]
        return [right * launch_speed / hand_speed, up * launch_speed / hand_speed]

    def fly(self, step_ms: int, area_height: int) -> None:
        """Move a thrown or falling body; touching the line ends the flight and calls land()."""
        seconds = step_ms / 1000
        self.velocity[1] -= GRAVITY * seconds
        self.lift += self.velocity[1] * seconds
        self.x += self.velocity[0] * seconds
        ceiling = self._maximum_lift(area_height)
        if self.lift > ceiling:
            self.lift, self.velocity[1] = ceiling, 0.0
        elif self.lift <= 0:
            impact_speed = -self.velocity[1]
            self.lift, self.is_flying = 0.0, False
            self.land(impact_speed)

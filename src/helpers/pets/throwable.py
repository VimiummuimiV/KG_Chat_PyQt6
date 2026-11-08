"""Shared physics of bodies on the pet line: held by the mouse, thrown, falling and landing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QPixmap


GRAVITY = 2400  # device pixels per second squared
_MAXIMUM_THROW_SPEED = 1800  # device pixels per second
_DRAG_THRESHOLD = 4  # device pixels; a shorter press is a click
_STALE_VELOCITY_MS = 80  # a body held still this long before release is dropped, not thrown
_VELOCITY_BLEND = 0.5  # weight of the newest mouse movement in the throw speed


@dataclass
class _Grab:
    """A body held by the mouse."""

    offset: QPoint  # grab point inside the body's pixmap
    start: QPoint
    last: QPoint
    _last_ms: int
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
    def maximum_lift(self, area_height: int) -> float:
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
        self.hold = _Grab(point - self.position(area_height), point, point, timestamp_ms)
        self.is_flying = False
        self.velocity = [0.0, 0.0]

    def drag_to(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        """Carry the held body to point, tracking the speed of the hand."""
        grab = self.hold
        if not grab._moved and (point - grab.start).manhattanLength() < _DRAG_THRESHOLD:
            return
        grab._moved = True
        self.x = point.x() - grab.offset.x()
        top = point.y() - grab.offset.y()
        self.lift = max(0.0, min(area_height - self.pixmap.height() - top, self.maximum_lift(area_height)))
        seconds = max(timestamp_ms - grab._last_ms, 1) / 1000
        newest = ((point.x() - grab.last.x()) / seconds, (grab.last.y() - point.y()) / seconds)
        self.velocity = [
            (1 - _VELOCITY_BLEND) * old + _VELOCITY_BLEND * new for old, new in zip(self.velocity, newest)
        ]
        grab.last, grab._last_ms = point, timestamp_ms

    def release(self, timestamp_ms: int) -> None:
        """Let go: a click only calls click(), a drag throws the body."""
        grab, self.hold = self.hold, None
        if not grab._moved:
            self.is_flying = self.lift > 0
            self.click()
            return
        if timestamp_ms - grab._last_ms > _STALE_VELOCITY_MS:
            self.velocity = [0.0, 0.0]
        self.velocity = [max(-_MAXIMUM_THROW_SPEED, min(speed, _MAXIMUM_THROW_SPEED)) for speed in self.velocity]
        self.is_flying = True

    def fly(self, step_ms: int, area_height: int) -> None:
        """Move a thrown or falling body; touching the line ends the flight and calls land()."""
        seconds = step_ms / 1000
        self.velocity[1] -= GRAVITY * seconds
        self.lift += self.velocity[1] * seconds
        self.x += self.velocity[0] * seconds
        ceiling = self.maximum_lift(area_height)
        if self.lift > ceiling:
            self.lift, self.velocity[1] = ceiling, 0.0
        elif self.lift <= 0:
            impact_speed = -self.velocity[1]
            self.lift, self.is_flying = 0.0, False
            self.land(impact_speed)

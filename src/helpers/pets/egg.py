"""Egg laid by a pet: falls, tips over, rolls by its shape, breaks on a hard landing and vanishes after its life-time."""

import math
import random

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QPixmap

from helpers.pets.animation import load_animation
from helpers.pets.catalog import PetKind
from helpers.pets.egg_rolling import advance, spin_for_speed
from helpers.pets.throwable import Throwable


_INTACT_LIFETIME_MS = 90000
_BROKEN_LIFETIME_MS = 8000  # counted from the landing; the break animation plays within it
_BREAK_IMPACT_SPEED = 600  # device pixels per second; about a 75 pixel fall
_MAXIMUM_ROLL_SPEED = 700  # device pixels per second
_START_TILT = 0.05  # radians; a laid egg stands on its blunt end only until this tilt grows
_PUSH_BLEND = 0.35  # share of the gap to the cursor speed closed by each mouse move over the egg
_WALL_BOUNCE = 0.4  # share of the spin kept after hitting the side of the area
_EGG_KIND = PetKind("egg", "white", frozenset())


class Egg(Throwable):
    """An egg that starts falling at the given height; it breaks when it lands too fast and rolls when it lands softly."""

    def __init__(self, center_x: float, lift: float, pixel_size: int):
        super().__init__()
        self._pixel_size = pixel_size
        self.is_broken = False
        self._age_ms = 0
        self._angle = random.choice((-_START_TILT, _START_TILT)) % math.tau  # clockwise turn; zero is upright
        self._spin = 0.0  # radians per second, clockwise
        self.x = center_x - self.pixmap.width() / 2
        self.lift = lift
        self.is_flying = True

    @property
    def _animation(self):
        return load_animation(_EGG_KIND, "break" if self.is_broken else "roll", self._pixel_size)

    @property
    def pixmap(self) -> QPixmap:
        animation = self._animation
        if self.is_broken:
            return animation.pixmap_once(self._age_ms)
        return animation.frames_right[round(self._angle / math.tau * len(animation.frames_right)) % len(animation.frames_right)]

    @property
    def can_be_held(self) -> bool:
        return not self.is_broken

    @property
    def expired(self) -> bool:
        """Whether the life-time is over and the egg should be removed."""
        return self._age_ms >= (_BROKEN_LIFETIME_MS if self.is_broken else _INTACT_LIFETIME_MS)

    def maximum_lift(self, area_height: int) -> float:
        return area_height - self.pixmap.height()

    def grab(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        super().grab(point, area_height, timestamp_ms)
        self._spin = 0.0

    def land(self, impact_speed: float) -> None:
        if impact_speed <= _BREAK_IMPACT_SPEED:
            self._spin = spin_for_speed(self._angle, self._limited_speed(self.velocity[0]), self._pixel_size)
            return
        center = self.x + self.pixmap.width() / 2
        self.is_broken = True
        self._age_ms = 0
        self.x = center - self.pixmap.width() / 2

    def push(self, speed: float) -> None:
        """Sweep the egg with the cursor: its rolling speed moves toward the speed of the cursor."""
        if self.is_flying or self.is_held or self.is_broken:
            return
        target = spin_for_speed(self._angle, self._limited_speed(speed), self._pixel_size)
        self._spin += (target - self._spin) * _PUSH_BLEND

    def rect(self, area_height: int) -> QRect:
        """Return the area covered by the visible pixels of the egg."""
        body = self._animation.body
        corner = self.position(area_height)
        return QRect(corner.x() + body.x(), corner.y() + body.y(), body.width(), body.height())

    def update(self, step_ms: int, line_width: int, area_height: int) -> None:
        """Advance the egg by step_ms and keep it inside the area; a held egg does not age."""
        if self.is_flying:
            self.fly(step_ms, area_height)
        elif not self.is_held and not self.is_broken:
            self._angle, self._spin, distance = advance(self._angle, self._spin, step_ms / 1000, self._pixel_size)
            self.x += distance
        if not self.is_held:
            self._age_ms += step_ms
        self._keep_inside(line_width)

    @staticmethod
    def _limited_speed(speed: float) -> float:
        return max(-_MAXIMUM_ROLL_SPEED, min(speed, _MAXIMUM_ROLL_SPEED))

    def _keep_inside(self, line_width: int) -> None:
        highest = line_width - self.pixmap.width()
        if self.x < 0 or self.x > highest:
            moving_out = (self.x < 0) == (self._spin < 0)
            self.x = max(0.0, min(self.x, highest))
            if moving_out:
                self._spin *= -_WALL_BOUNCE

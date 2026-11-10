"""Egg laid by a pet: falls, tips over, rolls by its shape, breaks on a hard landing or when old, then evaporates unless eaten."""

import math
import random

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QPixmap

from helpers.pets.animation import load_animation
from helpers.pets.catalog import EAT_STATE, FOOD_CATEGORY, PetKind
from helpers.pets.egg_rolling import advance, spin_for_speed
from helpers.pets.food import Food


_INTACT_LIFETIME_MS = 90000
_BROKEN_LIFETIME_MS = 8000  # counted from the break; the break animation plays within it, then the puddle evaporates
_BREAK_IMPACT_SPEED = 600  # device pixels per second; about a 75 pixel fall
_MAXIMUM_ROLL_SPEED = 700  # device pixels per second
_START_TILT = 0.05  # radians; a laid egg stands on its blunt end only until this tilt grows
_WALL_BOUNCE = 0.4  # share of the spin kept after hitting the side of the area
_RESTING_SPIN = 0.2  # radians per second; an old egg bursts only when it lies about this still
_EGG_KIND = PetKind("egg", "white", frozenset(), FOOD_CATEGORY)
_ROLL, _BREAK, _EVAPORATE = "roll", "break", "evaporate"  # sprite states; the egg is intact only while rolling
_BURST_RIGHT, _BURST_LEFT = "burst_right", "burst_left"  # an old egg cracking open, by the side its pointed end lies on


class Egg(Food):
    """An egg that starts falling at the given height; it breaks when it lands too fast and rolls when it lands softly."""

    def __init__(self, center_x: float, lift: float, pixel_size: int):
        super().__init__(pixel_size)
        self._state = _ROLL
        self._angle = random.choice((-_START_TILT, _START_TILT)) % math.tau  # clockwise turn; zero is upright
        self._spin = 0.0  # radians per second, clockwise
        self._fresh_ms = 0  # time spent being eaten, which does not count toward the evaporation of the broken egg
        self.x = center_x - self.pixmap.width() / 2
        self.lift = lift
        self.is_flying = True

    @classmethod
    def is_food_for(cls, kind: PetKind) -> bool:
        return EAT_STATE in kind.states

    @property
    def _animation(self):
        return load_animation(_EGG_KIND, self._state, self._pixel_size)

    @property
    def pixmap(self) -> QPixmap:
        animation = self._animation
        if self._state != _ROLL:
            return self._without_eaten(animation.pixmap_once(self._age_ms))
        return animation.frames_right[round(self._angle / math.tau * len(animation.frames_right)) % len(animation.frames_right)]

    @property
    def can_be_held(self) -> bool:
        return self._state == _ROLL

    @property
    def is_edible(self) -> bool:
        """Whether the egg is broken, not yet evaporating and not yet eaten up."""
        return self._state not in (_ROLL, _EVAPORATE) and not self.is_eaten

    @property
    def expired(self) -> bool:
        """Whether the egg has evaporated or been eaten and should be removed."""
        return self.is_eaten or (self._state == _EVAPORATE and self._age_ms >= self._animation.cycle_ms)

    def _maximum_lift(self, area_height: int) -> float:
        return area_height - self.pixmap.height()

    def grab(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        super().grab(point, area_height, timestamp_ms)
        self._spin = 0.0

    def drag_to(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        """Carry the held egg; while it stays on the floor it rolls under the cursor instead of sliding."""
        before = self.x
        super().drag_to(point, area_height, timestamp_ms)
        if self.lift <= self._pixel_size:
            turn = spin_for_speed(self._angle, self.x - before, self._pixel_size)
            self._angle = (self._angle + turn) % math.tau

    def land(self, impact_speed: float) -> None:
        if impact_speed <= _BREAK_IMPACT_SPEED:
            self._spin = spin_for_speed(self._angle, self._limited_speed(self.velocity[0]), self._pixel_size)
            return
        self._begin(_BREAK)

    def keep_fresh(self, step_ms: int) -> None:
        """Do not count step_ms spent being eaten toward the evaporation of the broken egg."""
        self._fresh_ms += step_ms

    def update(self, step_ms: int, line_width: int, area_height: int) -> None:
        """Advance the egg by step_ms and keep it inside the area; a held egg does not age."""
        if self.is_flying:
            self.fly(step_ms, area_height)
        elif not self.is_held and self._state == _ROLL:
            self._angle, self._spin, distance = advance(self._angle, self._spin, step_ms / 1000, self._pixel_size)
            self.x += distance
        if not self.is_held:
            self._age(step_ms)
            self._advance_life()
        self._keep_inside(line_width)

    def _begin(self, state: str) -> None:
        """Switch to another sprite state around the same center."""
        center = self.x + self.pixmap.width() / 2
        self._state, self._age_ms, self._fresh_ms = state, 0, 0
        self.x = center - self.pixmap.width() / 2

    def _advance_life(self) -> None:
        """Move to the next stage once the time of the current one is over."""
        if self._state == _ROLL:
            if self._age_ms >= _INTACT_LIFETIME_MS and not self.is_flying and abs(self._spin) < _RESTING_SPIN:
                self._begin(_BURST_RIGHT if math.sin(self._angle) > 0 else _BURST_LEFT)
        elif self._state != _EVAPORATE and self._age_ms - self._fresh_ms >= _BROKEN_LIFETIME_MS:
            self._begin(_EVAPORATE)

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

"""Pet behavior: random states, stepwise walking, and being picked up and thrown."""

import random
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect

from helpers.pets.animation import load_animation
from helpers.pets.catalog import PetKind


# Body lengths covered per cycle of the walk animation: ties speed to body size and animation tempo.
_WALK_STRIDE_RATIO = 0.8
# Faster gaits reuse the walk speed; their GIFs often share one cycle, so only the pace scales.
_GAIT_SPEED_FACTOR = {"walk": 1.0, "walk_fast": 1.6, "run": 2.5}
_TURN_CHANCE = 0.4
# state: (pick weight, minimum ms, maximum ms)
_STATE_PLAN = {
    "idle": (4, 2000, 6000),
    "walk": (5, 3000, 8000),
    "walk_fast": (2, 2000, 5000),
    "run": (1, 1500, 3500),
    "swipe": (1, 1500, 3000),
    "with_ball": (2, 4000, 9000),
    "lie": (1, 6000, 14000),
    "stand": (2, 3000, 8000),
}
_SCARE_MS = (1200, 2200)
_GRAVITY = 2400  # device pixels per second squared
_MAXIMUM_THROW_SPEED = 1800  # device pixels per second
_DRAG_THRESHOLD = 4  # device pixels; a shorter press is a click
_STALE_VELOCITY_MS = 80  # a pet held still this long before release is dropped, not thrown
_VELOCITY_BLEND = 0.5  # weight of the newest mouse movement in the throw speed


@dataclass
class _Grab:
    """A pet held by the mouse."""

    offset: QPoint  # grab point inside the pet's pixmap
    start: QPoint
    last: QPoint
    _last_ms: int
    _moved: bool = False


class Pet:
    """One pet moving along the bottom of an area measured in device pixels."""

    def __init__(self, kind: PetKind, pixel_size: int, line_width: int):
        self.kind = kind
        self.pixel_size = pixel_size
        self.stepped = True
        self._lift = 0.0  # height above the line
        self._flying = False
        self._grab: _Grab | None = None
        self._velocity = [0.0, 0.0]  # right, up
        walk = self._load("walk")
        self._walk_speed = walk.body.width() * _WALK_STRIDE_RATIO * 1000 / walk.cycle_ms
        self._facing_right = random.choice((True, False))
        self.x = float(random.randint(0, max(0, line_width - walk.body.width())))
        self._choose_state()

    @property
    def pixmap(self):
        animation, elapsed_ms = self._current()
        return animation.pixmap(elapsed_ms, self._facing_right)

    def position(self, area_height: int) -> QPoint:
        """Return where the pixmap's top left corner is drawn."""
        return QPoint(round(self.x), round(area_height - self._lift - self.pixmap.height()))

    def rect(self, area_height: int) -> QRect:
        """Return the area covered by the visible pixels of the pet."""
        animation = self._current()[0]
        left, right = animation.visible_span(self._facing_right)
        corner = self.position(area_height)
        return QRect(corner.x() + left, corner.y() + animation.body.y(), right - left, animation.body.height())

    def update(self, step_ms: int, line_width: int, area_height: int) -> None:
        """Advance the pet by step_ms and keep it inside the area."""
        if self._flying:
            self._fly(step_ms, area_height)
        elif self._grab is None:
            self._walk(step_ms)
        self._keep_inside(line_width)

    def grab(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        """Pick the pet up at point."""
        self._grab = _Grab(point - self.position(area_height), point, point, timestamp_ms)
        self._flying = False
        self._velocity = [0.0, 0.0]

    def drag_to(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        """Carry the held pet to point, tracking the speed of the hand."""
        grab = self._grab
        if not grab._moved and (point - grab.start).manhattanLength() < _DRAG_THRESHOLD:
            return
        grab._moved = True
        self.x = point.x() - grab.offset.x()
        top = point.y() - grab.offset.y()
        self._lift = max(0.0, min(area_height - self.pixmap.height() - top, self._maximum_lift(area_height)))
        seconds = max(timestamp_ms - grab._last_ms, 1) / 1000
        newest = ((point.x() - grab.last.x()) / seconds, (grab.last.y() - point.y()) / seconds)
        self._velocity = [
            (1 - _VELOCITY_BLEND) * old + _VELOCITY_BLEND * new for old, new in zip(self._velocity, newest)
        ]
        grab.last, grab._last_ms = point, timestamp_ms

    def release(self, timestamp_ms: int) -> None:
        """Let go: a click scares the pet, a drag throws it."""
        grab, self._grab = self._grab, None
        if not grab._moved:
            self._scare()
            return
        if timestamp_ms - grab._last_ms > _STALE_VELOCITY_MS:
            self._velocity = [0.0, 0.0]
        self._velocity = [max(-_MAXIMUM_THROW_SPEED, min(speed, _MAXIMUM_THROW_SPEED)) for speed in self._velocity]
        self._flying = True

    def _load(self, state: str):
        return load_animation(self.kind, state, self.pixel_size)

    def _current(self):
        """Return the animation on screen and its clock; a held or flying pet is frozen on its first idle frame."""
        if self._flying or self._grab is not None:
            return self._load("idle"), 0
        return self._animation, self._state_elapsed_ms

    def _maximum_lift(self, area_height: int) -> float:
        animation = self._current()[0]
        return area_height - animation.frames_right[0].height() + animation.body.y()

    def _start_state(self, state: str, duration_ms: int) -> None:
        self._state = state
        self._state_limit_ms = duration_ms
        self._state_elapsed_ms = 0
        self._animation = self._load(state)

    def _choose_state(self) -> None:
        states = sorted(self.kind.states)
        state = random.choices(states, [_STATE_PLAN[state][0] for state in states])[0]
        self._start_state(state, random.randint(*_STATE_PLAN[state][1:]))
        if state in _GAIT_SPEED_FACTOR and random.random() < _TURN_CHANCE:
            self._facing_right = not self._facing_right

    def _scare(self) -> None:
        """Run around in panic for a moment."""
        self._facing_right = random.choice((True, False))
        self._start_state("run", random.randint(*_SCARE_MS))

    def _walk(self, step_ms: int) -> None:
        before_ms = self._state_elapsed_ms
        self._state_elapsed_ms += step_ms
        gait_factor = _GAIT_SPEED_FACTOR.get(self._state)
        if gait_factor:
            moved_ms = self._ground_ms(self._state_elapsed_ms) - self._ground_ms(before_ms)
            direction = 1 if self._facing_right else -1
            self.x += direction * self._walk_speed * gait_factor * moved_ms / 1000
        if self._state_elapsed_ms >= self._state_limit_ms:
            self._choose_state()

    def _ground_ms(self, elapsed_ms: int) -> float:
        """Return the time the feet have worked: even, or bunched into steps."""
        return self._animation.stepped_ms(elapsed_ms) if self.stepped else elapsed_ms

    def _fly(self, step_ms: int, area_height: int) -> None:
        seconds = step_ms / 1000
        self._velocity[1] -= _GRAVITY * seconds
        self._lift += self._velocity[1] * seconds
        self.x += self._velocity[0] * seconds
        ceiling = self._maximum_lift(area_height)
        if self._lift > ceiling:
            self._lift, self._velocity[1] = ceiling, 0.0
        elif self._lift <= 0:
            self._lift, self._flying = 0.0, False
            self._scare()

    def _keep_inside(self, line_width: int) -> None:
        span_left, span_right = self._current()[0].visible_span(self._facing_right)
        lowest = -span_left
        highest = max(lowest, line_width - span_right)
        if self.x < lowest:
            self._facing_right = True
            self.x = -self._current()[0].visible_span(True)[0]
        elif self.x > highest:
            self._facing_right = False
            self.x = line_width - self._current()[0].visible_span(False)[1]

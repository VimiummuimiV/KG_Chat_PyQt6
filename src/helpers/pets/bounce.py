"""A flying pet bounces off the mouse cursor, and the bounces are counted until the pet has been on the floor for a while."""

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect


_CURSOR_RADIUS = 8  # device pixels; how near to the body of a pet the cursor counts as touching it
_RESTITUTION = 0.9  # share of the approach speed a bounce gives back
_MINIMUM_RISE_SPEED = 1100  # device pixels per second; about 250 pixels of height and 0.9 s in the air, time enough for the next hit
_MAXIMUM_BOUNCE_SPEED = 2200  # device pixels per second
_BADGE_LINGER_MS = 2500  # the counter stays this long after the pet has landed
_BADGE_LIMIT = 99


@dataclass(frozen=True)
class CursorMotion:
    """The cursor over one tick, in device pixels of the line, with its speed to the right and upwards."""

    previous: QPoint
    current: QPoint
    velocity: tuple[float, float]

    @property
    def distance(self) -> float:
        """Return how far the cursor moved during the tick."""
        delta = self.current - self.previous
        return math.hypot(delta.x(), delta.y())

    def at(self, fraction: float) -> QPoint:
        """Return where the cursor was the given share of the tick after it started."""
        delta = self.current - self.previous
        return QPoint(round(self.previous.x() + delta.x() * fraction), round(self.previous.y() + delta.y() * fraction))


def _is_touching(body: QRect, point: QPoint) -> bool:
    nearest_x = min(max(point.x(), body.left()), body.right())
    nearest_y = min(max(point.y(), body.top()), body.bottom())
    return math.hypot(point.x() - nearest_x, point.y() - nearest_y) <= _CURSOR_RADIUS


class BounceBehavior:
    """Flying while the cursor is an obstacle: a hit sends the pet away and adds to the counter shown beside it."""

    def _init_bounce(self) -> None:
        self.bounces = 0
        self._badge_ms = 0  # time left of the counter once the pet is down
        self._is_cursor_ignored = False  # the cursor that threw or just hit the pet is still on it and cannot hit it again

    @property
    def badge_text(self) -> str:
        """Return the counter to show beside the pet, empty when there is none."""
        if not self.bounces:
            return ""
        return f"{_BADGE_LIMIT}+" if self.bounces > _BADGE_LIMIT else str(self.bounces)

    def release(self, timestamp_ms: int) -> None:
        super().release(timestamp_ms)
        self._is_cursor_ignored = True

    def land(self, impact_speed: float) -> None:
        super().land(impact_speed)
        self._badge_ms = _BADGE_LINGER_MS

    def age_badge(self, step_ms: int) -> None:
        """Let the counter run out while the pet stands on the floor."""
        if not self.bounces or self.is_flying or self.is_held:
            return
        self._badge_ms -= step_ms
        if self._badge_ms <= 0:
            self.bounces = 0

    def fly_past_cursor(self, step_ms: int, area_height: int, cursor: CursorMotion | None) -> None:
        """Fly for step_ms in slices short enough that neither the pet nor the cursor can pass through the other between two checks."""
        if cursor is None:
            self.fly(step_ms, area_height)
            return
        reach = math.hypot(*self.velocity) * step_ms / 1000 + cursor.distance
        slices = max(1, math.ceil(reach / _CURSOR_RADIUS))
        for index in range(1, slices + 1):
            self.fly(step_ms / slices, area_height)
            if not self.is_flying:
                return
            self._bounce_off(cursor.at(index / slices), cursor.velocity, area_height)

    def _bounce_off(self, point: QPoint, cursor_velocity: tuple[float, float], area_height: int) -> None:
        """Bounce off the cursor at point when it is touched and approached; the cursor's own speed adds to the push."""
        body = self.rect(area_height)
        if not _is_touching(body, point):
            self._is_cursor_ignored = False
            return
        if self._is_cursor_ignored:
            return
        offset_right = body.center().x() - point.x()
        offset_up = point.y() - body.center().y()
        length = math.hypot(offset_right, offset_up)
        normal = (offset_right / length, offset_up / length) if length else (0.0, 1.0)
        relative = (self.velocity[0] - cursor_velocity[0], self.velocity[1] - cursor_velocity[1])
        approach = relative[0] * normal[0] + relative[1] * normal[1]
        if approach >= 0:
            return
        push = (1 + _RESTITUTION) * approach
        right = relative[0] - push * normal[0] + cursor_velocity[0]
        up = relative[1] - push * normal[1] + cursor_velocity[1]
        if normal[1] >= 0:
            up = max(up, _MINIMUM_RISE_SPEED)  # a hit from below or aside always lifts the pet clear
        speed = math.hypot(right, up)
        scale = min(1.0, _MAXIMUM_BOUNCE_SPEED / speed)
        self.velocity = [right * scale, up * scale]
        self.bounces += 1
        self._is_cursor_ignored = True  # one hit counts once, until the pet has got clear of the cursor

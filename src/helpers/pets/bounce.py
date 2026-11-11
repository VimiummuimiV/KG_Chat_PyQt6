"""A flying pet bounces off the mouse cursor, and the bounces are counted until the pet has been on the floor for a while."""

import math
from dataclasses import dataclass
from typing import Iterable

from PyQt6.QtCore import QPoint, QRect, QSize

from helpers.pets.animation import load_animation


_BOARD_WIDTH_RATIO = 1.25  # the board is this much wider than the widest pet
_BOARD_ROWS = 2  # thickness of the board in cells
_MAXIMUM_TILT = 0.6  # sideways share of the push when a pet is hit at the very end of the board
_RESTITUTION = 0.9  # share of the approach speed a bounce gives back
_MINIMUM_RISE_SPEED = 1100  # device pixels per second; about 250 pixels of height and 0.9 s in the air, time enough for the next hit
_MAXIMUM_BOUNCE_SPEED = 2200  # device pixels per second
_BADGE_LINGER_MS = 2500  # the counter stays this long after the pet has landed
_BADGE_LIMIT = 99


@dataclass(frozen=True)
class CollisionBoard:
    """The pixel board carried by the cursor: what pets bounce off and what is drawn there, the same for every pet."""

    size: QSize
    cell: int  # device pixels of one pixel of the board

    @classmethod
    def for_pets(cls, pets: Iterable) -> "CollisionBoard":
        """Return the board that fits the widest of the pets, in cells as big as the biggest pet pixel."""
        sizes = {(pet.kind, pet.pixel_size) for pet in pets}
        cell = max((pixel_size for _, pixel_size in sizes), default=1)
        widest = max((load_animation(kind, "idle", pixel_size).body.width() for kind, pixel_size in sizes), default=0)
        columns = math.ceil(widest * _BOARD_WIDTH_RATIO / cell)
        return cls(QSize(columns * cell, _BOARD_ROWS * cell), cell)

    def at(self, point: QPoint) -> QRect:
        """Return the board centered on point, on the grid of its cells."""
        left = round((point.x() - self.size.width() / 2) / self.cell) * self.cell
        top = round((point.y() - self.size.height() / 2) / self.cell) * self.cell
        return QRect(QPoint(left, top), self.size)


@dataclass(frozen=True)
class CursorMotion:
    """The cursor board over one tick, in device pixels of the line, with the cursor speed to the right and upwards."""

    board: CollisionBoard
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


class BounceBehavior:
    """Flying while the board at the cursor is an obstacle: a hit sends the pet away and adds to the counter shown beside it."""

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
        slices = max(1, math.ceil(reach / cursor.board.size.height()))
        for index in range(1, slices + 1):
            self.fly(step_ms / slices, area_height)
            if not self.is_flying:
                return
            self._bounce_off(cursor.board.at(cursor.at(index / slices)), cursor.velocity, area_height)

    def _bounce_off(self, board: QRect, cursor_velocity: tuple[float, float], area_height: int) -> None:
        """Bounce off the board when it is touched and approached; the push is up from above the board and down from below it, tilted by where the pet is hit, and the board's own speed adds to it."""
        body = self.rect(area_height)
        if not body.intersects(board):
            self._is_cursor_ignored = False
            return
        if self._is_cursor_ignored:
            return
        tilt = (body.center().x() - board.center().x()) / ((board.width() + body.width()) / 2)
        tilt = max(-1.0, min(1.0, tilt)) * _MAXIMUM_TILT
        side = 1.0 if body.center().y() <= board.center().y() else -1.0
        length = math.hypot(tilt, side)
        normal = (tilt / length, side / length)
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

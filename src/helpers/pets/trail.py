"""A trail of pixel sparks that streams off a flying pet and burns out behind it."""

import math
import random
from dataclasses import dataclass

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor

from helpers.pets.throwable import GRAVITY


_MILLISECONDS = 1000
_MINIMUM_SPEED = 300  # device pixels per second; a slower pet leaves nothing
_SPACING_ART_PIXELS = 3  # the pet flies this far between two sparks
_MAXIMUM_SPARKS_PER_STEP = 64
_LIFE_RANGE_MS = (450, 900)
_KEPT_SPEED_SHARE = 0.25  # of the velocity of the pet that a spark keeps when it leaves
_SIDE_SPREAD_SHARE = 0.18  # of the speed of the pet: the most a spark is thrown sideways
_ALONG_SPREAD_SHARE = 0.12  # the same along the flight, which makes the streaks ragged
_DRAG = 3.5  # per second: the sparks slow down
_FALL = GRAVITY * 0.15  # sparks sag slower than the pets fall
_SIZE_RANGE = (1, 2)  # art pixels
_SHRINK_AT = 0.5  # share of its life after which a spark loses a pixel
_COLORS = tuple(QColor(code) for code in ("#eee3c2", "#d9c79e", "#c5ad8f", "#aa8f83", "#8d7b83"))  # young to old


@dataclass
class _Spark:
    """One spark: where it was born, how it drifts, and how long it has burned."""

    x: float
    lift: float
    velocity: tuple[float, float]  # right, up
    life_ms: float
    age_ms: float
    size: int  # art pixels


class Trail:
    """The sparks of one pet: born along its flight, then slowing, sagging and shrinking until they burn out."""

    def __init__(self, pixel_size: int):
        self.revision = 0  # grows with every change, so the area can tell whether it must repaint
        self._pixel_size = pixel_size
        self._sparks: list[_Spark] = []
        self._last_source: tuple[float, float] | None = None
        self._carry = 0.0  # flight distance since the last spark

    @property
    def is_active(self) -> bool:
        """Whether any spark is still burning."""
        return bool(self._sparks)

    def age(self, step_ms: int) -> None:
        """Let every spark burn for step_ms and drop the ones that are out."""
        if not self._sparks:
            return
        for spark in self._sparks:
            spark.age_ms += step_ms
        self._sparks = [spark for spark in self._sparks if spark.age_ms < spark.life_ms]
        self.revision += 1

    def emit(self, source: tuple[float, float] | None, velocity: list[float], step_ms: int) -> None:
        """Leave sparks along the way the source (x, lift) went since the last call; None when the pet is not flying."""
        speed = math.hypot(*velocity)
        if source is None or speed < _MINIMUM_SPEED:
            self._last_source, self._carry = None, 0.0
            return
        previous, self._last_source = self._last_source or source, source
        distance = math.dist(previous, source)
        spacing = _SPACING_ART_PIXELS * self._pixel_size
        first = spacing - self._carry  # distance along this step to the first spark
        count = min(int((self._carry + distance) // spacing), _MAXIMUM_SPARKS_PER_STEP)
        self._carry = (self._carry + distance) % spacing
        if not count:
            return
        direction = (velocity[0] / speed, velocity[1] / speed)
        for index in range(count):
            fraction = min(1.0, (first + index * spacing) / distance)
            self._sparks.append(self._spark(
                previous[0] + (source[0] - previous[0]) * fraction,
                previous[1] + (source[1] - previous[1]) * fraction,
                velocity, direction, speed, (1 - fraction) * step_ms,
            ))
        self.revision += 1

    def cells(self, area_height: int) -> list[tuple[QRect, QColor]]:
        """Return the squares to draw, in device pixels on the grid of the art pixels, with their colors."""
        pixel = self._pixel_size
        cells = []
        for spark in self._sparks:
            seconds = spark.age_ms / _MILLISECONDS
            slowing = (1 - math.exp(-_DRAG * seconds)) / _DRAG
            x = spark.x + spark.velocity[0] * slowing
            lift = spark.lift + spark.velocity[1] * slowing - _FALL * seconds * seconds / 2
            life = spark.age_ms / spark.life_ms
            size = spark.size if life < _SHRINK_AT else max(1, spark.size - 1)
            left, top = math.floor(x / pixel) * pixel, math.floor((area_height - lift) / pixel) * pixel
            cells.append((QRect(left, top, size * pixel, size * pixel), _COLORS[int(life * len(_COLORS))]))
        return cells

    @staticmethod
    def _spark(
        x: float, lift: float, velocity: list[float], direction: tuple[float, float], speed: float, age_ms: float
    ) -> _Spark:
        """Return a spark thrown off the pet: it keeps a share of the flight and scatters around it."""
        sideways = random.uniform(-1, 1) * _SIDE_SPREAD_SHARE * speed
        along = random.uniform(-1, 1) * _ALONG_SPREAD_SHARE * speed
        spark_velocity = (
            velocity[0] * _KEPT_SPEED_SHARE - direction[1] * sideways + direction[0] * along,
            velocity[1] * _KEPT_SPEED_SHARE + direction[0] * sideways + direction[1] * along,
        )
        return _Spark(x, lift, spark_velocity, random.uniform(*_LIFE_RANGE_MS), age_ms, random.randint(*_SIZE_RANGE))

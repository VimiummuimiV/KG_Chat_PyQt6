"""Food on the pet line: eaten bite by bite from its ends and claimed by the pet that reaches it first."""

from abc import abstractmethod

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QPainter, QPixmap

from helpers.pets.catalog import PetKind
from helpers.pets.throwable import Throwable


BITES_PER_FOOD = 4  # each bite takes an equal part of the width
_CLAIM_MS = 300  # the pet that started eating keeps the food only while it renews the claim


class Food(Throwable):
    """A body that pets of some kinds eat from either end."""

    def __init__(self, pixel_size: int):
        super().__init__()
        self._pixel_size = pixel_size
        self._age_ms = 0
        self._bites = [0, 0]  # taken from the left end and from the right end
        self._eater = None
        self._claim_ms = 0

    @classmethod
    @abstractmethod
    def is_food_for(cls, kind: PetKind) -> bool:
        """Whether pets of this kind eat this food."""

    @property
    @abstractmethod
    def _animation(self):
        """The sprite state drawn now."""

    @property
    @abstractmethod
    def is_edible(self) -> bool:
        """Whether pets may eat it now."""

    @property
    def is_eaten(self) -> bool:
        """Whether every bite has been taken."""
        return sum(self._bites) >= BITES_PER_FOOD

    def is_free_for(self, pet: object) -> bool:
        """Whether pet may eat the food: nobody else has started on it."""
        return self._claim_ms <= 0 or self._eater is pet

    def claim(self, pet: object) -> bool:
        """Start eating the food or renew the claim; False when another pet got there first."""
        if not self.is_free_for(pet):
            return False
        self._eater, self._claim_ms = pet, _CLAIM_MS
        return True

    def keep_fresh(self, step_ms: int) -> None:
        """Do not count step_ms spent being eaten toward the decay of the food, if it decays."""

    def bite(self, from_left: bool) -> None:
        """Take one bite off the left or the right end."""
        self._bites[0 if from_left else 1] += 1

    def remaining_span(self) -> tuple[int, int]:
        """Return the horizontal [left, right) range of the uneaten food on the line."""
        eaten_left, eaten_right = self._eaten_widths()
        body = self._animation.body
        start = round(self.x) + body.x()
        return start + eaten_left, start + body.width() - eaten_right

    def rect(self, area_height: int) -> QRect:
        """Return the area covered by the visible pixels of the food."""
        body = self._animation.body
        corner = self.position(area_height)
        return QRect(corner.x() + body.x(), corner.y() + body.y(), body.width(), body.height())

    def _age(self, step_ms: int) -> None:
        self._age_ms += step_ms
        self._claim_ms -= step_ms

    def _eaten_widths(self) -> tuple[int, int]:
        """Return how many pixels are eaten from the left end and from the right end."""
        columns = self._animation.body.width() // self._pixel_size
        left, right = (columns * bites // BITES_PER_FOOD * self._pixel_size for bites in self._bites)
        return left, right

    def _without_eaten(self, frame: QPixmap) -> QPixmap:
        """Return the frame with the eaten ends made transparent."""
        eaten_left, eaten_right = self._eaten_widths()
        if not (eaten_left or eaten_right):
            return frame
        body = self._animation.body
        pixmap = frame.copy()
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(0, 0, body.x() + eaten_left, pixmap.height(), Qt.GlobalColor.transparent)
        painter.fillRect(body.x() + body.width() - eaten_right, 0, eaten_right, pixmap.height(), Qt.GlobalColor.transparent)
        painter.end()
        return pixmap

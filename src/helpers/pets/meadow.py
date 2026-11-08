"""The grass of the pet line: it grows only while a pet that grazes is there to eat it."""

import random
from typing import Iterable

from helpers.pets.egg import Egg
from helpers.pets.grass import Grass
from helpers.pets.pet import Pet


_GROW_INTERVAL_MS = (10000, 25000)  # between two tufts for one grazing pet; more pets make it shorter
_TUFTS_PER_GRAZER = 2
_GAP_ART_PIXELS = 2  # free space kept between a new tuft and the eggs and tufts beside it
_PLANTING_TRIES = 10


class Meadow:
    """Owner of the grass tufts: grows them, removes the eaten ones and keeps them off the eggs."""

    def __init__(self):
        self.grass: list[Grass] = []
        self._countdown_ms = random.randint(*_GROW_INTERVAL_MS)

    def update(self, step_ms: int, pets: Iterable[Pet], eggs: Iterable[Egg], line_width: int, area_height: int) -> None:
        """Age the tufts and, while some pet grazes, grow a new one when its time has come."""
        grazers = [pet for pet in pets if Grass.is_food_for(pet.kind)]
        if not grazers:
            self.grass.clear()
            return
        for tuft in self.grass:
            tuft.update(step_ms)
        self.grass = [tuft for tuft in self.grass if not tuft.expired]
        if len(self.grass) >= _TUFTS_PER_GRAZER * len(grazers):
            return
        self._countdown_ms -= step_ms * len(grazers)
        if self._countdown_ms <= 0:
            self._countdown_ms = random.randint(*_GROW_INTERVAL_MS)
            self._plant(grazers[0].pixel_size, eggs, line_width, area_height)

    def _plant(self, pixel_size: int, eggs: Iterable[Egg], line_width: int, area_height: int) -> None:
        """Grow a tuft at a random place that does not touch an egg or another tuft; skip when there is none."""
        tuft = Grass(0.0, pixel_size)
        body = tuft.rect(area_height)
        gap = _GAP_ART_PIXELS * pixel_size
        busy = [other.rect(area_height).adjusted(-gap, 0, gap, 0) for other in (*eggs, *self.grass)]
        for _ in range(_PLANTING_TRIES):
            tuft.x = random.uniform(-body.x(), line_width - body.right() - 1)
            if not any(tuft.rect(area_height).intersects(area) for area in busy):
                self.grass.append(tuft)
                return

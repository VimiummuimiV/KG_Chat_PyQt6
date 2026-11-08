"""Grass tuft that grows on the line and is grazed by hens."""

from helpers.pets.animation import load_animation
from helpers.pets.catalog import PetKind
from helpers.pets.food import Food


_GRASS_KIND = PetKind("grass", "green", frozenset())
_GROW_STATE = "grow"  # played once; the tuft can be eaten when it is over
_GRAZING_SPECIES = frozenset({"chicken"})


class Grass(Food):
    """A tuft standing on the line at x."""

    def __init__(self, x: float, pixel_size: int):
        super().__init__(pixel_size)
        self.x = x

    @classmethod
    def is_food_for(cls, kind: PetKind) -> bool:
        return kind.species in _GRAZING_SPECIES

    @property
    def _animation(self):
        return load_animation(_GRASS_KIND, _GROW_STATE, self._pixel_size)

    @property
    def pixmap(self):
        return self._without_eaten(self._animation.pixmap_once(self._age_ms))

    @property
    def can_be_held(self) -> bool:
        return False

    @property
    def is_edible(self) -> bool:
        return self._age_ms >= self._animation.cycle_ms and not self.is_eaten

    @property
    def expired(self) -> bool:
        """Whether the tuft has been eaten up and should be removed."""
        return self.is_eaten

    def maximum_lift(self, area_height: int) -> float:
        return area_height - self.pixmap.height()

    def update(self, step_ms: int) -> None:
        """Let the tuft grow and age its claim."""
        self._age(step_ms)

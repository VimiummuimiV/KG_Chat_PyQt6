"""Pet catalog: finds the bundled pet sprites and reads the pet options."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from helpers.data import get_resource_dir


MAXIMUM_PET_COUNT = 10
MAXIMUM_SIZE_MULTIPLIER = 10
DEFAULT_SIZE_MULTIPLIER = 2
PREDATOR_VISIT_SECONDS = (45, 5, 1800)  # default, minimum and maximum of the seconds between the visits of a predator
_VISIT_SPREAD = 0.3  # a visit every n seconds means every n -30% to n +30% seconds
_MILLISECONDS = 1000
EAT_STATE = "eat"
RUN_STATE = "run"
WALK_STATE = "walk"
BARK_STATE = "bark"
LIE_STATE = "lie"
PETS_CATEGORY = "pets"  # folders of the animals that roam the line
FOOD_CATEGORY = "food"  # folders of what they eat: not pets
_RESOURCE_FOLDER = "ecosystem"
_ANIMATIONS_FOLDER = "animations"
_ICONS_FOLDER = "icons"
_SPRITE_SUFFIX = "_8fps.gif"
# Longest names first so "walk_fast" is not read as "walk".
_STATE_NAMES = ("walk_fast", "with_ball", "walk", "run", "idle", "swipe", "lie", "stand", "bark", EAT_STATE)
_PIXEL_GRID_FILE = "pixel_grid.json"


@dataclass(frozen=True)
class PixelGrid:
    """Size of one original art pixel inside the upscaled GIF, and the screen pixels per art pixel at x1."""

    scale: tuple[float, float]
    base: int


@dataclass(frozen=True)
class PetKind:
    """One pet species in one color."""

    species: str
    color: str
    states: frozenset[str]
    category: str = PETS_CATEGORY

    @property
    def key(self) -> str:
        return f"{self.species}/{self.color}"

    @property
    def title(self) -> str:
        return f"{self.species} · {self.color}".replace("_", " ").title()

    @property
    def _folder(self) -> Path:
        return _category_folder(self.category) / self.species

    @property
    def icon_path(self) -> Path:
        return self._folder / _ICONS_FOLDER / f"icon_{self.color}.png"

    @property
    def pixel_grid(self) -> PixelGrid:
        grids = _load_pixel_grids()
        return grids.get(self.key) or grids[self.species]

    def sprite_path(self, state: str) -> Path:
        return self._folder / _ANIMATIONS_FOLDER / f"{self.color}_{state}{_SPRITE_SUFFIX}"


def _category_folder(category: str) -> Path:
    return get_resource_dir(_RESOURCE_FOLDER) / category


@lru_cache(maxsize=None)
def _load_pixel_grids() -> dict[str, PixelGrid]:
    path = get_resource_dir(_RESOURCE_FOLDER) / _PIXEL_GRID_FILE
    with open(path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    grids = {}
    for key, entry in raw.items():
        scale = entry["scale"]
        scale_x, scale_y = scale if isinstance(scale, list) else (scale, scale)
        grids[key] = PixelGrid((scale_x, scale_y), entry["base"])
    return grids


@lru_cache(maxsize=None)
def list_pet_kinds() -> tuple[PetKind, ...]:
    """Return every bundled pet species/color pair, sorted by key."""
    kinds = []
    for folder in sorted(_category_folder(PETS_CATEGORY).iterdir()):
        if not folder.is_dir():
            continue
        states_by_color: dict[str, set[str]] = {}
        for sprite in (folder / _ANIMATIONS_FOLDER).glob(f"*{_SPRITE_SUFFIX}"):
            stem = sprite.name[: -len(_SPRITE_SUFFIX)]
            state = next((name for name in _STATE_NAMES if stem.endswith(f"_{name}")), None)
            if state:
                states_by_color.setdefault(stem[: -len(state) - 1], set()).add(state)
        kinds.extend(PetKind(folder.name, color, frozenset(states)) for color, states in states_by_color.items())
    return tuple(sorted(kinds, key=lambda kind: kind.key))


def get_pet_kind(key: str) -> PetKind | None:
    """Return the pet kind for a "species/color" key, or None when it is not bundled."""
    return next((kind for kind in list_pet_kinds() if kind.key == key), None)


def pets_enabled(config) -> bool:
    """Return True when the master pets switch is on."""
    return bool(config.get("ui", "pets", "enabled"))


def pet_counts(config) -> dict[str, int]:
    """Return how many pets of each kind the user wants, keyed by "species/color"."""
    return dict(config.get("ui", "pets", "counts") or {})


def pets_stepped(config) -> bool:
    """Return True when pets move in steps tied to their animation instead of at a constant pace."""
    stepped = config.get("ui", "pets", "stepped")
    return True if stepped is None else bool(stepped)


def predator_visit_seconds(config) -> int:
    """Return the seconds a predator stays away between its visits, kept inside the limits of the settings page."""
    default, minimum, maximum = PREDATOR_VISIT_SECONDS
    seconds = config.get("ui", "pets", "predator_visit")
    is_number = isinstance(seconds, (int, float)) and not isinstance(seconds, bool)
    return max(minimum, min(maximum, round(seconds))) if is_number else default


def predator_visit_ms(config) -> tuple[int, int]:
    """Return the shortest and the longest time a predator stays away between its visits."""
    seconds = predator_visit_seconds(config) * _MILLISECONDS
    return round(seconds * (1 - _VISIT_SPREAD)), round(seconds * (1 + _VISIT_SPREAD))


def pet_size_multiplier(config, species: str) -> int:
    """Return the size the user chose for a species: how many times its base size."""
    multiplier = (config.get("ui", "pets", "sizes") or {}).get(species, DEFAULT_SIZE_MULTIPLIER)
    return max(1, min(int(multiplier), MAXIMUM_SIZE_MULTIPLIER))


def pet_pixel_size(config, kind: PetKind) -> int:
    """Return the screen pixels one art pixel of this pet is drawn with."""
    return kind.pixel_grid.base * pet_size_multiplier(config, kind.species)

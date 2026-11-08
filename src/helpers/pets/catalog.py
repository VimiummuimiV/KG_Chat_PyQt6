"""Pet catalog: finds the bundled pet sprites and reads the pet options."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from helpers.data import get_resource_dir


MAXIMUM_PET_COUNT = 10
MAXIMUM_SIZE_MULTIPLIER = 10
DEFAULT_SIZE_MULTIPLIER = 2
_DEFAULT_PET_COUNTS = {"dog/akita": 1}
_SPRITE_SUFFIX = "_8fps.gif"
# Longest names first so "walk_fast" is not read as "walk".
_STATE_NAMES = ("walk_fast", "with_ball", "walk", "run", "idle", "swipe", "lie", "stand", "eat")
_ICON_NAME_PATTERNS = ("icon_{color}.png", "{color}_icon.png", "icon.png")
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

    @property
    def key(self) -> str:
        return f"{self.species}/{self.color}"

    @property
    def title(self) -> str:
        return f"{self.species} · {self.color}".replace("_", " ").title()

    @property
    def _folder(self) -> Path:
        return get_resource_dir("pets") / self.species

    @property
    def icon_path(self) -> Path:
        candidates = (self._folder / pattern.format(color=self.color) for pattern in _ICON_NAME_PATTERNS)
        return next(path for path in candidates if path.exists())

    @property
    def pixel_grid(self) -> PixelGrid:
        grids = _load_pixel_grids()
        return grids.get(self.key) or grids[self.species]

    def sprite_path(self, state: str) -> Path:
        return self._folder / f"{self.color}_{state}{_SPRITE_SUFFIX}"


@lru_cache(maxsize=None)
def _load_pixel_grids() -> dict[str, PixelGrid]:
    path = get_resource_dir("pets") / _PIXEL_GRID_FILE
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
    for folder in sorted(get_resource_dir("pets").iterdir()):
        if not folder.is_dir():
            continue
        states_by_color: dict[str, set[str]] = {}
        for sprite in folder.glob(f"*{_SPRITE_SUFFIX}"):
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
    counts = config.get("ui", "pets", "counts")
    return dict(_DEFAULT_PET_COUNTS if counts is None else counts)


def pets_stepped(config) -> bool:
    """Return True when pets move in steps tied to their animation instead of at a constant pace."""
    stepped = config.get("ui", "pets", "stepped")
    return True if stepped is None else bool(stepped)


def pet_size_multiplier(config, species: str) -> int:
    """Return the size the user chose for a species: how many times its base size."""
    multiplier = (config.get("ui", "pets", "sizes") or {}).get(species, DEFAULT_SIZE_MULTIPLIER)
    return max(1, min(int(multiplier), MAXIMUM_SIZE_MULTIPLIER))


def pet_pixel_size(config, kind: PetKind) -> int:
    """Return the screen pixels one art pixel of this pet is drawn with."""
    return kind.pixel_grid.base * pet_size_multiplier(config, kind.species)

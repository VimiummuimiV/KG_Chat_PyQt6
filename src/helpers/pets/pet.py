"""Pet behavior: random states, stepwise walking, laying and eating eggs, and being picked up and thrown."""

import random
from dataclasses import dataclass
from typing import Iterable

from PyQt6.QtCore import QRect

from helpers.pets.animation import load_animation
from helpers.pets.catalog import PetKind
from helpers.pets.egg import Egg
from helpers.pets.throwable import Throwable


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
_LAYING_SPECIES = frozenset({"chicken"})
_EGG_INTERVAL_MS = (20000, 50000)  # walking time between two eggs
_EGG_DROP_ART_PIXELS = 4  # height the egg leaves the pet from, in art pixels
_NOSE_OVER_EGG_ART_PIXELS = 1  # how far the nose of an eating pet reaches into the edge of the egg
_CHASE_STATE = "run"
_EAT_STATE = "eat"


@dataclass
class _Meal:
    """A broken egg a pet is running to or eating."""

    egg: Egg
    from_left: bool  # the pet stands at the left end of the egg and faces right
    is_eating: bool = False
    bites: int = 0


class Pet(Throwable):
    """One pet moving along the bottom of an area measured in device pixels."""

    def __init__(self, kind: PetKind, pixel_size: int, line_width: int):
        super().__init__()
        self.kind = kind
        self.pixel_size = pixel_size
        self.stepped = True
        self._lays_eggs = kind.species in _LAYING_SPECIES
        self._egg_countdown_ms = random.randint(*_EGG_INTERVAL_MS)
        self._egg_due = False
        self._eats_eggs = _EAT_STATE in kind.states
        self._meal: _Meal | None = None
        self._is_scared = False
        walk = self._load("walk")
        self._walk_speed = walk.body.width() * _WALK_STRIDE_RATIO * 1000 / walk.cycle_ms
        self._facing_right = random.choice((True, False))
        self.x = float(random.randint(0, max(0, line_width - walk.body.width())))
        self._choose_state()

    @property
    def pixmap(self):
        animation, elapsed_ms = self._current()
        return animation.pixmap(elapsed_ms, self._facing_right)

    def rect(self, area_height: int) -> QRect:
        """Return the area covered by the visible pixels of the pet."""
        animation = self._current()[0]
        left, right = animation.visible_span(self._facing_right)
        corner = self.position(area_height)
        return QRect(corner.x() + left, corner.y() + animation.body.y(), right - left, animation.body.height())

    def update(self, step_ms: int, line_width: int, area_height: int) -> None:
        """Advance the pet by step_ms and keep it inside the area."""
        if self.is_flying:
            self.fly(step_ms, area_height)
        elif not self.is_held:
            self._walk(step_ms)
        self._keep_inside(line_width)

    def take_egg(self) -> Egg | None:
        """Return the egg the pet has just laid at its tail, if any."""
        if not self._egg_due:
            return None
        self._egg_due = False
        left, right = self._animation.visible_span(self._facing_right)
        tail = self.x + (left if self._facing_right else right)
        return Egg(tail, _EGG_DROP_ART_PIXELS * self.pixel_size, self.pixel_size)

    def look_for_food(self, eggs: Iterable[Egg]) -> None:
        """Run to the nearest broken egg nobody has started eating; every pet that eats eggs joins the race."""
        if not self._eats_eggs or self._is_scared or self.is_held or self.is_flying:
            return
        if self._meal and self._meal.is_eating:
            return
        free = (egg for egg in eggs if egg.is_edible and egg.is_free_for(self))
        nearest = min(free, key=lambda egg: self._approach(egg)[0], default=None)
        if nearest is None or (self._meal and self._meal.egg is nearest):
            return
        self._meal = _Meal(nearest, self._approach(nearest)[1])
        self._facing_right = self._meal.from_left
        self._start_state(_CHASE_STATE, 0)

    def click(self) -> None:
        self._scare()

    def land(self, impact_speed: float) -> None:
        self._scare()

    def maximum_lift(self, area_height: int) -> float:
        animation = self._current()[0]
        return area_height - animation.frames_right[0].height() + animation.body.y()

    def _load(self, state: str):
        return load_animation(self.kind, state, self.pixel_size)

    def _current(self):
        """Return the animation on screen and its clock; a held or flying pet is frozen on its first idle frame."""
        if self.is_flying or self.is_held:
            return self._load("idle"), 0
        return self._animation, self._state_elapsed_ms

    def _start_state(self, state: str, duration_ms: int) -> None:
        self._state = state
        self._state_limit_ms = duration_ms
        self._state_elapsed_ms = 0
        self._animation = self._load(state)

    def _choose_state(self) -> None:
        self._is_scared = False
        states = [state for state in sorted(self.kind.states) if state in _STATE_PLAN]
        state = random.choices(states, [_STATE_PLAN[state][0] for state in states])[0]
        self._start_state(state, random.randint(*_STATE_PLAN[state][1:]))
        if state in _GAIT_SPEED_FACTOR and random.random() < _TURN_CHANCE:
            self._facing_right = not self._facing_right

    def _scare(self) -> None:
        """Run around in panic for a moment, forgetting any egg."""
        self._meal = None
        self._is_scared = True
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
            if self._lays_eggs:
                self._count_down_egg(step_ms)
        if self._meal:
            self._follow_meal(step_ms)
        elif self._state_elapsed_ms >= self._state_limit_ms:
            self._choose_state()

    def _follow_meal(self, step_ms: int) -> None:
        """Run to the egg of the meal, then eat it; give up when another pet or the evaporation wins."""
        meal = self._meal
        if not meal.is_eating and not (meal.egg.is_edible and meal.egg.is_free_for(self)):
            self._end_meal()
            return
        self._facing_right = meal.from_left
        if meal.is_eating:
            self._eat(meal, step_ms)
        else:
            self._reach_egg(meal)

    def _reach_egg(self, meal: _Meal) -> None:
        """Keep running until the nose touches the egg; the pet that gets there first claims it and eats."""
        stop = self._nose_stop(meal.egg, meal.from_left)
        if (stop - self.x) * (1 if meal.from_left else -1) > 0:
            return
        if not meal.egg.claim(self):
            self._end_meal()
            return
        self.x = stop
        meal.is_eating = True
        self._start_state(_EAT_STATE, 0)

    def _eat(self, meal: _Meal, step_ms: int) -> None:
        """Take one bite at the start of every eating cycle and step forward to the new end of the egg."""
        egg = meal.egg
        egg.claim(self)
        egg.keep_fresh(step_ms)
        cycle_ms = self._animation.cycle_ms
        bites_due = self._state_elapsed_ms // cycle_ms + 1
        while meal.bites < bites_due and not egg.is_eaten:
            egg.bite(meal.from_left)
            meal.bites += 1
            self.x = self._nose_stop(egg, meal.from_left)
        if egg.is_eaten and self._state_elapsed_ms >= meal.bites * cycle_ms:
            self._end_meal()

    def _end_meal(self) -> None:
        self._meal = None
        self._choose_state()

    def _approach(self, egg: Egg) -> tuple[float, bool]:
        """Return how far to go to reach the nearer end of the egg, and whether that is its left end."""
        return min(
            (abs(self._nose_stop(egg, True) - self.x), True),
            (abs(self._nose_stop(egg, False) - self.x), False),
        )

    def _nose_stop(self, egg: Egg, from_left: bool) -> float:
        """Return the x at which an eating pet has its nose just inside the chosen end of the egg."""
        left, right = self._load(_EAT_STATE).visible_span(from_left)
        edge = egg.remaining_span()[0 if from_left else 1]
        reach = _NOSE_OVER_EGG_ART_PIXELS * self.pixel_size
        return edge + reach - right if from_left else edge - reach - left

    def _count_down_egg(self, step_ms: int) -> None:
        self._egg_countdown_ms -= step_ms
        if self._egg_countdown_ms <= 0:
            self._egg_due = True
            self._egg_countdown_ms = random.randint(*_EGG_INTERVAL_MS)

    def _ground_ms(self, elapsed_ms: int) -> float:
        """Return the time the feet have worked: even, or bunched into steps."""
        return self._animation.stepped_ms(elapsed_ms) if self.stepped else elapsed_ms

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

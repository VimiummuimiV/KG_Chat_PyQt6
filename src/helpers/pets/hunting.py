"""Wild predators: they come from beyond an edge, hunt the nearest prey without rest and leave over an edge."""

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from helpers.pets.catalog import RUN_STATE, WALK_STATE
from helpers.pets.relations import PREDATOR_SPECIES, guards_against, preys_on

if TYPE_CHECKING:  # pet.py imports this module
    from helpers.pets.pet import Pet


_STALK, _POUNCE, _CARRY, _LEAVE = "stalk", "pounce", "carry", "leave"
_POUNCE_LIMIT_MS = 6000  # a pounce that has caught nothing by then turns back into stalking
_GUARD_RADIUS_ART_PIXELS = 120  # a predator runs off the line when a guard is this close
_POUNCE_RANGE_ART_PIXELS = 40  # a predator springs when its head is this close to the prey
_POUNCE_BOOST = 1.35
_CARRY_STATE = "carry"  # the sprite state is "carry_<color of the prey>"
_ENTRY_MS = (3000, 6000)  # prey walks this long after coming back
_ARRIVAL_MS = (3000, 10000)  # a predator first shows up after this long
_AWAY_MS = (30000, 60000)  # how long a predator stays away before it comes back, until the settings say otherwise


@dataclass
class _Raid:
    """What a predator on the line is doing: creeping up on prey, springing at it, carrying it off, running off."""

    phase: str = _STALK
    elapsed_ms: int = 0


class HuntingBehavior:
    """Predator side (stalk, pounce, carry off, run off), prey side (being seized) and leaving or entering at an edge."""

    def _init_hunting(self) -> None:
        self.is_predator = self.kind.species in PREDATOR_SPECIES
        self.is_gone = False  # the pet has been carried off for good
        self.exit_right = False  # the edge a predator ran off by with its prey, or by itself
        self._raid: _Raid | None = None
        self._prey: "Pet | None" = None
        self._speed_boost = 1.0
        self._is_seized = False
        self._is_away = self.is_predator  # a predator is never at home on the line: it comes from beyond an edge
        self._is_entering = False
        self.away_ms = _AWAY_MS
        self._return_ms = random.randint(*_ARRIVAL_MS)

    @property
    def is_visible(self) -> bool:
        """Whether the pet is on the line: not carried off and not away."""
        return not (self._is_seized or self._is_away)

    @property
    def is_hunting_now(self) -> bool:
        """Whether the pet is after prey that is still free."""
        return self._raid is not None and self._raid.phase in (_STALK, _POUNCE)

    @property
    def is_leaving(self) -> bool:
        """Whether the pet is running to an edge to leave the line."""
        return self._raid is not None and self._raid.phase in (_CARRY, _LEAVE)

    def seize(self) -> None:
        """Hide the pet: a predator has it."""
        self._meal = self._noticed = self._watching = None
        self._is_seized = True

    def free_at(self, center_x: float) -> None:
        """Bring the pet back where the predator dropped it and let it run for its life."""
        self._is_seized = False
        left, right = self._animation.visible_span(self._facing_right)
        self.x = center_x - (left + right) / 2
        self._scare(away_from=center_x)

    def enter(self, line_width: int, from_right: bool) -> None:
        """Walk in over the left or the right edge of the line, starting just outside it."""
        self._is_away = False
        self._is_entering = True
        self._facing_right = not from_right
        self._start_state(WALK_STATE, random.randint(*_ENTRY_MS))
        left, right = self._animation.visible_span(self._facing_right)
        self.x = line_width - left if from_right else -right

    def hunt(self, others: list["Pet"], step_ms: int) -> None:
        """Hunt the nearest prey, whichever one it is now; run off the line when a guard is near or no prey is left."""
        if not self.is_predator or self._is_scared:
            return
        if self._raid is None:
            self._start_raid()
        guards = [other for other in others if guards_against(other.kind, self.kind)]
        prey = [other for other in others if preys_on(self.kind, other.kind) and not (other.is_held or other.is_flying)]
        self._advance_raid(prey, guards, step_ms)

    def flee(self, away_from: float) -> None:
        """Drop the prey that is carried and run off the line over the edge on the far side of the x."""
        self._abort_raid()
        self._run_to_edge(_LEAVE, RUN_STATE, self.center_x > away_from)

    def wait_away(self, step_ms: int, line_width: int) -> None:
        """Count down the time away and come back over a random edge."""
        self._return_ms -= step_ms
        if self._return_ms <= 0:
            self.enter(line_width, random.choice((True, False)))

    def _start_raid(self) -> None:
        self._raid = _Raid()
        self._meal = self._noticed = self._watching = None
        self._start_state(WALK_STATE, math.inf)

    def _advance_raid(self, prey: list["Pet"], guards: list["Pet"], step_ms: int) -> None:
        raid = self._raid
        raid.elapsed_ms += step_ms
        if self.is_leaving:
            self._leave_line()
            return
        target = min(prey, key=self.distance_to, default=None)  # always the nearest prey, not the one chased before
        touched = min((other for other in prey if self.touches(other)), key=self.distance_to, default=None)
        if touched:
            self._carry_off(touched)  # whatever touches a predator is caught, nothing is run past
        elif self._guard_near(guards):
            self.flee(min(guards, key=self.distance_to).center_x)
        elif target is None:
            self._run_to_edge(_LEAVE, RUN_STATE, self.center_x > self._line_width / 2)
        else:
            self._face_toward(target.center_x)
            self._chase(raid, target)

    def _carry_off(self, prey: "Pet") -> None:
        prey.seize()
        self._prey = prey
        self._run_to_edge(_CARRY, f"{_CARRY_STATE}_{prey.kind.color}", self.center_x > self._line_width / 2)

    def _chase(self, raid: _Raid, target: "Pet") -> None:
        """Spring at the prey once it is near enough; fall back to stalking when it gets away."""
        if raid.phase == _STALK and self.reach_to(target) <= _POUNCE_RANGE_ART_PIXELS * self.pixel_size:
            raid.phase, raid.elapsed_ms, self._speed_boost = _POUNCE, 0, _POUNCE_BOOST
            self._start_state(RUN_STATE, math.inf)
        elif raid.phase == _POUNCE and raid.elapsed_ms > _POUNCE_LIMIT_MS:
            self._start_raid()
            self._speed_boost = 1.0

    def _run_to_edge(self, phase: str, state: str, exit_right: bool) -> None:
        self._raid = _Raid(phase)
        self._speed_boost = 1.0
        self.exit_right = exit_right
        self._facing_right = exit_right
        self._start_state(state, math.inf)

    def _leave_line(self) -> None:
        """Once the edge is passed, go away with the prey if there is one."""
        left, right = self._animation.visible_span(self._facing_right)
        if self.x + left < self._line_width and self.x + right > 0:
            return
        if self._prey:
            self._prey.is_gone = True
            self._prey.exit_right = self.exit_right
            self._prey = None
        self._raid = None
        self._is_away = True
        self._return_ms = random.randint(*self.away_ms)

    def _abort_raid(self) -> None:
        """End the raid, dropping the prey if it is carried."""
        if not self._raid:
            return
        if self._prey:
            self._prey.free_at(self.center_x)
            self._prey = None
        self._raid = None
        self._speed_boost = 1.0

    def _guard_near(self, guards: Iterable["Pet"]) -> bool:
        radius = _GUARD_RADIUS_ART_PIXELS * self.pixel_size
        return any(self.distance_to(guard) < radius for guard in guards)
"""Prey running from raiders and guards chasing predators off."""

import math
import random
from typing import TYPE_CHECKING, Iterable

from helpers.pets.catalog import BARK_STATE, RUN_STATE
from helpers.pets.relations import guards_against, preys_on

if TYPE_CHECKING:  # pet.py imports this module
    from helpers.pets.pet import Pet


_PREY_NOTICE_ART_PIXELS = 70  # how far prey sees a raider coming
GUARD_NOTICE_ART_PIXELS = 220  # how far a guard sees a predator ahead, and a predator a guard
_GUARD_HEARING_ART_PIXELS = 60  # how near a lone raider is heard from any side; every further raider on the same side adds this much
_THREAT_REACTION_MS = (100, 700)
_FLIGHT_MS = (2000, 3500)
_CHASE_LIMIT_MS = 10000
_BARK_BOUT_MS = (800, 1600)  # a guard barks in bouts while it chases, and runs on in silence in between
_QUIET_RUN_MS = (900, 2200)
_BITE_STATE = "swipe"  # a guard lunges once at the quarry it has caught up with


class DefenseBehavior:
    """Prey flees a hunting predator; a guard runs after any predator in sight until it catches up with it or loses it."""

    def _init_defense(self) -> None:
        self._threat: "Pet | None" = None  # the raider the pet has noticed and is about to react to
        self._threat_reaction_ms = 0
        self._chasing: "Pet | None" = None
        self._chase_ms = 0
        self._is_barking = False
        self._bark_phase_ms = 0

    def defend(self, others: list["Pet"], step_ms: int) -> None:
        """Notice raiders after a random moment; prey runs from them, a guard chases them."""
        if self._chasing:
            self._keep_chasing(others, step_ms)
            return
        raider = self._raider_in_sight(others)
        if raider is None or self._is_scared:
            self._threat = None
            return
        if self._threat is not raider:
            self._threat, self._threat_reaction_ms = raider, random.randint(*_THREAT_REACTION_MS)
        self._threat_reaction_ms -= step_ms
        if self._threat_reaction_ms > 0:
            return
        self._threat = None
        if guards_against(self.kind, raider.kind):
            self._start_chase(raider)
        else:
            self._scare(away_from=raider.center_x, duration_ms=_FLIGHT_MS)

    def _bolt(self, away_from: float) -> None:
        """Run away from the x as a guard has caught up with the pet: a predator leaves the line, the rest panic."""
        if self.is_predator:
            self.flee(away_from)
        else:
            self._scare(away_from=away_from, duration_ms=_FLIGHT_MS)

    def is_path_blocked(self, x: float, others: Iterable["Pet"]) -> bool:
        """Whether a predator of this pet stands between it and the x: nobody runs for food past a fox."""
        low, high = sorted((self.center_x, x))
        return any(preys_on(other.kind, self.kind) and low <= other.center_x <= high for other in others)

    def _raider_in_sight(self, others: list["Pet"]) -> "Pet | None":
        """Return the nearest predator this pet reacts to: a hunter after its kind, or one its kind guards against that a guard sees ahead or hears close by."""
        guard_reach = GUARD_NOTICE_ART_PIXELS * self.pixel_size
        prey_reach = _PREY_NOTICE_ART_PIXELS * self.pixel_size
        seen = [
            other for other in others
            if (guards_against(self.kind, other.kind) and other.is_grounded and self._guard_notices(other, guard_reach, others))
            or (other.is_hunting_now and preys_on(other.kind, self.kind) and self.distance_to(other) <= prey_reach)
        ]
        return min(seen, key=self.distance_to, default=None)

    def _guard_notices(self, raider: "Pet", sight_reach: float, others: list["Pet"]) -> bool:
        """Whether a guard sees the raider within its reach on the side it looks at, or hears it near on either side; a pack on one side is heard from farther."""
        distance = self.distance_to(raider)
        if distance <= sight_reach and self.is_facing(raider):
            return True
        pack = sum(
            guards_against(self.kind, other.kind) and (other.center_x > self.center_x) == (raider.center_x > self.center_x)
            for other in others
        )
        return distance <= _GUARD_HEARING_ART_PIXELS * self.pixel_size * pack

    def _start_chase(self, raider: "Pet") -> None:
        self._meal = self._noticed = self._watching = None
        self._chasing, self._chase_ms = raider, 0
        self._face_toward(raider.center_x)
        self._start_chase_phase(barking=True)

    def _start_chase_phase(self, barking: bool) -> None:
        """Stand and bark for a bout, or run on in silence for a while."""
        self._is_barking = barking and BARK_STATE in self.kind.states
        self._bark_phase_ms = random.randint(*(_BARK_BOUT_MS if self._is_barking else _QUIET_RUN_MS))
        self._start_state(BARK_STATE if self._is_barking else RUN_STATE, math.inf)

    def _keep_chasing(self, others: list["Pet"], step_ms: int) -> None:
        """Run after the quarry, barking in bouts, even when it has stopped raiding; bite it away on reaching it, give up when it is lost."""
        self._chase_ms += step_ms
        quarry = self._chasing
        sight = GUARD_NOTICE_ART_PIXELS * self.pixel_size
        if quarry in others and quarry.is_grounded and self._chase_ms <= _CHASE_LIMIT_MS and self.distance_to(quarry) <= sight:
            self._face_toward(quarry.center_x)
            if not self.touches(quarry):
                self._bark_phase_ms -= step_ms
                if self._bark_phase_ms <= 0:
                    self._start_chase_phase(barking=not self._is_barking)
                return
            quarry._bolt(self.center_x)
            self._chasing = None
            self._bite()
            return
        self._chasing = None
        self._choose_state()

    def _bite(self) -> None:
        """Lunge once at the quarry, then carry on as usual."""
        if _BITE_STATE not in self.kind.states:
            self._choose_state()
            return
        self._start_state(_BITE_STATE, self._load(_BITE_STATE).cycle_ms)

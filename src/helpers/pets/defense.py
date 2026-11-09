"""Prey running from raiders and guards chasing predators off."""

import math
import random
from typing import TYPE_CHECKING, Iterable

from helpers.pets.catalog import RUN_STATE
from helpers.pets.relations import guards_against, preys_on

if TYPE_CHECKING:  # pet.py imports this module
    from helpers.pets.pet import Pet


_PREY_NOTICE_ART_PIXELS = 70  # how far prey sees a raider coming
_GUARD_NOTICE_ART_PIXELS = 220
_THREAT_REACTION_MS = (100, 700)
_FLIGHT_MS = (2000, 3500)
_CHASE_LIMIT_MS = 10000


class DefenseBehavior:
    """Prey flees a hunting predator; a guard runs after any predator in sight until it catches up with it or loses it."""

    def _init_defense(self) -> None:
        self._threat: "Pet | None" = None  # the raider the pet has noticed and is about to react to
        self._threat_reaction_ms = 0
        self._chasing: "Pet | None" = None
        self._chase_ms = 0

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
        """Return the nearest predator this pet reacts to and sees: a hunter after its kind or one its kind guards against."""
        guard_reach = _GUARD_NOTICE_ART_PIXELS * self.pixel_size
        prey_reach = _PREY_NOTICE_ART_PIXELS * self.pixel_size
        seen = [
            other for other in others
            if (guards_against(self.kind, other.kind) and self.distance_to(other) <= guard_reach)
            or (other.is_hunting_now and preys_on(other.kind, self.kind) and self.distance_to(other) <= prey_reach)
        ]
        return min(seen, key=self.distance_to, default=None)

    def _start_chase(self, raider: "Pet") -> None:
        self._meal = self._noticed = self._watching = None
        self._chasing, self._chase_ms = raider, 0
        self._face_toward(raider.center_x)
        self._start_state(RUN_STATE, math.inf)

    def _keep_chasing(self, others: list["Pet"], step_ms: int) -> None:
        """Run after the quarry even when it has stopped raiding; bite it away on reaching it, give up when it is lost."""
        self._chase_ms += step_ms
        quarry = self._chasing
        sight = _GUARD_NOTICE_ART_PIXELS * self.pixel_size
        if quarry in others and self._chase_ms <= _CHASE_LIMIT_MS and self.distance_to(quarry) <= sight:
            self._face_toward(quarry.center_x)
            if not self.touches(quarry):
                return
            quarry._bolt(self.center_x)
        self._chasing = None
        self._choose_state()

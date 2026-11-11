"""Pet behavior: random states, stepwise walking, eating, laying eggs when fed, and being picked up and thrown."""

import math
import random
from dataclasses import dataclass
from typing import Iterable

from PyQt6.QtCore import QPoint, QRect

from helpers.pets.animation import load_animation
from helpers.pets.bounce import BounceBehavior, CursorMotion
from helpers.pets.catalog import BARK_STATE, EAT_STATE, LAY_STATE, LIE_STATE, RUN_STATE, WALK_STATE, PetKind
from helpers.pets.defense import DefenseBehavior
from helpers.pets.egg import Egg
from helpers.pets.food import BITES_PER_FOOD, Food
from helpers.pets.hunting import HuntingBehavior
from helpers.pets.throwable import Throwable


# Body lengths covered per cycle of the walk animation: ties speed to body size and animation tempo.
_WALK_STRIDE_RATIO = 0.8
# Faster gaits reuse the walk speed; their GIFs often share one cycle, so only the pace scales.
_GAIT_SPEED_FACTOR = {"walk": 1.0, "walk_fast": 1.6, "run": 2.5}
_CARRY_SPEED_FACTOR = 2.0  # a predator slowed by its prey
_WALL_BOUNCE = 0.5  # share of the sideways speed a flying pet keeps after hitting a side
_TURN_CHANCE = 0.4
_CONTACT_ART_PIXELS = 2  # how close two pets must get to touch
# state: (pick weight, minimum ms, maximum ms); running is not here: a pet runs only to chase, flee or reach food
_STATE_PLAN = {
    "idle": (5, 2000, 6000),
    "walk": (5, 3000, 8000),
    "walk_fast": (1, 1500, 3500),
    "swipe": (1, 1500, 3000),
    "with_ball": (2, 4000, 9000),
    "lie": (3, 6000, 14000),
    "stand": (2, 3000, 8000),
}
_EFFECT_STATES = frozenset({BARK_STATE})  # their canvas is widened on the facing side for effects such as sound waves
_SCARE_MS = (1200, 2200)
_LAYING_SPECIES = frozenset({"chicken"})
_EGG_INTERVAL_MS = (20000, 50000)  # walking time between two eggs
_LAY_PHASE = 0.4  # share of the laying animation after which the egg leaves the hen
_BITES_PER_EGG = BITES_PER_FOOD  # a hen lays an egg for each tuft of grass eaten
_BITE_LIMIT = 2 * _BITES_PER_EGG  # the most bites a pet keeps in stock
_EGG_DROP_ART_PIXELS = 4  # height the egg leaves the pet from, in art pixels
_NOSE_OVER_FOOD_ART_PIXELS = 1  # how far the nose of an eating pet reaches into the edge of the food
_WATCH_STATE = "idle"  # a pet that stays out of a race stands and looks at it
_FOOD_SIGHT_ART_PIXELS = 160  # how far a pet sees food on either side; farther food does not exist for it
_REACTION_MS = (150, 1500)  # how long a pet takes to notice food and set off
_CATCH_UP_MARGIN_MS = 500  # a pet gives up when a rival gets to the food this much sooner than it could
_PECK_STATE = "swipe"  # the eating state of pets without their own
_NOSE_SETBACK = {_PECK_STATE: 6}  # art pixels by which the comb of a pecking hen is ahead of its beak, the part that touches the food
_BITE_PHASE = {_PECK_STATE: 0.7}  # share of the eating cycle at which the beak touches the ground; 0 when not listed


@dataclass
class _Meal:
    """A food a pet is running to or eating."""

    food: Food
    from_left: bool  # the pet stands at the left end of the egg and faces right
    is_eating: bool = False
    bites: int = 0


class Pet(HuntingBehavior, DefenseBehavior, BounceBehavior, Throwable):
    """One pet moving along the bottom of an area measured in device pixels."""

    def __init__(self, kind: PetKind, pixel_size: int, line_width: int):
        super().__init__()
        self.kind = kind
        self.pixel_size = pixel_size
        self.stepped = True
        self._lays_eggs = kind.species in _LAYING_SPECIES
        self._egg_countdown_ms = random.randint(*_EGG_INTERVAL_MS)
        self._egg_due = False
        self._eat_state = EAT_STATE if EAT_STATE in kind.states else _PECK_STATE
        self._fed_bites = _BITES_PER_EGG  # a hen starts fed for one egg
        self._meal: _Meal | None = None
        self._noticed: Food | None = None  # the food the pet has seen and is about to react to
        self._reaction_ms = 0
        self._watching: Food | None = None  # the food whose race the pet watches instead of running
        self._is_scared = False
        self._state = WALK_STATE
        self._line_width = line_width
        self._init_hunting()
        self._init_defense()
        self._init_bounce()
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

    @property
    def edges(self) -> tuple[float, float]:
        """Return the x of the left and the right end of the visible pixels of the pet."""
        left, right = self._current()[0].visible_span(self._facing_right)
        return self.x + left, self.x + right

    @property
    def center_x(self) -> float:
        """Return the x of the middle of the visible pixels of the pet."""
        return sum(self.edges) / 2

    def distance_to(self, other: "Pet") -> float:
        """Return the horizontal distance between the middles of two pets."""
        return abs(self.center_x - other.center_x)

    def reach_to(self, other: "Pet") -> float:
        """Return how far the head of the pet is from the near end of the other pet; negative once it is over it."""
        left, right = self.edges
        other_left, other_right = other.edges
        return other_left - right if self._facing_right else left - other_right

    def touches(self, other: "Pet") -> bool:
        """Whether the bodies of the two pets touch, from either side."""
        left, right = self.edges
        other_left, other_right = other.edges
        margin = _CONTACT_ART_PIXELS * self.pixel_size
        return left - margin < other_right and other_left - margin < right

    def update(
        self, step_ms: int, line_width: int, area_height: int, cursor: CursorMotion | None = None
    ) -> None:
        """Advance the pet by step_ms and keep it inside; a flying pet bounces off the cursor."""
        self._line_width = line_width
        if self._is_seized:
            return
        if self._is_away:
            self.wait_away(step_ms, line_width)
            return
        if self.is_flying:
            self.fly_past_cursor(step_ms, area_height, cursor)
        elif not self.is_held:
            self._walk(step_ms)
        self.age_badge(step_ms)
        self._keep_inside(line_width)

    def take_egg(self) -> Egg | None:
        """Return the egg the pet has just laid at its tail, if any."""
        if not self._egg_due:
            return None
        self._egg_due = False
        left, right = self._animation.visible_span(self._facing_right)
        tail = self.x + (left if self._facing_right else right)
        return Egg(tail, _EGG_DROP_ART_PIXELS * self.pixel_size, self.pixel_size)

    def look_for_food(self, foods: Iterable[Food], rivals: Iterable["Pet"], step_ms: int) -> None:
        """Notice food after a random moment and run for it, unless a rival clearly gets there first; then watch the race."""
        if self._is_scared or self.is_held or self.is_flying or self._state == LAY_STATE or (self._meal and self._meal.is_eating):
            return
        rivals = [rival for rival in rivals if rival is not self]
        if self._meal and self.is_path_blocked(self._meal.food.center_x, rivals):
            self._end_meal()
            return
        if self._meal and self._is_outrun(self._meal.food, rivals):
            self._watch(self._meal.food)
            return
        free = [
            food for food in foods
            if food.is_food_for(self.kind) and food.is_edible and food.is_free_for(self)
            and self._sees(food) and self._can_reach(food) and not self.is_path_blocked(food.center_x, rivals)
        ]
        if self._watching:
            has_other_food = any(food is not self._watching for food in free)
            if self._watching.is_edible and not has_other_food and any(rival._is_going_to(self._watching) for rival in rivals):
                self._face(self._watching)
                return
            self._watching = None
            self._choose_state()
        nearest = min(free, key=lambda food: self._approach(food)[0], default=None)
        if nearest is None or (self._meal and self._meal.food is nearest):
            self._noticed = None
            return
        if self._noticed is not nearest:
            self._noticed, self._reaction_ms = nearest, random.randint(*_REACTION_MS)
        self._reaction_ms -= step_ms
        if self._reaction_ms > 0:
            return
        self._noticed = None
        if self._is_outrun(nearest, rivals):
            self._watch(nearest)
            return
        self._meal = _Meal(nearest, self._approach(nearest)[1])
        self._facing_right = self._meal.from_left
        self._start_state(RUN_STATE, 0)

    def interact(self, others: Iterable["Pet"], step_ms: int) -> None:
        """React to the other pets on the line: run from predators, chase them off, or hunt."""
        if self.is_held or self.is_flying:
            return
        others = [other for other in others if other is not self]
        self.defend(others, step_ms)
        self.hunt(others, step_ms)

    def _sees(self, food: Food) -> bool:
        """Whether the food is within the sight of the pet."""
        return abs(food.center_x - self.center_x) <= _FOOD_SIGHT_ART_PIXELS * self.pixel_size

    def _is_going_to(self, food: Food) -> bool:
        """Whether the pet is running to the food or eating it."""
        return self._meal is not None and self._meal.food is food

    def grab(self, point: QPoint, area_height: int, timestamp_ms: int) -> None:
        self._abort_raid()
        super().grab(point, area_height, timestamp_ms)

    def click(self) -> None:
        self._scare()

    def land(self, impact_speed: float) -> None:
        super().land(impact_speed)
        self._scare()

    def _maximum_lift(self, area_height: int) -> float:
        animation = self._current()[0]
        return area_height - animation.frames_right[0].height() + animation.body.y()

    def _load(self, state: str):
        return load_animation(self.kind, state, self.pixel_size)

    def _current(self):
        """Return the animation on screen and its clock; a held or flying pet is frozen on its first idle frame."""
        if self.is_flying or self.is_held:
            return self._load("idle"), 0
        return self._animation, self._state_elapsed_ms

    def _effect_margin(self, state: str) -> int:
        """Return the width the canvas of a state adds in front of the pet for effects, beyond its idle canvas."""
        if state not in _EFFECT_STATES:
            return 0
        return self._load(state).frames_right[0].width() - self._load("idle").frames_right[0].width()

    def _start_state(self, state: str, duration_ms: int) -> None:
        if not self._facing_right:  # a mirrored canvas grows to the left: keep the body where it stands
            self.x += self._effect_margin(self._state) - self._effect_margin(state)
        self._state = state
        self._state_limit_ms = duration_ms
        self._state_elapsed_ms = 0
        self._animation = self._load(state)

    def _choose_state(self) -> None:
        self._is_scared = False
        if self.is_predator and not self.is_exploring:
            self._start_raid()  # a wild predator never idles about while there is prey: it hunts
            return
        states = [
            state for state in sorted(self.kind.states)
            if state in _STATE_PLAN and not (state == LIE_STATE and self._is_guard_present)
        ]
        state = random.choices(states, [_STATE_PLAN[state][0] for state in states])[0]
        self._start_state(state, random.randint(*_STATE_PLAN[state][1:]))
        if state in _GAIT_SPEED_FACTOR and random.random() < _TURN_CHANCE:
            self._facing_right = not self._facing_right

    def _scare(self, away_from: float | None = None, duration_ms: tuple[int, int] = _SCARE_MS) -> None:
        """Run around in panic for a moment, forgetting any food; run from the x away_from when given."""
        self._abort_raid()
        self._meal = self._noticed = self._watching = self._chasing = None
        self._is_scared = True
        self._facing_right = random.choice((True, False)) if away_from is None else self.center_x > away_from
        self._start_state(RUN_STATE, random.randint(*duration_ms))

    def _walk(self, step_ms: int) -> None:
        before_ms = self._state_elapsed_ms
        self._state_elapsed_ms += step_ms
        gait_factor = _GAIT_SPEED_FACTOR.get(self._state) or (_CARRY_SPEED_FACTOR if self._prey else None)
        if gait_factor:
            moved_ms = self._ground_ms(self._state_elapsed_ms) - self._ground_ms(before_ms)
            direction = 1 if self._facing_right else -1
            self.x += direction * self._walk_speed * gait_factor * self._speed_boost * moved_ms / 1000
            if self._lays_eggs:
                self._count_down_egg(step_ms)
        self._lay_egg(before_ms)
        if self._meal:
            self._follow_meal(step_ms)
        elif self._state_elapsed_ms >= self._state_limit_ms:
            if self._state == LAY_STATE:
                self._resume_walk()
            else:
                self._choose_state()

    def _follow_meal(self, step_ms: int) -> None:
        """Run to the food of the meal, then eat it; give up when another pet or the evaporation wins."""
        meal = self._meal
        if not meal.is_eating and not (meal.food.is_edible and meal.food.is_free_for(self)):
            self._end_meal()
            return
        self._facing_right = meal.from_left
        if meal.is_eating:
            self._eat(meal, step_ms)
        else:
            self._reach_egg(meal)

    def _reach_egg(self, meal: _Meal) -> None:
        """Keep running until the nose touches the food; the pet that gets there first claims it and eats."""
        if not self._can_reach_from(meal.food, meal.from_left):
            self._end_meal()
            return
        stop = self._nose_stop(meal.food, meal.from_left)
        if (stop - self.x) * (1 if meal.from_left else -1) > 0:
            return
        if not meal.food.claim(self):
            self._end_meal()
            return
        self.x = stop
        meal.is_eating = True
        self._start_state(self._eat_state, 0)

    def _eat(self, meal: _Meal, step_ms: int) -> None:
        """Take one bite per eating cycle and step forward to the new end of the food once it is bitten and chewed."""
        food = meal.food
        food.claim(self)
        food.keep_fresh(step_ms)
        cycle_ms = self._animation.cycle_ms
        bite_ms = round(_BITE_PHASE.get(self._eat_state, 0.0) * cycle_ms)
        step_ms_in_cycle = cycle_ms if bite_ms else 0  # a pet that bites mid-cycle chews first and steps at the cycle's end
        bites_due = (self._state_elapsed_ms - bite_ms) // cycle_ms + 1
        while meal.bites < bites_due and not food.is_eaten:
            food.bite(meal.from_left)
            meal.bites += 1
            self._fed_bites = min(self._fed_bites + 1, _BITE_LIMIT)
        if meal.bites and self._state_elapsed_ms >= (meal.bites - 1) * cycle_ms + step_ms_in_cycle:
            self.x = self._nose_stop(food, meal.from_left)
        if food.is_eaten and self._state_elapsed_ms >= meal.bites * cycle_ms:
            self._end_meal()

    def _arrival_ms(self, food: Food) -> float:
        """Return how long the pet needs to run to the nearer end of the food."""
        run_speed = self._walk_speed * _GAIT_SPEED_FACTOR[RUN_STATE]
        return self._approach(food)[0] / run_speed * 1000

    def _is_outrun(self, food: Food, rivals: list["Pet"]) -> bool:
        """Whether a rival running to the food gets there clearly sooner than this pet could."""
        arrival_ms = self._arrival_ms(food)
        return any(
            rival._is_going_to(food) and rival._arrival_ms(food) + _CATCH_UP_MARGIN_MS < arrival_ms for rival in rivals
        )

    def _watch(self, food: Food) -> None:
        """Stop running for the food and stand looking at it until it is gone or nobody runs for it."""
        self._meal = None
        self._watching = food
        self._start_state(_WATCH_STATE, math.inf)
        self._face(food)

    def _face(self, food: Food) -> None:
        self._face_toward(food.center_x)

    def _face_toward(self, x: float) -> None:
        self._facing_right = x > self.center_x

    def is_facing(self, other: "Pet") -> bool:
        """Whether the other pet is on the side this pet looks at."""
        return (other.center_x > self.center_x) == self._facing_right

    def _end_meal(self) -> None:
        self._meal = None
        self._choose_state()

    def _approach(self, food: Food) -> tuple[float, bool]:
        """Return the distance to the nearer reachable end of the food, and whether it is the left."""
        distances = (
            (abs(self._nose_stop(food, from_left) - self.x), from_left)
            for from_left in (True, False)
            if self._can_reach_from(food, from_left)
        )
        return min(distances, default=(math.inf, True))

    def _can_reach(self, food: Food) -> bool:
        """Whether the pet can stand at an end of the food with its whole body inside the line."""
        return any(self._can_reach_from(food, from_left) for from_left in (True, False))

    def _can_reach_from(self, food: Food, from_left: bool) -> bool:
        lowest, highest = self._horizontal_range(self._load(self._eat_state), from_left)
        return lowest <= self._nose_stop(food, from_left) <= highest

    def _nose_stop(self, food: Food, from_left: bool) -> float:
        """Return the x at which an eating pet has its nose just inside the chosen end of the food."""
        left, right = self._load(self._eat_state).visible_span(from_left)
        edge = food.remaining_span()[0 if from_left else 1]
        reach = (_NOSE_OVER_FOOD_ART_PIXELS + _NOSE_SETBACK.get(self._eat_state, 0)) * self.pixel_size
        return edge + reach - right if from_left else edge - reach - left

    def _count_down_egg(self, step_ms: int) -> None:
        """Sit down to lay once the countdown ends, the hen is fed and nothing else occupies her."""
        self._egg_countdown_ms -= step_ms
        if self._egg_countdown_ms > 0 or self._fed_bites < _BITES_PER_EGG or self._meal or self._is_scared:
            return
        self._egg_countdown_ms = random.randint(*_EGG_INTERVAL_MS)
        self._start_state(LAY_STATE, self._load(LAY_STATE).cycle_ms)

    def _lay_egg(self, before_ms: int) -> None:
        """Release the egg at the moment of the laying animation when the hen is at its deepest sit."""
        laying_ms = _LAY_PHASE * self._state_limit_ms
        if self._state == LAY_STATE and before_ms < laying_ms <= self._state_elapsed_ms:
            self._fed_bites -= _BITES_PER_EGG
            self._egg_due = True

    def _resume_walk(self) -> None:
        """Walk on in the same direction after laying."""
        self._start_state(WALK_STATE, random.randint(*_STATE_PLAN[WALK_STATE][1:]))

    def _ground_ms(self, elapsed_ms: int) -> float:
        """Return the time the feet have worked: even, or bunched into steps."""
        return self._animation.stepped_ms(elapsed_ms) if self.stepped else elapsed_ms

    def _walk_in(self, line_width: int) -> None:
        """Keep a pet coming over an edge facing inward until it is wholly on the line."""
        left, right = self._current()[0].visible_span(self._facing_right)
        self._facing_right = self.center_x < line_width / 2
        self._is_entering = not (self.x + left >= 0 and self.x + right <= line_width)

    @property
    def _turns_at_wall(self) -> bool:
        """Whether an edge turns the pet around; a flying pet or one with a goal keeps its side."""
        has_goal = self._meal or self._watching or self._chasing or self.is_hunting_now
        return not (self.is_flying or has_goal)

    def _horizontal_range(
        self, animation, facing_right: bool, effect_margin: int = 0
    ) -> tuple[float, float]:
        """Return the lowest and the highest x that keep the visible pixels inside the line."""
        span_left, span_right = animation.visible_span(facing_right)
        if facing_right:
            span_right -= effect_margin
        else:
            span_left += effect_margin
        lowest = -span_left
        return lowest, max(lowest, self._line_width - span_right)

    def _keep_inside(self, line_width: int) -> None:
        if self.is_leaving:
            return  # a predator running off leaves over the edge
        if self._is_entering:
            self._walk_in(line_width)
            return
        animation, margin = self._current()[0], self._effect_margin(self._state)
        lowest, highest = self._horizontal_range(animation, self._facing_right, margin)
        if lowest <= self.x <= highest:
            return
        was_left = self.x < lowest
        if self._turns_at_wall:
            self._facing_right = was_left
            lowest, highest = self._horizontal_range(animation, self._facing_right, margin)
        if self.is_flying:
            self.velocity[0] = _WALL_BOUNCE * abs(self.velocity[0]) * (1 if was_left else -1)
        self.x = max(lowest, min(self.x, highest))

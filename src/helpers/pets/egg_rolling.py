"""Rolling of an egg-shaped body on a flat floor seen from the side: its shape decides how it tumbles and rocks."""

import math
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache

from helpers.pets.throwable import GRAVITY


# The outline in art pixels: (WIDTH sin t - BLUNTNESS WIDTH / 2 sin 2t, -LENGTH cos t); the pointed end is at the top.
_EGG_HALF_LENGTH = 4.0
_EGG_HALF_WIDTH = 2.75
_EGG_BLUNTNESS = 0.15
_CURVE_SAMPLES = 2048
_TABLE_SIZE = 1440
_SUBSTEP_SECONDS = 0.008
_ROLL_DAMPING = 1.2  # per second; the floor slowly takes the spin away


@dataclass(frozen=True)
class _Profile:
    """Tables over the turn angle: height of the center of mass, its slope, the inertia about the contact point and its slope."""

    height: tuple[float, ...]
    slope: tuple[float, ...]
    inertia: tuple[float, ...]
    inertia_slope: tuple[float, ...]


def _curve(angle: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Return the outline point and its first and second derivatives at the curve parameter."""
    sine, cosine = math.sin(angle), math.cos(angle)
    double_sine, double_cosine = math.sin(2 * angle), math.cos(2 * angle)
    point = (_EGG_HALF_WIDTH * (sine - _EGG_BLUNTNESS / 2 * double_sine), -_EGG_HALF_LENGTH * cosine)
    tangent = (_EGG_HALF_WIDTH * (cosine - _EGG_BLUNTNESS * double_cosine), _EGG_HALF_LENGTH * sine)
    curvature = (_EGG_HALF_WIDTH * (-sine + 2 * _EGG_BLUNTNESS * double_sine), _EGG_HALF_LENGTH * cosine)
    return point, tangent, curvature


def _mass_properties(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Return the center of mass and the moment of inertia about it per unit of mass for a uniform polygon."""
    area = center_x = center_y = polar = 0.0
    for (x_first, y_first), (x_second, y_second) in zip(points, points[1:] + points[:1]):
        cross = x_first * y_second - x_second * y_first
        area += cross
        center_x += (x_first + x_second) * cross
        center_y += (y_first + y_second) * cross
        polar += cross * (
            x_first ** 2 + x_first * x_second + x_second ** 2 + y_first ** 2 + y_first * y_second + y_second ** 2
        )
    area /= 2
    center_x /= 6 * area
    center_y /= 6 * area
    return center_x, center_y, polar / (12 * area) - center_x ** 2 - center_y ** 2


@lru_cache(maxsize=None)
def _profile() -> _Profile:
    samples = [_curve(math.tau * index / _CURVE_SAMPLES) for index in range(_CURVE_SAMPLES)]
    center_x, center_y, inertia_center = _mass_properties([point for point, _, _ in samples])
    rows = []
    for (point_x, point_y), (tangent_x, tangent_y), (curvature_x, curvature_y) in samples:
        offset_x, offset_y = point_x - center_x, point_y - center_y
        tangent_length = math.hypot(tangent_x, tangent_y)
        normal_x, normal_y = tangent_y / tangent_length, -tangent_x / tangent_length
        if offset_x * normal_x + offset_y * normal_y < 0:
            normal_x, normal_y = -normal_x, -normal_y
        slope = offset_x * normal_y - offset_y * normal_x
        radius = tangent_length ** 3 / abs(tangent_x * curvature_y - tangent_y * curvature_x)
        rows.append((
            math.atan2(normal_x, normal_y) % math.tau,  # turn angle at which this point touches the floor
            offset_x * normal_x + offset_y * normal_y,
            slope,
            inertia_center + offset_x ** 2 + offset_y ** 2,
            2 * slope * radius,
        ))
    rows.sort()
    angles = [row[0] for row in rows]
    tables = ([], [], [], [])
    for index in range(_TABLE_SIZE):
        angle = math.tau * index / _TABLE_SIZE
        after = bisect_left(angles, angle)
        before_angle, before_row = (angles[after - 1], rows[after - 1]) if after else (angles[-1] - math.tau, rows[-1])
        after_angle, after_row = (angles[after], rows[after]) if after < len(rows) else (angles[0] + math.tau, rows[0])
        fraction = (angle - before_angle) / (after_angle - before_angle)
        for table, before_value, after_value in zip(tables, before_row[1:], after_row[1:]):
            table.append(before_value + (after_value - before_value) * fraction)
    return _Profile(*(tuple(table) for table in tables))


def _sample(table: tuple[float, ...], angle: float) -> float:
    position = (angle % math.tau) * _TABLE_SIZE / math.tau
    index = int(position)
    fraction = position - index
    return table[index % _TABLE_SIZE] * (1 - fraction) + table[(index + 1) % _TABLE_SIZE] * fraction


def spin_for_speed(angle: float, speed: float, pixel_size: int) -> float:
    """Return the spin in radians per second that moves the egg along the floor at speed in pixels per second."""
    return speed / (_sample(_profile().height, angle) * pixel_size)


def _rates(profile: _Profile, angle: float, spin: float, pixel_size: int) -> tuple[float, float, float]:
    """Return how fast the angle, the spin and the traveled distance change."""
    torque = -0.5 * _sample(profile.inertia_slope, angle) * spin ** 2 - GRAVITY * _sample(profile.slope, angle) / pixel_size
    acceleration = torque / _sample(profile.inertia, angle) - _ROLL_DAMPING * spin
    return spin, acceleration, spin * _sample(profile.height, angle) * pixel_size


def advance(angle: float, spin: float, seconds: float, pixel_size: int) -> tuple[float, float, float]:
    """Roll the egg without slipping; return its new turn angle, spin and the distance its center moved."""
    profile = _profile()
    steps = max(1, math.ceil(seconds / _SUBSTEP_SECONDS))
    step = seconds / steps
    distance = 0.0
    for _ in range(steps):
        first = _rates(profile, angle, spin, pixel_size)
        second = _rates(profile, angle + step / 2 * first[0], spin + step / 2 * first[1], pixel_size)
        third = _rates(profile, angle + step / 2 * second[0], spin + step / 2 * second[1], pixel_size)
        fourth = _rates(profile, angle + step * third[0], spin + step * third[1], pixel_size)
        angle_rate, spin_rate, distance_rate = (
            (one + 2 * two + 2 * three + four) / 6 for one, two, three, four in zip(first, second, third, fourth)
        )
        angle = (angle + step * angle_rate) % math.tau
        spin += step * spin_rate
        distance += step * distance_rate
    return angle, spin, distance

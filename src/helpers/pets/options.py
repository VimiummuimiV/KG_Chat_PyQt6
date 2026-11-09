"""Options of the raids of predators on prey: defaults, limits and the readers of the config."""

from dataclasses import dataclass


RAID_SECONDS_SETTING = (330, 5, 1800)  # default, minimum, maximum of the settings page
DEFAULT_CATCH_PERCENT = 50
_RANGE_SPREAD = 0.3  # a raid interval of n seconds stands for the range n -30% to n +30%
_MILLISECONDS = 1000
_PERCENT = 100


def _raid_interval_ms(seconds: int) -> tuple[int, int]:
    return round(seconds * (1 - _RANGE_SPREAD) * _MILLISECONDS), round(seconds * (1 + _RANGE_SPREAD) * _MILLISECONDS)


@dataclass(frozen=True)
class HuntingOptions:
    """How often predators raid and how often a raid ends in a catch."""

    enabled: bool = True
    raid_interval_ms: tuple[int, int] = _raid_interval_ms(RAID_SECONDS_SETTING[0])
    catch_chance: float = DEFAULT_CATCH_PERCENT / _PERCENT


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def hunting_settings(config) -> dict:
    """Return the hunting part of the config as a dict; a plain true or false under "hunting" only switches the raids."""
    raw = config.get("ui", "pets", "hunting")
    if isinstance(raw, bool):
        return {"enabled": raw}
    return dict(raw) if isinstance(raw, dict) else {}


def hunting_raid_seconds(config) -> int:
    """Return the seconds between raids, kept inside the limits of the settings page."""
    default, minimum, maximum = RAID_SECONDS_SETTING
    seconds = hunting_settings(config).get("raid_interval")
    return max(minimum, min(maximum, round(seconds))) if _is_number(seconds) else default


def hunting_catch_percent(config) -> int:
    """Return the chance of catching prey in percent."""
    percent = hunting_settings(config).get("catch_chance")
    return max(0, min(_PERCENT, round(percent))) if _is_number(percent) else DEFAULT_CATCH_PERCENT


def hunting_options(config) -> HuntingOptions:
    """Return the hunting options of the config."""
    return HuntingOptions(
        enabled=bool(hunting_settings(config).get("enabled", HuntingOptions.enabled)),
        raid_interval_ms=_raid_interval_ms(hunting_raid_seconds(config)),
        catch_chance=hunting_catch_percent(config) / _PERCENT,
    )

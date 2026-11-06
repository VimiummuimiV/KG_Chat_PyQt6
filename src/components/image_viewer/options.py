"""Image viewer options read from the config; the defaults and limits are shared with the settings page."""

from components.image_viewer.layer import TRANSITION_MODES


DEFAULT_TRANSITION_MODE = "fade"
DEFAULT_TRANSITION_MS = 350
TRANSITION_MS_RANGE = (100, 1500)
DEFAULT_SLIDESHOW_SECONDS = 3
SLIDESHOW_SECONDS_RANGE = (1, 60)
DEFAULT_SHOW_THUMBNAILS = True

_MS_PER_SECOND = 1000


def _read_bounded_int(config, key: str, default: int, bounds: tuple[int, int]) -> int:
    value = config.get("image_viewer", key) if config else None
    try:
        return max(bounds[0], min(bounds[1], int(value)))
    except (TypeError, ValueError):
        return default


def transition_mode(config) -> str:
    value = config.get("image_viewer", "transition") if config else None
    return value if value in TRANSITION_MODES else DEFAULT_TRANSITION_MODE


def transition_duration_ms(config) -> int:
    return _read_bounded_int(config, "transition_ms", DEFAULT_TRANSITION_MS, TRANSITION_MS_RANGE)


def slideshow_interval_seconds(config) -> int:
    return _read_bounded_int(config, "slideshow_interval", DEFAULT_SLIDESHOW_SECONDS, SLIDESHOW_SECONDS_RANGE)


def slideshow_interval_ms(config) -> int:
    return slideshow_interval_seconds(config) * _MS_PER_SECOND


def show_thumbnails(config) -> bool:
    value = config.get("image_viewer", "show_thumbnails") if config else None
    return DEFAULT_SHOW_THUMBNAILS if value is None else bool(value)

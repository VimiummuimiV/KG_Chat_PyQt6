"""Notification config resolution: sizes, timings, margins and mute-bypass."""

from typing import Tuple

from PyQt6.QtWidgets import QApplication


_NOTIFICATION_DEFAULT_WIDTH = 550
_FADE_DURATION_MS_DEFAULT = 300
NOTIFICATION_DURATION_MS_DEFAULT = 5000
_REPLY_FOCUS_WIDTH_EXPAND_DEFAULT = 200
_NOTIFICATION_MARGIN_X_DEFAULT = 20
_NOTIFICATION_MARGIN_TOP_DEFAULT = 20


def _resolve_focus_expand_width(config=None) -> int:
    """Extra px added to popup width on reply focus, from
    config('notification', 'reply_focus_expand_width')."""
    if config is not None:
        value = config.get("notification", "reply_focus_expand_width")
        if value is not None:
            try:
                return max(0, min(600, int(value)))
            except (TypeError, ValueError):
                pass
    return _REPLY_FOCUS_WIDTH_EXPAND_DEFAULT


def resolve_fade_ms(config=None) -> int:
    if config is not None:
        value = config.get("notification", "fade_ms")
        if value is not None:
            try:
                return max(50, min(2000, int(value)))
            except (TypeError, ValueError):
                pass
    return _FADE_DURATION_MS_DEFAULT


def resolve_duration_ms(config=None) -> int:
    """Auto-hide duration in ms, from config('notification', 'duration_ms')."""
    if config is not None:
        value = config.get("notification", "duration_ms")
        if value is not None:
            try:
                return max(1000, int(value))
            except (TypeError, ValueError):
                pass
    return NOTIFICATION_DURATION_MS_DEFAULT


def resolve_margin_x(config=None) -> int:
    """Side margin for left/right-positioned popups, from config('notification', 'margin_x')."""
    if config is not None:
        value = config.get("notification", "margin_x")
        if value is not None:
            try:
                return max(0, min(500, int(value)))
            except (TypeError, ValueError):
                pass
    return _NOTIFICATION_MARGIN_X_DEFAULT


def resolve_margin_top(config=None) -> int:
    """Top margin for the popup stack, from config('notification', 'margin_top')."""
    if config is not None:
        value = config.get("notification", "margin_top")
        if value is not None:
            try:
                return max(0, min(500, int(value)))
            except (TypeError, ValueError):
                pass
    return _NOTIFICATION_MARGIN_TOP_DEFAULT


def resolve_notification_width(config=None) -> int:
    """Base popup width in px, clamped to 50% of the primary screen. From config('ui', 'notification_width')."""
    value = config.get("ui", "notification_width") if config else None
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = _NOTIFICATION_DEFAULT_WIDTH
    screen_width = QApplication.primaryScreen().availableGeometry().width()
    return min(int(screen_width * 0.50), max(100, value))


def expanded_reply_width(config, base_width: int, screen_width: int) -> int:
    """Width while widened for reply focus, clamped to 80% of screen_width."""
    expand = _resolve_focus_expand_width(config)
    return max(base_width, min(int(screen_width * 0.8), base_width + expand))


def mute_bypass_mode(config, key: str) -> str:
    """Read notification.*_bypass_mute: off | default | duration."""
    if not config:
        return "off"
    value = config.get("notification", key)
    return value if value in ("default", "duration") else "off"




def resolve_margin_spacing(config) -> Tuple[int, int]:
    """(margin, spacing) for popup layouts, from config with shared defaults."""
    margin = (config.get("ui", "margins", "notification") if config else None) or 8
    spacing = (config.get("ui", "spacing", "widget_elements") if config else None) or 4
    return margin, spacing


def resolve_centered_style(config, section: str, key: str) -> str:
    """Shared 'inline' | 'center' resolution for reply/competition placement.
    Falls back to inline when notifications are already centered — a detached
    centered group would sit on the same X as the regular stack and overlap it."""
    if not config:
        return "inline"
    if (config.get("ui", "notification_position") or "").lower() == "center":
        return "inline"
    value = config.get(section, key)
    return value if value == "center" else "inline"

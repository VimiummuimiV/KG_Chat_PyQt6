"""Popup stack manager and the show_notification entry point."""

from typing import List, Optional

from ui.notification.notification_data import apply_mute_bypass, NotificationData
from ui.notification.notification_settings import (
    mute_bypass_mode,
    resolve_centered_style,
    resolve_duration_ms,
    resolve_margin_top,
    resolve_margin_x,
    resolve_notification_width,
)
from ui.notification.popup_notification import PopupNotification
from ui.notification.presence_popup import PresenceMiniPopup


class _PopupManager:

    def __init__(self):
        self.popups: List[PopupNotification] = []
        self.focused_popups: List[PopupNotification] = []  # detached for centered reply
        self.gap = 10
        self.config = None
        self.notification_mode = "stack"
        self.muted = False
        self._scroll_offset = 0
        self.emoticon_selector = None  # Single shared instance, created on first use

    def set_notification_mode(self, mode: str):
        """Set notification mode: 'stack', 'replace' or 'scroll'"""
        if mode in ["stack", "replace", "scroll"]:
            self.notification_mode = mode

    def scroll_by(self, delta: int):
        """Shift the notification stack in scroll mode; clamped in _position_and_cleanup"""
        if self.notification_mode != "scroll" or not self.popups:
            return
        self._scroll_offset = max(0, self._scroll_offset - delta)
        self.position_and_cleanup()

    def set_muted(self, muted: bool):
        """Set muted state"""
        self.muted = muted

    def show_presence(self, login: str, event_type: str = 'join', avatar_pixmap=None, config=None,
                      on_click=None, event_ts=None, cache=None, game_id=None, is_join=None):
        """Compact presence toast. When muted, only if tracked_bypass_mute.
        is_join kept for backward compat → maps to join/left."""
        if is_join is not None and event_type == 'join':
            event_type = 'join' if is_join else 'left'
        cfg = config or self.config
        if cfg is not None and cfg.get("user_tracker", "notifications") is False:
            return None
        mode = mute_bypass_mode(cfg, "tracked_bypass_mute")
        if mode == "off" and self.muted:
            return None
        self.config = cfg
        duration_ms = resolve_duration_ms(cfg)
        force_duration = mode == "duration"
        popup = PresenceMiniPopup(
            self, login, event_type=event_type, avatar_pixmap=avatar_pixmap,
            config=cfg, duration_ms=duration_ms,
            on_click=on_click, event_ts=event_ts, cache=cache, game_id=game_id,
            force_duration=force_duration,
        )
        self.popups.append(popup)
        self.position_and_cleanup()
        return popup


    def _competition_style(self) -> str:
        """competitions.notification_style: inline (default) | center."""
        return resolve_centered_style(self.config, "competitions", "notification_style")

    def show_notification(self, data: NotificationData, force: bool = False):
        """Create and show notification (unless muted). Mute-bypass modes per type.
        force=True skips mute checks (settings preview)."""
        if not force:
            if data.is_competition:
                key = "competitions_bypass_mute"
            elif data.is_mention or data.is_private:
                key = "mentions_bypass_mute"
            elif data.is_ban:
                key = "bans_bypass_mute"
            elif not data.is_system and not data.is_parser:
                key = "messages_bypass_mute"
            else:
                key = None
            if key is not None:
                if not apply_mute_bypass(data, self.muted, key):
                    return None
            elif self.muted:
                return None

        self.config = data.config

        # In replace mode, close existing notifications EXCEPT those with active reply fields
        if self.notification_mode == "replace":
            for popup in list(self.popups) + list(self.focused_popups):
                # Keep notifications with visible reply field
                if not popup.reply_field_visible:
                    popup.close_immediately()
                    (self.focused_popups if popup in self.focused_popups else self.popups).remove(popup)

        # Calculate width before creating popup (max 50% of screen)
        width = resolve_notification_width(self.config)

        popup = PopupNotification(data, self, width)
        if data.is_competition and self._competition_style() == "center":
            self.focused_popups.append(popup)
        else:
            self.popups.append(popup)
        self.position_and_cleanup()
        return popup

    def remove_popup(self, popup: PopupNotification):
        """Remove popup (from whichever list holds it) and reposition"""
        for lst in (self.popups, self.focused_popups):
            if popup in lst:
                lst.remove(popup)
        if not self.popups:
            self._scroll_offset = 0
        self.position_and_cleanup()

    def close_all(self):
        """Close all notifications"""
        for popup in list(self.popups) + list(self.focused_popups):
            popup.close_immediately()
        self.popups.clear()
        self.focused_popups.clear()
        self._scroll_offset = 0

    def close_by_tag(self, tag: str):
        """Close notifications with the given tag"""
        if not tag:
            return
        for popup in list(self.popups) + list(self.focused_popups):
            if getattr(popup.data, "tag", None) == tag:
                popup.animate_out(force=True)

    def find_by_tag(self, tag: str) -> Optional["PopupNotification"]:
        """Find an open notification by tag, for in-place content updates."""
        if not tag:
            return None
        return next((p for p in self.popups + self.focused_popups if getattr(p.data, "tag", None) == tag), None)

    def _popup_x(self, screen, position: str, popup_width: int) -> int:
        margin_x = resolve_margin_x(self.config)
        if position == "left":
            return screen.x() + margin_x
        if position == "right":
            return screen.x() + screen.width() - popup_width - margin_x
        return screen.x() + (screen.width() - popup_width) // 2

    def _stack_popups(self, popups, x_fn, start_y):
        """Shared top-down vertical stacking, used for both the side stack
        and the centered focused group. Returns the y past the last popup."""
        current_y = start_y
        for popup in popups:
            popup.move(x_fn(popup), current_y)
            current_y += popup.height() + self.gap
        return current_y

    def _group_height(self, popups):
        """(heights, total stacked height incl. gaps) for a group of popups."""
        heights = [p.height() for p in popups]
        return heights, sum(heights) + self.gap * max(0, len(heights) - 1)

    def _position_focused_popups(self):
        """Center the detached (reply-in-progress) popups as their own
        stacked group, so several open reply fields never overlap.
        Y is centered by default, adjustable via notification.reply_center_offset_y."""
        if not self.focused_popups:
            return
        screen = self.focused_popups[0].screen().availableGeometry()
        _, total_height = self._group_height(self.focused_popups)
        offset_y = self.config.get("notification", "reply_center_offset_y") if self.config else 0
        try:
            offset_y = int(offset_y or 0)
        except (TypeError, ValueError):
            offset_y = 0
        base_y = screen.y() + (screen.height() - total_height) // 2 + offset_y
        min_y = screen.y() + 20
        max_y = screen.y() + screen.height() - 20 - total_height
        start_y = max(min_y, min(base_y, max(min_y, max_y)))
        self._stack_popups(
            self.focused_popups,
            x_fn=lambda p: self._popup_x(screen, "center", p.width()),
            start_y=start_y,
        )

    def position_and_cleanup(self):
        """Position every popup group, then drop stack-mode overflow that doesn't fit."""
        self._position_focused_popups()
        self._position_popups()

    def _position_popups(self):
        """Stack the regular (non-focused) popups top-down at their configured edge."""
        if not self.popups:
            return

        screen = self.popups[0].screen().availableGeometry()
        position = self.config.get("ui", "notification_position") if self.config else "center"
        position = (position or "center").lower()

        margin_top = resolve_margin_top(self.config)
        heights, total_height = self._group_height(self.popups)
        available_height = screen.height() - margin_top - 20

        # In scroll mode, clamp offset instead of dropping popups
        if self.notification_mode == "scroll":
            max_offset = max(0, total_height - available_height)
            self._scroll_offset = min(self._scroll_offset, max_offset)

        start_y = screen.y() + margin_top - (self._scroll_offset if self.notification_mode == "scroll" else 0)
        self._stack_popups(self.popups, lambda p: self._popup_x(screen, position, p.width()), start_y)

        if self.notification_mode == "stack":
            self._cleanup_overflow(screen, position, heights, total_height, available_height, margin_top)

    def _cleanup_overflow(self, screen, position, heights, total_height, available_height, margin_top):
        """Drop the oldest popups without an active reply field until the stack fits."""
        while total_height > available_height and len(self.popups) > 1:
            # Find the oldest notification that doesn't have an active reply field
            removed = False
            for i, popup in enumerate(self.popups):
                if not popup.reply_field_visible:
                    # Remove this notification
                    self.popups.pop(i)
                    popup.close()
                    total_height -= (heights.pop(i) + self.gap)
                    removed = True
                    break

            # If all notifications have active reply fields, stop trying to remove
            if not removed:
                break

            # Reposition remaining popups
            self._stack_popups(self.popups, lambda p: self._popup_x(screen, position, p.width()), screen.y() + margin_top)


# Global manager
popup_manager = _PopupManager()


def show_notification(**kwargs):
    # Resolve duration from config (seconds → ms) when the caller didn't pass one.
    force = kwargs.pop("force", False)
    if "duration" not in kwargs:
        kwargs["duration"] = resolve_duration_ms(kwargs.get("config"))
    data = NotificationData(**kwargs)
    return popup_manager.show_notification(data, force=force)

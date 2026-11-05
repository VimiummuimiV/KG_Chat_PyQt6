"""Notification payload."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from ui.notification.notification_settings import mute_bypass_mode, NOTIFICATION_DURATION_MS_DEFAULT


@dataclass
class NotificationData:
    """Encapsulates all notification parameters to avoid code duplication"""
    title: str
    message: str
    duration: int = NOTIFICATION_DURATION_MS_DEFAULT
    xmpp_client: Optional[Any] = None
    cache: Optional[Any] = None
    config: Optional[Any] = None
    emoticon_manager: Optional[Any] = None
    local_message_callback: Optional[Callable] = None
    account: Optional[dict] = None
    window_show_callback: Optional[Callable] = None
    is_private: bool = False
    recipient_jid: Optional[str] = None
    room_jid: Optional[str] = None
    source_label: Optional[str] = None
    is_ban: bool = False
    is_system: bool = False
    is_parser: bool = False
    is_competition: bool = False
    is_mention: bool = False
    auto_hide_after_duration: bool = False
    timestamp: Optional[datetime] = None
    tag: Optional[str] = None
    players: Optional[list] = None
    competition_game_id: Optional[int] = None
    open_room_callback: Optional[Callable] = None
    profile_callback: Optional[Callable] = None  # username → open profile
    competition_entered_callback: Optional[Callable] = None  # game_id → remove chat message + close this notification
    icon: Optional[str] = None  # svg filename fallback avatar for non-user notifications


def apply_mute_bypass(data: NotificationData, muted: bool, key: str) -> bool:
    """Return True if notification may show. Sets auto_hide_after_duration on data."""
    mode = mute_bypass_mode(data.config, key)
    if mode == "off":
        return not muted
    if mode == "duration":
        data.auto_hide_after_duration = True
    return True

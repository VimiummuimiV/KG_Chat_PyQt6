"""Context menu for a username in chat / chatlog messages."""
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QMenu

from helpers.create import _render_svg_icon
from helpers.fonts import get_font, FontType

PROFILE = "profile"
PRIVATE = "private"
COPY_USERNAME = "copy_username"
COPY_ID = "copy_id"
TRACK = "track"
UNTRACK = "untrack"
BAN_PERMANENT = "ban_permanent"
BAN_TEMPORARY = "ban_temporary"
REMOVE_MESSAGE = "remove_message"
REMOVE_UP = "remove_up"
REMOVE_DOWN = "remove_down"
REMOVE_ALL = "remove_all"
REMOVE_PRESENCE = "remove_presence"


def show_message_user_context_menu(
    icons_path: Path,
    parent,
    global_pos,
    *,
    is_tracked: bool = False,
    show_track: bool = True,
    show_ban: bool = True,
    show_private: bool = True,
    show_message_removes: bool = True,
    show_presence_remove: bool = False,
) -> Optional[str]:
    def icon(name: str):
        return _render_svg_icon(icons_path / name, 16)

    menu = QMenu(parent)
    menu.setFont(get_font(FontType.UI))

    profile_act = menu.addAction(icon("user.svg"), "Profile")
    private_act = None
    if show_private:
        private_act = menu.addAction(icon("private-chat.svg"), "Private Chat")
    menu.addSeparator()

    copy_username_act = menu.addAction(icon("clipboard.svg"), "Copy username")
    copy_id_act = menu.addAction(icon("hashtag.svg"), "Copy ID")

    track_act = None
    if show_track:
        menu.addSeparator()
        if is_tracked:
            track_act = menu.addAction(icon("user-minus.svg"), "Untrack user")
        else:
            track_act = menu.addAction(icon("user-add.svg"), "Track user")

    perm_act = temp_act = None
    if show_ban:
        menu.addSeparator()
        perm_act = menu.addAction(icon("prohibited.svg"), "Ban permanently")
        temp_act = menu.addAction(icon("forbidden.svg"), "Ban temporarily")

    remove_msg_act = remove_up_act = remove_down_act = remove_all_act = presence_remove_act = None
    if show_presence_remove:
        menu.addSeparator()
        presence_remove_act = menu.addAction(icon("delete-back.svg"), "Remove this presence log")
    elif show_message_removes:
        menu.addSeparator()
        remove_msg_act = menu.addAction(icon("delete-back.svg"), "Remove this message")
        remove_up_act = menu.addAction(icon("delete-bin-up.svg"), "Remove from here upward")
        remove_down_act = menu.addAction(icon("delete-bin-down.svg"), "Remove from here downward")
        remove_all_act = menu.addAction(icon("delete-bin.svg"), "Remove all messages")

    chosen = menu.exec(global_pos)
    if chosen is None:
        return None
    if chosen is profile_act:
        return PROFILE
    if private_act is not None and chosen is private_act:
        return PRIVATE
    if chosen is copy_username_act:
        return COPY_USERNAME
    if chosen is copy_id_act:
        return COPY_ID
    if track_act is not None and chosen is track_act:
        return UNTRACK if is_tracked else TRACK
    if perm_act is not None and chosen is perm_act:
        return BAN_PERMANENT
    if temp_act is not None and chosen is temp_act:
        return BAN_TEMPORARY
    if presence_remove_act is not None and chosen is presence_remove_act:
        return REMOVE_PRESENCE
    if remove_msg_act is not None and chosen is remove_msg_act:
        return REMOVE_MESSAGE
    if remove_up_act is not None and chosen is remove_up_act:
        return REMOVE_UP
    if remove_down_act is not None and chosen is remove_down_act:
        return REMOVE_DOWN
    if remove_all_act is not None and chosen is remove_all_act:
        return REMOVE_ALL
    return None

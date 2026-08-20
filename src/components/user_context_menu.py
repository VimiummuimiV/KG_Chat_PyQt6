"""Shared context menu for user rows (general + game-room + chatlog userlists)."""
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QMenu

from helpers.create import _render_svg_icon
from helpers.fonts import get_font, FontType

# Action ids returned by show_user_context_menu
PROFILE = "profile"
PRIVATE = "private"
PASTE_USERNAME = "paste_username"
COPY_USERNAME = "copy_username"
COPY_ID = "copy_id"
FILTER = "filter"          # chatlog userlist: filter messages by this user
OPEN_GAME = "open_game"    # open game room chat for this user's game_id


def show_user_context_menu(
    icons_path: Path,
    parent,
    global_pos,
    *,
    has_game: bool = False,
    show_filter: bool = False,
) -> Optional[str]:
    """Show the user context menu and return the chosen action id, or None.

    has_game:    show "Open game chat" (user is in a race)
    show_filter: show "Filter" (chatlog userlist context)
    """

    def icon(name: str):
        return _render_svg_icon(icons_path / name, 16)

    menu = QMenu(parent)
    menu.setFont(get_font(FontType.UI))

    profile_act = menu.addAction(icon("user.svg"), "Profile")
    private_act = menu.addAction(icon("private-chat.svg"), "Private Chat")
    menu.addSeparator()

    paste_act = menu.addAction(icon("add-circle.svg"), "Paste Username")
    copy_username_act = menu.addAction(icon("clipboard.svg"), "Copy Username")
    copy_id_act = menu.addAction(icon("hashtag.svg"), "Copy ID")

    filter_act = None
    if show_filter:
        menu.addSeparator()
        filter_act = menu.addAction(icon("filter.svg"), "Filter")

    open_game_act = None
    if has_game:
        menu.addSeparator()
        open_game_act = menu.addAction(icon("play.svg"), "Open game chat")

    chosen = menu.exec(global_pos)
    if chosen is None:
        return None
    if chosen is profile_act:
        return PROFILE
    if chosen is private_act:
        return PRIVATE
    if chosen is paste_act:
        return PASTE_USERNAME
    if chosen is copy_username_act:
        return COPY_USERNAME
    if chosen is copy_id_act:
        return COPY_ID
    if filter_act is not None and chosen is filter_act:
        return FILTER
    if open_game_act is not None and chosen is open_game_act:
        return OPEN_GAME
    return None

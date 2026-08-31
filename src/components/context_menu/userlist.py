"""Context menu for userlist rows (general, game-room, chatlog)."""
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QMenu

from helpers.create import _render_svg_icon
from helpers.fonts import get_font, FontType
from helpers.translate import tr

PROFILE = "profile"
PRIVATE = "private"
PASTE_USERNAME = "paste_username"
COPY_USERNAME = "copy_username"
COPY_ID = "copy_id"
FILTER = "filter"
OPEN_GAME = "open_game"
TRACK = "track"
UNTRACK = "untrack"


def show_userlist_context_menu(
    icons_path: Path,
    parent,
    global_pos,
    *,
    has_game: bool = False,
    show_filter: bool = False,
    is_tracked: bool = False,
    show_track: bool = True,
    show_private: bool = True,
) -> Optional[str]:
    def icon(name: str):
        return _render_svg_icon(icons_path / name, 16)

    menu = QMenu(parent)
    menu.setFont(get_font(FontType.UI))

    profile_act = menu.addAction(icon("user.svg"), tr("Profile", "Профиль"))
    private_act = None
    if show_private:
        private_act = menu.addAction(icon("private-chat.svg"), tr("Private Chat", "Приватный чат"))
    menu.addSeparator()

    paste_act = menu.addAction(icon("add-circle.svg"), tr("Paste Username", "Вставить имя"))
    copy_username_act = menu.addAction(icon("clipboard.svg"), tr("Copy Username", "Копировать имя"))
    copy_id_act = menu.addAction(icon("hashtag.svg"), tr("Copy ID", "Копировать ID"))

    track_act = None
    if show_track:
        menu.addSeparator()
        if is_tracked:
            track_act = menu.addAction(icon("user-minus.svg"), tr("Untrack user", "Не Отслеживать"))
        else:
            track_act = menu.addAction(icon("user-add.svg"), tr("Track user", "Отслеживать"))

    filter_act = None
    if show_filter:
        menu.addSeparator()
        filter_act = menu.addAction(icon("filter.svg"), tr("Filter", "Фильтр"))

    open_game_act = None
    if has_game:
        menu.addSeparator()
        open_game_act = menu.addAction(icon("play.svg"), tr("Open game chat", "Открыть игровой чат"))

    chosen = menu.exec(global_pos)
    if chosen is None:
        return None
    if chosen is profile_act:
        return PROFILE
    if private_act is not None and chosen is private_act:
        return PRIVATE
    if chosen is paste_act:
        return PASTE_USERNAME
    if chosen is copy_username_act:
        return COPY_USERNAME
    if chosen is copy_id_act:
        return COPY_ID
    if track_act is not None and chosen is track_act:
        return UNTRACK if is_tracked else TRACK
    if filter_act is not None and chosen is filter_act:
        return FILTER
    if open_game_act is not None and chosen is open_game_act:
        return OPEN_GAME
    return None

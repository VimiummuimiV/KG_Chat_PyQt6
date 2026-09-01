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
BAN_PERMANENT = "ban_permanent"
BAN_TEMPORARY = "ban_temporary"
SET_PRONUNCIATION = "set_pronunciation"


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
    show_ban: bool = True,
    has_pronunciation: bool = False,
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
    menu.addSeparator()
    if show_track:
        if is_tracked:
            track_act = menu.addAction(icon("user-minus.svg"), tr("Untrack user", "Не Отслеживать"))
        else:
            track_act = menu.addAction(icon("user-add.svg"), tr("Track user", "Отслеживать"))

    if has_pronunciation:
        pronunciation_act = menu.addAction(icon("user-voice.svg"), tr("Edit Pronunciation", "Изменить произношение"))
    else:
        pronunciation_act = menu.addAction(icon("user-voice.svg"), tr("Set Pronunciation", "Задать произношение"))

    perm_act = temp_act = None
    if show_ban:
        menu.addSeparator()
        perm_act = menu.addAction(icon("prohibited.svg"), tr("Ban permanently", "Вечный бан"))
        temp_act = menu.addAction(icon("forbidden.svg"), tr("Ban temporarily", "Временный бан"))

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
    if perm_act is not None and chosen is perm_act:
        return BAN_PERMANENT
    if temp_act is not None and chosen is temp_act:
        return BAN_TEMPORARY
    if chosen is pronunciation_act:
        return SET_PRONUNCIATION
    if filter_act is not None and chosen is filter_act:
        return FILTER
    if open_game_act is not None and chosen is open_game_act:
        return OPEN_GAME
    return None
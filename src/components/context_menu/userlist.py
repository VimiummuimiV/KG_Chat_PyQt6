"""Context menu for userlist rows (general, game-room, chatlog)."""

from pathlib import Path
from typing import Optional

from components.button import render_svg_icon
from components.menu import create_menu
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
        return render_svg_icon(icons_path / name, 16)

    menu = create_menu(parent.window())  # not a child of the row: its filter highlight stylesheet would cascade into the menu

    profile_action = menu.addAction(icon("fill/user-3-fill.svg"), tr("Profile", "Профиль"))
    private_action = None
    if show_private:
        private_action = menu.addAction(icon("fill/chat-3-fill.svg"), tr("Private Chat", "Приватный чат"))
    menu.addSeparator()

    paste_action = menu.addAction(icon("fill/add-circle-fill.svg"), tr("Paste Username", "Вставить имя"))
    copy_username_action = menu.addAction(icon("fill/clipboard-fill.svg"), tr("Copy Username", "Копировать имя"))
    copy_id_action = menu.addAction(icon("line/hashtag-line.svg"), tr("Copy ID", "Копировать ID"))

    track_action = None
    menu.addSeparator()
    if show_track:
        if is_tracked:
            track_action = menu.addAction(icon("fill/user-minus-fill.svg"), tr("Untrack user", "Не Отслеживать"))
        else:
            track_action = menu.addAction(icon("fill/user-add-fill.svg"), tr("Track user", "Отслеживать"))

    if has_pronunciation:
        pronunciation_action = menu.addAction(icon("fill/user-voice-fill.svg"), tr("Edit Pronunciation", "Изменить произношение"))
    else:
        pronunciation_action = menu.addAction(icon("fill/user-voice-fill.svg"), tr("Set Pronunciation", "Задать произношение"))

    perm_action = temp_action = None
    if show_ban:
        menu.addSeparator()
        perm_action = menu.addAction(icon("fill/prohibited-fill.svg"), tr("Ban permanently", "Вечный бан"))
        temp_action = menu.addAction(icon("fill/forbid-fill.svg"), tr("Ban temporarily", "Временный бан"))

    filter_action = None
    if show_filter:
        menu.addSeparator()
        filter_action = menu.addAction(icon("fill/filter-2-fill.svg"), tr("Filter", "Фильтр"))

    open_game_action = None
    if has_game:
        menu.addSeparator()
        open_game_action = menu.addAction(icon("fill/play-large-fill.svg"), tr("Open game chat", "Открыть игровой чат"))

    chosen = menu.exec(global_pos)
    if chosen is None:
        return None
    if chosen is profile_action:
        return PROFILE
    if private_action is not None and chosen is private_action:
        return PRIVATE
    if chosen is paste_action:
        return PASTE_USERNAME
    if chosen is copy_username_action:
        return COPY_USERNAME
    if chosen is copy_id_action:
        return COPY_ID
    if track_action is not None and chosen is track_action:
        return UNTRACK if is_tracked else TRACK
    if perm_action is not None and chosen is perm_action:
        return BAN_PERMANENT
    if temp_action is not None and chosen is temp_action:
        return BAN_TEMPORARY
    if chosen is pronunciation_action:
        return SET_PRONUNCIATION
    if filter_action is not None and chosen is filter_action:
        return FILTER
    if open_game_action is not None and chosen is open_game_action:
        return OPEN_GAME
    return None

"""Context menu for a username in chat / chatlog messages."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QMenu

from components.button import render_svg_icon
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import tr


PROFILE = "profile"
PRIVATE = "private"
COPY_USERNAME = "copy_username"
COPY_ID = "copy_id"
TRACK = "track"
UNTRACK = "untrack"
BAN_PERMANENT = "ban_permanent"
BAN_TEMPORARY = "ban_temporary"
SET_PRONUNCIATION = "set_pronunciation"
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
    has_pronunciation: bool = False,
) -> Optional[str]:
    def icon(name: str):
        return render_svg_icon(icons_path / name, 16)

    menu = QMenu(parent)
    menu.setFont(get_font(FontType.UI))

    profile_action = menu.addAction(icon("fill/user-3-fill.svg"), tr("Profile", "Профиль"))
    private_action = None
    if show_private:
        private_action = menu.addAction(icon("fill/chat-3-fill.svg"), tr("Private chat", "Приватный чат"))
    menu.addSeparator()

    copy_username_action = menu.addAction(icon("fill/clipboard-fill.svg"), tr("Copy username", "Копировать имя"))
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

    remove_msg_action = remove_up_action = remove_down_action = remove_all_action = presence_remove_action = None
    if show_presence_remove:
        menu.addSeparator()
        presence_remove_action = menu.addAction(icon("fill/delete-back-fill.svg"), tr("Remove this presence log", "Удалить эту запись присутствия"))
    elif show_message_removes:
        menu.addSeparator()
        remove_msg_action = menu.addAction(icon("fill/delete-back-fill.svg"), tr("Remove this message", "Удалить это сообщение"))
        remove_up_action = menu.addAction(icon("fill/delete-bin-2-up-fill.svg"), tr("Remove from here upward", "Удалить отсюда вверх"))
        remove_down_action = menu.addAction(icon("fill/delete-bin-2-down-fill.svg"), tr("Remove from here downward", "Удалить отсюда вниз"))
        remove_all_action = menu.addAction(icon("fill/delete-bin-2-fill.svg"), tr("Remove all messages", "Удалить все сообщения"))

    chosen = menu.exec(global_pos)
    if chosen is None:
        return None
    if chosen is profile_action:
        return PROFILE
    if private_action is not None and chosen is private_action:
        return PRIVATE
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
    if presence_remove_action is not None and chosen is presence_remove_action:
        return REMOVE_PRESENCE
    if remove_msg_action is not None and chosen is remove_msg_action:
        return REMOVE_MESSAGE
    if remove_up_action is not None and chosen is remove_up_action:
        return REMOVE_UP
    if remove_down_action is not None and chosen is remove_down_action:
        return REMOVE_DOWN
    if remove_all_action is not None and chosen is remove_all_action:
        return REMOVE_ALL
    return None

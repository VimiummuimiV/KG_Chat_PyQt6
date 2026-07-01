"""Compact right-click context menu shared by userlist widgets.

Shows Profile / Private / Copy / Copy ID (+ optional Filter) actions for a
user. Used by both the live userlist (ui_userlist.py) and the chatlog
userlist (ui_chatlog_userlist.py) so the menu isn't built twice.
"""
from PyQt6.QtWidgets import QMenu

from helpers.create import _render_svg_icon

PROFILE = "profile"
PRIVATE = "private"
COPY = "copy"
COPY_ID = "copy_id"
FILTER = "filter"


def show_user_context_menu(icons_path, parent, global_pos, show_filter=False):
    """Show the compact user menu at global_pos.

    show_filter=True adds a "Filter" action (chatlog userlist only).
    Returns PROFILE, PRIVATE, COPY, COPY_ID, FILTER, or None (menu dismissed).
    """
    def icon(name):
        return _render_svg_icon(icons_path / name, 16)

    menu = QMenu(parent)
    profile_act = menu.addAction(icon("user.svg"), "Profile")
    private_act = menu.addAction(icon("private-chat.svg"), "Private Chat")
    copy_act = menu.addAction(icon("clipboard.svg"), "Copy Username")
    copy_id_act = menu.addAction(icon("hashtag.svg"), "Copy ID")
    filter_act = menu.addAction(icon("filter.svg"), "Filter by User") if show_filter else None

    act = menu.exec(global_pos)
    if act == profile_act:
        return PROFILE
    if act == private_act:
        return PRIVATE
    if act == copy_act:
        return COPY
    if act == copy_id_act:
        return COPY_ID
    if filter_act and act == filter_act:
        return FILTER
    return None
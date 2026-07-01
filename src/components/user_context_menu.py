"""Compact right-click context menu shared by userlist widgets.

Shows Profile / Private / Copy actions for a user. Used by both the live
userlist (ui_userlist.py) and the chatlog userlist (ui_chatlog_userlist.py)
so the menu isn't built twice.
"""
from PyQt6.QtWidgets import QMenu

from helpers.create import _render_svg_icon

PROFILE = "profile"
PRIVATE = "private"
COPY = "copy"


def show_user_context_menu(icons_path, parent, global_pos):
    """Show the compact user menu at global_pos.

    Returns PROFILE, PRIVATE, COPY, or None (menu dismissed without a choice).
    """
    def icon(name):
        return _render_svg_icon(icons_path / name, 16)

    menu = QMenu(parent)
    profile_act = menu.addAction(icon("user.svg"), "Profile")
    private_act = menu.addAction(icon("private-chat.svg"), "Private")
    copy_act = menu.addAction(icon("clipboard.svg"), "Copy")

    act = menu.exec(global_pos)
    if act == profile_act:
        return PROFILE
    if act == private_act:
        return PRIVATE
    if act == copy_act:
        return COPY
    return None
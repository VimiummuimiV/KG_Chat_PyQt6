"""Menus in the UI font."""

from PyQt6.QtWidgets import QMenu, QWidget

from helpers.fonts.fonts import FontType, set_font_role


def create_menu(parent: QWidget | None = None) -> QMenu:
    """A menu in the UI font: menus are windows and do not inherit the font of their parent."""
    menu = QMenu(parent)
    set_font_role(menu, FontType.UI)
    return menu


def add_submenu(parent_menu: QMenu) -> QMenu:
    """A submenu in the UI font; QMenu.addMenu would create one without it."""
    submenu = create_menu(parent_menu)
    parent_menu.addMenu(submenu)
    return submenu

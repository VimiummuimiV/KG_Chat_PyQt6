"""Shared presence event badge (join / left / game)."""
from typing import Optional
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt
from helpers.fonts import get_font, FontType

_STYLES = {
    "join": ("JOIN", "#2d6a4f", "#d8f3dc"),
    "left": ("LEFT", "#6a2d2d", "#f3d8d8"),
    "game": ("GAME", "#1d4e89", "#cfe2ff"),
}


def presence_badge_style(event_type: str) -> tuple:
    return _STYLES.get(event_type, _STYLES["left"])


def make_presence_badge(event_type: str) -> QLabel:
    text, bg, fg = presence_badge_style(event_type)
    badge = QLabel(text)
    badge.setFont(get_font(FontType.UI))
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"QLabel {{ background: {bg}; color: {fg}; border-radius: 4px; padding: 2px 6px; }}"
    )
    return badge


def make_game_id_label(event_type: str, game_id) -> Optional[QLabel]:
    """#game_id label for game events, or None."""
    if not game_id or event_type != "game":
        return None
    label = QLabel(f"#{game_id}")
    label.setFont(get_font(FontType.UI))
    label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    label.setStyleSheet("color: #888;")
    return label

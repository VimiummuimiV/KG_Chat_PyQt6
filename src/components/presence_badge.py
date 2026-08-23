"""Shared presence event badge (join / left / game)."""
from typing import Optional, Tuple
from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, pyqtSignal
from helpers.fonts import get_font, FontType

# text, background, foreground — single source for pills and counters
_STYLES = {
    "join": ("JOIN", "#2d6a4f", "#d8f3dc"),
    "left": ("LEFT", "#6a2d2d", "#f3d8d8"),
    "game": ("GAME", "#1d4e89", "#cfe2ff"),
}

EVENT_TYPES = ("join", "left", "game")


def presence_badge_style(event_type: str) -> Tuple[str, str, str]:
    return _STYLES.get(event_type, _STYLES["left"])


def _pill_css(bg: str, fg: str) -> str:
    return (
        f"QLabel {{ background: {bg}; color: {fg}; border-radius: 4px; "
        f"padding: 2px 6px; border: none; }}"
    )


def _counter_css(bg: str, fg: str) -> str:
    return (
        f"QLabel {{ background: {bg}; color: {fg}; border-radius: 3px; "
        f"padding: 0 3px; font-size: 9px; font-weight: bold; border: none; }}"
    )


def make_presence_badge(event_type: str) -> QLabel:
    text, bg, fg = presence_badge_style(event_type)
    badge = QLabel(text)
    badge.setFont(get_font(FontType.UI))
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(_pill_css(bg, fg))
    return badge


def apply_counter_style(label: QLabel, event_type: str = "join"):
    """Style a small unread counter with the same palette as presence badges."""
    _, bg, fg = presence_badge_style(event_type or "join")
    label.setStyleSheet(_counter_css(bg, fg))


def set_badge_active(badge: QLabel, active: bool, dim: float = 0.4):
    """Dim inactive filter pills; full opacity when active."""
    if active:
        badge.setGraphicsEffect(None)
    else:
        effect = QGraphicsOpacityEffect(badge)
        effect.setOpacity(dim)
        badge.setGraphicsEffect(effect)


class TypeFilterBadge(QLabel):
    """Colored JOIN/LEFT/GAME pill toggle for the tracker filter panel."""
    clicked = pyqtSignal(str, bool)  # event_type, ctrl_pressed

    def __init__(self, event_type: str):
        text, bg, fg = presence_badge_style(event_type)
        super().__init__(text)
        self.event_type = event_type
        self._active = False
        self.setFont(get_font(FontType.UI))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_pill_css(bg, fg))
        set_badge_active(self, False)

    def set_active(self, active: bool):
        self._active = bool(active)
        set_badge_active(self, self._active)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.clicked.emit(self.event_type, ctrl)
        super().mousePressEvent(event)


def make_game_id_label(event_type: str, game_id) -> Optional[QLabel]:
    if not game_id or event_type != "game":
        return None
    label = QLabel(f"#{game_id}")
    label.setFont(get_font(FontType.UI))
    label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    label.setStyleSheet("color: #888; border: none;")
    return label

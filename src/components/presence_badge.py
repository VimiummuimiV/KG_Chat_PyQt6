"""Shared presence event badge (join / left / game)."""
from typing import Optional, Tuple, Iterable, Set
from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect, QWidget, QHBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal
from helpers.fonts import get_font, FontType
from helpers.color_utils import tinted_chip_colors, hex_to_rgb, rgb_to_hsl, hsl_to_rgb, rgb_to_hex

# text, base accent color — bg/fg/border derived via tinted_chip_colors
_STYLES = {
    "join": ("JOIN", "#2d6a4f"),
    "left": ("LEFT", "#6a2d2d"),
    "game": ("GAME", "#1d4e89"),
}

EVENT_TYPES = ("join", "left", "game")


def _lighten_hex(base_hex: str, lightness: float = 0.90) -> str:
    h, s, _ = rgb_to_hsl(hex_to_rgb(base_hex))
    return rgb_to_hex(hsl_to_rgb((h, min(1.0, s * 0.55), lightness)))


def presence_badge_style(event_type: str, is_dark: bool = True) -> Tuple[str, str, str, str]:
    """Return (text, bg, fg, border) for a presence badge."""
    text, base = _STYLES.get(event_type, _STYLES["left"])
    bg, fg, border = tinted_chip_colors(base, is_dark)
    return text, bg, fg, border


def _pill_css(bg: str, fg: str, border: str) -> str:
    return (
        f"QLabel {{ background: {bg}; color: {fg}; border-radius: 4px; "
        f"padding: 2px 6px; border: 2px solid {border}; }}"
    )


def _counter_css(bg: str, fg: str, font_size: int = 9) -> str:
    return (
        f"QLabel {{ background: {bg}; color: {fg}; border-radius: 3px; "
        f"padding: 0 3px; font-size: {font_size}px; font-weight: bold; border: none; }}"
    )


def make_presence_badge(event_type: str, is_dark: bool = True) -> QLabel:
    text, bg, fg, border = presence_badge_style(event_type, is_dark)
    badge = QLabel(text)
    badge.setFont(get_font(FontType.UI))
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(_pill_css(bg, fg, border))
    return badge


def apply_counter_style(label: QLabel, event_type: str = "join", font_size: int = 9,
                        is_dark: bool = True):
    """Style the small unread counter with solid base fill and lightened text."""
    _, base = _STYLES.get(event_type or "join", _STYLES["join"])
    label.setStyleSheet(_counter_css(base, _lighten_hex(base), max(8, min(18, int(font_size)))))


def toggle_filter_value(current: Set[str], value: str, ctrl_pressed: bool, always_multi: bool = False) -> Set[str]:
    """Shared single-click-exclusive / ctrl-multi-toggle semantics for filter sets."""
    if ctrl_pressed or always_multi:
        updated = set(current)
        if value in updated:
            updated.discard(value)
        else:
            updated.add(value)
        return updated
    return set() if current == {value} else {value}


def set_badge_active(badge: QLabel, active: bool, dim: float = 0.4):
    """Dim inactive filter pills; full opacity when active."""
    if active:
        badge.setGraphicsEffect(None)
    else:
        effect = QGraphicsOpacityEffect(badge)
        effect.setOpacity(dim)
        badge.setGraphicsEffect(effect)


class TypeFilterBadge(QLabel):
    """Colored JOIN/LEFT/GAME pill toggle."""
    clicked = pyqtSignal(str, bool)  # event_type, ctrl_pressed

    def __init__(self, event_type: str, is_dark: bool = True):
        text, bg, fg, border = presence_badge_style(event_type, is_dark)
        super().__init__(text)
        self.event_type = event_type
        self._active = False
        self._is_dark = is_dark
        self.setFont(get_font(FontType.UI))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_pill_css(bg, fg, border))
        set_badge_active(self, False)

    def set_active(self, active: bool):
        self._active = bool(active)
        set_badge_active(self, self._active)

    def is_active(self) -> bool:
        return self._active

    def update_theme(self, is_dark: bool):
        self._is_dark = is_dark
        _, bg, fg, border = presence_badge_style(self.event_type, is_dark)
        self.setStyleSheet(_pill_css(bg, fg, border))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.clicked.emit(self.event_type, ctrl)
        super().mousePressEvent(event)


class TypeFilterBar(QWidget):
    """Row of JOIN/LEFT/GAME toggles. Reused by tracker filter panel and settings.

    empty_means_all: filter mode — empty active set means all types pass.
    Otherwise settings mode — active set is the enabled types (default all).
    """
    changed = pyqtSignal(object)  # set[str]

    def __init__(self, parent=None, *, empty_means_all: bool = True, is_dark: bool = True):
        super().__init__(parent)
        self.empty_means_all = empty_means_all
        self._is_dark = is_dark
        self._active: Set[str] = set()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.badges = {}
        for et in EVENT_TYPES:
            badge = TypeFilterBadge(et, is_dark=is_dark)
            badge.clicked.connect(self._on_click)
            self.badges[et] = badge
            layout.addWidget(badge)
        layout.addStretch()
        self._sync()

    def active_types(self) -> Set[str]:
        return set(self._active)

    def set_active_types(self, types: Iterable[str]):
        self._active = {t for t in types if t in EVENT_TYPES}
        self._sync()

    def update_theme(self, is_dark: bool):
        self._is_dark = is_dark
        for badge in self.badges.values():
            badge.update_theme(is_dark)

    def _sync(self):
        for et, badge in self.badges.items():
            badge.set_active(et in self._active)

    def _on_click(self, event_type: str, ctrl_pressed: bool):
        self._active = toggle_filter_value(
            self._active, event_type, ctrl_pressed, always_multi=not self.empty_means_all
        )
        self._sync()
        self.changed.emit(self.active_types())


def make_game_id_label(event_type: str, game_id) -> Optional[QLabel]:
    if not game_id or event_type != "game":
        return None
    label = QLabel(f"#{game_id}")
    label.setFont(get_font(FontType.UI))
    label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    label.setStyleSheet("color: #888; border: none;")
    return label

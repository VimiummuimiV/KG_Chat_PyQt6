"""Avatar helpers: rounded real avatar, or a theme-colored SVG placeholder."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QLabel

from components.button import render_svg_icon
from helpers.load import make_rounded_pixmap


def _svg_avatar_pixmap(icons_path, size: int, color=None, icon_name: str = "user.svg"):
    """Fallback icon pixmap rendered at the given size."""
    icon = render_svg_icon(icons_path / icon_name, size, color) if color is not None \
        else render_svg_icon(icons_path / icon_name, size)
    return icon.pixmap(QSize(size, size))


def make_avatar_label(size: int = 36) -> QLabel:
    """Styled, fixed-size avatar placeholder shared by all popup layouts."""
    label = QLabel()
    label.setFixedSize(size, size)
    label.setStyleSheet("background: transparent; border: none; padding: 0; margin: 0;")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def make_avatar_pixmap(icons_path, raw_pixmap, size: int = 36, svg_size: int = 24, color=None, icon_name: str = "user.svg"):
    """Rounded real avatar if one is available, else the SVG fallback icon."""
    if raw_pixmap is not None and not raw_pixmap.isNull():
        return make_rounded_pixmap(raw_pixmap, size, 8)
    return _svg_avatar_pixmap(icons_path, svg_size, color, icon_name)

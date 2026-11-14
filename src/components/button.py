import math
import re
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QEasingCurve, QPointF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QPushButton


# Global state
_icon_registry = []
is_dark_theme = True

# Theme accent colors
_COLOR_DARK  = "#e28743"
_COLOR_LIGHT = "#154c79"
COLOR_GRAY  = "#888888"

# Icon bounce animation: (position, scale) keyframes between a start and end scale of 1.0
_BOUNCE_DURATION_MS = 440
_BOUNCE_KEYFRAMES = ((0.16, 1.48), (0.38, 0.82), (0.62, 1.14))
_BOUNCE_PEAK_SCALE = max(scale for _, scale in _BOUNCE_KEYFRAMES)


def set_theme(is_dark: bool):
    """Set current theme state"""
    global is_dark_theme
    is_dark_theme = is_dark


def register_icon_button(button) -> None:
    """Track a button so its icon is re-rendered on theme change."""
    _icon_registry.append(button)


def get_accent_color() -> str:
    """Accent color of the current theme."""
    return _COLOR_DARK if is_dark_theme else _COLOR_LIGHT


def get_user_svg_color(is_known: bool, is_dark: bool) -> str:
    """SVG icon color: theme accent for known users, gray for unknown."""
    return (_COLOR_DARK if is_dark else _COLOR_LIGHT) if is_known else COLOR_GRAY


def render_svg_icon(svg_file: Path, icon_size: int, color: str = None, stroke_width: float = None):
    """Render SVG file to QIcon with given or current-theme color, optionally overriding stroke-width."""
    if not svg_file.exists():
        return QIcon()

    with open(svg_file, 'r') as f:
        svg = f.read()

    color = color or get_accent_color()
    for attr in ('fill', 'stroke'):  # skip "none" - it means don't paint this channel
        svg = re.sub(rf'{attr}="(?!none")[^"]*"', f'{attr}="{color}"', svg)

    if stroke_width is not None:
        svg = re.sub(r'stroke-width="[^"]*"', f'stroke-width="{stroke_width}"', svg)

    renderer = QSvgRenderer()
    renderer.load(svg.encode('utf-8'))

    if isinstance(icon_size, int):
        icon_size = QSize(icon_size, icon_size)

    pixmap = QPixmap(icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)

def get_button_sizes(size_type: str = "large", config=None) -> tuple[int, int]:
    """Return (icon size, button size) of an icon button: the defaults, overridden by the config."""
    icon_size = 30 if size_type == "large" else 20
    button_size = 48 if size_type == "large" else 32

    # Safely read from config using .get()
    if config and hasattr(config, "get"):
        button_config = config.get("ui", "buttons") or {}
        if isinstance(button_config, dict):
            icon_size = button_config.get("icon_size", icon_size)
            button_size = button_config.get("button_size", button_size)
    return icon_size, button_size


def create_icon_button(
    icons_path: Path,
    icon_name: str,
    tooltip: str = "",
    size_type: str = "large",
    config=None
):
    """Create icon button using sizes from config"""
    button = QPushButton()
    icon_size, button_size = get_button_sizes(size_type, config)

    # Apply
    button.icon_path = icons_path
    button.icon_size = icon_size

    set_button_icon(button, icon_name)
    button.setIconSize(QSize(icon_size, icon_size))
    button.setFixedSize(button_size, button_size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)

    register_icon_button(button)
    return button


def set_button_icon(button, icon_name: str) -> None:
    """Switch an icon button to another icon; the name is kept so theme changes re-render it."""
    button._icon_name = icon_name
    button.setIcon(render_svg_icon(button.icon_path / icon_name, button.icon_size))


def animate_button_bounce(button: QPushButton) -> None:
    """Pop and bounce the button's own icon; frames are repainted inside a fixed-size icon so Qt never re-centers it."""
    previous = getattr(button, "_bounce_animation", None)
    if previous is not None:
        previous.stop()
        previous.deleteLater()

    icon_size = button.icon_size
    canvas_size = icon_size + 2 * math.ceil(icon_size * (_BOUNCE_PEAK_SCALE - 1) / 2)  # same parity as icon_size
    source = render_svg_icon(button.icon_path / button._icon_name, canvas_size).pixmap(canvas_size, canvas_size)
    center = canvas_size / 2

    def paint_frame(scale: float) -> None:
        canvas = QPixmap(canvas_size, canvas_size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(center, center)
        painter.scale(scale * icon_size / canvas_size, scale * icon_size / canvas_size)
        painter.drawPixmap(QPointF(-center, -center), source)
        painter.end()
        button.setIcon(QIcon(canvas))

    def restore_icon() -> None:
        set_button_icon(button, button._icon_name)
        button.setIconSize(QSize(icon_size, icon_size))

    animation = QVariantAnimation(button)
    animation.setDuration(_BOUNCE_DURATION_MS)
    animation.setStartValue(1.0)
    for position, scale in _BOUNCE_KEYFRAMES:
        animation.setKeyValueAt(position, scale)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.valueChanged.connect(paint_frame)
    animation.finished.connect(restore_icon)
    button._bounce_animation = animation
    button.setIconSize(QSize(canvas_size, canvas_size))
    animation.start()


def create_disabled_icon(icons_path: Path, icon_name: str, icon_size: int) -> QIcon:
    """Render an icon in the muted gray tone used for a disabled button state"""
    return render_svg_icon(icons_path / icon_name, icon_size, color=COLOR_GRAY)


def set_visual_active(widget, is_active: bool, opacity: float = 0.5):
    """Dim widget when inactive"""
    if widget is None:
        return
    widget._is_visually_active = is_active
    if is_active:
        widget.setGraphicsEffect(None)
    else:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(opacity)
        widget.setGraphicsEffect(effect)


class HoverIconButton(QPushButton):
    """Icon button that changes icon on hover"""

    def __init__(self, icons_path: Path, normal_icon: str, hover_icon: str,
                 tooltip: str = "", icon_size: int = 30, button_size: int = 48):
        super().__init__()

        self.icon_path = icons_path
        self._normal_icon = normal_icon
        self._hover_icon = hover_icon
        self.icon_size = icon_size
        self._hovered = False

        self.setIconSize(QSize(icon_size, icon_size))
        self.setFixedSize(button_size, button_size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

        self._update_icon()
        register_icon_button(self)

    def _update_icon(self):
        """Update icon based on hover state"""
        set_button_icon(self, self._hover_icon if self._hovered else self._normal_icon)

    def enterEvent(self, event):
        self._hovered = True
        self._update_icon()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._update_icon()
        super().leaveEvent(event)


def update_all_icons():
    """Update all registered icon buttons when theme changes"""
    _icon_registry[:] = [btn for btn in _icon_registry if not sip.isdeleted(btn)]

    for button in _icon_registry:
        if hasattr(button, 'icon_path') and hasattr(button, '_icon_name'):
            set_button_icon(button, button._icon_name)

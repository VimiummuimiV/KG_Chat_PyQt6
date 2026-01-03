from pathlib import Path
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtSvg import QSvgRenderer
from PyQt6 import sip


# Global state
_icon_registry = []
_is_dark_theme = True


def set_theme(is_dark: bool):
    """Set current theme state"""
    global _is_dark_theme
    _is_dark_theme = is_dark


def _render_svg_icon(svg_file: Path, icon_size: int):
    """Render SVG file to QIcon with current theme color"""
    if not svg_file.exists():
        return QIcon()
    
    with open(svg_file, 'r') as f:
        svg = f.read()
    
    color = "#e28743" if _is_dark_theme else "#154c79"
    svg = svg.replace('fill="currentColor"', f'fill="{color}"')
    
    renderer = QSvgRenderer()
    renderer.load(svg.encode('utf-8'))
    pixmap = QPixmap(icon_size, icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    
    return QIcon(pixmap)


def create_icon_button(
        icons_path: Path,
        icon_name: str,
        tooltip: str = "",
        icon_size: int = 30,
        button_size: int = 48
    ):
    """Create icon button with auto-colorized icon"""
    button = QPushButton()
    
    # Store metadata for updates
    button._icon_path = icons_path
    button._icon_name = icon_name
    button._icon_size = icon_size
    
    # Set icon
    button.setIcon(_render_svg_icon(icons_path / icon_name, icon_size))
    button.setIconSize(QSize(icon_size, icon_size))
    button.setFixedSize(button_size, button_size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    
    if tooltip:
        button.setToolTip(tooltip)
    
    _icon_registry.append(button)
    return button


def update_all_icons():
    """Update all registered icon buttons when theme changes"""
    global _icon_registry
    _icon_registry = [btn for btn in _icon_registry if not sip.isdeleted(btn)]
    
    for button in _icon_registry:
        if hasattr(button, '_icon_path') and hasattr(button, '_icon_name'):
            icon = _render_svg_icon(button._icon_path / button._icon_name, button._icon_size)
            button.setIcon(icon)
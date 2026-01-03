from pathlib import Path
from PyQt6.QtWidgets import QPushButton, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtSvg import QSvgRenderer


def colorize_svg_icon(
        icons_path: Path,
        icon_name: str,
        icon_size: int = 30,
        is_dark_theme: bool = None
    ):
    # Read and colorize SVG
    with open(icons_path / icon_name, 'r') as f:
        svg = f.read()
    
    # Determine theme
    if is_dark_theme is None:
        app = QApplication.instance()
        is_dark_theme = app.palette().window().color().lightness() < 128 if app else True
    
    color = "#e28743" if is_dark_theme else "#154c79"
    svg = svg.replace('fill="currentColor"', f'fill="{color}"')
    
    # Render to pixmap
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
        button_size: int = 48,
        is_dark_theme: bool = None
    ):
    button = QPushButton()
    
    # Use the helper to get colorized icon
    icon = colorize_svg_icon(icons_path, icon_name, icon_size, is_dark_theme)
    
    button.setIcon(icon)
    button.setIconSize(QSize(icon_size, icon_size))
    button.setFixedSize(button_size, button_size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    
    if tooltip:
        button.setToolTip(tooltip)
    
    return button


def update_icon_button(
        button: QPushButton,
        icons_path: Path,
        icon_name: str,
        tooltip: str = "",
        icon_size: int = 30,
        is_dark_theme: bool = None
    ):
    # Use the helper to get colorized icon
    icon = colorize_svg_icon(icons_path, icon_name, icon_size, is_dark_theme)
    
    button.setIcon(icon)
    if tooltip:
        button.setToolTip(tooltip)
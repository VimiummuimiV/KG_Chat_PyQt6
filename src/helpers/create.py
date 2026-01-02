from pathlib import Path
from PyQt6.QtWidgets import QPushButton, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtSvg import QSvgRenderer


def colorize_svg_icon(icons_path: Path, icon_name: str, icon_size: int = 30):
    """Helper function to colorize SVG and return a QIcon"""
    # Read and colorize SVG
    with open(icons_path / icon_name, 'r') as f:
        svg = f.read()
    
    # Detect theme and set orange color
    app = QApplication.instance()
    is_dark = app.palette().window().color().lightness() < 128 if app else True
    color = "#ffa726" if is_dark else "#e67e22"  # Light orange for dark theme, dark orange for light theme
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


def create_icon_button(icons_path: Path, icon_name: str, tooltip: str = "", icon_size: int = 30, button_size: int = 48):
    """Create a new button with colorized icon"""
    button = QPushButton()
    
    # Use the helper to get colorized icon
    icon = colorize_svg_icon(icons_path, icon_name, icon_size)
    
    button.setIcon(icon)
    button.setIconSize(QSize(icon_size, icon_size))
    button.setFixedSize(button_size, button_size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    
    if tooltip:
        button.setToolTip(tooltip)
    
    return button


def update_icon_button(button: QPushButton, icons_path: Path, icon_name: str, tooltip: str = "", icon_size: int = 30):
    """Update an existing button's icon with proper colorization"""
    # Use the helper to get colorized icon
    icon = colorize_svg_icon(icons_path, icon_name, icon_size)
    
    button.setIcon(icon)
    if tooltip:
        button.setToolTip(tooltip)
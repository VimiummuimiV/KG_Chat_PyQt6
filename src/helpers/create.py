from pathlib import Path
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize


def create_icon_button(icons_path: Path, icon_name: str, tooltip: str = "", icon_size: int = 30, button_size: int = 48):
    button = QPushButton()
    button.setIcon(QIcon(str(icons_path / icon_name)))
    button.setIconSize(QSize(icon_size, icon_size))
    button.setFixedSize(button_size, button_size)
    if tooltip:
        button.setToolTip(tooltip)
    return button
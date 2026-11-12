"""QLabel painted in an arbitrary data color (e.g. a username color) without a per-widget stylesheet."""

from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QLabel


class ColoredLabel(QLabel):
    """Plain-text label whose color is data, not a theme token, so it stays out of the stylesheet."""

    def __init__(self, text: str = "", color: str = "#FFFFFF"):
        super().__init__(text)
        self._color = QColor(color)

    def set_text_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self._color)
        painter.drawText(self.contentsRect(), self.alignment().value, self.text())

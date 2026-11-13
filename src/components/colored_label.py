"""QLabel painted in an arbitrary data color (e.g. a username color) without a per-widget stylesheet."""

from PyQt6.QtCore import Qt
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
        rect = self.contentsRect()
        if self.frameWidth():  # QLabel insets its text by half an "x" inside a frame
            inset = self.fontMetrics().horizontalAdvance("x") // 2
            if self.alignment() & Qt.AlignmentFlag.AlignLeft:
                rect.setLeft(rect.left() + inset)
            elif self.alignment() & Qt.AlignmentFlag.AlignRight:
                rect.setRight(rect.right() - inset)
        painter.drawText(rect, self.alignment().value, self.text())

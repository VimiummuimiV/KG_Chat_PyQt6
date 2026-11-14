"""Bounce counter of the pets: a button-looking block in the top left corner of the message area."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QPushButton, QWidget

from components.button import get_accent_color, get_button_sizes
from helpers.fonts.fonts import get_display_font


CORNER_MARGIN = 8  # between a corner button and the edge of the message area
_FONT_SHARE = 0.75  # of the icon size of a button: the digits are as big as its icons
_PADDING_SHARE = 0.4  # of the icon size, each side of a long text


class BounceCounter(QPushButton):
    """Shows the bounces of the running throw in the look of the buttons; the mouse passes through it."""

    def __init__(self, parent: QWidget, config):
        super().__init__(parent)
        self._icon_size, self._button_size = get_button_sizes("large", config)
        self._value = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self._button_size, self._button_size)
        self.hide()

    def set_value(self, value: str) -> None:
        """Show value, widening the block for a long one."""
        if value == self._value:
            return
        self._value = value
        padding = round(self._icon_size * _PADDING_SHARE)
        width = QFontMetrics(self._value_font()).horizontalAdvance(value) + 2 * padding
        self.setFixedWidth(max(self._button_size, width))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setFont(self._value_font())
        painter.setPen(QColor(get_accent_color()))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._value)

    def _value_font(self) -> QFont:
        return get_display_font(round(self._icon_size * _FONT_SHARE))

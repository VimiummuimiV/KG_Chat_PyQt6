"""Scoreboard of the pet throws: a panel hanging from the top edge of the message area with the previous record and the running bounces."""

from typing import Callable

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QFrame, QPushButton, QWidget

from components.button import COLOR_GRAY, get_accent_color, get_button_sizes
from helpers.fonts.fonts import get_display_font


_FONT_SHARE = 0.75  # of the icon size of a button: the digits are as big as its icons
_PADDING_SHARE = 0.4  # of the icon size, each side of a long text
_BOARD_PADDING = 8  # between the panel edge and the cells
_OVERHANG = 16  # of the panel above the window edge, clipped there, so its top corners never show
_CELL_GAP = 6


class _ScoreCell(QPushButton):
    """One indicator in the look of the buttons; the mouse passes through it."""

    def __init__(self, parent: QWidget, config, get_color: Callable[[], QColor | str]):
        super().__init__(parent)
        self._icon_size, self._button_size = get_button_sizes("large", config)
        self._get_color = get_color
        self._value = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self._button_size, self._button_size)

    def set_value(self, value: str) -> None:
        """Show value, widening the cell for a long one."""
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
        painter.setPen(QColor(self._get_color()))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._value)

    def _value_font(self) -> QFont:
        return get_display_font(round(self._icon_size * _FONT_SHARE))


class BounceScoreboard(QFrame):
    """Shows the running bounces in the accent color, with the previous record in gray to its left once there is one."""

    def __init__(self, parent: QWidget, config):
        super().__init__(parent)
        self.setObjectName("petScoreboard")
        self._record_cell = _ScoreCell(self, config, lambda: COLOR_GRAY)
        self._count_cell = _ScoreCell(self, config, get_accent_color)
        self._zone = QRect()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def set_values(self, record: str, count: str) -> None:
        """Show count; record is the previous record, empty when there is none."""
        self._record_cell.setVisible(bool(record))
        self._record_cell.set_value(record)
        self._count_cell.set_value(count)
        self._arrange()

    def center_in(self, zone: QRect) -> None:
        """Hang the panel from the top edge of zone, in the middle of it; zone starts at the window edge."""
        self._zone = zone
        self._arrange()

    def _arrange(self) -> None:
        cells = [cell for cell in (self._record_cell, self._count_cell) if not cell.isHidden()]
        width = sum(cell.width() for cell in cells) + _CELL_GAP * (len(cells) - 1) + 2 * _BOARD_PADDING
        self.setFixedSize(width, self._count_cell.height() + 2 * _BOARD_PADDING + _OVERHANG)
        left = _BOARD_PADDING
        for cell in cells:
            cell.move(left, _BOARD_PADDING + _OVERHANG)
            left += cell.width() + _CELL_GAP
        self.move(self._zone.x() + (self._zone.width() - width) // 2, self._zone.y() - _OVERHANG)

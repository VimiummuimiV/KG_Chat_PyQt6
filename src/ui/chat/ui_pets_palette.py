"""Colors of the pet score: gold for the new one, brown for the beaten one, shared by the record effect and the scoreboard."""

from dataclasses import dataclass

from PyQt6.QtGui import QColor


@dataclass(frozen=True)
class LetteringPalette:
    """Colors of lettering with volume: face gradient from light to dark, the side, the rim."""

    light: QColor
    middle: QColor
    dark: QColor
    side: QColor
    rim: QColor


GOLD = LetteringPalette(QColor("#fff6b8"), QColor("#ffd23f"), QColor("#e09a10"), QColor("#8c5a0a"), QColor("#4a2c05"))
BROWN = LetteringPalette(QColor("#c99a6b"), QColor("#a0693a"), QColor("#6f4220"), QColor("#3d2210"), QColor("#24120a"))

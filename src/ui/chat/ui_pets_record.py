"""Record effect over the pet area: a trophy pulses in, confetti bursts out, the new score shines under it."""

import math
import random
from dataclasses import dataclass

from PyQt6.QtCore import QEasingCurve, QPointF, QRect, QRectF, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QWidget

from helpers.data import get_resource_dir
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import tr


_MILLISECONDS = 1000
_DURATION_MS = 3400
_BURST_MS = 300  # the trophy reaches its first peak and the confetti flies
_FADE_START_MS = 2700
_TEXT_START_MS = 450
_TEXT_REVEAL_MS = 350
_GLOW_MS = 700
# (time in ms, scale): grows past full size, dips under it and settles, one pulse
_SCALE_KEYFRAMES = ((0, 0.0), (300, 1.3), (500, 0.9), (680, 1.08), (850, 1.0))
_ZONE_WIDTH = 520  # logical pixels of the area where the throws happen: the effect is centered in it
_ZONE_HEIGHT = 340
_TROPHY_SIZE = 112
_TEXT_GAP = 4
_TEXT_RISE = 14  # the text slides up this far while it appears
_TITLE_ROW = 26
_SCORE_ROW = 62
_PREVIOUS_ROW = 22
_TEXT_HEIGHT = _TITLE_ROW + _SCORE_ROW + _PREVIOUS_ROW
_TITLE_PIXELS = 20
_SCORE_PIXELS = 50
_PREVIOUS_PIXELS = 14
_TITLE_DEPTH = 2  # pixels of the volume under the lettering
_SCORE_DEPTH = 5
_OUTLINE_WIDTH = 2  # pixels of the dark rim around the gold
_GLOW_RADIUS = 150
_GLOW_ALPHA = 0.7
_CONFETTI_COUNT = 56
_SPEED_RANGE = (180, 560)  # logical pixels per second at the burst
_TILE_WIDTH_RANGE = (9, 14)
_TILE_HEIGHT_RANGE = (5, 8)
_SPIN_RANGE = (-9.0, 9.0)  # radians per second
_FLIP_RANGE = (5.0, 12.0)  # radians per second of the flutter that turns a tile edge-on
_DRAG = 2.2  # per second: the burst slows down
_GRAVITY = 260  # logical pixels per second squared
_TILE_RADIUS = 1
_CONFETTI_COLORS = tuple(QColor(code) for code in ("#ffd23f", "#ffb300", "#ff5252", "#4fc3f7", "#81c784", "#f48fb1", "#fff176"))
_GOLD_LIGHT = QColor("#fff6b8")
_GOLD_MIDDLE = QColor("#ffd23f")
_GOLD_DARK = QColor("#e09a10")
_GOLD_SHADOW = QColor("#8c5a0a")
_GOLD_OUTLINE = QColor("#4a2c05")
_PREVIOUS_COLOR = QColor(255, 224, 130, 150)
_SMOOTH = QEasingCurve(QEasingCurve.Type.InOutSine)
_SETTLE = QEasingCurve(QEasingCurve.Type.OutCubic)


@dataclass(frozen=True)
class _Piece:
    """One confetti tile: where it flies, how fast, and how it spins and flutters."""

    direction_x: float
    direction_y: float
    speed: float
    width: float
    height: float
    phase: float
    spin: float
    flip: float
    color: QColor


def _scatter() -> list[_Piece]:
    pieces = []
    for _ in range(_CONFETTI_COUNT):
        angle = random.uniform(0, math.tau)
        pieces.append(_Piece(
            math.cos(angle), math.sin(angle), random.uniform(*_SPEED_RANGE),
            random.uniform(*_TILE_WIDTH_RANGE), random.uniform(*_TILE_HEIGHT_RANGE),
            random.uniform(0, math.tau), random.uniform(*_SPIN_RANGE), random.uniform(*_FLIP_RANGE),
            random.choice(_CONFETTI_COLORS),
        ))
    return pieces


def _ramp(value: float, start: float, length: float) -> float:
    return max(0.0, min(1.0, (value - start) / length))


def _trophy_scale(elapsed_ms: float) -> float:
    for (start, from_scale), (end, to_scale) in zip(_SCALE_KEYFRAMES, _SCALE_KEYFRAMES[1:]):
        if elapsed_ms <= end:
            return from_scale + (to_scale - from_scale) * _SMOOTH.valueForProgress(_ramp(elapsed_ms, start, end - start))
    return _SCALE_KEYFRAMES[-1][1]


def _display_font(pixel_size: int) -> QFont:
    font = QFont(get_font(FontType.UI))
    font.setFamilies([font.family()])  # the emoji fallback has no outlines for the lettering path
    font.setPixelSize(pixel_size)
    font.setBold(True)
    return font


def _text_path(text: str, pixel_size: int, center: QPointF) -> QPainterPath:
    """Return the outline of text with the middle of its box at center."""
    path = QPainterPath()
    path.addText(0, 0, _display_font(pixel_size), text)
    return path.translated(center - path.boundingRect().center())


def _paint_gold(painter: QPainter, path: QPainterPath, depth: int) -> None:
    """Draw the lettering as gold with a dark outline around it and a solid volume of depth pixels under it."""
    outline = QPen(_GOLD_OUTLINE, _OUTLINE_WIDTH * 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(outline)
    painter.drawPath(path)
    painter.drawPath(path.translated(0, depth))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_GOLD_SHADOW)
    for offset in range(depth, 0, -1):
        painter.drawPath(path.translated(0, offset))
    bounds = path.boundingRect()
    face = QLinearGradient(bounds.topLeft(), bounds.bottomLeft())
    face.setColorAt(0.0, _GOLD_LIGHT)
    face.setColorAt(0.5, _GOLD_MIDDLE)
    face.setColorAt(1.0, _GOLD_DARK)
    painter.setBrush(face)
    painter.drawPath(path)


class RecordCelebration(QWidget):
    """Plays the record effect once over the pet area and hides again; the mouse passes through it."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._elapsed_ms = 0.0
        self._pieces: list[_Piece] = []
        self._trophy = QPixmap()
        self._text = QPixmap()
        self._trophy_center = QPointF()
        self._text_top = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(float(_DURATION_MS))
        self._animation.setDuration(_DURATION_MS)
        self._animation.valueChanged.connect(self._advance)
        self._animation.finished.connect(self.hide)
        self.hide()

    def play(self, area: QRect, count: int, previous: int) -> None:
        """Celebrate count, which beat previous (zero for the first record), centered in the throwing zone at the bottom of area."""
        self._animation.stop()
        ratio = self.devicePixelRatioF()
        width, height = min(area.width(), _ZONE_WIDTH), min(area.height(), _ZONE_HEIGHT)
        self.setGeometry(area.x() + (area.width() - width) // 2, area.y() + area.height() - height, width, height)
        top = (height - _TROPHY_SIZE - _TEXT_GAP - _TEXT_HEIGHT) / 2
        self._trophy_center = QPointF(width / 2, top + _TROPHY_SIZE / 2)
        self._text_top = top + _TROPHY_SIZE + _TEXT_GAP
        self._trophy = self._render_trophy(ratio)
        self._text = self._render_text(count, previous, ratio)
        self._pieces = _scatter()
        self._elapsed_ms = 0.0
        self.raise_()
        self.show()
        self._animation.start()

    def stop(self) -> None:
        """End the effect at once."""
        self._animation.stop()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        opacity = 1.0 - _ramp(self._elapsed_ms, _FADE_START_MS, _DURATION_MS - _FADE_START_MS)
        painter.setOpacity(opacity)
        self._paint_glow(painter)
        self._paint_confetti(painter)
        self._paint_trophy(painter)
        reveal = _SETTLE.valueForProgress(_ramp(self._elapsed_ms, _TEXT_START_MS, _TEXT_REVEAL_MS))
        painter.setOpacity(opacity * reveal)
        painter.drawPixmap(QPointF(0, self._text_top + (1 - reveal) * _TEXT_RISE), self._text)

    def _advance(self, elapsed_ms: float) -> None:
        self._elapsed_ms = elapsed_ms
        self.update()

    @staticmethod
    def _render_trophy(ratio: float) -> QPixmap:
        size = round(_TROPHY_SIZE * ratio)
        pixmap = QIcon(str(get_resource_dir("icons") / "emoticon_groups" / "trophy.svg")).pixmap(size, size)
        pixmap.setDevicePixelRatio(ratio)
        return pixmap

    def _render_text(self, count: int, previous: int, ratio: float) -> QPixmap:
        """Draw the lettering once: the title and the new score in gold, the beaten score faded under them."""
        width = self.width()
        pixmap = QPixmap(round(width * ratio), round(_TEXT_HEIGHT * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        title = _text_path(tr("NEW RECORD", "НОВЫЙ РЕКОРД"), _TITLE_PIXELS, QPointF(width / 2, _TITLE_ROW / 2))
        score = _text_path(str(count), _SCORE_PIXELS, QPointF(width / 2, _TITLE_ROW + _SCORE_ROW / 2))
        _paint_gold(painter, title, _TITLE_DEPTH)
        _paint_gold(painter, score, _SCORE_DEPTH)
        if previous:
            font = _display_font(_PREVIOUS_PIXELS)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(_PREVIOUS_COLOR)
            row = QRectF(0, _TITLE_ROW + _SCORE_ROW, width, _PREVIOUS_ROW)
            painter.drawText(row, Qt.AlignmentFlag.AlignCenter, tr(f"Previous: {previous}", f"Было: {previous}"))
        painter.end()
        return pixmap

    def _paint_glow(self, painter: QPainter) -> None:
        """Flash a gold ring around the trophy that widens and dies out as the burst starts."""
        age = self._elapsed_ms - _BURST_MS
        if not 0 <= age < _GLOW_MS:
            return
        life = 1 - age / _GLOW_MS
        radius = _GLOW_RADIUS * (1.4 - 0.6 * life)
        gold = QColor(_GOLD_MIDDLE)
        gold.setAlphaF(_GLOW_ALPHA * life)
        fade = QColor(_GOLD_MIDDLE)
        fade.setAlpha(0)
        glow = QRadialGradient(self._trophy_center, radius)
        glow.setColorAt(0.0, gold)
        glow.setColorAt(1.0, fade)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(self._trophy_center, radius, radius)

    def _paint_confetti(self, painter: QPainter) -> None:
        seconds = (self._elapsed_ms - _BURST_MS) / _MILLISECONDS
        if seconds <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        slowing = (1 - math.exp(-_DRAG * seconds)) / _DRAG
        fall = _GRAVITY * seconds * seconds / 2
        for piece in self._pieces:
            painter.save()
            painter.translate(
                self._trophy_center.x() + piece.direction_x * piece.speed * slowing,
                self._trophy_center.y() + piece.direction_y * piece.speed * slowing + fall,
            )
            painter.rotate(math.degrees(piece.phase + piece.spin * seconds))
            painter.scale(abs(math.cos(piece.phase + piece.flip * seconds)), 1)
            painter.setBrush(piece.color)
            painter.drawRoundedRect(QRectF(-piece.width / 2, -piece.height / 2, piece.width, piece.height), _TILE_RADIUS, _TILE_RADIUS)
            painter.restore()

    def _paint_trophy(self, painter: QPainter) -> None:
        scale = _trophy_scale(self._elapsed_ms)
        painter.save()
        painter.translate(self._trophy_center)
        painter.scale(scale, scale)
        painter.drawPixmap(QPointF(-_TROPHY_SIZE / 2, -_TROPHY_SIZE / 2), self._trophy)
        painter.restore()

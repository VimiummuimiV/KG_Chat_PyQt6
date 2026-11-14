"""Record effect over the pet area: a trophy pulses in, confetti bursts out, the beaten and the new score shine under it, a button closes it."""

import math
import random
from dataclasses import dataclass

from PyQt6.QtCore import QEasingCurve, QEvent, QPointF, QRect, QRectF, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient
from PyQt6.QtWidgets import QApplication, QWidget

from components.button import create_icon_button
from helpers.data import get_resource_dir
from helpers.fonts.fonts import get_display_font
from helpers.translate import tr


_MILLISECONDS = 1000
_CORNER_MARGIN = 8  # between the close button and the edge of the area
_INTRO_MS = 3500  # the burst has fallen out of the area by then; the trophy and the score stay until Esc
_BURST_MS = 300  # the trophy reaches its first peak and the confetti flies
_TEXT_START_MS = 450
_TEXT_REVEAL_MS = 350
_GLOW_MS = 700
# (time in ms, scale): grows past full size, dips under it and settles, one pulse
_SCALE_KEYFRAMES = ((0, 0.0), (300, 1.3), (500, 0.9), (680, 1.08), (850, 1.0))
_TROPHY_SIZE = 144
_TEXT_GAP = 6
_TEXT_RISE = 16  # the text slides up this far while it appears
_TEXT_MARGIN = 8
_TITLE_ROW = 34
_SCORE_ROW = 84
_TEXT_HEIGHT = _TITLE_ROW + _SCORE_ROW
_TITLE_PIXELS = 24
_SCORE_PIXELS = 66
_TITLE_DEPTH = 3  # pixels of the volume under the lettering
_SCORE_DEPTH = 7
_OUTLINE_WIDTH = 2  # pixels of the dark rim around the lettering
_SEPARATOR_WIDTH = 26
_SEPARATOR_HEIGHT = 46
_SEPARATOR_GAP = 16
_GLOW_SHARE = 0.4  # of the smaller side of the area
_GLOW_ALPHA = 0.7
_CONFETTI_COUNT = 170
_REACH_RANGE = (0.25, 1.1)  # of half the area: how far a tile flies from the trophy before it falls
_TILE_WIDTH_RANGE = (10, 16)
_TILE_HEIGHT_RANGE = (6, 9)
_SPIN_RANGE = (-9.0, 9.0)  # radians per second
_FLIP_RANGE = (5.0, 12.0)  # radians per second of the flutter that turns a tile edge-on
_DRAG = 2.2  # per second: the burst slows down
_GRAVITY_SHARE = 0.3  # of the area height per second squared
_TILE_RADIUS = 1
_CONFETTI_COLORS = tuple(QColor(code) for code in ("#ffd23f", "#ffb300", "#ff5252", "#4fc3f7", "#81c784", "#f48fb1", "#fff176"))
_MOUSE_EVENTS = (
    QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick, QEvent.Type.ContextMenu,
)
_SMOOTH = QEasingCurve(QEasingCurve.Type.InOutSine)
_SETTLE = QEasingCurve(QEasingCurve.Type.OutCubic)


@dataclass(frozen=True)
class _Palette:
    """Colors of lettering with volume: face gradient from light to dark, the side, the rim."""

    light: QColor
    middle: QColor
    dark: QColor
    side: QColor
    rim: QColor


_GOLD = _Palette(QColor("#fff6b8"), QColor("#ffd23f"), QColor("#e09a10"), QColor("#8c5a0a"), QColor("#4a2c05"))
_BROWN = _Palette(QColor("#c99a6b"), QColor("#a0693a"), QColor("#6f4220"), QColor("#3d2210"), QColor("#24120a"))


@dataclass(frozen=True)
class _Piece:
    """One confetti tile: where it flies, and how it spins and flutters."""

    velocity_x: float
    velocity_y: float
    width: float
    height: float
    phase: float
    spin: float
    flip: float
    color: QColor


def _scatter(width: int, height: int) -> list[_Piece]:
    """Return tiles that burst in every direction and reach as far as the area is wide and high."""
    pieces = []
    for _ in range(_CONFETTI_COUNT):
        angle, reach = random.uniform(0, math.tau), random.uniform(*_REACH_RANGE)
        pieces.append(_Piece(
            math.cos(angle) * reach * _DRAG * width / 2, math.sin(angle) * reach * _DRAG * height / 2,
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


def _text_path(text: str, pixel_size: int) -> QPainterPath:
    """Return the outline of text with the middle of its box at the origin."""
    path = QPainterPath()
    path.addText(0, 0, get_display_font(pixel_size), text)
    return path.translated(-path.boundingRect().center())


def _separator_path() -> QPainterPath:
    """Return a thick chevron pointing right, with its middle at the origin."""
    half_width, half_height, arm = _SEPARATOR_WIDTH / 2, _SEPARATOR_HEIGHT / 2, _SEPARATOR_WIDTH / 2
    path = QPainterPath()
    path.addPolygon(QPolygonF([
        QPointF(-half_width, -half_height), QPointF(-half_width + arm, -half_height), QPointF(half_width, 0),
        QPointF(-half_width + arm, half_height), QPointF(-half_width, half_height), QPointF(half_width - arm, 0),
    ]))
    path.closeSubpath()
    return path


def _paint_lettering(painter: QPainter, path: QPainterPath, depth: int, palette: _Palette) -> None:
    """Draw the shape with a dark rim around it and a solid side of depth pixels under it."""
    rim = QPen(palette.rim, _OUTLINE_WIDTH * 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(rim)
    painter.drawPath(path)
    painter.drawPath(path.translated(0, depth))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(palette.side)
    for offset in range(depth, 0, -1):
        painter.drawPath(path.translated(0, offset))
    bounds = path.boundingRect()
    face = QLinearGradient(bounds.topLeft(), bounds.bottomLeft())
    face.setColorAt(0.0, palette.light)
    face.setColorAt(0.5, palette.middle)
    face.setColorAt(1.0, palette.dark)
    painter.setBrush(face)
    painter.drawPath(path)


class RecordCelebration(QWidget):
    """Plays the record effect over the pet area and stays until Esc or its close button; it takes the mouse from what lies under it."""

    def __init__(self, parent: QWidget, config):
        super().__init__(parent)
        self._close_button = create_icon_button(get_resource_dir("icons"), "line/close-large-line.svg", config=config)
        self._close_button.setParent(self)
        self._close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Esc stays with the window
        self._close_button.clicked.connect(self.stop)
        self._elapsed_ms = 0.0
        self._pieces: list[_Piece] = []
        self._trophy = QPixmap()
        self._text = QPixmap()
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(float(_INTRO_MS))
        self._animation.setDuration(_INTRO_MS)
        self._animation.valueChanged.connect(self._advance)
        self.hide()

    def play(self, area: QRect, count: int, previous: int) -> None:
        """Celebrate count, which beat previous (zero for the first record), centered in area."""
        self._animation.stop()
        self.setGeometry(area)
        ratio = self.devicePixelRatioF()
        self._trophy = self._render_trophy(ratio)
        self._text = self._render_text(count, previous, ratio)
        self._pieces = _scatter(area.width(), area.height())
        self._elapsed_ms = 0.0
        self._close_button.setToolTip(tr("Close (Esc)", "Закрыть (Esc)"))
        self.show()
        self._animation.start()

    def stop(self) -> None:
        """Close the effect at once."""
        self._animation.stop()
        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        super().hideEvent(event)
        QApplication.instance().removeEventFilter(self)

    def event(self, event):
        if event.type() in _MOUSE_EVENTS:  # a click on the effect must not reach the messages under it
            event.accept()
            return True
        return super().event(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._close_button.move(self.width() - self._close_button.width() - _CORNER_MARGIN, _CORNER_MARGIN)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and self.window().isActiveWindow():
            self.stop()
            return True
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        stack_top = (self.height() - _TROPHY_SIZE - _TEXT_GAP - _TEXT_HEIGHT) / 2
        trophy_center = QPointF(self.width() / 2, stack_top + _TROPHY_SIZE / 2)
        self._paint_glow(painter, trophy_center)
        self._paint_confetti(painter, trophy_center)
        self._paint_trophy(painter, trophy_center)
        reveal = _SETTLE.valueForProgress(_ramp(self._elapsed_ms, _TEXT_START_MS, _TEXT_REVEAL_MS))
        painter.setOpacity(reveal)
        text_left = (self.width() - self._text.width() / self._text.devicePixelRatio()) / 2
        painter.drawPixmap(QPointF(text_left, stack_top + _TROPHY_SIZE + _TEXT_GAP + (1 - reveal) * _TEXT_RISE), self._text)

    def _advance(self, elapsed_ms: float) -> None:
        self._elapsed_ms = elapsed_ms
        self.update()

    @staticmethod
    def _render_trophy(ratio: float) -> QPixmap:
        size = round(_TROPHY_SIZE * ratio)
        pixmap = QIcon(str(get_resource_dir("icons") / "emoji" / "trophy.svg")).pixmap(size, size)
        pixmap.setDevicePixelRatio(ratio)
        return pixmap

    @staticmethod
    def _render_text(count: int, previous: int, ratio: float) -> QPixmap:
        """Draw the lettering once: the title and the scores, the beaten score in brown and the new one in gold with a separator between."""
        title = _text_path(tr("NEW RECORD", "НОВЫЙ РЕКОРД"), _TITLE_PIXELS)
        score = _text_path(str(count), _SCORE_PIXELS)
        shapes = [(score, _GOLD)]
        if previous:
            shapes = [(_text_path(str(previous), _SCORE_PIXELS), _BROWN), (_separator_path(), _GOLD), *shapes]
        gaps = _SEPARATOR_GAP * 2 if previous else 0
        row_width = sum(path.boundingRect().width() for path, _ in shapes) + gaps
        width = math.ceil(max(title.boundingRect().width(), row_width)) + 2 * _TEXT_MARGIN
        pixmap = QPixmap(round(width * ratio), round(_TEXT_HEIGHT * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _paint_lettering(painter, title.translated(width / 2, _TITLE_ROW / 2), _TITLE_DEPTH, _GOLD)
        left = (width - row_width) / 2
        for path, palette in shapes:
            shape_width = path.boundingRect().width()
            _paint_lettering(painter, path.translated(left + shape_width / 2, _TITLE_ROW + _SCORE_ROW / 2), _SCORE_DEPTH, palette)
            left += shape_width + _SEPARATOR_GAP
        painter.end()
        return pixmap

    def _paint_glow(self, painter: QPainter, center: QPointF) -> None:
        """Flash a gold ring around the trophy that widens and dies out as the burst starts."""
        age = self._elapsed_ms - _BURST_MS
        if not 0 <= age < _GLOW_MS:
            return
        life = 1 - age / _GLOW_MS
        radius = min(self.width(), self.height()) * _GLOW_SHARE * (1.4 - 0.6 * life)
        gold = QColor(_GOLD.middle)
        gold.setAlphaF(_GLOW_ALPHA * life)
        fade = QColor(_GOLD.middle)
        fade.setAlpha(0)
        glow = QRadialGradient(center, radius)
        glow.setColorAt(0.0, gold)
        glow.setColorAt(1.0, fade)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius, radius)

    def _paint_confetti(self, painter: QPainter, origin: QPointF) -> None:
        seconds = (self._elapsed_ms - _BURST_MS) / _MILLISECONDS
        if seconds <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        slowing = (1 - math.exp(-_DRAG * seconds)) / _DRAG
        fall = _GRAVITY_SHARE * self.height() * seconds * seconds / 2
        for piece in self._pieces:
            painter.save()
            painter.translate(origin.x() + piece.velocity_x * slowing, origin.y() + piece.velocity_y * slowing + fall)
            painter.rotate(math.degrees(piece.phase + piece.spin * seconds))
            painter.scale(abs(math.cos(piece.phase + piece.flip * seconds)), 1)
            painter.setBrush(piece.color)
            painter.drawRoundedRect(QRectF(-piece.width / 2, -piece.height / 2, piece.width, piece.height), _TILE_RADIUS, _TILE_RADIUS)
            painter.restore()

    def _paint_trophy(self, painter: QPainter, center: QPointF) -> None:
        scale = _trophy_scale(self._elapsed_ms)
        painter.save()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.drawPixmap(QPointF(-_TROPHY_SIZE / 2, -_TROPHY_SIZE / 2), self._trophy)
        painter.restore()

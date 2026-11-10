"""One displayed image with its own pan/zoom, and the animation that swaps two of them."""

from typing import Callable, NamedTuple, Optional

from PyQt6.QtCore import pyqtSignal, QBuffer, QEasingCurve, QIODevice, QObject, QPointF, QSize, QVariantAnimation
from PyQt6.QtGui import QMovie, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication


_FIT_RATIO = 0.95
MIN_SCALE = 0.1
MAX_SCALE = 10.0
_ACTUAL_SIZE_TOLERANCE = 0.005
INSTANT_MODE = "instant"
_DRIFT_SHIFT = 0.25
_ZOOM_AMOUNT = 0.15
_FLIP_MIDPOINT = 0.5


class _Pose(NamedTuple):
    """Extra transform applied to a layer while it is animated."""
    shift: float = 0.0    # horizontal offset as a fraction of the viewport width
    stretch: float = 1.0  # horizontal scale factor (flip)
    scale: float = 1.0
    opacity: float = 1.0


_IDENTITY_POSE = _Pose()
_HIDDEN_POSE = _Pose(opacity=0.0)


# Each function maps (progress 0..1, direction +1/-1) to the (outgoing, incoming) poses.
def _fade(progress: float, direction: int):
    return _Pose(opacity=1 - progress), _Pose(opacity=progress)


def _slide(progress: float, direction: int):
    return _Pose(shift=-direction * progress), _Pose(shift=direction * (1 - progress))


def _drift(progress: float, direction: int):
    return (
        _Pose(shift=-direction * _DRIFT_SHIFT * progress, opacity=1 - progress),
        _Pose(shift=direction * _DRIFT_SHIFT * (1 - progress), opacity=progress),
    )


def _zoom(progress: float, direction: int):
    return (
        _Pose(scale=1 + _ZOOM_AMOUNT * progress, opacity=1 - progress),
        _Pose(scale=1 - _ZOOM_AMOUNT * (1 - progress), opacity=progress),
    )


def _flip(progress: float, direction: int):
    if progress < _FLIP_MIDPOINT:
        return _Pose(stretch=1 - progress / _FLIP_MIDPOINT), _HIDDEN_POSE
    return _HIDDEN_POSE, _Pose(stretch=progress / _FLIP_MIDPOINT - 1)


_POSE_FUNCTIONS = {
    "fade": _fade,
    "slide": _slide,
    "drift": _drift,
    "zoom": _zoom,
    "flip": _flip,
}
TRANSITION_MODES = (INSTANT_MODE, *_POSE_FUNCTIONS)


class TransitionAnimator(QObject):
    """Drives the progress of a transition between two layers."""

    changed = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pose_function = _fade
        self._direction = 1
        self._progress = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_value_changed)
        self._animation.finished.connect(self.finished)

    @property
    def running(self) -> bool:
        return self._animation.state() == QVariantAnimation.State.Running

    def start(self, mode: str, direction: int, duration_ms: int):
        """Begin animating with the given mode; direction is +1 (next) or -1 (previous)."""
        self._pose_function = _POSE_FUNCTIONS[mode]
        self._direction = direction or 1
        self._progress = 0.0
        self._animation.setDuration(duration_ms)
        self._animation.start()

    def stop(self):
        self._animation.stop()

    def poses(self) -> tuple[_Pose, _Pose]:
        """Poses of the (outgoing, incoming) layers at the current progress."""
        return self._pose_function(self._progress, self._direction)

    def _on_value_changed(self, value):
        self._progress = float(value)
        self.changed.emit()


class ImageLayer:
    """A decoded still or animated image positioned inside the viewport."""

    def __init__(self, pixmap: Optional[QPixmap] = None, movie: Optional[QMovie] = None,
                 on_frame_changed: Optional[Callable] = None):
        self._pixmap = pixmap
        self._movie = movie
        self.offset = QPointF(0, 0)
        self.scale = 1.0
        self._on_frame_changed = on_frame_changed
        if movie and on_frame_changed:
            movie.frameChanged.connect(on_frame_changed)
            movie.start()

    @classmethod
    def from_data(cls, url: str, data: bytes, on_frame_changed: Callable) -> Optional["ImageLayer"]:
        """Decode image bytes into a layer, or return None when they are not a valid image."""
        if url.lower().endswith(".gif") or data.startswith(b"GIF"):
            movie = QMovie()
            movie.setParent(QApplication.instance())
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            buffer = QBuffer()
            buffer.setParent(movie)
            buffer.setData(data)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            movie.setDevice(buffer)
            movie.jumpToFrame(0)
            if movie.isValid() and not movie.currentPixmap().isNull():
                return cls(movie=movie, on_frame_changed=on_frame_changed)
            movie.deleteLater()
            return None
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        return None if pixmap.isNull() else cls(pixmap=pixmap)

    @property
    def is_actual_size(self) -> bool:
        return abs(self.scale - 1.0) < _ACTUAL_SIZE_TOLERANCE

    def _frame(self) -> Optional[QPixmap]:
        return self._movie.currentPixmap() if self._movie else self._pixmap

    def fit(self, viewport: QSize, reserved_bottom: int = 0):
        """Scale down to fit and center above the reserved bottom strip."""
        frame = self._frame()
        available_height = viewport.height() - reserved_bottom
        self.scale = min(
            viewport.width() * _FIT_RATIO / frame.width(),
            available_height * _FIT_RATIO / frame.height(),
            1.0,
        )
        self._center(viewport, frame, available_height)

    def _center(self, viewport: QSize, frame: QPixmap, available_height: int):
        self.offset = QPointF(
            (viewport.width() - frame.width() * self.scale) / 2,
            (available_height - frame.height() * self.scale) / 2,
        )

    def set_actual_size(self, viewport: QSize, reserved_bottom: int = 0):
        """Show the image at its original size and center it above the reserved bottom strip."""
        frame = self._frame()
        available_height = viewport.height() - reserved_bottom
        self.scale = 1.0
        self._center(viewport, frame, available_height)

    def paint(self, painter: QPainter, viewport: QSize, pose: _Pose = _IDENTITY_POSE):
        frame = self._frame()
        if not frame or frame.isNull() or pose.opacity <= 0 or pose.stretch <= 0:
            return
        painter.save()
        painter.setOpacity(pose.opacity)
        painter.translate(viewport.width() / 2 + pose.shift * viewport.width(), viewport.height() / 2)
        painter.scale(pose.stretch * pose.scale, pose.scale)
        painter.translate(-viewport.width() / 2, -viewport.height() / 2)
        painter.translate(self.offset)
        painter.scale(self.scale, self.scale)
        painter.drawPixmap(0, 0, frame)
        painter.restore()

    def release(self):
        """Stop the animation and free the movie."""
        if self._movie:
            self._movie.stop()
            try:
                self._movie.frameChanged.disconnect(self._on_frame_changed)
            except (TypeError, RuntimeError):
                pass
            self._movie.deleteLater()
        self._movie = self._pixmap = None

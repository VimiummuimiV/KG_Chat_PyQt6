"""Pet sprite animations loaded from GIF files."""

import math
from dataclasses import dataclass
from functools import lru_cache

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QBitmap, QImage, QImageReader, QPixmap, QRegion

from helpers.pets.catalog import PetKind, PixelGrid


_MINIMUM_FRAME_MS = 10
_GRID_TOLERANCE = 0.05  # cells; absorbs float error when the canvas holds a whole number of cells
_OFFSET_LINE_STEP = 3  # only every third line is compared when looking for the grid start
_LUNGE_RATIO = 0.6  # share of a frame during which a step moves the pet; the rest of the frame it stays planted


@dataclass(frozen=True)
class _PetAnimation:
    """Frames of one pet state facing right and mirrored, with timing and visible area."""

    frames_right: tuple[QPixmap, ...]
    _frames_left: tuple[QPixmap, ...]
    _frame_ends_ms: tuple[int, ...]
    body: QRect  # union of the visible pixels over all frames, facing right

    @property
    def cycle_ms(self) -> int:
        return self._frame_ends_ms[-1]

    def pixmap(self, elapsed_ms: int, facing_right: bool) -> QPixmap:
        """Return the frame shown after elapsed_ms of the looping animation."""
        index, _ = self._frame_at(elapsed_ms % self.cycle_ms)
        return (self.frames_right if facing_right else self._frames_left)[index]

    def pixmap_once(self, elapsed_ms: int) -> QPixmap:
        """Return the frame shown after elapsed_ms of the animation played once and then held on its last frame."""
        index, _ = self._frame_at(min(elapsed_ms, self.cycle_ms - 1))
        return self.frames_right[index]

    def stepped_ms(self, elapsed_ms: int) -> float:
        """Return elapsed_ms with each frame's time pulled to its start: motion measured by it advances in steps."""
        cycles, moment = divmod(elapsed_ms, self.cycle_ms)
        index, start = self._frame_at(moment)
        delay = self._frame_ends_ms[index] - start
        progress = min((moment - start) / delay / _LUNGE_RATIO, 1.0)
        return cycles * self.cycle_ms + start + delay * progress * progress * (3 - 2 * progress)

    def _frame_at(self, moment_ms: int) -> tuple[int, int]:
        """Return the index and start time of the frame shown at moment_ms of one cycle."""
        index = next(index for index, end in enumerate(self._frame_ends_ms) if moment_ms < end)
        return index, self._frame_ends_ms[index - 1] if index else 0

    def visible_span(self, facing_right: bool) -> tuple[int, int]:
        """Return the horizontal [left, right) range of the visible pixels inside the frame."""
        right = self.body.x() + self.body.width()
        if facing_right:
            return self.body.x(), right
        width = self.frames_right[0].width()
        return width - right, width - self.body.x()


def _cell_centers(length: int, scale: float, offset: int) -> list[int]:
    """Return the source pixel at the middle of every art cell along one axis."""
    count = math.ceil((length - offset) / scale - _GRID_TOLERANCE)
    centers = [min(length - 1, int(offset + (cell + 0.5) * scale)) for cell in range(count)]
    return [offset // 2, *centers] if offset else centers


def _grid_offset(image: QImage, scale: float, horizontal: bool) -> int:
    """Return where the art cells start along one axis: the shift that makes the cells most uniform."""
    length, lines = (image.width(), image.height()) if horizontal else (image.height(), image.width())

    def uniform_pixels(offset: int) -> int:
        total = 0
        for position in range(length):
            cell = math.floor((position - offset) / scale)
            center = max(0, min(length - 1, int(offset + (cell + 0.5) * scale)))
            for line in range(0, lines, _OFFSET_LINE_STEP):
                same = (
                    image.pixel(position, line) == image.pixel(center, line) if horizontal
                    else image.pixel(line, position) == image.pixel(line, center)
                )
                total += same
        return total

    return max(range(math.ceil(scale)), key=uniform_pixels)


def _redraw_at_pixel_size(image: QImage, grid: PixelGrid, offsets: tuple[int, int], pixel_size: int) -> QImage:
    """Rebuild the original art from the upscaled frame and enlarge it by a whole factor."""
    columns = _cell_centers(image.width(), grid.scale[0], offsets[0])
    rows = _cell_centers(image.height(), grid.scale[1], offsets[1])
    art = QImage(len(columns), len(rows), QImage.Format.Format_ARGB32)
    for row_index, row in enumerate(rows):
        for column_index, column in enumerate(columns):
            art.setPixel(column_index, row_index, image.pixel(column, row))
    return art.scaled(
        art.width() * pixel_size, art.height() * pixel_size,
        Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation,
    )


@lru_cache(maxsize=None)
def load_animation(kind: PetKind, state: str, pixel_size: int) -> _PetAnimation:
    """Load one state of a pet; every art pixel becomes pixel_size screen pixels, never a fraction."""
    reader = QImageReader(str(kind.sprite_path(state)))
    grid = kind.pixel_grid
    offsets = None
    frames_right, frames_left, frame_ends_ms = [], [], []
    body = QRect()
    elapsed_ms = 0
    while reader.canRead():
        delay_ms = max(reader.nextImageDelay(), _MINIMUM_FRAME_MS)
        image = reader.read()
        if image.isNull():
            break
        image = image.convertToFormat(QImage.Format.Format_ARGB32)
        offsets = offsets or (_grid_offset(image, grid.scale[0], True), _grid_offset(image, grid.scale[1], False))
        image = _redraw_at_pixel_size(image, grid, offsets, pixel_size)
        frames_right.append(QPixmap.fromImage(image))
        frames_left.append(QPixmap.fromImage(image.mirrored(True, False)))
        elapsed_ms += delay_ms
        frame_ends_ms.append(elapsed_ms)
        body = body.united(QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect())
    return _PetAnimation(tuple(frames_right), tuple(frames_left), tuple(frame_ends_ms), body)

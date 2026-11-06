"""Floating panels of the image viewer: source badge (top left) and gallery bar (bottom center)."""

from datetime import date
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import pyqtSignal, QBuffer, QIODevice, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from components.avatar import make_avatar_label, make_avatar_pixmap
from components.button import create_icon_button, get_user_svg_color, set_button_icon
from components.image_viewer.gallery import GalleryImage
from helpers.cache import get_cache
from helpers.fonts.fonts import FontType, get_font
from helpers.load import make_rounded_pixmap
from helpers.translate import tr


THUMBNAIL_SIZE = QSize(84, 56)
THUMBNAIL_MAX_VISIBLE = 9
_THUMBNAIL_GAP = 6
_THUMBNAIL_RADIUS = 4
_THUMBNAIL_BORDER_WIDTH = 2
_THUMBNAIL_DIMMED_OPACITY = 0.55
_COUNTER_WIDTH = 90
_PANEL_MARGIN = 10
_PANEL_SPACING = 8
_PANEL_RADIUS = 12
_BADGE_AVATAR_SIZE = 28
_BADGE_SVG_AVATAR_SIZE = 20
_BADGE_AVATAR_RADIUS = 8
_BADGE_MARGIN = 6
_BADGE_SPACING = 8
_PANEL_STYLES = {
    True: {"background": "rgba(30, 30, 30, 215)", "text": "#dddddd", "muted": "#999999", "placeholder": "#3a3a3a"},
    False: {"background": "rgba(245, 245, 245, 225)", "text": "#333333", "muted": "#777777", "placeholder": "#cfcfcf"},
}


def _panel_stylesheet(object_name: str, is_dark: bool) -> str:
    style = _PANEL_STYLES[is_dark]
    return (
        f"#{object_name} {{ background-color: {style['background']}; border-radius: {_PANEL_RADIUS}px; }}"
        f"#{object_name} QLabel {{ color: {style['text']}; background: transparent; }}"
    )


def thumbnail_window(index: int, count: int) -> range:
    """Gallery indices shown in the strip: a window of thumbnails around the current image."""
    visible = min(count, THUMBNAIL_MAX_VISIBLE)
    start = max(0, min(index - visible // 2, count - visible))
    return range(start, start + visible)


def make_thumbnail(data: bytes) -> Optional[QPixmap]:
    """Decode a cover-cropped thumbnail without keeping the full-size image in memory."""
    buffer = QBuffer()
    buffer.setData(data)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    source_size = reader.size()
    if source_size.isValid():
        reader.setScaledSize(source_size.scaled(THUMBNAIL_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
    image = reader.read()
    if image.isNull():
        return None
    image = image.scaled(
        THUMBNAIL_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
    )
    left = (image.width() - THUMBNAIL_SIZE.width()) // 2
    top = (image.height() - THUMBNAIL_SIZE.height()) // 2
    return QPixmap.fromImage(image.copy(left, top, THUMBNAIL_SIZE.width(), THUMBNAIL_SIZE.height()))


class _ThumbnailStrip(QWidget):
    """Row of clickable thumbnails; the current one is outlined, the others dimmed."""

    clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.indices = range(0)
        self._current = 0
        self._is_dark = True
        self._thumbnails: dict[int, QPixmap] = {}
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_state(self, indices: range, current: int):
        self.indices = indices
        self._current = current
        width = len(indices) * (THUMBNAIL_SIZE.width() + _THUMBNAIL_GAP) - _THUMBNAIL_GAP
        self.setFixedSize(max(width, 0), THUMBNAIL_SIZE.height())
        self.update()

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        self.update()

    def set_thumbnail(self, index: int, pixmap: QPixmap):
        self._thumbnails[index] = pixmap
        self.update()

    def has_thumbnail(self, index: int) -> bool:
        return index in self._thumbnails

    def clear(self):
        self._thumbnails.clear()
        self.indices = range(0)

    def _slot_rect(self, slot: int) -> QRect:
        return QRect(slot * (THUMBNAIL_SIZE.width() + _THUMBNAIL_GAP), 0, THUMBNAIL_SIZE.width(), THUMBNAIL_SIZE.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        placeholder = QColor(_PANEL_STYLES[self._is_dark]["placeholder"])
        accent = QColor(get_user_svg_color(True, self._is_dark))  # theme accent
        for slot, index in enumerate(self.indices):
            rect = self._slot_rect(slot)
            is_current = index == self._current
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), _THUMBNAIL_RADIUS, _THUMBNAIL_RADIUS)
            painter.save()
            painter.setClipPath(path)
            painter.setOpacity(1.0 if is_current else _THUMBNAIL_DIMMED_OPACITY)
            pixmap = self._thumbnails.get(index)
            if pixmap:
                painter.drawPixmap(rect, pixmap)
            else:
                painter.fillRect(rect, placeholder)
            painter.restore()
            if is_current:
                painter.setPen(QPen(accent, _THUMBNAIL_BORDER_WIDTH))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                half = _THUMBNAIL_BORDER_WIDTH / 2
                painter.drawRoundedRect(QRectF(rect).adjusted(half, half, -half, -half), _THUMBNAIL_RADIUS, _THUMBNAIL_RADIUS)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            slot = int(event.position().x()) // (THUMBNAIL_SIZE.width() + _THUMBNAIL_GAP)
            if 0 <= slot < len(self.indices):
                self.clicked.emit(self.indices[slot])
        event.accept()


class GalleryBar(QFrame):
    """Translucent panel with navigation buttons, position counter and thumbnail strip."""

    previous_requested = pyqtSignal()
    next_requested = pyqtSignal()
    slideshow_toggled = pyqtSignal()
    thumbnail_clicked = pyqtSignal(int)

    def __init__(self, icons_path: Path, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("galleryBar")
        self._is_playing = False

        self._previous_button = create_icon_button(icons_path, "arrow-left.svg", config=config)
        self._slideshow_button = create_icon_button(icons_path, "play.svg", config=config)
        self._next_button = create_icon_button(icons_path, "arrow-right.svg", config=config)
        for button in (self._previous_button, self._slideshow_button, self._next_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the viewer
        self._previous_button.clicked.connect(self.previous_requested)
        self._slideshow_button.clicked.connect(self.slideshow_toggled)
        self._next_button.clicked.connect(self.next_requested)

        self._counter = QLabel()
        self._counter.setFont(get_font(FontType.UI))
        self._counter.setFixedWidth(_COUNTER_WIDTH)
        self._counter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._strip = _ThumbnailStrip(self)
        self._strip.clicked.connect(self.thumbnail_clicked)

        controls = QHBoxLayout()
        controls.setSpacing(_PANEL_SPACING)
        controls.addWidget(self._counter)
        controls.addWidget(self._previous_button)
        controls.addWidget(self._slideshow_button)
        controls.addWidget(self._next_button)
        controls.addSpacing(_COUNTER_WIDTH)  # mirrors the counter so the buttons stay centered

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_PANEL_MARGIN, _PANEL_MARGIN, _PANEL_MARGIN, _PANEL_MARGIN)
        layout.setSpacing(_PANEL_SPACING)
        layout.addLayout(controls)
        layout.setAlignment(controls, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._strip, 0, Qt.AlignmentFlag.AlignHCenter)

        self._refresh_tooltips()

    def apply_theme(self, is_dark: bool):
        self.setStyleSheet(_panel_stylesheet("galleryBar", is_dark))
        self._strip.set_theme(is_dark)

    def set_position(self, index: int, count: int, show_thumbnails: bool):
        """Update the counter and the thumbnail window for the image at index of count."""
        self._counter.setText(f"{index + 1} / {count}")
        self._strip.setVisible(show_thumbnails)
        self._strip.set_state(thumbnail_window(index, count) if show_thumbnails else range(0), index)
        self._refresh_tooltips()
        self._fit_to_content()

    def _fit_to_content(self):
        self.layout().invalidate()  # a hidden widget keeps its stale layout until shown
        self.resize(self.sizeHint())

    def set_slideshow_playing(self, is_playing: bool):
        self._is_playing = is_playing
        set_button_icon(self._slideshow_button, "stop.svg" if is_playing else "play.svg")
        self._refresh_tooltips()

    def visible_indices(self) -> range:
        """Gallery indices whose thumbnails are currently shown."""
        return self._strip.indices

    def has_thumbnail(self, index: int) -> bool:
        return self._strip.has_thumbnail(index)

    def set_thumbnail(self, index: int, pixmap: QPixmap):
        self._strip.set_thumbnail(index, pixmap)

    def clear_thumbnails(self):
        self._strip.clear()

    def _refresh_tooltips(self):
        self._previous_button.setToolTip(tr("Previous image (H / ←)", "Предыдущее изображение (H / ←)"))
        self._next_button.setToolTip(tr("Next image (L / →)", "Следующее изображение (L / →)"))
        self._slideshow_button.setToolTip(
            tr("Stop slideshow (P)", "Остановить слайдшоу (P)") if self._is_playing
            else tr("Start slideshow (P)", "Запустить слайдшоу (P)")
        )


class SourceBadge(QFrame):
    """Compact avatar + username + time of the message the current image was posted in; click jumps to it."""

    clicked = pyqtSignal()
    _avatar_ready = pyqtSignal(str, QPixmap)  # emitted from the avatar loader thread

    def __init__(self, icons_path: Path, parent=None):
        super().__init__(parent)
        self.setObjectName("sourceBadge")
        self._icons_path = icons_path
        self._user_id = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._avatar_label = make_avatar_label(_BADGE_AVATAR_SIZE)
        self._username_label = QLabel()
        self._username_label.setFont(get_font(FontType.TEXT))
        self._time_label = QLabel()
        self._time_label.setFont(get_font(FontType.TEXT))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_BADGE_MARGIN, _BADGE_MARGIN, _BADGE_MARGIN + _BADGE_SPACING, _BADGE_MARGIN)
        layout.setSpacing(_BADGE_SPACING)
        layout.addWidget(self._avatar_label)
        layout.addWidget(self._username_label)
        layout.addWidget(self._time_label)

        self._avatar_ready.connect(self._on_avatar_ready)
        self._refresh_tooltip()

    def show_image(self, image: GalleryImage, is_dark: bool):
        """Fill the badge with the sender and time of the message that holds this image."""
        cache = get_cache()
        self._user_id = cache.get_user_id(image.username)
        color = get_user_svg_color(cache.has_user(self._user_id), is_dark)
        cached_avatar = cache.get_avatar(self._user_id) if self._user_id else None
        self._avatar_label.setPixmap(
            make_avatar_pixmap(self._icons_path, cached_avatar, _BADGE_AVATAR_SIZE, _BADGE_SVG_AVATAR_SIZE, color)
        )
        if self._user_id and not cached_avatar:
            cache.load_avatar_async(self._user_id, self._avatar_ready.emit)
        style = _PANEL_STYLES[is_dark]
        self.setStyleSheet(_panel_stylesheet("sourceBadge", is_dark))
        self._username_label.setText(image.username)
        self._username_label.setStyleSheet(f"color: {cache.get_username_color(image.username, is_dark)};")
        self._time_label.setText(self._format_time(image))
        self._time_label.setStyleSheet(f"color: {style['muted']};")
        self._refresh_tooltip()
        self.adjustSize()

    @staticmethod
    def _format_time(image: GalleryImage) -> str:
        if image.timestamp is None:
            return ""
        pattern = "%H:%M:%S" if image.timestamp.date() == date.today() else "%Y-%m-%d %H:%M:%S"
        return image.timestamp.strftime(pattern)

    def _on_avatar_ready(self, user_id: str, pixmap: QPixmap):
        if user_id == self._user_id:
            self._avatar_label.setPixmap(make_rounded_pixmap(pixmap, _BADGE_AVATAR_SIZE, _BADGE_AVATAR_RADIUS))

    def _refresh_tooltip(self):
        self.setToolTip(tr("Go to message", "Перейти к сообщению"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()

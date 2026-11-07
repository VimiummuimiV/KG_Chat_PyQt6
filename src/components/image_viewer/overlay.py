"""Floating panels of the image viewer: source and position badges (top left), close button (top right), gallery bar and reply panel (bottom center), notice."""

from datetime import date
from pathlib import Path
from typing import NamedTuple, Optional

from PyQt6.QtCore import pyqtSignal, QBuffer, QEvent, QIODevice, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from components.avatar import apply_user_avatar, make_avatar_label
from components.button import create_icon_button, get_user_svg_color, render_svg_icon, set_button_icon
from components.image_viewer.gallery import DayState, GalleryImage
from components.input_row import InputRow
from helpers.cache import get_cache
from helpers.fonts.fonts import FontType, get_font
from helpers.input_style import resolve_input_style
from helpers.translate import tr


_THUMBNAIL_SIZE = QSize(84, 56)
_THUMBNAIL_MAX_VISIBLE = 9
_THUMBNAIL_GAP = 6
_THUMBNAIL_RADIUS = 4
_THUMBNAIL_BORDER_WIDTH = 2
_THUMBNAIL_DIMMED_OPACITY = 0.55
_UNAVAILABLE_ICON = "image-fill.svg"
_UNAVAILABLE_ICON_SIZE = 24
_GROUP_SPACING = 16
_POSITION_SEPARATOR = "  ·  "
_NOTICE_ICON_SIZE = 40
_PANEL_MARGIN = 10
_PANEL_SPACING = 8
_PANEL_RADIUS = 12
_BADGE_AVATAR_SIZE = 28
_BADGE_SVG_AVATAR_SIZE = 20
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


def _thumbnail_window(index: int, count: int) -> range:
    """Gallery indices shown in the strip: a window of thumbnails around the current image."""
    visible = min(count, _THUMBNAIL_MAX_VISIBLE)
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
        reader.setScaledSize(source_size.scaled(_THUMBNAIL_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
    image = reader.read()
    if image.isNull():
        return None
    image = image.scaled(
        _THUMBNAIL_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
    )
    left = (image.width() - _THUMBNAIL_SIZE.width()) // 2
    top = (image.height() - _THUMBNAIL_SIZE.height()) // 2
    return QPixmap.fromImage(image.copy(left, top, _THUMBNAIL_SIZE.width(), _THUMBNAIL_SIZE.height()))


class _ThumbnailStrip(QWidget):
    """Row of clickable thumbnails; the current one is outlined, the others dimmed."""

    clicked = pyqtSignal(int)

    def __init__(self, icons_path: Path, parent=None):
        super().__init__(parent)
        self.indices = range(0)
        self._icons_path = icons_path
        self._current = 0
        self._is_dark = True
        self._thumbnails: dict[int, Optional[QPixmap]] = {}  # None = image unavailable
        self._unavailable_icon = QPixmap()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_state(self, indices: range, current: int):
        self.indices = indices
        self._current = current
        width = len(indices) * (_THUMBNAIL_SIZE.width() + _THUMBNAIL_GAP) - _THUMBNAIL_GAP
        self.setFixedSize(max(width, 0), _THUMBNAIL_SIZE.height())
        self.update()

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        icon = render_svg_icon(self._icons_path / _UNAVAILABLE_ICON, _UNAVAILABLE_ICON_SIZE, _PANEL_STYLES[is_dark]["muted"])
        self._unavailable_icon = icon.pixmap(_UNAVAILABLE_ICON_SIZE, _UNAVAILABLE_ICON_SIZE)
        self.update()

    def set_thumbnail(self, index: int, pixmap: Optional[QPixmap]):
        """Store the thumbnail of an image; None marks it as unavailable."""
        self._thumbnails[index] = pixmap
        self.update()

    def has_thumbnail(self, index: int) -> bool:
        return index in self._thumbnails

    def clear(self):
        self._thumbnails.clear()
        self.indices = range(0)

    def _slot_rect(self, slot: int) -> QRect:
        return QRect(slot * (_THUMBNAIL_SIZE.width() + _THUMBNAIL_GAP), 0, _THUMBNAIL_SIZE.width(), _THUMBNAIL_SIZE.height())

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
                if index in self._thumbnails:
                    icon_rect = QRect(0, 0, _UNAVAILABLE_ICON_SIZE, _UNAVAILABLE_ICON_SIZE)
                    icon_rect.moveCenter(rect.center())
                    painter.drawPixmap(icon_rect, self._unavailable_icon)
            painter.restore()
            if is_current:
                painter.setPen(QPen(accent, _THUMBNAIL_BORDER_WIDTH))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                half = _THUMBNAIL_BORDER_WIDTH / 2
                painter.drawRoundedRect(QRectF(rect).adjusted(half, half, -half, -half), _THUMBNAIL_RADIUS, _THUMBNAIL_RADIUS)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            slot = int(event.position().x()) // (_THUMBNAIL_SIZE.width() + _THUMBNAIL_GAP)
            if 0 <= slot < len(self.indices):
                self.clicked.emit(self.indices[slot])
        event.accept()


class GalleryBar(QFrame):
    """Translucent panel with message actions, navigation buttons, day buttons and thumbnail strip."""

    previous_requested = pyqtSignal()
    next_requested = pyqtSignal()
    slideshow_toggled = pyqtSignal()
    thumbnail_clicked = pyqtSignal(int)
    day_pressed = pyqtSignal(int)  # -1 / +1; the viewer repeats it while the button stays down
    day_released = pyqtSignal()
    reply_requested = pyqtSignal()
    source_requested = pyqtSignal()

    def __init__(self, icons_path: Path, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("galleryBar")
        self._is_playing = False

        self._reply_button = create_icon_button(icons_path, "reply.svg", config=config)
        self._source_button = create_icon_button(icons_path, "crosshair.svg", config=config)
        self._previous_button = create_icon_button(icons_path, "arrow-left.svg", config=config)
        self._slideshow_button = create_icon_button(icons_path, "play.svg", config=config)
        self._next_button = create_icon_button(icons_path, "arrow-right.svg", config=config)
        self._previous_day_button = create_icon_button(icons_path, "calendar-arrow-left.svg", config=config)
        self._next_day_button = create_icon_button(icons_path, "calendar-arrow-right.svg", config=config)
        self._image_buttons = (self._previous_button, self._slideshow_button, self._next_button)
        side_buttons = (self._reply_button, self._source_button, self._previous_day_button, self._next_day_button)
        for button in (*self._image_buttons, *side_buttons):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the viewer
        for button in side_buttons:
            policy = button.sizePolicy()
            policy.setRetainSizeWhenHidden(True)  # equal side groups keep the navigation buttons centered
            button.setSizePolicy(policy)
        self._reply_button.clicked.connect(self.reply_requested)
        self._source_button.clicked.connect(self.source_requested)
        for button, step in ((self._previous_day_button, -1), (self._next_day_button, 1)):
            button.pressed.connect(lambda step=step: self.day_pressed.emit(step))
            button.released.connect(self.day_released)
        self._previous_button.clicked.connect(self.previous_requested)
        self._slideshow_button.clicked.connect(self.slideshow_toggled)
        self._next_button.clicked.connect(self.next_requested)

        self._strip = _ThumbnailStrip(icons_path, self)
        self._strip.clicked.connect(self.thumbnail_clicked)

        controls = QHBoxLayout()
        controls.setSpacing(_PANEL_SPACING)
        controls.addWidget(self._reply_button)
        controls.addWidget(self._source_button)
        controls.addSpacing(_GROUP_SPACING)
        for button in self._image_buttons:
            controls.addWidget(button)
        controls.addSpacing(_GROUP_SPACING)
        controls.addWidget(self._previous_day_button)
        controls.addWidget(self._next_day_button)

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

    def set_message_actions(self, can_go_to_source: bool, can_reply: bool):
        """Show the buttons that act on the message of the current image."""
        self._source_button.setVisible(can_go_to_source)
        self._reply_button.setVisible(can_reply)

    def set_position(self, index: int, count: int, show_thumbnails: bool, day_state: Optional[DayState]):
        """Update the navigation buttons, thumbnail window and day buttons for the image at index of count."""
        for button in self._image_buttons:
            button.setEnabled(count > 1)
        self._set_day(day_state)
        self._strip.setVisible(show_thumbnails)
        self._strip.set_state(_thumbnail_window(index, count) if show_thumbnails else range(0), index)
        self._refresh_tooltips()
        self._fit_to_content()

    def _set_day(self, state: Optional[DayState]):
        """Show the chatlog day buttons for the state, or hide them when days do not apply."""
        for button in (self._previous_day_button, self._next_day_button):
            button.setVisible(state is not None)
        if state is not None:
            self._previous_day_button.setEnabled(state.has_previous)
            self._next_day_button.setEnabled(state.has_next)

    def _fit_to_content(self):
        self.layout().invalidate()  # a hidden widget keeps its stale layout until shown
        self.layout().activate()  # nested layouts of just shown widgets would otherwise report stale sizes
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

    def set_thumbnail(self, index: int, pixmap: Optional[QPixmap]):
        self._strip.set_thumbnail(index, pixmap)

    def clear_thumbnails(self):
        self._strip.clear()

    def _refresh_tooltips(self):
        self._reply_button.setToolTip(tr("Reply to the message (R)", "Ответить на сообщение (R)"))
        self._source_button.setToolTip(tr("Go to the message (G)", "Перейти к сообщению (G)"))
        self._previous_button.setToolTip(tr("Previous image (H / ←)", "Предыдущее изображение (H / ←)"))
        self._next_button.setToolTip(tr("Next image (L / →)", "Следующее изображение (L / →)"))
        self._previous_day_button.setToolTip(tr("Previous day (Shift+H / Shift+←)", "Предыдущий день (Shift+H / Shift+←)"))
        self._next_day_button.setToolTip(tr("Next day (Shift+L / Shift+→)", "Следующий день (Shift+L / Shift+→)"))
        self._slideshow_button.setToolTip(
            tr("Stop slideshow (P)", "Остановить слайдшоу (P)") if self._is_playing
            else tr("Start slideshow (P)", "Запустить слайдшоу (P)")
        )


class CloseButton(QFrame):
    """Translucent panel with the button that closes the viewer."""

    clicked = pyqtSignal()

    def __init__(self, icons_path: Path, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("closeButton")
        self._button = create_icon_button(icons_path, "close.svg", config=config)
        self._button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the viewer
        self._button.clicked.connect(self.clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PANEL_MARGIN, _PANEL_MARGIN, _PANEL_MARGIN, _PANEL_MARGIN)
        layout.addWidget(self._button)
        self.adjustSize()
        self.refresh_tooltip()

    def apply_theme(self, is_dark: bool):
        """Restyle the panel for the theme."""
        self.setStyleSheet(_panel_stylesheet("closeButton", is_dark))

    def refresh_tooltip(self):
        """Re-translate the tooltip for the current interface language."""
        self._button.setToolTip(tr("Close (Esc / Space / Q / RMB)", "Закрыть (Esc / Space / Q / ПКМ)"))


class NoticeKind(NamedTuple):
    icon: str
    color: str


NOTICE_ERROR = NoticeKind("close-circle-line.svg", "#e53935")
NOTICE_WARNING = NoticeKind("error-warning-line.svg", "#fbc02d")


class Notice(QFrame):
    """Icon with a caption on an opaque black plate, colored by its kind."""

    def __init__(self, icons_path: Path, parent=None):
        super().__init__(parent)
        self.setObjectName("galleryNotice")
        self.setStyleSheet(
            f"#galleryNotice {{ background-color: #000000; border-radius: {_PANEL_RADIUS}px; }}"
            "#galleryNotice QLabel { background: transparent; }"
        )
        self._icons_path = icons_path
        self._icon_label = QLabel()
        self._label = QLabel()
        self._label.setFont(get_font(FontType.UI))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(_PANEL_MARGIN, _PANEL_MARGIN, _PANEL_MARGIN, _PANEL_MARGIN)
        layout.setSpacing(_PANEL_SPACING)
        layout.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignHCenter)

    def show_notice(self, kind: NoticeKind, text: str):
        icon = render_svg_icon(self._icons_path / kind.icon, _NOTICE_ICON_SIZE, kind.color)
        self._icon_label.setPixmap(icon.pixmap(_NOTICE_ICON_SIZE, _NOTICE_ICON_SIZE))
        self._label.setStyleSheet(f"color: {kind.color};")
        self._label.setText(text)
        self.adjustSize()
        self.show()


class SourceBadge(QFrame):
    """Compact avatar + username + time of the message the current image was posted in; click jumps to it."""

    clicked = pyqtSignal()

    def __init__(self, icons_path: Path, parent=None):
        super().__init__(parent)
        self.setObjectName("sourceBadge")
        self._icons_path = icons_path
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

        self._refresh_tooltip()

    def show_image(self, image: GalleryImage, is_dark: bool):
        """Fill the badge with the sender and time of the message that holds this image."""
        cache = get_cache()
        apply_user_avatar(
            self._avatar_label, cache.get_user_id(image.username), _BADGE_AVATAR_SIZE, _BADGE_SVG_AVATAR_SIZE,
            is_dark, self._icons_path,
        )
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

    def _refresh_tooltip(self):
        self.setToolTip(tr("Go to message", "Перейти к сообщению"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()


class PositionBadge(QFrame):
    """Compact "index / count" of the current image with the chatlog day when days apply."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("positionBadge")
        self._label = QLabel()
        self._label.setFont(get_font(FontType.TEXT))
        self.setMinimumHeight(_BADGE_AVATAR_SIZE + 2 * _BADGE_MARGIN)  # same height as the source badge
        layout = QHBoxLayout(self)
        layout.setContentsMargins(_BADGE_MARGIN + _BADGE_SPACING, _BADGE_MARGIN, _BADGE_MARGIN + _BADGE_SPACING, _BADGE_MARGIN)
        layout.addWidget(self._label)

    def show_position(self, index: int, count: int, day: Optional[date], is_dark: bool):
        """Fill the badge for the image at index of count; day is None outside chatlog days."""
        self.setStyleSheet(_panel_stylesheet("positionBadge", is_dark))
        text = f"{index + 1 if count else 0} / {count}"
        self._label.setText(f"{text}{_POSITION_SEPARATOR}{day:%Y-%m-%d}" if day else text)
        self.adjustSize()


class ReplyPanel(QFrame):
    """Translucent panel with the input of a reply written inside the viewer; Esc cancels."""

    cancelled = pyqtSignal()

    def __init__(self, icons_path: Path, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("replyPanel")
        self._config = config
        self.input_row = InputRow(icons_path, config, parent=self)
        self.input_row.input_field.installEventFilter(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PANEL_MARGIN, _PANEL_MARGIN, _PANEL_MARGIN, _PANEL_MARGIN)
        layout.addWidget(self.input_row)

    def open(self, text: str, has_emoticons: bool, is_dark: bool):
        """Show the panel with the text in the field and the cursor at its end."""
        self.setStyleSheet(_panel_stylesheet("replyPanel", is_dark))
        field = self.input_row.input_field
        if self._config:
            field.setStyleSheet(resolve_input_style(self._config, is_dark)[0])
        self.input_row.emoticon_button.setVisible(has_emoticons)
        field.setText(text)
        field.setCursorPosition(len(text))
        self.show()
        field.setFocus()

    def focus_field(self):
        self.input_row.input_field.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.input_row.input_field and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return True
        return super().eventFilter(watched, event)

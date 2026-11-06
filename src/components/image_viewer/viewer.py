"""Fullscreen image viewer: gallery navigation, slideshow, transitions and source badge."""

from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QCursor, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from components.help_panel import HelpPanel
from components.image_viewer.gallery import DayState, extract_image_url, GalleryImage, ImageGallery
from components.image_viewer.layer import ImageLayer, INSTANT_MODE, TransitionAnimator
from components.image_viewer.options import (
    show_thumbnails,
    slideshow_interval_ms,
    transition_duration_ms,
    transition_mode,
)
from components.image_viewer.overlay import CloseButton, GalleryBar, make_thumbnail, SourceBadge, UnavailableNotice
from components.loading_spinner import LoadingSpinner
from core.web.image_loader import ImageLoader
from helpers.data import get_resource_dir


_MIN_SCALE = 0.1
_MAX_SCALE = 10.0
_ZOOM_IN_FACTOR = 1.15
_ZOOM_OUT_FACTOR = 0.87
_SCALE_DRAG_SENSITIVITY = 0.003
_DRAG_PAN = "pan"
_DRAG_SCALE = "scale"
_SPINNER_SIZE = 60
_SPINNER_FOLLOW_INTERVAL_MS = 16
_SPINNER_FOLLOW_THRESHOLD = 5
_OVERLAY_MARGIN = 16
_CURRENT_PRIORITY = 2
_NEIGHBOR_PRIORITY = 1
_THUMBNAIL_PRIORITY = 0
_NAVIGATION_KEYS = {
    Qt.Key.Key_H: -1,
    Qt.Key.Key_Left: -1,
    Qt.Key.Key_L: 1,
    Qt.Key.Key_Right: 1,
}


class ImageHoverView(QWidget):
    """Fullscreen viewport for image view with internal image transformations"""

    _active_viewer: Optional["ImageHoverView"] = None  # only one viewer is open at a time

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self._config = config
        self._gallery: Optional[ImageGallery] = None
        self._index = 0
        self._direction = 0
        self._is_dark = True
        self._is_playing = False
        self._layer: Optional[ImageLayer] = None
        self._outgoing: Optional[ImageLayer] = None

        screen = QApplication.primaryScreen()
        self._screen_rect = screen.availableGeometry()

        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setGeometry(self._screen_rect)
        self.hide()

        self._loader = ImageLoader(self)
        self._loader.loaded.connect(self._on_image_loaded)

        self._loading_spinner = LoadingSpinner(None, _SPINNER_SIZE)
        self._position_timer = QTimer()
        self._position_timer.timeout.connect(self._update_spinner_position)
        self._target_pos = None

        self._transition = TransitionAnimator(self)
        self._transition.changed.connect(self.update)
        self._transition.finished.connect(self._release_outgoing)

        self._slideshow_timer = QTimer(self)
        self._slideshow_timer.setSingleShot(True)
        self._slideshow_timer.timeout.connect(lambda: self._navigate(1))

        icons_path = get_resource_dir("icons")
        self._gallery_bar = GalleryBar(icons_path, config, self)
        self._gallery_bar.previous_requested.connect(lambda: self._navigate(-1))
        self._gallery_bar.next_requested.connect(lambda: self._navigate(1))
        self._gallery_bar.slideshow_toggled.connect(self._toggle_slideshow)
        self._gallery_bar.thumbnail_clicked.connect(self._on_thumbnail_clicked)
        self._gallery_bar.day_requested.connect(self._on_day_requested)
        self._gallery_bar.hide()
        self._unavailable_notice = UnavailableNotice(icons_path, self)
        self._unavailable_notice.hide()
        self._source_badge = SourceBadge(icons_path, self)
        self._source_badge.clicked.connect(self._on_source_clicked)
        self._source_badge.hide()
        self._close_button = CloseButton(icons_path, config, self)
        self._close_button.clicked.connect(self.hide_preview)
        self._close_button.hide()

        self._drag_mode: Optional[str] = None
        self._last_mouse_pos: Optional[QPointF] = None

        self._help_panel = HelpPanel(self)

    @property
    def _current_image(self) -> Optional[GalleryImage]:
        return self._gallery.images[self._index] if self._gallery else None

    def paintEvent(self, event):
        """Paint the current image, and the outgoing one while a transition runs"""
        if not self._layer:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._outgoing and self._transition.running:
            outgoing_pose, incoming_pose = self._transition.poses()
            self._outgoing.paint(painter, self.size(), outgoing_pose)
            self._layer.paint(painter, self.size(), incoming_pose)
        else:
            self._layer.paint(painter, self.size())

    def show_preview(self, url: str, cursor_pos: QPoint, gallery: Optional[ImageGallery] = None):
        image_url = extract_image_url(url)
        current = self._current_image
        if not image_url or (current and current.url == image_url and self.isVisible()):
            return

        self.hide_preview()
        active = ImageHoverView._active_viewer
        if active is not None and active is not self:
            active.hide_preview()
        ImageHoverView._active_viewer = self
        self.update_theme((self._config.get("ui", "theme") if self._config else None) != "light")
        self._gallery = gallery or ImageGallery.single(image_url)
        if self._gallery.messages_replaced:
            self._gallery.messages_replaced.connect(self._on_messages_replaced)

        spinner_pos = LoadingSpinner.calculate_position(
            cursor_pos, self._loading_spinner.width(), self._screen_rect
        )
        self._loading_spinner.move(spinner_pos)
        self._loading_spinner.start()
        self._target_pos = cursor_pos
        self._position_timer.start(_SPINNER_FOLLOW_INTERVAL_MS)

        self._show_image(self._gallery.start_index, 0)

    def update_theme(self, is_dark: bool):
        """Re-theme the overlays; also called while the viewer is open when the app theme is switched."""
        self._is_dark = is_dark
        self._gallery_bar.apply_theme(is_dark)
        self._close_button.apply_theme(is_dark)
        self._unavailable_notice.apply_theme(is_dark)
        if self._gallery:
            self._update_overlays(self._current_image)

    def _on_messages_replaced(self):
        """Rebuild the gallery after its messages were replaced, keeping the current image if it is still there."""
        current_url = self._current_image.url
        self._gallery = self._gallery.reloaded(current_url)
        self._gallery_bar.clear_thumbnails()
        self._position_timer.stop()
        kept_index = next((index for index, image in enumerate(self._gallery.images) if image.url == current_url), None)
        if kept_index is None:
            self._show_image(0, 1)
            return
        self._index = kept_index
        self._update_overlays(self._current_image)
        self._prefetch_neighbors()
        self._request_thumbnails()

    def _show_image(self, index: int, direction: int):
        """Make the image at index current: show it as soon as it is loaded, and warm up its neighbors."""
        self._index = index
        self._direction = direction
        self._unavailable_notice.hide()
        image = self._gallery.images[index]
        self._update_overlays(image)

        data = self._loader.request(image.url, _CURRENT_PRIORITY)
        self._prefetch_neighbors()
        self._request_thumbnails()
        if data is not None:
            self._display(image.url, data)
        elif self._loader.has_failed(image.url):
            self._on_current_failed()
        elif direction:
            self._start_spinner_at_center()

    def _prefetch_neighbors(self):
        images = self._gallery.images
        if len(images) < 2:
            return
        for step in (1, -1):
            self._loader.request(images[(self._index + step) % len(images)].url, _NEIGHBOR_PRIORITY)

    def _request_thumbnails(self):
        for index in self._gallery_bar.visible_indices():
            if self._gallery_bar.has_thumbnail(index):
                continue
            url = self._gallery.images[index].url
            data = self._loader.request(url, _THUMBNAIL_PRIORITY)
            if data is not None or self._loader.has_failed(url):
                self._store_thumbnail(url, data)

    def _store_thumbnail(self, url: str, data: Optional[bytes]):
        """Give every thumbnail slot of the url its picture; None or undecodable data marks it unavailable."""
        indices = [
            index for index, image in enumerate(self._gallery.images)
            if image.url == url and not self._gallery_bar.has_thumbnail(index)
        ]
        if not indices:
            return
        thumbnail = make_thumbnail(data) if data is not None else None
        for index in indices:
            self._gallery_bar.set_thumbnail(index, thumbnail)

    def _on_image_loaded(self, url: str, data: bytes, is_error: bool):
        """Handle loaded image data"""
        if not self._gallery:
            return
        self._store_thumbnail(url, None if is_error else data)
        if url != self._current_image.url:
            return
        if is_error:
            self._on_current_failed()
        else:
            self._display(url, data)

    def _display(self, url: str, data: bytes):
        try:
            layer = ImageLayer.from_data(url, data, self.update)
        except Exception as e:
            print(f"Error displaying image: {e}")
            layer = None
        if layer is None:
            self._on_current_failed()
        else:
            self._present(layer)

    def _on_current_failed(self):
        """Replace the image with a red cross and a caption so the user sees why nothing is shown."""
        self._stop_spinner()
        self._release_layers()
        self._unavailable_notice.refresh_text()
        self._unavailable_notice.move(
            (self.width() - self._unavailable_notice.width()) // 2,
            (self.height() - self._reserved_bottom() - self._unavailable_notice.height()) // 2,
        )
        self._unavailable_notice.show()
        self._show_widget()
        self._restart_slideshow_timer()

    def _present(self, layer: ImageLayer):
        """Show the layer, animating from the previous one when there is one."""
        self._stop_spinner()
        layer.fit(self.size(), self._reserved_bottom())
        previous = self._layer
        self._release_outgoing()
        self._layer = layer
        mode = transition_mode(self._config)
        if previous is None:
            self._show_widget()
            self.update()
        elif mode == INSTANT_MODE:
            previous.release()
            self.update()
        else:
            self._outgoing = previous
            self._transition.start(mode, self._direction, transition_duration_ms(self._config))
        self._restart_slideshow_timer()

    def _release_layers(self):
        self._release_outgoing()
        if self._layer:
            self._layer.release()
            self._layer = None
            self.update()

    def _release_outgoing(self):
        self._transition.stop()
        if self._outgoing:
            self._outgoing.release()
            self._outgoing = None
            self.update()

    def _reserved_bottom(self) -> int:
        """Height kept free at the bottom for the gallery bar."""
        return self._gallery_bar.height() + 2 * _OVERLAY_MARGIN if self._gallery_bar.isVisibleTo(self) else 0

    def _update_overlays(self, image: GalleryImage):
        count = len(self._gallery.images)
        has_source = image.source is not None and self._gallery.on_source is not None
        day_state = self._day_state()
        self._gallery_bar.setVisible(count > 1 or day_state is not None)
        self._gallery_bar.set_position(self._index, count, show_thumbnails(self._config), day_state)
        self._gallery_bar.move(
            (self.width() - self._gallery_bar.width()) // 2,
            self.height() - self._gallery_bar.height() - _OVERLAY_MARGIN,
        )
        self._close_button.refresh_tooltip()
        self._close_button.move(self.width() - self._close_button.width() - _OVERLAY_MARGIN, _OVERLAY_MARGIN)
        self._close_button.show()
        self._source_badge.setVisible(has_source)
        if has_source:
            self._source_badge.show_image(image, self._is_dark)
            self._source_badge.move(_OVERLAY_MARGIN, _OVERLAY_MARGIN)

    def _start_spinner_at_center(self):
        self._position_timer.stop()
        center = self._screen_rect.center()
        self._loading_spinner.move(center.x() - self._loading_spinner.width() // 2,
                                  center.y() - self._loading_spinner.height() // 2)
        self._loading_spinner.start()

    def _stop_spinner(self):
        """Stop and hide loading spinner"""
        self._loading_spinner.stop()

    def _show_widget(self):
        """Show and focus widget"""
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _navigate(self, step: int):
        """Go to the next (+1) or previous (-1) image, wrapping around."""
        count = len(self._gallery.images) if self._gallery else 0
        if count > 1:
            self._go_to((self._index + step) % count, step)

    def _go_to(self, index: int, direction: int):
        if index != self._index:
            self._position_timer.stop()
            self._show_image(index, direction)

    def _day_state(self) -> Optional[DayState]:
        navigation = self._gallery.day_navigation
        return navigation.state() if navigation else None

    def _on_day_requested(self, step: int):
        """Switch the chatlog behind the viewer by a day; the gallery follows once its messages are replaced."""
        self._gallery.day_navigation.step(step)
        self._update_overlays(self._current_image)

    def _on_thumbnail_clicked(self, index: int):
        self._go_to(index, 1 if index > self._index else -1)

    def _toggle_slideshow(self):
        if self._gallery and len(self._gallery.images) > 1:
            self._set_slideshow_playing(not self._is_playing)

    def _set_slideshow_playing(self, is_playing: bool):
        self._is_playing = is_playing
        self._gallery_bar.set_slideshow_playing(is_playing)
        self._restart_slideshow_timer()

    def _restart_slideshow_timer(self):
        """Count the interval from the moment the current image is shown."""
        self._slideshow_timer.stop()
        if self._is_playing:
            self._slideshow_timer.start(slideshow_interval_ms(self._config))

    def _on_source_clicked(self):
        """Close the viewer and let the owning view scroll to the message of the current image."""
        gallery, image = self._gallery, self._current_image
        self.hide_preview()
        gallery.on_source(image.source)

    def _update_spinner_position(self):
        """Update spinner position to follow cursor"""
        if self._target_pos and self._loading_spinner.isVisible():
            cursor_pos = QCursor.pos()
            if (abs(cursor_pos.x() - self._target_pos.x()) > _SPINNER_FOLLOW_THRESHOLD
                    or abs(cursor_pos.y() - self._target_pos.y()) > _SPINNER_FOLLOW_THRESHOLD):
                self._target_pos = cursor_pos
                spinner_pos = LoadingSpinner.calculate_position(
                    cursor_pos, self._loading_spinner.width(), self._screen_rect
                )
                self._loading_spinner.move(spinner_pos)

    def _apply_zoom(self, new_scale: float, pivot: QPointF):
        """Apply zoom transformation around pivot point"""
        if not self._layer or not (_MIN_SCALE <= new_scale <= _MAX_SCALE):
            return
        point_before = (pivot - self._layer.offset) / self._layer.scale
        self._layer.scale = new_scale
        self._layer.offset = pivot - point_before * new_scale
        self.update()

    def wheelEvent(self, event):
        """Handle mouse wheel for zoom"""
        if self._layer:
            scale_factor = _ZOOM_IN_FACTOR if event.angleDelta().y() > 0 else _ZOOM_OUT_FACTOR
            self._apply_zoom(self._layer.scale * scale_factor, event.position())
            event.accept()

    def mousePressEvent(self, event):
        """Handle mouse press for dragging or scaling"""
        if event.button() == Qt.MouseButton.LeftButton:
            is_ctrl = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
            self._drag_mode = _DRAG_SCALE if is_ctrl else _DRAG_PAN
            self._last_mouse_pos = event.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.hide_preview()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging or scaling"""
        if not self._drag_mode or not self._layer:
            return

        delta = event.position() - self._last_mouse_pos

        if self._drag_mode == _DRAG_PAN:
            self._layer.offset += delta
            self.update()
        else:
            new_scale = self._layer.scale * (1.0 - delta.y() * _SCALE_DRAG_SENSITIVITY)
            new_scale = max(_MIN_SCALE, min(new_scale, _MAX_SCALE))
            center = QPointF(self.width() / 2, self.height() / 2)
            self._apply_zoom(new_scale, center)

        self._last_mouse_pos = event.position()
        event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if event.button() == Qt.MouseButton.LeftButton and self._drag_mode:
            self._end_drag()
            event.accept()

    def _end_drag(self):
        self._drag_mode = self._last_mouse_pos = None
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts - layout independent"""
        key, native_key = event.key(), event.nativeVirtualKey()
        step = _NAVIGATION_KEYS.get(key) or _NAVIGATION_KEYS.get(native_key)

        if key == Qt.Key.Key_F1:
            self._help_panel.show_for_context('image')
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_Escape) or Qt.Key.Key_Q in (key, native_key):
            self.hide_preview()
            event.accept()
        elif step:
            self._navigate(step)
            event.accept()
        elif Qt.Key.Key_P in (key, native_key):
            if not event.isAutoRepeat():
                self._toggle_slideshow()
            event.accept()
        else:
            super().keyPressEvent(event)

    def hide_preview(self):
        """Hide preview and reset state"""
        self._position_timer.stop()
        self._slideshow_timer.stop()
        self._stop_spinner()
        self._loader.reset()
        self._release_layers()
        self._unavailable_notice.hide()
        if ImageHoverView._active_viewer is self:
            ImageHoverView._active_viewer = None
        self._set_slideshow_playing(False)
        self._gallery_bar.clear_thumbnails()
        if self._help_panel:
            self._help_panel.close()

        if self._gallery and self._gallery.messages_replaced:
            try:
                self._gallery.messages_replaced.disconnect(self._on_messages_replaced)
            except (RuntimeError, TypeError):
                pass  # the source model is already gone
        self._gallery = self._target_pos = None
        self._end_drag()
        self.hide()

    def cleanup(self):
        """Cleanup resources"""
        self.hide_preview()
        if self._help_panel:
            self._help_panel.deleteLater()
            self._help_panel = None

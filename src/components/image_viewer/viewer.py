"""Fullscreen image viewer: gallery navigation, slideshow, transitions and source badge."""

from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QCursor, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from components.help_panel import HelpPanel
from components.image_viewer.gallery import extract_image_url, GalleryImage, ImageGallery
from components.image_viewer.layer import ImageLayer, INSTANT_MODE, TransitionAnimator
from components.image_viewer.options import (
    show_thumbnails,
    slideshow_interval_ms,
    transition_duration_ms,
    transition_mode,
)
from components.image_viewer.overlay import GalleryBar, make_thumbnail, SourceBadge
from components.loading_spinner import LoadingSpinner
from core.web.image_loader import ImageLoader
from helpers.data import get_resource_dir


_MIN_SCALE = 0.1
_MAX_SCALE = 10.0
_ZOOM_IN_FACTOR = 1.15
_ZOOM_OUT_FACTOR = 0.87
_SCALE_DRAG_SENSITIVITY = 0.003
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

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config
        self._gallery: Optional[ImageGallery] = None
        self._index = 0
        self._direction = 0
        self._is_dark = True
        self._is_playing = False
        self._layer: Optional[ImageLayer] = None
        self._outgoing: Optional[ImageLayer] = None

        screen = QApplication.primaryScreen()
        self.screen_rect = screen.availableGeometry()

        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setGeometry(self.screen_rect)
        self.hide()

        self.loader = ImageLoader(self)
        self.loader.loaded.connect(self._on_image_loaded)

        self.loading_spinner = LoadingSpinner(None, _SPINNER_SIZE)
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_spinner_position)
        self.target_pos = None

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
        self._gallery_bar.hide()
        self._source_badge = SourceBadge(icons_path, self)
        self._source_badge.clicked.connect(self._on_source_clicked)
        self._source_badge.hide()

        # Image interaction state
        self.dragging, self.scaling, self.last_mouse_pos = False, False, None

        self.help_panel = HelpPanel(self)

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
        self._gallery = gallery or ImageGallery.single(image_url)
        self._is_dark = (self.config.get("ui", "theme") if self.config else None) != "light"
        self._gallery_bar.apply_theme(self._is_dark)

        spinner_pos = LoadingSpinner.calculate_position(
            cursor_pos, self.loading_spinner.width(), self.screen_rect
        )
        self.loading_spinner.move(spinner_pos)
        self.loading_spinner.start()
        self.target_pos = cursor_pos
        self.position_timer.start(_SPINNER_FOLLOW_INTERVAL_MS)

        self._show_image(self._gallery.start_index, 0)

    def _show_image(self, index: int, direction: int):
        """Make the image at index current: show it as soon as it is loaded, and warm up its neighbors."""
        self._index = index
        self._direction = direction
        image = self._gallery.images[index]
        self._update_overlays(image)

        data = self.loader.request(image.url, _CURRENT_PRIORITY)
        self._prefetch_neighbors()
        self._request_thumbnails()
        if data is not None:
            self._display(image.url, data)
        elif self.loader.has_failed(image.url):
            self._on_current_failed()
        elif direction:
            self._start_spinner_at_center()

    def _prefetch_neighbors(self):
        images = self._gallery.images
        if len(images) < 2:
            return
        for step in (1, -1):
            self.loader.request(images[(self._index + step) % len(images)].url, _NEIGHBOR_PRIORITY)

    def _request_thumbnails(self):
        for index in self._gallery_bar.visible_indices():
            if self._gallery_bar.has_thumbnail(index):
                continue
            url = self._gallery.images[index].url
            data = self.loader.request(url, _THUMBNAIL_PRIORITY)
            if data is not None:
                self._store_thumbnail(url, data)

    def _store_thumbnail(self, url: str, data: bytes):
        indices = [
            index for index, image in enumerate(self._gallery.images)
            if image.url == url and not self._gallery_bar.has_thumbnail(index)
        ]
        if not indices:
            return
        thumbnail = make_thumbnail(data)
        if thumbnail:
            for index in indices:
                self._gallery_bar.set_thumbnail(index, thumbnail)

    def _on_image_loaded(self, url: str, data: bytes, is_error: bool):
        """Handle loaded image data"""
        if not self._gallery:
            return
        if not is_error:
            self._store_thumbnail(url, data)
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
        self._stop_spinner()
        self._restart_slideshow_timer()

    def _present(self, layer: ImageLayer):
        """Show the layer, animating from the previous one when there is one."""
        self._stop_spinner()
        layer.fit(self.size(), self._reserved_bottom())
        previous = self._layer
        self._release_outgoing()
        self._layer = layer
        mode = transition_mode(self.config)
        if previous is None:
            self._show_widget()
        elif mode == INSTANT_MODE:
            previous.release()
            self.update()
        else:
            self._outgoing = previous
            self._transition.start(mode, self._direction, transition_duration_ms(self.config))
        self._restart_slideshow_timer()

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
        self._gallery_bar.setVisible(count > 1)
        self._gallery_bar.set_position(self._index, count, show_thumbnails(self.config))
        self._gallery_bar.move(
            (self.width() - self._gallery_bar.width()) // 2,
            self.height() - self._gallery_bar.height() - _OVERLAY_MARGIN,
        )
        self._source_badge.setVisible(has_source)
        if has_source:
            self._source_badge.show_image(image, self._is_dark)
            self._source_badge.move(_OVERLAY_MARGIN, _OVERLAY_MARGIN)

    def _start_spinner_at_center(self):
        self.position_timer.stop()
        center = self.screen_rect.center()
        self.loading_spinner.move(center.x() - self.loading_spinner.width() // 2,
                                  center.y() - self.loading_spinner.height() // 2)
        self.loading_spinner.start()

    def _stop_spinner(self):
        """Stop and hide loading spinner"""
        self.loading_spinner.stop()

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
            self.position_timer.stop()
            self._show_image(index, direction)

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
            self._slideshow_timer.start(slideshow_interval_ms(self.config))

    def _on_source_clicked(self):
        """Close the viewer and let the owning view scroll to the message of the current image."""
        gallery, image = self._gallery, self._current_image
        self.hide_preview()
        gallery.on_source(image.source)

    def _update_spinner_position(self):
        """Update spinner position to follow cursor"""
        if self.target_pos and self.loading_spinner.isVisible():
            cursor_pos = QCursor.pos()
            if (abs(cursor_pos.x() - self.target_pos.x()) > _SPINNER_FOLLOW_THRESHOLD
                    or abs(cursor_pos.y() - self.target_pos.y()) > _SPINNER_FOLLOW_THRESHOLD):
                self.target_pos = cursor_pos
                spinner_pos = LoadingSpinner.calculate_position(
                    cursor_pos, self.loading_spinner.width(), self.screen_rect
                )
                self.loading_spinner.move(spinner_pos)

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
            self.scaling, self.dragging = bool(is_ctrl), not is_ctrl
            self.last_mouse_pos = event.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.hide_preview()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging or scaling"""
        if not self.last_mouse_pos or not self._layer:
            return

        delta = event.position() - self.last_mouse_pos

        if self.dragging:
            self._layer.offset += delta
            self.update()
        elif self.scaling:
            new_scale = self._layer.scale * (1.0 - delta.y() * _SCALE_DRAG_SENSITIVITY)
            new_scale = max(_MIN_SCALE, min(new_scale, _MAX_SCALE))
            center = QPointF(self.width() / 2, self.height() / 2)
            self._apply_zoom(new_scale, center)

        self.last_mouse_pos = event.position()
        event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if event.button() == Qt.MouseButton.LeftButton and (self.dragging or self.scaling):
            self.dragging = self.scaling = False
            self.last_mouse_pos = None
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts - layout independent"""
        key, native_key = event.key(), event.nativeVirtualKey()
        step = _NAVIGATION_KEYS.get(key) or _NAVIGATION_KEYS.get(native_key)

        if key == Qt.Key.Key_F1:
            self.help_panel.show_for_context('image')
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
        self.position_timer.stop()
        self._slideshow_timer.stop()
        self._stop_spinner()
        self.loader.reset()
        self._release_outgoing()
        if self._layer:
            self._layer.release()
            self._layer = None
        self._set_slideshow_playing(False)
        self._gallery_bar.clear_thumbnails()
        if self.help_panel:
            self.help_panel.close()

        self._gallery = self.target_pos = self.last_mouse_pos = None
        self.dragging = self.scaling = False
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.hide()

    def cleanup(self):
        """Cleanup resources"""
        self.hide_preview()
        if self.help_panel:
            self.help_panel.deleteLater()
            self.help_panel = None

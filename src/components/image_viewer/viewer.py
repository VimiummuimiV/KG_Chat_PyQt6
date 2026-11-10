"""Fullscreen image viewer: gallery navigation, slideshow, transitions and source badge."""

from typing import Callable, Optional

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from components.help_panel import HelpPanel
from components.image_viewer.controls import CloseButton, EdgeZone, ZoomButtons
from components.image_viewer.gallery import (
    DayState,
    extract_image_url,
    first_image,
    GalleryImage,
    ImageGallery,
    InlineReply,
)
from components.image_viewer.layer import ImageLayer, INSTANT_MODE, TransitionAnimator
from components.image_viewer.options import (
    REPLY_MODE_INLINE,
    reply_mode,
    show_thumbnails,
    slideshow_interval_ms,
    transition_duration_ms,
    transition_mode,
)
from components.image_viewer.overlay import (
    GalleryBar,
    make_thumbnail,
    Notice,
    NOTICE_ERROR,
    NOTICE_WARNING,
    NoticeKind,
    PositionBadge,
    ReplyPanel,
    SourceBadge,
)
from components.loading_spinner import LoadingSpinner
from core.web.image_loader import ImageLoader
from helpers.data import get_resource_dir
from helpers.hold_repeater import HoldRepeater
from helpers.system.memory import release_memory_soon
from helpers.translate import tr


_MIN_SCALE = 0.1
_MAX_SCALE = 10.0
_ZOOM_IN_FACTOR = 1.15
_ZOOM_OUT_FACTOR = 0.87
_ZOOM_BUTTON_FACTOR = 1.25
_SCALE_DRAG_SENSITIVITY = 0.003
_DRAG_PAN = "pan"
_DRAG_SCALE = "scale"
_SPINNER_SIZE = 60
_SPINNER_FOLLOW_INTERVAL_MS = 16
_SPINNER_FOLLOW_THRESHOLD = 5
_OVERLAY_MARGIN = 16
_OVERLAY_SPACING = 8
_REPLY_PANEL_WIDTH = 560
_SELECTOR_SETTLE_MS = 50
_EMOTICON_MIN_HEIGHT = 250
_EMOTICON_MAX_HEIGHT = 650
_NEIGHBOR_PRIORITY = 1
_THUMBNAIL_PRIORITY = 0
_HIT_TEST_FILL = QColor(0, 0, 0, 1)  # on Windows a fully transparent pixel of a translucent window lets the mouse through
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
        self._day_hold = HoldRepeater(self._on_day_requested, self)
        self._gallery_bar.day_pressed.connect(self._day_hold.press)
        self._gallery_bar.day_released.connect(self._day_hold.release)
        self._gallery_bar.reply_requested.connect(self._on_reply_requested)
        self._gallery_bar.source_requested.connect(self._on_source_clicked)
        self._gallery_bar.hide()
        self._notice = Notice(icons_path, self)
        self._notice.hide()
        self._source_badge = SourceBadge(icons_path, self)
        self._source_badge.clicked.connect(self._on_source_clicked)
        self._source_badge.hide()
        self._position_badge = PositionBadge(self)
        self._position_badge.hide()
        self._reply_panel = ReplyPanel(icons_path, config, self)
        self._reply_panel.input_row.submitted.connect(self._on_reply_submitted)
        self._reply_panel.input_row.emoticon_requested.connect(self._toggle_emoticons)
        self._reply_panel.cancelled.connect(self._close_reply)
        self._reply_panel.hide()
        self._inline_reply: Optional[InlineReply] = None
        self._emoticon_selector = None  # the shared selector while it is borrowed from the chat
        self._close_button = CloseButton(icons_path, config, self)
        self._close_button.clicked.connect(self._hide_preview)
        self._close_button.hide()
        self._zoom_buttons = ZoomButtons(icons_path, config, self)
        self._zoom_hold = HoldRepeater(self._zoom_step, self)
        self._zoom_buttons.zoom_pressed.connect(self._zoom_hold.press)
        self._zoom_buttons.zoom_released.connect(self._zoom_hold.release)
        self._zoom_buttons.hide()
        self._edge_zones = (EdgeZone(icons_path, True, self), EdgeZone(icons_path, False, self))
        for zone, step in zip(self._edge_zones, (-1, 1)):
            zone.clicked.connect(lambda step=step: self._navigate(step))
            zone.cursor_left.connect(self._update_edge_zones)

        self._drag_mode: Optional[str] = None
        self._last_mouse_pos: Optional[QPointF] = None

        self._help_panel = HelpPanel(self)

    @property
    def _current_image(self) -> Optional[GalleryImage]:
        images = self._gallery.images if self._gallery else []
        return images[self._index] if self._index < len(images) else None

    def paintEvent(self, event):
        """Paint the current image, and the outgoing one while a transition runs"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), _HIT_TEST_FILL)
        if not self._layer:
            return
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

        self._hide_preview()
        active = ImageHoverView._active_viewer
        if active is not None and active is not self:
            active._hide_preview()
        ImageHoverView._active_viewer = self
        self.update_theme((self._config.get("ui", "theme") if self._config else None) != "light")
        self._gallery = gallery or ImageGallery.single(image_url)
        if self._gallery.messages_replaced:
            self._gallery.messages_replaced.connect(self._on_messages_replaced)
        if self._gallery.day_navigation:
            self._gallery.day_navigation.loaded.connect(self._on_day_loaded)

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
        self._zoom_buttons.apply_theme(is_dark)
        for zone in self._edge_zones:
            zone.apply_theme(is_dark)
        if self._gallery:
            self._update_overlays(self._current_image)

    def _on_messages_replaced(self):
        """Rebuild the gallery after its messages were replaced, keeping the current image if it is still there."""
        current = self._current_image
        current_url = current.url if current else None
        self._gallery = self._gallery.reloaded(current_url)
        self._loader.retain_only({image.url for image in self._gallery.images})
        self._gallery_bar.clear_thumbnails()
        self._position_timer.stop()
        if not self._gallery.images:
            self._update_overlays(None)
            return
        kept_index = next((index for index, image in enumerate(self._gallery.images) if image.url == current_url), None)
        if kept_index is None:
            self._show_image(0, 1)
            return
        self._index = kept_index
        self._update_overlays(self._current_image)
        self._warm_up()

    def _on_day_loaded(self):
        """A chatlog day finished loading: with no image in it, say so instead of keeping a stale image or a spinner."""
        if self._day_state() is None or first_image(self._gallery.get_messages()):
            return
        self._gallery = self._gallery.without_images()
        self._loader.retain_only(())
        self._index = 0
        self._gallery_bar.clear_thumbnails()
        self._update_overlays(None)
        self._show_notice(NOTICE_WARNING, tr("No images for this day", "В этот день нет изображений"))

    def _show_image(self, index: int, direction: int):
        """Make the image at index current: show it as soon as it is loaded, and warm up its neighbors."""
        self._index = index
        self._direction = direction
        self._close_reply()
        self._notice.hide()
        image = self._gallery.images[index]
        self._update_overlays(image)

        data = self._loader.request(image.url)
        if data is not None:
            self._display(image.url, data)
        elif self._loader.has_failed(image.url):
            self._on_current_failed()
        else:
            self._loader.cancel_except((image.url,))
            if direction:
                self._start_spinner_at_center()
        self._warm_up()

    def _warm_up(self):
        """Fetch neighbors and thumbnails only once the current image is settled, so they never slow it down."""
        current = self._current_image
        if current and self._loader.is_settled(current.url):
            self._prefetch_neighbors()
            self._request_thumbnails()

    def _prefetch_neighbors(self):
        images = self._gallery.images
        if len(images) < 2:
            return
        for step in (1, -1):
            self._loader.request(images[(self._index + step) % len(images)].url, _NEIGHBOR_PRIORITY, background=True)

    def _request_thumbnails(self):
        for index in self._gallery_bar.visible_indices():
            if self._gallery_bar.has_thumbnail(index):
                continue
            url = self._gallery.images[index].url
            data = self._loader.request(url, _THUMBNAIL_PRIORITY, background=True)
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
        current = self._current_image
        if current is None or url != current.url:
            return
        if is_error:
            self._on_current_failed()
        else:
            self._display(url, data)
        self._warm_up()

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
        self._show_notice(NOTICE_ERROR, tr(
            "Image unavailable: it was removed from the host or the link is broken",
            "Изображение недоступно: удалено с хостинга или ссылка не работает",
        ))
        self._restart_slideshow_timer()

    def _show_notice(self, kind: NoticeKind, text: str):
        """Replace the image with a notice so the user sees why nothing is shown."""
        self._stop_spinner()
        self._release_layers()
        self._notice.show_notice(kind, text)
        self._notice.move(
            (self.width() - self._notice.width()) // 2,
            (self.height() - self._reserved_bottom() - self._notice.height()) // 2,
        )
        self._show_widget()

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
        self._update_zoom_buttons()
        self._restart_slideshow_timer()

    def _release_layers(self):
        self._release_outgoing()
        if self._layer:
            self._layer.release()
            self._layer = None
            self.update()
        self._update_zoom_buttons()

    def _release_outgoing(self):
        self._transition.stop()
        if self._outgoing:
            self._outgoing.release()
            self._outgoing = None
            self.update()

    def _reserved_bottom(self) -> int:
        """Height kept free at the bottom for the gallery bar."""
        return self._gallery_bar.height() + 2 * _OVERLAY_MARGIN if self._gallery_bar.isVisibleTo(self) else 0

    def _update_overlays(self, image: Optional[GalleryImage]):
        count = len(self._gallery.images)
        has_message = image is not None and image.source is not None
        has_source = has_message and self._gallery.on_source is not None
        can_reply = has_message and self._gallery.on_reply is not None
        day_state = self._day_state()
        self._gallery_bar.setVisible(count > 1 or day_state is not None or has_source or can_reply)
        self._gallery_bar.set_message_actions(has_source, can_reply)
        self._gallery_bar.set_position(self._index, count, count > 0 and show_thumbnails(self._config), day_state)
        self._gallery_bar.move(
            (self.width() - self._gallery_bar.width()) // 2,
            self.height() - self._gallery_bar.height() - _OVERLAY_MARGIN,
        )
        self._close_button.refresh_tooltip()
        self._close_button.move(self.width() - self._close_button.width() - _OVERLAY_MARGIN, _OVERLAY_MARGIN)
        self._close_button.show()
        self._zoom_buttons.refresh_tooltips()
        self._zoom_buttons.move(self._close_button.x() - _OVERLAY_SPACING - self._zoom_buttons.width(), _OVERLAY_MARGIN)
        self._zoom_buttons.show()
        edge_zone_top = self._close_button.geometry().bottom() + _OVERLAY_SPACING
        for zone in self._edge_zones:
            zone.place(self.size(), edge_zone_top)
        self._update_edge_zones()
        self._source_badge.setVisible(has_source)
        if has_source:
            self._source_badge.show_image(image, self._is_dark)
            self._source_badge.move(_OVERLAY_MARGIN, _OVERLAY_MARGIN)
        has_position = count > 1 or day_state is not None
        self._position_badge.setVisible(has_position)
        if has_position:
            self._position_badge.show_position(self._index, count, day_state.day if day_state else None, self._is_dark)
            left = self._source_badge.geometry().right() + _OVERLAY_SPACING if has_source else _OVERLAY_MARGIN
            self._position_badge.move(left, _OVERLAY_MARGIN)
        if self._reply_panel.isVisible():
            self._place_reply()

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
        self._loader.cancel_except(())  # the old day's downloads would only compete with the chatlog being loaded
        self._stop_spinner()
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
        self._leave_to_message(lambda gallery: gallery.on_source)

    def _on_reply_requested(self):
        """Reply to the message of the current image: in a field here, or in the chat after closing the viewer."""
        image = self._current_image
        inline = self._gallery.inline_reply if self._gallery else None
        if inline and image and image.source is not None and reply_mode(self._config) == REPLY_MODE_INLINE:
            self._open_reply(inline, image.source)
        else:
            self._leave_to_message(lambda gallery: gallery.on_reply)

    def _open_reply(self, inline: InlineReply, message):
        if self._reply_panel.isVisible():
            self._reply_panel.focus_field()
            return
        self._inline_reply = inline
        self._set_slideshow_playing(False)
        self._reply_panel.open(inline.prefill(message), inline.emoticon_selector() is not None, self._is_dark)
        self._place_reply()

    def _place_reply(self):
        """Put the reply panel above the gallery bar, and the emoticon selector above the panel."""
        panel = self._reply_panel
        panel.setFixedWidth(min(_REPLY_PANEL_WIDTH, self.width() - 2 * _OVERLAY_MARGIN))
        panel.adjustSize()
        bottom = self._gallery_bar.y() if self._gallery_bar.isVisibleTo(self) else self.height() - _OVERLAY_MARGIN
        panel.move((self.width() - panel.width()) // 2, bottom - _OVERLAY_SPACING - panel.height())
        panel.raise_()
        if self._emoticon_selector is not None and self._emoticon_selector.isVisible():
            self._place_emoticons()

    def _place_emoticons(self):
        selector = self._emoticon_selector
        button = self._reply_panel.input_row.emoticon_button
        right = button.mapTo(self, button.rect().topRight()).x()
        bottom = self._reply_panel.y() - _OVERLAY_SPACING
        height = max(_EMOTICON_MIN_HEIGHT, min(_EMOTICON_MAX_HEIGHT, bottom - _OVERLAY_MARGIN))
        selector.setFixedHeight(height)
        left = max(_OVERLAY_MARGIN, min(right - selector.width(), self.width() - selector.width() - _OVERLAY_MARGIN))
        selector.move(left, max(_OVERLAY_MARGIN, bottom - height))
        selector.raise_()

    def _toggle_emoticons(self):
        """Show the shared emoticon selector over the viewer, or hand it back."""
        if self._emoticon_selector is not None and self._emoticon_selector.isVisible():
            self._release_emoticons()
            return
        selector = self._inline_reply.emoticon_selector() if self._inline_reply else None
        if selector is None:
            return
        selector.attach(self, self._reply_panel.input_row.insert_emoticon)
        self._emoticon_selector = selector
        selector.setVisible(True)
        self._place_emoticons()
        QTimer.singleShot(_SELECTOR_SETTLE_MS, selector.resume_animations)
        self._reply_panel.focus_field()

    def _release_emoticons(self):
        """Hide the borrowed selector and unparent it so the chat can reclaim it."""
        selector, self._emoticon_selector = self._emoticon_selector, None
        if selector is not None and selector.parent() is self:
            selector.setVisible(False)
            selector.setParent(None)

    def _close_reply(self):
        """Hide the reply field, hand the emoticon selector back and return the keys to the viewer."""
        self._release_emoticons()
        self._inline_reply = None
        if self._reply_panel.isVisible():
            self._reply_panel.hide()
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_reply_submitted(self, text: str):
        inline = self._inline_reply
        self._close_reply()
        inline.send(text)

    def _leave_to_message(self, pick_action: Callable[[ImageGallery], Optional[Callable[[object], None]]]):
        """Close the viewer and hand the message of the current image to the gallery action, when there is one."""
        gallery, image = self._gallery, self._current_image
        action = pick_action(gallery) if gallery else None
        if action is None or image is None or image.source is None:
            return
        self._hide_preview()
        action(image.source)

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
        """Apply zoom transformation around pivot point, keeping the scale within its limits"""
        if not self._layer:
            return
        new_scale = max(_MIN_SCALE, min(new_scale, _MAX_SCALE))
        point_before = (pivot - self._layer.offset) / self._layer.scale
        self._layer.scale = new_scale
        self._layer.offset = pivot - point_before * new_scale
        self._update_zoom_buttons()
        self.update()

    def _viewport_center(self) -> QPointF:
        """Center of the area the image is fitted into, above the gallery bar."""
        return QPointF(self.width() / 2, (self.height() - self._reserved_bottom()) / 2)

    def _zoom_step(self, step: int):
        """Zoom in (+1) or out (-1) by one button step around the viewport center."""
        if self._layer:
            self._apply_zoom(self._layer.scale * _ZOOM_BUTTON_FACTOR ** step, self._viewport_center())

    def _update_zoom_buttons(self):
        layer = self._layer
        can_zoom_out = layer is not None and layer.scale > _MIN_SCALE
        can_zoom_in = layer is not None and layer.scale < _MAX_SCALE
        self._zoom_buttons.set_limits(can_zoom_out, can_zoom_in)
        if not (can_zoom_out and can_zoom_in):
            self._zoom_hold.release()  # a button disabled under the cursor never reports its release

    def _update_edge_zones(self):
        """Reveal an edge zone while the cursor is in its hot area; keep both hidden with nothing to turn to."""
        position = self.mapFromGlobal(QCursor.pos())
        can_navigate = self._gallery is not None and len(self._gallery.images) > 1
        for zone in self._edge_zones:
            zone.set_active(can_navigate and zone.is_hot(position))

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
            self._hide_preview()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging or scaling"""
        self._update_edge_zones()
        if not self._drag_mode or not self._layer:
            return

        delta = event.position() - self._last_mouse_pos

        if self._drag_mode == _DRAG_PAN:
            self._layer.offset += delta
            self.update()
        else:
            self._apply_zoom(self._layer.scale * (1.0 - delta.y() * _SCALE_DRAG_SENSITIVITY), self._viewport_center())

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
        is_day_step = bool(step) and bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier) and self._day_state() is not None

        if key == Qt.Key.Key_F1:
            self._help_panel.show_for_context('image')
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_Escape) or Qt.Key.Key_Q in (key, native_key):
            self._hide_preview()
            event.accept()
        elif is_day_step:
            if not event.isAutoRepeat():
                self._day_hold.press(step)
            event.accept()
        elif step:
            self._navigate(step)
            event.accept()
        elif Qt.Key.Key_P in (key, native_key):
            if not event.isAutoRepeat():
                self._toggle_slideshow()
            event.accept()
        elif Qt.Key.Key_R in (key, native_key):
            self._on_reply_requested()
            event.accept()
        elif Qt.Key.Key_G in (key, native_key):
            self._on_source_clicked()
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat() and (event.key() in _NAVIGATION_KEYS or event.nativeVirtualKey() in _NAVIGATION_KEYS):
            self._day_hold.release()
        super().keyReleaseEvent(event)

    def leaveEvent(self, event):
        self._update_edge_zones()
        super().leaveEvent(event)

    def focusOutEvent(self, event):
        self._day_hold.release()  # the key release would go to another window
        self._zoom_hold.release()
        super().focusOutEvent(event)

    def _hide_preview(self):
        """Hide preview and reset state"""
        self._day_hold.release()
        self._zoom_hold.release()
        self._position_timer.stop()
        self._slideshow_timer.stop()
        self._stop_spinner()
        self._close_reply()
        self._loader.reset()
        self._release_layers()
        self._notice.hide()
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
        if self._gallery and self._gallery.day_navigation:
            try:
                self._gallery.day_navigation.loaded.disconnect(self._on_day_loaded)
            except (RuntimeError, TypeError):
                pass  # the chatlog is already gone
        self._gallery = self._target_pos = None
        self._update_edge_zones()
        self._end_drag()
        self.hide()
        release_memory_soon()

    def cleanup(self):
        """Cleanup resources"""
        self._hide_preview()
        if self._help_panel:
            self._help_panel.deleteLater()
            self._help_panel = None

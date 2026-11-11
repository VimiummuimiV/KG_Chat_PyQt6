"""Controls over the image: close button, zoom buttons and zoom slider (top right),
   minimap (bottom right) and the navigation strips at the screen edges."""

import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import pyqtSignal, QEvent, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from components.button import create_icon_button, render_svg_icon, set_button_icon
from components.image_viewer.layer import ImageLayer, MAX_SCALE, MIN_SCALE
from components.image_viewer.overlay import PANEL_MARGIN, PANEL_SPACING, PANEL_STYLES, panel_stylesheet
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import tr


_EDGE_ZONE_WIDTH = 72
_EDGE_ZONE_MARGIN = 16  # gap between the visible strip and the screen edge; it still counts as the strip
_EDGE_ZONE_HOT_RATIO = 0.2  # share of the viewport width, counted from each edge
_EDGE_ZONE_ICON_SIZE = 36
_EDGE_ZONE_FADE_MS = 150
_EDGE_ZONE_ICONS = {True: "line/arrow-left-s-line.svg", False: "line/arrow-right-s-line.svg"}
_ACTUAL_SIZE_ICON = "line/aspect-ratio-line.svg"
_FIT_ICON = "line/fullscreen-line.svg"
_ZOOM_SLIDER_WIDTH = 140
_ZOOM_SLIDER_STEPS = 200  # positions across MIN_SCALE..MAX_SCALE, spaced logarithmically
_PERCENT = 100
_MINIMAP_MAX_SIZE = QSize(180, 120)
_MINIMAP_PADDING = 6
_MINIMAP_VISIBLE_AREA_LIMIT = 0.5  # shown while the viewport covers less of the image than this
_MINIMAP_VIEW_FILL_ALPHA = 40
_MINIMAP_VIEW_BORDER_WIDTH = 1.5
_WIDEST_ZOOM_TEXT = str(round(MAX_SCALE * _PERCENT))
_ZOOM_VALUE_SLACK = 2  # the advance is rounded down, which would clip the last digit
_SLIDER_STYLESHEET = """
    #zoomSlider QSlider {
        background: transparent;
    }
"""


class CloseButton(QFrame):
    """Translucent panel with the button that closes the viewer."""

    clicked = pyqtSignal()

    def __init__(self, icons_path: Path, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("closeButton")
        self._button = create_icon_button(icons_path, "line/close-large-line.svg", config=config)
        self._button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the viewer
        self._button.clicked.connect(self.clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        layout.addWidget(self._button)
        self.adjustSize()
        self.refresh_tooltip()

    def apply_theme(self, is_dark: bool):
        """Restyle the panel for the theme."""
        self.setStyleSheet(panel_stylesheet("closeButton", is_dark))

    def refresh_tooltip(self):
        """Re-translate the tooltip for the current interface language."""
        self._button.setToolTip(tr("Close (Esc / Space / Q / RMB)", "Закрыть (Esc / Space / Q / ПКМ)"))


class ZoomButtons(QFrame):
    """Translucent panel with zoom out, zoom in and actual-size / fit buttons."""

    zoom_pressed = pyqtSignal(int)  # -1 / +1; the viewer repeats it while the button stays down
    zoom_released = pyqtSignal()

    def __init__(self, icons_path: Path, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("zoomButtons")
        self._zoom_out_button = create_icon_button(icons_path, "line/zoom-out-line.svg", config=config)
        self._zoom_in_button = create_icon_button(icons_path, "line/zoom-in-line.svg", config=config)
        self.actual_size_button = create_icon_button(icons_path, _ACTUAL_SIZE_ICON, config=config)
        self._is_actual_size = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        layout.setSpacing(PANEL_SPACING)
        for button, step in ((self._zoom_out_button, -1), (self._zoom_in_button, 1)):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the viewer
            button.pressed.connect(lambda step=step: self.zoom_pressed.emit(step))
            button.released.connect(self.zoom_released)
            layout.addWidget(button)
        self.actual_size_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.actual_size_button)
        self.adjustSize()
        self.refresh_tooltips()

    def apply_theme(self, is_dark: bool):
        """Restyle the panel for the theme."""
        self.setStyleSheet(panel_stylesheet("zoomButtons", is_dark))

    def set_layer(self, layer: Optional[ImageLayer]):
        """Enable each button only while it has something to do; the last one flips between 100% and fit."""
        has_layer = layer is not None
        self._zoom_out_button.setEnabled(has_layer and layer.scale > MIN_SCALE)
        self._zoom_in_button.setEnabled(has_layer and layer.scale < MAX_SCALE)
        self.actual_size_button.setEnabled(has_layer)
        is_actual_size = has_layer and layer.is_actual_size
        if is_actual_size != self._is_actual_size:
            self._is_actual_size = is_actual_size
            set_button_icon(self.actual_size_button, _FIT_ICON if is_actual_size else _ACTUAL_SIZE_ICON)
            self._refresh_actual_size_tooltip()

    def refresh_tooltips(self):
        """Re-translate the tooltips for the current interface language."""
        self._zoom_out_button.setToolTip(tr("Zoom out (wheel down / -)", "Уменьшить (колесо вниз / -)"))
        self._zoom_in_button.setToolTip(tr("Zoom in (wheel up / +)", "Увеличить (колесо вверх / +)"))
        self._refresh_actual_size_tooltip()

    def _refresh_actual_size_tooltip(self):
        self.actual_size_button.setToolTip(
            tr("Fit to screen (0)", "По размеру экрана (0)") if self._is_actual_size
            else tr("Zoom to 100% (1)", "Масштаб 100% (1)")
        )


def _position_from_scale(scale: float) -> int:
    return round(math.log(scale / MIN_SCALE) / math.log(MAX_SCALE / MIN_SCALE) * _ZOOM_SLIDER_STEPS)


def _scale_from_position(position: int) -> float:
    return MIN_SCALE * (MAX_SCALE / MIN_SCALE) ** (position / _ZOOM_SLIDER_STEPS)


class ZoomSlider(QFrame):
    """Translucent panel with a slider over the whole zoom range and the current zoom in percent (without the sign)."""

    scale_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("zoomSlider")
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _ZOOM_SLIDER_STEPS)
        self._slider.setFixedWidth(_ZOOM_SLIDER_WIDTH)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the viewer
        self._slider.valueChanged.connect(lambda position: self.scale_requested.emit(_scale_from_position(position)))
        self._value_label = QLabel()
        self._value_label.setFont(get_font(FontType.UI))
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.installEventFilter(self)
        self._reserve_value_width()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        layout.setSpacing(PANEL_SPACING)
        layout.addWidget(self._slider)
        layout.addWidget(self._value_label)
        self.set_layer(None)
        self.adjustSize()
        self.refresh_tooltip()

    def apply_theme(self, is_dark: bool):
        """Restyle the panel for the theme."""
        self.setStyleSheet(panel_stylesheet("zoomSlider", is_dark) + _SLIDER_STYLESHEET)

    def _reserve_value_width(self):
        self._value_label.setFixedWidth(
            self._value_label.fontMetrics().horizontalAdvance(_WIDEST_ZOOM_TEXT) + _ZOOM_VALUE_SLACK
        )

    def eventFilter(self, watched, event):
        if watched is self._value_label and event.type() == QEvent.Type.FontChange:  # the width follows the real font
            self._reserve_value_width()
            self.adjustSize()
        return super().eventFilter(watched, event)

    def set_layer(self, layer: Optional[ImageLayer]):
        """Show the zoom of the layer; the slider is disabled while there is no image."""
        self._slider.setEnabled(layer is not None)
        if layer is None:
            self._value_label.clear()
            return
        self._value_label.setText(str(round(layer.scale * _PERCENT)))
        if self._slider.isSliderDown():  # the drag itself is the source of the value
            return
        self._slider.blockSignals(True)
        self._slider.setValue(_position_from_scale(layer.scale))
        self._slider.blockSignals(False)

    def refresh_tooltip(self):
        """Re-translate the tooltip for the current interface language."""
        self.setToolTip(tr("Zoom (%)", "Масштаб (%)"))


class Minimap(QFrame):
    """Corner overview of a zoomed-in image: shows which part is in view; a click or drag moves the view."""

    position_requested = pyqtSignal(QPointF)  # a point of the image as fractions (0..1) of its size

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("minimap")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._is_dark = True
        self._layer: Optional[ImageLayer] = None
        self._preview = QPixmap()
        self._view = QRectF()  # the part in view, as fractions of the image

    def apply_theme(self, is_dark: bool):
        """Restyle the panel for the theme."""
        self._is_dark = is_dark
        self.setStyleSheet(panel_stylesheet("minimap", is_dark))

    def update_view(self, layer: Optional[ImageLayer], viewport: QSize):
        """Show the overview only while the viewport covers a small part of the layer's image."""
        if layer is not self._layer:
            self._layer = layer
            self._preview = QPixmap()
        view = layer.visible_fraction(viewport) if layer else QRectF()
        is_zoomed_in = layer is not None and view.width() * view.height() < _MINIMAP_VISIBLE_AREA_LIMIT
        self.setVisible(is_zoomed_in)
        if not is_zoomed_in:
            return
        if self._preview.isNull():
            self._preview = layer.preview(_MINIMAP_MAX_SIZE)
            self.setFixedSize(self._preview.size() + QSize(2 * _MINIMAP_PADDING, 2 * _MINIMAP_PADDING))
        self._view = view
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.drawPixmap(_MINIMAP_PADDING, _MINIMAP_PADDING, self._preview)
        if self._view.isEmpty():
            return
        width, height = self._preview.width(), self._preview.height()
        view_rect = QRectF(
            _MINIMAP_PADDING + self._view.x() * width, _MINIMAP_PADDING + self._view.y() * height,
            self._view.width() * width, self._view.height() * height,
        )
        color = QColor(PANEL_STYLES[self._is_dark]["text"])
        painter.setPen(QPen(color, _MINIMAP_VIEW_BORDER_WIDTH))
        color.setAlpha(_MINIMAP_VIEW_FILL_ALPHA)
        painter.setBrush(color)
        painter.drawRect(view_rect)

    def _request_position(self, position: QPointF):
        fraction_x = (position.x() - _MINIMAP_PADDING) / self._preview.width()
        fraction_y = (position.y() - _MINIMAP_PADDING) / self._preview.height()
        self.position_requested.emit(QPointF(max(0.0, min(1.0, fraction_x)), max(0.0, min(1.0, fraction_y))))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._request_position(event.position())
        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._request_position(event.position())
        event.accept()


class EdgeZone(QWidget):
    """Tall strip near a screen edge: fades in when the cursor comes near it, a click turns the image.

    The widget reaches to the screen edge; only its inner part is drawn, so the gap still clicks.
    """

    clicked = pyqtSignal()
    cursor_left = pyqtSignal()

    def __init__(self, icons_path: Path, is_left_edge: bool, parent=None):
        super().__init__(parent)
        self._icon_path = icons_path / _EDGE_ZONE_ICONS[is_left_edge]
        self._is_left_edge = is_left_edge
        self._is_active = False
        self._hot_rect = QRect()
        self._icon_label = QLabel()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._strip = QFrame()
        self._strip.setObjectName("edgeZone")
        strip_layout = QVBoxLayout(self._strip)
        strip_layout.setContentsMargins(0, 0, 0, 0)
        strip_layout.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(_EDGE_ZONE_MARGIN if is_left_edge else 0, 0, 0 if is_left_edge else _EDGE_ZONE_MARGIN, 0)
        layout.addWidget(self._strip)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(_EDGE_ZONE_FADE_MS)
        self._fade.finished.connect(self._hide_when_inactive)
        self.hide()

    def apply_theme(self, is_dark: bool):
        """Restyle the strip and recolor its arrow for the theme."""
        self._strip.setStyleSheet(panel_stylesheet("edgeZone", is_dark))
        icon = render_svg_icon(self._icon_path, _EDGE_ZONE_ICON_SIZE, PANEL_STYLES[is_dark]["text"])
        self._icon_label.setPixmap(icon.pixmap(_EDGE_ZONE_ICON_SIZE, _EDGE_ZONE_ICON_SIZE))

    def place(self, viewport: QSize, top_margin: int, bottom_margin: int):
        """Put the strip flush against its edge of the viewport; the hot area reaches from the edge inwards."""
        height = viewport.height() - top_margin - bottom_margin
        width = _EDGE_ZONE_MARGIN + _EDGE_ZONE_WIDTH
        self.setGeometry(0 if self._is_left_edge else viewport.width() - width, top_margin, width, height)
        hot_width = int(viewport.width() * _EDGE_ZONE_HOT_RATIO)
        hot_left = 0 if self._is_left_edge else viewport.width() - hot_width
        self._hot_rect = QRect(hot_left, top_margin, hot_width, height)

    def is_hot(self, position: QPoint) -> bool:
        """Whether the position (in viewport coordinates) is close enough to reveal the strip."""
        return self._hot_rect.contains(position)

    def set_active(self, is_active: bool):
        """Fade the strip in or out."""
        if is_active == self._is_active:
            return
        self._is_active = is_active
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(1.0 if is_active else 0.0)
        if is_active:
            self.show()
        self._fade.start()

    def _hide_when_inactive(self):
        if not self._is_active:
            self.hide()

    def leaveEvent(self, event):
        self.cursor_left.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()

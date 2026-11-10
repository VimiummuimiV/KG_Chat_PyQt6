"""Controls over the image: close and zoom buttons (top right) and the navigation strips at the screen edges."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal, QPoint, QPropertyAnimation, QRect, QSize, Qt
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout

from components.button import create_icon_button, render_svg_icon
from components.image_viewer.overlay import PANEL_MARGIN, PANEL_SPACING, PANEL_STYLES, panel_stylesheet
from helpers.translate import tr


_EDGE_ZONE_WIDTH = 72
_EDGE_ZONE_MARGIN = 16
_EDGE_ZONE_HOT_RATIO = 0.2  # share of the viewport width, counted from each edge
_EDGE_ZONE_ICON_SIZE = 36
_EDGE_ZONE_FADE_MS = 150
_EDGE_ZONE_ICONS = {True: "line/arrow-left-s-line.svg", False: "line/arrow-right-s-line.svg"}


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
    """Translucent panel with the zoom out and zoom in buttons."""

    zoom_pressed = pyqtSignal(int)  # -1 / +1; the viewer repeats it while the button stays down
    zoom_released = pyqtSignal()

    def __init__(self, icons_path: Path, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("zoomButtons")
        self._zoom_out_button = create_icon_button(icons_path, "line/zoom-out-line.svg", config=config)
        self._zoom_in_button = create_icon_button(icons_path, "line/zoom-in-line.svg", config=config)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        layout.setSpacing(PANEL_SPACING)
        for button, step in ((self._zoom_out_button, -1), (self._zoom_in_button, 1)):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the viewer
            button.pressed.connect(lambda step=step: self.zoom_pressed.emit(step))
            button.released.connect(self.zoom_released)
            layout.addWidget(button)
        self.adjustSize()
        self.refresh_tooltips()

    def apply_theme(self, is_dark: bool):
        """Restyle the panel for the theme."""
        self.setStyleSheet(panel_stylesheet("zoomButtons", is_dark))

    def set_limits(self, can_zoom_out: bool, can_zoom_in: bool):
        """Enable each button only while its direction still has room."""
        self._zoom_out_button.setEnabled(can_zoom_out)
        self._zoom_in_button.setEnabled(can_zoom_in)

    def refresh_tooltips(self):
        """Re-translate the tooltips for the current interface language."""
        self._zoom_out_button.setToolTip(tr("Zoom out (wheel down)", "Уменьшить (колесо вниз)"))
        self._zoom_in_button.setToolTip(tr("Zoom in (wheel up)", "Увеличить (колесо вверх)"))


class EdgeZone(QFrame):
    """Tall strip at a screen edge: fades in when the cursor comes near it, a click turns the image."""

    clicked = pyqtSignal()
    cursor_left = pyqtSignal()

    def __init__(self, icons_path: Path, is_left_edge: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("edgeZone")
        self._icon_path = icons_path / _EDGE_ZONE_ICONS[is_left_edge]
        self._is_left_edge = is_left_edge
        self._is_active = False
        self._hot_rect = QRect()
        self._icon_label = QLabel()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignCenter)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(_EDGE_ZONE_FADE_MS)
        self._fade.finished.connect(self._hide_when_inactive)
        self.hide()

    def apply_theme(self, is_dark: bool):
        """Restyle the strip and recolor its arrow for the theme."""
        self.setStyleSheet(panel_stylesheet("edgeZone", is_dark))
        icon = render_svg_icon(self._icon_path, _EDGE_ZONE_ICON_SIZE, PANEL_STYLES[is_dark]["text"])
        self._icon_label.setPixmap(icon.pixmap(_EDGE_ZONE_ICON_SIZE, _EDGE_ZONE_ICON_SIZE))

    def place(self, viewport: QSize, vertical_margin: int):
        """Put the strip at its edge of the viewport; the hot area reaches from the screen edge inwards."""
        height = viewport.height() - 2 * vertical_margin
        left = _EDGE_ZONE_MARGIN if self._is_left_edge else viewport.width() - _EDGE_ZONE_MARGIN - _EDGE_ZONE_WIDTH
        self.setGeometry(left, vertical_margin, _EDGE_ZONE_WIDTH, height)
        hot_width = int(viewport.width() * _EDGE_ZONE_HOT_RATIO)
        hot_left = 0 if self._is_left_edge else viewport.width() - hot_width
        self._hot_rect = QRect(hot_left, vertical_margin, hot_width, height)

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

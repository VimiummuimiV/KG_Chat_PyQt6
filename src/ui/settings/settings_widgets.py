"""Small widgets and preview helpers shared by the settings sections."""

from PyQt6.QtCore import pyqtSignal, QObject, Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSlider, QWidget


FONT_PREVIEW_BORDER = 1
FONT_PREVIEW_PADDING = 6
SLIDER_DEBOUNCE_MS = 150
SLIDER_GROOVE_HEIGHT = 6
SLIDER_HANDLE_SIZE = 14


def preview_box_colors(theme: str) -> tuple[str, str, str]:
    """(bg, fg, border) for a themed preview box; shared by font and flash previews."""
    if theme == "dark":
        return "#1E1E1E", "#D4D4D4", "#3C3C3C"
    return "#F5F5F5", "#333333", "#CCCCCC"


def preview_box_stylesheet(widget_selector: str, theme: str) -> str:
    bg, fg, border = preview_box_colors(theme)
    return (
        f"{widget_selector} {{ background-color: {bg}; color: {fg}; "
        f"border: {FONT_PREVIEW_BORDER}px solid {border}; border-radius: 4px; "
        f"padding: {FONT_PREVIEW_PADDING}px; }}"
    )


def gradient_slider_stylesheet(color_stops: list[str]) -> str:
    """Horizontal slider whose groove is an even gradient through the given colors."""
    last_index = len(color_stops) - 1
    stops = ", ".join(f"stop:{index / last_index:.3f} {color}" for index, color in enumerate(color_stops))
    handle_margin = (SLIDER_HANDLE_SIZE - SLIDER_GROOVE_HEIGHT) // 2
    return (
        f"QSlider::groove:horizontal {{ height: {SLIDER_GROOVE_HEIGHT}px; "
        f"border-radius: {SLIDER_GROOVE_HEIGHT // 2}px; "
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {stops}); }}"
        f"QSlider::handle:horizontal {{ width: {SLIDER_HANDLE_SIZE}px; margin: -{handle_margin}px 0; "
        f"border-radius: {SLIDER_HANDLE_SIZE // 2}px; background: #F2F2F2; border: 1px solid #404040; }}"
    )


class SpinCommitSignal(QObject):
    """Fires once a slider/spin row's debounced value has been committed, for
    external listeners that need the settled value rather than every step."""
    committed = pyqtSignal(int)


class NoWheelSlider(QSlider):
    """QSlider that ignores mouse wheel events, letting the parent scroll area handle scrolling instead."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events, letting the parent scroll area handle scrolling instead."""

    def wheelEvent(self, event):
        event.ignore()


class ClickableLabel(QLabel):
    """QLabel that emits clicked() on left-click."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SettingsRow(QWidget):
    """Label + control line with a soft hover fill so the pair stays readable when wide."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self.setObjectName("settingsRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(spacing)
        # Soft row fill; label/slider transparent so it shows through (combo/spin keep chrome).
        self.setStyleSheet(
            "#settingsRow { background: transparent; border-radius: 6px; }"
            "#settingsRow:hover { background: rgba(128, 128, 128, 0.10); }"
            "#settingsRow QLabel, #settingsRow QSlider { background: transparent; }"
        )

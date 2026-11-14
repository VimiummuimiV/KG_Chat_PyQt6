"""Toast: a short message that slides in at the top center of a window and fades away."""

from enum import Enum
from typing import Callable

from PyQt6.QtCore import QEasingCurve, QEvent, QRect, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from components.button import render_svg_icon
from helpers.colors.color_utils import tinted_chip_colors
from helpers.data import get_resource_dir
from helpers.translate import tr


DEFAULT_DURATION_MS = 2200
_ENTER_MS = 220
_EXIT_MS = 300
_SLIDE_DISTANCE = 18
_TOP_MARGIN = 14
_DODGE_PADDING = 12  # the toast steps aside when the cursor comes this close to it
_DODGE_MS = 180
_CURSOR_POLL_MS = 50
_COPIED_TEXT_LIMIT = 40
_ICON_SIZE = 18
_RADIUS = 12
_PADDING_HORIZONTAL = 16
_PADDING_VERTICAL = 10
_SPACING = 10


class ToastKind(Enum):
    """Toast state: (icon file, accent color its tinted background and text are made from)."""

    SUCCESS = ("line/checkbox-circle-line.svg", "#3fa06a")
    ERROR = ("line/error-warning-line.svg", "#d04a4a")
    WARNING = ("line/alert-line.svg", "#d99a2b")
    INFO = ("line/information-line.svg", "#3b82c4")


class Toast(QFrame):
    """One reusable toast of a window; a new message replaces the one on screen."""

    def __init__(self, host: QWidget, is_dark_fn: Callable[[], bool]):
        super().__init__(host)
        self._host = host
        self._is_dark_fn = is_dark_fn
        self._progress = 0.0
        self._dodge = 0.0
        self._is_dodged = False
        self._curve = QEasingCurve(QEasingCurve.Type.OutCubic)

        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._icon_label = QLabel()
        self._text_label = QLabel()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PADDING_HORIZONTAL, _PADDING_VERTICAL, _PADDING_HORIZONTAL, _PADDING_VERTICAL)
        layout.setSpacing(_SPACING)
        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)

        self._animation = QVariantAnimation(self)
        self._animation.valueChanged.connect(self._apply_progress)
        self._animation.finished.connect(self._finish)

        self._dodge_animation = QVariantAnimation(self)
        self._dodge_animation.setDuration(_DODGE_MS)
        self._dodge_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._dodge_animation.valueChanged.connect(self._apply_dodge)

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(_CURSOR_POLL_MS)
        self._cursor_timer.timeout.connect(self._follow_cursor)

        host.installEventFilter(self)
        self.hide()

    def show_message(self, text: str, kind: ToastKind = ToastKind.INFO, duration_ms: int = DEFAULT_DURATION_MS) -> None:
        """Show the text in the colors of the kind and keep it fully visible for duration_ms."""
        icon_name, base_color = kind.value
        background, foreground, border = tinted_chip_colors(base_color, self._is_dark_fn())
        self.setStyleSheet(
            f"#toast {{ background: {background}; border: 1px solid {border}; border-radius: {_RADIUS}px; }}"
            f"#toast QLabel {{ background: transparent; color: {foreground}; }}"
        )
        icon = render_svg_icon(get_resource_dir("icons") / icon_name, _ICON_SIZE, color=foreground)
        self._icon_label.setPixmap(icon.pixmap(_ICON_SIZE, _ICON_SIZE))
        self._text_label.setText(text)
        self.adjustSize()

        total_ms = _ENTER_MS + duration_ms + _EXIT_MS
        self._animation.stop()
        self._dodge_animation.stop()
        self._dodge = 0.0
        self._is_dodged = False
        self._animation.setDuration(total_ms)
        self._animation.setKeyValues([
            (0.0, 0.0),
            (_ENTER_MS / total_ms, 1.0),
            (1.0 - _EXIT_MS / total_ms, 1.0),
            (1.0, 0.0),
        ])
        self._apply_progress(0.0)
        self.show()
        self.raise_()
        self._animation.start()
        self._cursor_timer.start()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._host and event.type() == QEvent.Type.Resize and self.isVisible():
            self._place()
        return super().eventFilter(watched, event)

    def _finish(self) -> None:
        self._cursor_timer.stop()
        self.hide()

    def _follow_cursor(self) -> None:
        """Step aside (down) while the cursor is near the toast, so the controls under it stay visible."""
        home = QRect((self._host.width() - self.width()) // 2, _TOP_MARGIN, self.width(), self.height())
        is_near = home.adjusted(-_DODGE_PADDING, -_DODGE_PADDING, _DODGE_PADDING, _DODGE_PADDING).contains(
            self._host.mapFromGlobal(QCursor.pos())
        )
        if is_near == self._is_dodged:
            return
        self._is_dodged = is_near
        self._dodge_animation.stop()
        self._dodge_animation.setStartValue(self._dodge)
        self._dodge_animation.setEndValue(1.0 if is_near else 0.0)
        self._dodge_animation.start()

    def _apply_dodge(self, dodge: float) -> None:
        self._dodge = dodge
        self._place()

    def _apply_progress(self, progress: float) -> None:
        self._progress = progress
        self._opacity_effect.setOpacity(progress)
        self._place()

    def _place(self) -> None:
        slide = round((1.0 - self._curve.valueForProgress(self._progress)) * _SLIDE_DISTANCE)
        dodge_distance = round(self._dodge * (self.height() + _TOP_MARGIN))
        self.move((self._host.width() - self.width()) // 2, _TOP_MARGIN + dodge_distance - slide)


def show_toast(widget: QWidget, text: str, kind: ToastKind = ToastKind.INFO, duration_ms: int = DEFAULT_DURATION_MS) -> None:
    """Show a toast on the window that holds the widget; does nothing when that window has none."""
    toast = widget.window().findChild(Toast, options=Qt.FindChildOption.FindDirectChildrenOnly)
    if toast is not None:
        toast.show_message(text, kind, duration_ms)


def copy_text_with_toast(widget: QWidget, text: str, message: str = "") -> None:
    """Put the text on the clipboard and confirm it with a toast; the message defaults to the copied text."""
    if not text:
        show_toast(widget, tr("Nothing to copy", "Нечего копировать"), ToastKind.WARNING)
        return
    QApplication.clipboard().setText(text)
    if not message:
        shown = text if len(text) <= _COPIED_TEXT_LIMIT else f"{text[:_COPIED_TEXT_LIMIT]}…"
        message = tr(f"Copied: {shown}", f"Скопировано: {shown}")
    show_toast(widget, message, ToastKind.SUCCESS)


def copy_messages_with_toast(widget: QWidget, text: str, message_count: int) -> None:
    """Copy exported messages and confirm with their count."""
    copy_text_with_toast(widget, text, tr(f"Messages copied: {message_count}", f"Скопировано сообщений: {message_count}"))

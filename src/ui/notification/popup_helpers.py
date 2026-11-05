"""Shared popup window chrome, fading and avatar helpers."""

from PyQt6.QtCore import QPropertyAnimation, QSize, Qt
from PyQt6.QtGui import QPainter, QPainterPath
from PyQt6.QtWidgets import QLabel

from components.button import create_icon_button, render_svg_icon
from helpers.load import make_rounded_pixmap
from ui.notification.notification_settings import resolve_fade_ms


def fade_opacity(widget, start: float, end: float, on_finished=None, duration_ms=None):
    """Shared windowOpacity animation for notification popups."""
    if duration_ms is None:
        cfg = getattr(widget, "config", None)
        if cfg is None:
            data = getattr(widget, "data", None)
            cfg = getattr(data, "config", None) if data is not None else None
        if cfg is None:
            manager = getattr(widget, "manager", None)
            cfg = getattr(manager, "config", None) if manager is not None else None
        duration_ms = resolve_fade_ms(cfg)
    anim = QPropertyAnimation(widget, b"windowOpacity")
    anim.setDuration(int(duration_ms))
    anim.setStartValue(start)
    anim.setEndValue(end)
    if on_finished is not None:
        anim.finished.connect(on_finished)
    anim.start()
    return anim


def hold_all_popups(manager):
    """Stop hide timers / fade-outs and restore full opacity on the whole stack."""
    for p in manager.popups:
        if getattr(p, "hide_timer", None) and p.hide_timer.isActive():
            p.hide_timer.stop()
        fade = getattr(p, "fade_out", None)
        if fade is not None and fade.state() == QPropertyAnimation.State.Running:
            fade.stop()
        p.setWindowOpacity(1.0)


def resume_all_hide_timers(manager):
    """Restart auto-hide on every popup when none are hovered."""
    if any(getattr(p, "is_hovered", False) for p in manager.popups):
        return
    for p in manager.popups:
        if getattr(p, "cursor_moved", False) and not getattr(p, "reply_field_visible", False):
            start = getattr(p, "start_hide_timer", None)
            if start:
                start()


def setup_popup_window(widget):
    """Frameless, always-on-top, click-through-to-show popup chrome shared by all toasts."""
    widget.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.Tool |
        Qt.WindowType.WindowStaysOnTopHint
    )
    widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    widget.setMouseTracking(True)


def paint_rounded_background(widget, radius: int = 10):
    """Shared rounded-rect background painter for popup widgets."""
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(widget.rect().toRectF(), radius, radius)
    painter.fillPath(path, widget.palette().window())
    painter.setPen(widget.palette().mid().color())
    painter.drawPath(path)


def safe_call(fn, *args, err_msg: str = "Callback error"):
    """Invoke an optional callback, swallowing and logging any exception."""
    if fn is None:
        return
    try:
        fn(*args)
    except Exception as e:
        print(f"❌ {err_msg}: {e}")


def _svg_avatar_pixmap(icons_path, size: int, color=None, icon_name: str = "user.svg"):
    """Fallback icon pixmap rendered at the given size."""
    icon = render_svg_icon(icons_path / icon_name, size, color) if color is not None \
        else render_svg_icon(icons_path / icon_name, size)
    return icon.pixmap(QSize(size, size))


def make_avatar_label(size: int = 36) -> QLabel:
    """Styled, fixed-size avatar placeholder shared by all popup layouts."""
    label = QLabel()
    label.setFixedSize(size, size)
    label.setStyleSheet("background: transparent; border: none; padding: 0; margin: 0;")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def make_avatar_pixmap(icons_path, raw_pixmap, size: int = 36, svg_size: int = 24, color=None, icon_name: str = "user.svg"):
    """Rounded real avatar if one is available, else the SVG fallback icon."""
    if raw_pixmap is not None and not raw_pixmap.isNull():
        return make_rounded_pixmap(raw_pixmap, size, 8)
    return _svg_avatar_pixmap(icons_path, svg_size, color, icon_name)


def icon_btn(icons_path, icon_name: str, tooltip: str, config, size_type: str = "small"):
    """Shortcut for the repeated create_icon_button(icons_path, ..., config=config) calls."""
    return create_icon_button(icons_path, icon_name, tooltip, size_type=size_type, config=config)

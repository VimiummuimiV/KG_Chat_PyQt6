"""Shared popup window chrome and fading helpers."""

from PyQt6.QtCore import QPropertyAnimation, Qt
from PyQt6.QtGui import QPainter, QPainterPath

from components.button import create_icon_button
from ui.notification.notification_settings import resolve_fade_ms


def fade_opacity(widget, start: float, end: float, on_finished=None, duration_ms=None):
    """Shared windowOpacity animation for notification popups."""
    if duration_ms is None:
        config = getattr(widget, "config", None)
        if config is None:
            data = getattr(widget, "data", None)
            config = getattr(data, "config", None) if data is not None else None
        if config is None:
            manager = getattr(widget, "manager", None)
            config = getattr(manager, "config", None) if manager is not None else None
        duration_ms = resolve_fade_ms(config)
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


def icon_btn(icons_path, icon_name: str, tooltip: str, config, size_type: str = "small"):
    """Shortcut for the repeated create_icon_button(icons_path, ..., config=config) calls."""
    return create_icon_button(icons_path, icon_name, tooltip, size_type=size_type, config=config)

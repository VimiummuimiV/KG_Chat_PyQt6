"""Auto-hide behavior shared by popup widgets."""

from PyQt6.QtCore import QPropertyAnimation, QTimer

from helpers.system.input_activity import activity_detected
from ui.notification.popup_helpers import (
    fade_opacity,
    hold_all_popups,
    paint_rounded_background,
    resume_all_hide_timers,
)


class AutoHidePopupMixin:
    """Shared hover/cursor-tracking/fade/hide-timer behavior for popup widgets.
    Host class must set: manager, config, duration, is_hovered, cursor_moved,
    reply_field_visible, initial_cursor_pos, hide_timer, cursor_check_timer."""

    def self_hides_after_duration(self) -> bool:
        """Override to ignore hide_on and close purely after duration."""
        return False

    def _hide_on_mode(self) -> str:
        """notification.hide_on: manual | mouse | keyboard | mouse_keyboard (default)."""
        if self.config:
            mode = self.config.get("notification", "hide_on")
            if mode in ("manual", "mouse", "keyboard", "mouse_keyboard"):
                return mode
        return "mouse_keyboard"

    def start_cursor_monitoring(self):
        """Monitor activity (per hide_on setting) to trigger auto-hide."""
        if self.self_hides_after_duration():
            self.cursor_moved = True
            self.start_hide_timer()
            return
        if self._hide_on_mode() == "manual":
            return
        self.cursor_check_timer = QTimer(self)
        self.cursor_check_timer.timeout.connect(self._check_cursor_movement)
        self.cursor_check_timer.start(100)

    def _check_cursor_movement(self):
        if self.cursor_moved or self.reply_field_visible:
            return
        if activity_detected(self.initial_cursor_pos, self._hide_on_mode()):
            self.cursor_moved = True
            self.cursor_check_timer.stop()
            self.start_hide_timer()

    def start_hide_timer(self):
        if self.is_hovered or self.reply_field_visible:
            return
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.animate_out)
        self.hide_timer.start(self.duration)

    def animate_in(self):
        self._fade_in = fade_opacity(self, 0.0, 1.0)

    def animate_out(self, force: bool = False):
        if self.reply_field_visible or (self.is_hovered and not force):
            return
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        self.fade_out = fade_opacity(self, self.windowOpacity(), 0.0, self.on_close)

    def paintEvent(self, event):
        paint_rounded_background(self)

    def enterEvent(self, event):
        self.is_hovered = True
        hold_all_popups(self.manager)

    def leaveEvent(self, event):
        self.is_hovered = False
        resume_all_hide_timers(self.manager)

    def _cleanup_widgets(self):
        """Override for widgets owning extra resources (e.g. emoticon selector)."""
        pass

    def close_immediately(self):
        """Close notification immediately without animation. Doesn't touch
        manager.popups - callers manage the list themselves."""
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        if self.cursor_check_timer and self.cursor_check_timer.isActive():
            self.cursor_check_timer.stop()
        fade = getattr(self, "fade_out", None)
        if fade is not None and fade.state() == QPropertyAnimation.State.Running:
            fade.stop()
        self._cleanup_widgets()
        self.close()

    def on_close(self):
        self._cleanup_widgets()
        self.manager.remove_popup(self)
        self.close()
        self.deleteLater()

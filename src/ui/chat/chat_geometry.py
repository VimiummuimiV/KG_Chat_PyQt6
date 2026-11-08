"""ChatWindow: window geometry, resizing and user list visibility."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from helpers.window.resize import handle_chat_resize, recalculate_layout
from ui.dialogs.window_presets_dialog import WindowPresetsDialog


class ChatGeometryMixin:
    """ChatWindow: window geometry, resizing and user list visibility."""

    def calculate_default_geometry(self):
        """Calculate default window size and position"""
        geo = QApplication.primaryScreen().availableGeometry()
        width = geo.width() if geo.width() < 1000 else int(geo.width() * 0.7)
        height = geo.height() - 32
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y()
        return width, height, x, y

    def apply_resize(self, width: int):
        """handle_chat_resize only knows about the main chat's userlist/messages
        (it predates game-room tabs), so sync the same compact-width behaviour
        to any open game rooms here instead of teaching resize.py about tabs."""
        handle_chat_resize(self, width)
        if self.presence_log_widget:
            self.presence_log_widget.set_compact_mode(self.messages_widget.delegate.compact_mode)
        self._sync_room_compact_state(width)

    def _sync_room_compact_state(self, width: int):
        """Apply the compact-mode / userlist auto-hide threshold to every open
        game-room / custom-room tab, same 1000px breakpoint as the main chat."""
        all_rooms = self.all_room_widgets()
        if not all_rooms:
            return
        is_compact = width <= 1000
        if is_compact != getattr(self, '_rooms_were_compact', is_compact):
            for room in all_rooms:
                room.auto_hide_userlist = True
        self._rooms_were_compact = is_compact
        for room in all_rooms:
            room.set_compact_mode(is_compact)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_resize(self.width())

        self._update_geometry_on_manual_change()

    def moveEvent(self, event):
        """Track window position changes"""
        super().moveEvent(event)

        self._update_geometry_on_manual_change()

    def mouseMoveEvent(self, event):
        """Hover-reveal button panel when mouse near right edge"""
        if self.width() < 500 and hasattr(self, 'button_panel'):
            near_edge = (self.width() - event.pos().x()) <= 40
            over_panel = self.button_panel.geometry().contains(event.pos())

            if near_edge and not self.button_panel.isVisible():
                self.button_panel.setVisible(True)
                self.hover_reveal = True
            elif self.hover_reveal and not near_edge and not over_panel:
                def hide_if_away():
                    cursor_pos = self.mapFromGlobal(self.cursor().pos())
                    if self.width() < 500 and not self.button_panel.geometry().contains(cursor_pos):
                        self.button_panel.setVisible(False)

                QTimer.singleShot(300, hide_if_away)
                self.hover_reveal = False
        super().mouseMoveEvent(event)

    def reset_window_size(self):
        """Reset window to default calculated size and position"""
        # Stop any pending saves in WindowSizeManager to prevent race condition
        self.window_size_manager.save_timer.stop()

        was_reset = self.window_size_manager.reset_size()

        if not was_reset:
            return  # Already at default

        # Set flag to prevent resize/move events from saving during reset
        self.resetting_geometry = True

        # Apply default geometry
        width, height, x, y = self.calculate_default_geometry()
        self.resize(width, height)
        self.move(x, y)

        # Clear flag after events have fired
        QTimer.singleShot(100, lambda: setattr(self, 'resetting_geometry', False))

        # Update button state immediately
        self.update_reset_size_button_state()

    def show_window_presets(self):
        """Show window presets dialog"""
        dialog = WindowPresetsDialog(self.config, self, parent=self)
        dialog.exec()

    def update_reset_size_button_state(self):
        """Update reset size button state based on whether geometry is customized"""
        if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'reset_size_button'):
            has_custom = self.window_size_manager.has_saved_size()
            self.button_panel.set_button_state(self.button_panel.reset_size_button, has_custom)

    def _update_geometry_on_manual_change(self):
        """Update saved geometry when the user has manually changed window size/position."""
        if getattr(self, 'showing_window', False) or getattr(self, 'resetting_geometry', False):
            return
        cur = (self.width(), self.height(), self.x(), self.y())
        if self.window_size_manager.has_saved_size() or cur != self.calculate_default_geometry():
            self.window_size_manager.update_geometry(*cur)

    def complete_resize_recalculation(self):
        """Complete resize with aggressive recalculation"""
        current = self.stacked_widget.currentWidget()
        if current == self.messages_splitter:
            mw = self.active_messages_widget()
            mw.force_recalculate()
            self.scroll_to_bottom(mw.list_view)
            if self.chatlog_split_widget:
                self.chatlog_split_widget.force_recalculate()
            if self.presence_log_widget:
                self.presence_log_widget.force_recalculate()
                self.apply_presence_split_sizes()
        elif current == self.chatlog_widget and self.chatlog_widget:
            self.chatlog_widget.force_recalculate()
            self.scroll_to_bottom(self.chatlog_widget.list_view)
            nested = self.chatlog_widget.split_chatlog_widget
            if nested:
                nested.force_recalculate()

    def toggle_user_list(self):
        """Toggle userlist based on current view with proper recalculation"""

        current_view = self.stacked_widget.currentWidget()
        is_chatlog_view = (current_view == self.chatlog_widget)
        is_tracker_view = (
            getattr(self, 'user_tracker_widget', None) is not None
            and current_view == self.user_tracker_widget
        )
        width = self.width()

        if is_tracker_view:
            visible = self.user_tracker_widget.toggle_userlist()
            self.auto_hide_tracker_userlist = False
        elif is_chatlog_view and self.chatlog_userlist_widget:
            visible = not self.chatlog_userlist_widget.isVisible()
            self.chatlog_userlist_widget.setVisible(visible)
            self.userlist_panel.setVisible(visible)
            self.config.set("ui", "userlist", "chatlog", value=visible)
            self.auto_hide_chatlog_userlist = False
        else:
            visible = not self.user_list_widget.isVisible()
            self.user_list_widget.setVisible(visible)
            if hasattr(self, 'userlist_panel'):
                self.userlist_panel.setVisible(visible)
            self.config.set("ui", "userlist", "messages", value=visible)
            self.auto_hide_messages_userlist = False

        # Update button visual state
        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, visible)

        # Force resize handler to sync everything
        QTimer.singleShot(10, lambda: self.apply_resize(width))

        # Force recalculation after visibility change
        QTimer.singleShot(20, lambda: recalculate_layout(self))

"""ChatWindow: show, close and theme switching."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

from components.button import set_theme, update_all_icons
from helpers.deferred import call_later
from ui.messages.message_delegate import freeze_row_sizes


class ChatLifecycleMixin:
    """ChatWindow: show, close and theme switching."""

    def showEvent(self, event):
        """Handle window show events"""
        super().showEvent(event)

        # Prevent programmatic geometry changes during show from being saved
        self.showing_window = True

        # Reset unread count when window becomes visible
        if self.app_controller:
            self.app_controller.reset_unread()

        # Position emoticon selector when showing
        if hasattr(self, 'emoticon_selector'):
            QTimer.singleShot(50, self.position_emoticon_selector)
            if self.emoticon_selector.isVisible():
                QTimer.singleShot(100, self.emoticon_selector.resume_animations)

        # Restore delegate references and restart animations when showing
        try:
            if self.messages_widget and getattr(self.messages_widget, 'delegate', None):
                delegate = self.messages_widget.delegate
                delegate.set_list_view(self.messages_widget.list_view)
                # Ensure timer is running
                if not delegate.animation_timer.isActive():
                    delegate.animation_timer.start(33)
                # Restart any QMovie instances
                if delegate.message_renderer and hasattr(delegate.message_renderer, 'movie_cache'):
                    for movie in delegate.message_renderer.movie_cache.values():
                        try:
                            movie.start()
                        except Exception:
                            pass
        except Exception as e:
            print(f"ShowEvent resume animations error: {e}")

        # Update notification and always-on-top button state on show
        if hasattr(self, 'button_panel'):
            self.button_panel.update_notification_button_icon()
            # Ensure pin/unpin icon reflects current config
            self.button_panel.update_pin_button_icon()

        # Trigger an initial resize handler so UI elements (userlist, button panel)
        # reflect the current width immediately on first show
        call_later(self, 50, lambda: self.apply_resize(self.width()))

        # Clear the showing flag after a short delay so subsequent user-initiated resize/move
        # events will be persisted normally
        call_later(self, 200, lambda: setattr(self, 'showing_window', False))

    def show_and_focus_window(self, game_id=None):
        """Show/focus the chat window; switch to the originating room tab if any."""
        was_hidden = not self.isVisible()
        if was_hidden:
            self.setWindowOpacity(0)
            self.show()
            call_later(self, 50, lambda: self.setWindowOpacity(1))
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.activateWindow()
        self.raise_()
        if self.stacked_widget.currentWidget() is not self.messages_splitter:
            self.show_messages_view()
        if self.room_tabs:
            if game_id is not None and game_id in self.game_rooms:
                self.room_tabs.setCurrentWidget(self.game_rooms[game_id])
            else:
                self.room_tabs.setCurrentIndex(0)

    def toggle_theme(self):
        try:
            with freeze_row_sizes():
                self.theme_manager.toggle_theme()
                is_dark = self.theme_manager.is_dark()
                set_theme(is_dark)

            # Update theme button icon via button panel
            self.button_panel.update_theme_button_icon()

            # Update input styling for theme
            self.update_input_style()

            update_all_icons()

            # Update shared emoticon manager theme
            self.emoticon_manager.set_theme(is_dark)

            # Update widgets
            self.messages_widget.update_theme()
            if self.presence_log_widget:
                self.presence_log_widget.update_theme()
            self.user_list_widget.update_theme()

            if self.chatlog_widget:
                self.chatlog_widget.update_theme()

            if self.chatlog_userlist_widget:
                self.chatlog_userlist_widget.update_theme()

            if hasattr(self, 'profile_widget') and self.profile_widget:
                self.profile_widget.update_theme()

            # Update emoticon selector theme
            if hasattr(self, 'emoticon_selector'):
                self.emoticon_selector.update_theme()

            # Update button panel theme
            if hasattr(self, 'button_panel'):
                self.button_panel.update_theme()

            if getattr(self, "settings_widget", None):
                self.settings_widget.update_theme()

            if getattr(self, "user_tracker_widget", None):
                self.user_tracker_widget.update_theme()

            self.messages_widget.rebuild_messages()
            if self.presence_log_widget:
                self.presence_log_widget.rebuild_messages()

            if self.chatlog_widget and self.stacked_widget.currentWidget() == self.chatlog_widget:
                self.chatlog_widget.force_recalculate()

            # Re-theme open game rooms and custom rooms
            for room in self.all_room_widgets():
                room.update_theme()

            QApplication.processEvents()
        except Exception as e:
            print(f"Theme toggle error: {e}")

    def closeEvent(self, event):
        self.save_draft()
        # Cleanup emoticon selector
        if hasattr(self, 'emoticon_selector'):
            self.emoticon_selector.cleanup()

        # Remove new messages marker when closing
        self.clear_new_messages_marker()

        # Hiding to tray keeps animations and delegate state; full cleanup only on real close
        if self.tray_mode and not self.really_close:
            self.teardown_presence_log_widget()
            event.ignore()
            self.hide()
            return

        # Reset unread when actually closing
        if self.app_controller:
            self.app_controller.reset_unread()

        # Cleanup window size manager
        if hasattr(self, 'window_size_manager'):
            self.window_size_manager.cleanup()

        self.reset_competition_live_state()

        if self.my_username:
            self.mentions_digest.mark_session_end(self.my_username)
            if self.mentions_digest_active and self.chatlog_widget:
                self.chatlog_widget.on_parse_cancelled()
                self.end_mentions_digest()

        # Proceed with full cleanup when actually closing
        if self.messages_widget:
            if hasattr(self.messages_widget, 'auto_scroller'):
                try:
                    self.messages_widget.auto_scroller.cleanup()
                except Exception:
                    pass
            self.messages_widget.cleanup()
        if self.presence_log_widget:
            self.presence_log_widget.cleanup()
        if self.chatlog_split_widget:
            self.chatlog_split_widget.cleanup()
        for game_id in list(self.game_rooms.keys()):
            self.close_game_room_tab(game_id)
        if self.chatlog_widget:
            self.chatlog_widget.cleanup()

        if self.xmpp_client:
            try:
                self.xmpp_client.disconnect()
            except Exception:
                pass
        self.set_connection_status('offline')

        # Shutdown voice engine (TTS) and voice input (STT)
        if hasattr(self, 'voice_engine'):
            self.voice_engine.shutdown()
        if getattr(self, "voice_input", None):
            self.voice_input.shutdown()
        event.accept()


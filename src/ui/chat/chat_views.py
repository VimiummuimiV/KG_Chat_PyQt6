"""ChatWindow: messages, chatlog and split views."""

from datetime import datetime

from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication

from helpers.deferred import call_later
from helpers.scroll.scroll import scroll
from helpers.system.memory import release_memory_soon
from ui.chatlog.ui_chatlog import ChatlogWidget
from ui.chatlog.ui_chatlog_userlist import ChatlogUserlistWidget


class ChatViewsMixin:
    """ChatWindow: messages, chatlog and split views."""

    def show_messages_view(self):
        """Switch back to messages and conditionally destroy chatlog widgets"""
        self.ensure_general_tab_visible()
        # Cleanup and destroy chatlog userlist
        if self.chatlog_userlist_widget:
            try:
                self.chatlog_userlist_widget.filter_requested.disconnect()
                self.chatlog_userlist_widget.clear_cache()
            except Exception:
                pass
            self.userlist_panel.layout().removeWidget(self.chatlog_userlist_widget)
            self.chatlog_userlist_widget.deleteLater()
            self.chatlog_userlist_widget = None

        # For chatlog widget, destroy only if not parsing
        if self.chatlog_widget:
            if self.chatlog_widget.parser_widget.is_parsing:
                # Keep alive during parsing, just switch view
                pass
            else:
                try:
                    self.chatlog_widget.back_requested.disconnect()
                    self.chatlog_widget.messages_loaded.disconnect()
                    self.chatlog_widget.filter_changed.disconnect()
                    self.chatlog_widget.cleanup()
                except Exception:
                    pass
                self.stacked_widget.removeWidget(self.chatlog_widget)
                self.chatlog_widget.deleteLater()
                self.chatlog_widget = None
                release_memory_soon()

        self.stacked_widget.setCurrentWidget(self.messages_splitter)

        # Restore messages userlist, respecting compact width threshold
        width = self.width()
        messages_userlist_visible = self.config.get("ui", "userlist", "messages")
        if messages_userlist_visible is None:
            messages_userlist_visible = True
        visible = False if (width <= 1000 and self.auto_hide_messages_userlist) else messages_userlist_visible

        self.user_list_widget.setVisible(visible)
        if hasattr(self, 'userlist_panel'):
            self.userlist_panel.setVisible(visible)

        # Sync button state for messages userlist
        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(
                self.button_panel.toggle_userlist_button,
                self.user_list_widget.isVisible()
            )

        self.messages_widget.force_recalculate()
        self.scroll_to_bottom(self.messages_widget.list_view)
        # If parsing ongoing, show status widget
        if self.chatlog_widget and self.chatlog_widget.parser_widget.is_parsing:
            self.start_parse_status()

    def configure_chatlog_widget(self, widget):
        """Configure chatlog widget (main + split view) with actions support and shared settings."""
        if not widget:
            return

        # Enable Reply and Paste - chatlogs SHOULD include timestamp
        widget.set_input_field(self.input_field, include_timestamp=True)

        # Layout / compact mode
        compact = self.width() <= 1000
        widget.set_compact_mode(compact)
        widget.set_compact_layout(compact)

        # Username click handlers (reuse same logic as live messages)
        self.wire_username_signals(widget.interactions, right_click_widget=widget)

    def ensure_chatlog_widget(self):
        """Create chatlog + userlist widgets if needed (without switching the view)."""
        if not self.chatlog_widget:
            self.chatlog_widget = ChatlogWidget(
                self.config,
                self.emoticon_manager,
                self.icons_path,
                self.account,
                parent_window=self,
                ban_manager=self.ban_manager,
            )
            self.chatlog_widget.back_requested.connect(self.on_stacked_back)
            self.chatlog_widget.messages_loaded.connect(self._on_chatlog_messages_loaded)
            self.chatlog_widget.filter_changed.connect(self._on_chatlog_filter_changed)
            self.stacked_widget.addWidget(self.chatlog_widget)
            self.configure_chatlog_widget(self.chatlog_widget)

        if not self.chatlog_userlist_widget:
            self.chatlog_userlist_widget = ChatlogUserlistWidget(
                self.config,
                self.icons_path,
                self.ban_manager,
                self.user_tracker,
                my_username=self.my_username,
            )
            self.chatlog_userlist_widget.filter_requested.connect(self._on_filter_requested)
            self.wire_userlist_signals(self.chatlog_userlist_widget)
            self.userlist_panel.layout().insertWidget(0, self.chatlog_userlist_widget, stretch=1)
            self.chatlog_userlist_widget.setVisible(False)

    def show_chatlog_view(self, timestamp: str = None, reload: bool = True):
        """Open chatlog for today. reload=False just re-shows the existing widget
        as-is (used when returning from the profile view)."""
        self.ensure_general_tab_visible()
        # Hide messages userlist when in chatlog view
        self.user_list_widget.setVisible(False)

        self.ensure_chatlog_widget()

        # Show chatlog userlist based on config, compact width, and auto-hide
        width = self.width()
        chatlog_userlist_visible = self.config.get("ui", "userlist", "chatlog")
        if chatlog_userlist_visible is None:
            chatlog_userlist_visible = True
        visible = False if (width <= 1000 and self.auto_hide_chatlog_userlist) else chatlog_userlist_visible
        self.chatlog_userlist_widget.setVisible(visible)
        self.userlist_panel.setVisible(visible)

        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(
                self.button_panel.toggle_userlist_button,
                chatlog_userlist_visible
            )

        # Sync userlist ban visibility with chatlog parse mode
        if self.chatlog_widget and self.chatlog_userlist_widget:
            self.chatlog_userlist_widget.set_show_banned(self.chatlog_widget.is_parsing)

        # If reload is True and the parser is not visible, reset to today's date
        if reload and not self.chatlog_widget.parser_visible:
            self.chatlog_widget.current_date = datetime.now().date()
            self.chatlog_widget.update_date_display()
            self.chatlog_widget.load_current_date()

        self.stacked_widget.setCurrentWidget(self.chatlog_widget)

    def show_chatlog_split_view(self, date_str: str, time_str: str = ""):
        """Show that date's chatlog in a split pane below the messages view, keeping the messages
        view open. Used both for RMB on a live-chat timestamp and for clicking a chatlog link in a
        message body (time_str, if given, scrolls to and highlights that specific message)."""
        if self.chatlog_split_widget is None:
            if self.presence_log_widget:
                self.presence_log_widget.hide()
            self.chatlog_split_widget = ChatlogWidget(
                self.config,
                self.emoticon_manager,
                self.icons_path,
                self.account,
                parent_window=self,
                ban_manager=self.ban_manager
            )
            self.tr_set(self.chatlog_split_widget.back_button.setToolTip, "Close split view", "Закрыть разделённый вид")
            self.chatlog_split_widget.back_requested.connect(self.close_chatlog_split_view)
            # Match the live messages view's row layout so the two panes line up
            self.configure_chatlog_widget(self.chatlog_split_widget)
            self.messages_splitter.insertWidget(0, self.chatlog_split_widget)
            self.messages_splitter.setSizes([self.height() // 2, self.height() // 2])
            self.chatlog_split_widget.load_date_and_scroll(date_str, time_str)

            # Shrinking messages_widget's viewport here invalidates its "at bottom"
            # scroll position, breaking future auto-scroll in add_message() unless restored.
            call_later(self, 150, lambda: scroll(self.messages_widget.list_view, mode="bottom", delay=50))
            return

        self.chatlog_split_widget.load_date_and_scroll(date_str, time_str)

    def close_chatlog_split_view(self):
        """Close the split pane opened via RMB on a live-chat timestamp"""
        if not self.chatlog_split_widget:
            return
        widget = self.chatlog_split_widget
        self.chatlog_split_widget = None
        widget.cleanup()
        widget.setParent(None)
        widget.deleteLater()
        release_memory_soon()
        if self.presence_log_widget:
            self.presence_log_widget.show()
            self.apply_presence_split_sizes()

    def get_hovered_chatlog_widget(self):
        """Return the ChatlogWidget (main or split) currently under the mouse cursor.
        Returns None if no suitable chatlog widget is hovered."""
        gp = QCursor.pos()
        widget = QApplication.widgetAt(gp)
        if not widget:
            return None

        while widget:
            if isinstance(widget, ChatlogWidget):
                if not getattr(widget, 'parser_visible', False):
                    return widget
            widget = widget.parentWidget()
        return None

    def chatlog_for_hotkey(self):
        """Chatlog target for day-nav / search / mentions: pane under cursor, else main."""
        if not self.chatlog_widget or self.stacked_widget.currentWidget() != self.chatlog_widget:
            return None
        return self.get_hovered_chatlog_widget() or self.chatlog_widget

    def toggle_search_for_current_view(self):
        """Context search: chatlog pane under cursor, or active messages tab."""
        current = self.stacked_widget.currentWidget()
        if current == self.chatlog_widget:
            cw = self.chatlog_for_hotkey()
            if not cw:
                return
            if cw.parser_visible and not cw.parser_widget.is_parsing:
                cw.parser_widget.on_parse_clicked()
            elif not cw.parser_visible:
                cw.toggle_search()
            return
        if current == self.messages_splitter:
            mw = self.active_messages_widget()
            if mw:
                mw.toggle_search()

    def _on_chatlog_messages_loaded(self, messages):
        if self.chatlog_userlist_widget and messages:
            # Sync show_banned state with chatlog parse mode
            if self.chatlog_widget:
                self.chatlog_userlist_widget.set_show_banned(self.chatlog_widget.is_parsing)

            self.chatlog_userlist_widget.load_from_messages(messages)

    def _on_filter_requested(self, usernames: set):
        """Handle filter request from userlist"""
        if self.chatlog_widget:
            self.chatlog_widget.set_username_filter(usernames)

    def _on_chatlog_filter_changed(self, usernames: set):
        """Handle filter change from chatlog widget - sync to userlist"""
        if self.chatlog_userlist_widget:
            self.chatlog_userlist_widget.update_filter_state(usernames)

    def scroll_to_bottom(self, view, delay: int = 50):
        """Scroll a list view to bottom after `delay` ms (lets layout settle first).
        Small shared helper — this exact QTimer+lambda+scroll pattern was repeated
        all over the file for messages/chatlog/competition scroll-to-bottom calls."""
        call_later(view, delay, lambda: scroll(view, mode="bottom"))

    def scroll_to_row(self, view, row: int, delay: int = 0):
        """Scroll a list view to a specific row, centered."""
        call_later(view, delay, lambda: scroll(view, mode="middle", target_row=row))

    def active_messages_widget(self):
        """MessagesWidget of the current tab (game room or General)."""
        room = self.current_room()
        return room.messages_widget if room else self.messages_widget

    def apply_chatlog_max_messages(self):
        for widget in (self.chatlog_widget, self.chatlog_split_widget):
            if widget is not None:
                widget.apply_max_messages_limit()
                split = getattr(widget, "split_chatlog_widget", None)
                if split is not None:
                    split.apply_max_messages_limit()

    def apply_chat_max_messages(self):
        widgets = [self.messages_widget, self.presence_log_widget]
        widgets.extend(
            room.messages_widget for room in self.all_room_widgets()
            if room and room.messages_widget
        )
        for widget in widgets:
            if widget:
                widget.apply_max_messages_limit()

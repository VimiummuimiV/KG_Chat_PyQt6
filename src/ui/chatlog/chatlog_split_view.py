"""ChatlogWidget: message clicks and the nested split chatlog."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from components.button import set_button_icon
from helpers.deferred import call_later
from helpers.scroll.scroll import scroll
from helpers.system.memory import release_memory_soon
from helpers.translate import tr
from ui.settings.settings_options import DEFAULTS


class ChatlogSplitViewMixin:
    """ChatlogWidget: message clicks and the nested split chatlog."""

    def find_message_row(self, messages, predicate):
        return next(
            (i for i, msg in enumerate(messages)
             if not getattr(msg, 'is_separator', False) and predicate(msg)),
            None
        )

    def scroll_and_highlight(self, target_row: int, scroll_delay: int = 50, highlight_delay: int = 200):
        """Scroll to target row and highlight it after a delay."""
        scroll(self.list_view, mode="middle", target_row=target_row, delay=scroll_delay)
        call_later(self, highlight_delay, lambda: self.delegate.highlight_row(target_row, anchor=True))

    def anchor_frame_active(self) -> bool:
        """The anchor frame is held only while a filtered list and its full-log split are shown together"""
        return bool(self.split_chatlog_widget) and self.has_active_search_or_filter()

    def clear_anchors(self):
        for widget in (self, self.split_chatlog_widget):
            if widget:
                widget.delegate.set_anchor(None)

    def _filtered_click_opens_split(self) -> bool:
        action = self.config.get("ui", "chatlog", "filtered_click_action") or DEFAULTS["chatlog"]["filtered_click_action"]
        return action == "split"

    def on_message_clicked(self, row: int):
        """Handle message click - show the message in the split pane, or reveal all messages and scroll to it"""
        clicked_msg = self.model.data(self.model.index(row, 0), Qt.ItemDataRole.DisplayRole)
        has_filters = self.has_active_search_or_filter()

        # Split view open (or requested for filtered clicks) → show the message in the split
        # chatlog, loading that message's own date first if it differs
        if self.split_chatlog_widget or (has_filters and self._filtered_click_opens_split()):
            if clicked_msg and not getattr(clicked_msg, 'is_separator', False):
                self._ensure_split_chatlog_widget().load_date_and_scroll(
                    clicked_msg.timestamp.strftime("%Y-%m-%d"), clicked_msg.get_time_str()
                )
            self.delegate.highlight_row(row, anchor=True)
            return

        # No active filters → simple direct scroll + highlight
        if not has_filters:
            self.scroll_and_highlight(row, scroll_delay=50, highlight_delay=200)
            return

        # Filters are active → clear them and find message in full list
        if not clicked_msg:
            return

        # Find corresponding row in unfiltered messages
        target_row = next((i for i, msg in enumerate(self.all_messages)
                        if not msg.is_separator 
                        and msg.username == clicked_msg.username
                        and msg.body == clicked_msg.body 
                        and msg.timestamp == clicked_msg.timestamp), None)

        if target_row is None:
            return

        # Clear filters
        self.filtered_usernames = set()
        self.search.clear()

        # Only update icon if it was actually active
        if self.filter_mentions:
            self.filter_mentions = False
            set_button_icon(self.mention_filter_button, "line/at-line.svg")

        self.apply_filter()
        self.filter_changed.emit(self.filtered_usernames)

        # Scroll + highlight after the list has rebuilt
        call_later(self, 100, lambda: self.scroll_and_highlight(
            target_row,
            scroll_delay=100,
            highlight_delay=250
        ))

    def _ensure_split_chatlog_widget(self):
        """Create (if needed) and return the split pane showing another date's chatlog"""
        if self.split_chatlog_widget is None:
            self.split_chatlog_widget = type(self)(
                self.config,
                self.emoticon_manager,
                self.icons_path,
                account=self.account,
                parent_window=self,
                ban_manager=self.ban_manager
            )
            self.split_chatlog_widget.delegate.anchor_frame_enabled = self.anchor_frame_active
            self.split_chatlog_widget.back_button.setToolTip(tr("Close split view", "Закрыть разделённый вид"))
            self.split_chatlog_widget.back_requested.connect(self.close_split_view)
            self.content_splitter.addWidget(self.split_chatlog_widget)
            self.content_splitter.setSizes([self.height() // 2, self.height() // 2])

            # Configure reply, compact mode, username clicks, etc.
            if self.parent_window:
                self.parent_window.configure_chatlog_widget(self.split_chatlog_widget)

        return self.split_chatlog_widget

    def on_date_separator_clicked(self, date_str: str):
        """Open (or update) a split pane showing the full chatlog for the clicked date"""
        widget = self._ensure_split_chatlog_widget()
        if widget.current_date.strftime("%Y-%m-%d") == date_str and widget.all_messages:
            return
        widget.load_date(date_str)

    def on_chatlog_link_clicked(self, date_str: str, time_str: str):
        """A chatlog URL inside a message body was clicked - open/update the split pane
        at that date, scrolling to and highlighting the linked message if a time was given"""
        self._ensure_split_chatlog_widget().load_date_and_scroll(date_str, time_str)

    def on_info_label_clicked(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        text = self.info_label.text().strip()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.info_label.flash()
        event.accept()

    def close_split_view(self):
        """Close the split pane showing a single date's full chatlog"""
        if not self.split_chatlog_widget:
            return
        widget = self.split_chatlog_widget
        self.split_chatlog_widget = None
        self.clear_anchors()
        widget.cleanup()
        widget.setParent(None)
        widget.deleteLater()
        release_memory_soon()

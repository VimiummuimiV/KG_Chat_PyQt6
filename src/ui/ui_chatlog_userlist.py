"""Chatlog userlist widget - shows users with message counts and filtering"""
from pathlib import Path
from collections import Counter
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QApplication
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor

from helpers.create import create_icon_button
from helpers.cache import get_cache
from helpers.fonts import get_font, FontType
from helpers.scroll.auto_scroll import AutoScroller
from components.user_count_row import UserCountRow
from components.user_context_menu import (
    show_user_context_menu,
    PROFILE,
    PRIVATE,
    PASTE_USERNAME,
    COPY_USERNAME,
    COPY_ID,
    FILTER,
    TRACK,
    UNTRACK
)


class ChatlogUserWidget(UserCountRow):
    """Single user widget for chatlog - adds context menu (profile/private/track/etc) on top of the base row"""

    profile_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    private_chat_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    paste_requested = pyqtSignal(str) # username
    track_requested = pyqtSignal(str, str, bool)  # user_id, login, track

    def __init__(self, username, msg_count, config, icons_path, user_id=None, user_tracker=None):
        super().__init__(username, msg_count, config, icons_path, user_id)
        self.user_tracker = user_tracker

    def contextMenuEvent(self, event):
        is_tracked = bool(
            self.user_tracker and self.user_tracker.is_tracked(
                user_id=self.user_id, login=self.username
            )
        )
        action = show_user_context_menu(
            self.icons_path, self, QCursor.pos(),
            show_filter=True, is_tracked=is_tracked, show_track=True,
        )
        if action == PROFILE:
            self.profile_requested.emit("", self.username, self.user_id or "")
        elif action == PRIVATE:
            self.private_chat_requested.emit("", self.username, self.user_id or "")
        elif action == PASTE_USERNAME:
            self.paste_requested.emit(self.username)
        elif action == COPY_USERNAME:
            QApplication.clipboard().setText(self.username)
        elif action == COPY_ID:
            QApplication.clipboard().setText(str(self.user_id or ""))
        elif action == FILTER:
            self.clicked.emit(self.username, False)
        elif action == TRACK:
            self.track_requested.emit(str(self.user_id or ""), self.username, True)
        elif action == UNTRACK:
            self.track_requested.emit(str(self.user_id or ""), self.username, False)


class ChatlogUserlistWidget(QWidget):
    """Userlist for chatlog view with message counts and filtering"""
    
    filter_requested = pyqtSignal(set)  # Emit set of usernames to filter
    profile_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    private_chat_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    paste_requested = pyqtSignal(str) # username
    track_requested = pyqtSignal(str, str, bool)

    def __init__(self, config, icons_path, ban_manager=None, user_tracker=None):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.cache = get_cache()
        self.ban_manager = ban_manager
        self.user_tracker = user_tracker
        self.show_banned = False  # Track if we should show banned users
        self.user_widgets = {}  # username -> widget
        self.filtered_usernames = set()
        
        margin = config.get("ui", "margins", "widget") or 5
        spacing = config.get("ui", "spacing", "widget_elements") or 6
        
        layout = QVBoxLayout()
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)
        self.setLayout(layout)
        
        # Clear filter button (initially hidden)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(config.get("ui", "buttons", "spacing") or 8)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.clear_filter_btn = create_icon_button(
            icons_path,
            "go-back.svg",
            "Clear filter and show all users",
            size_type="large",
            config=config
        )
        self.clear_filter_btn.clicked.connect(self.clear_filter)
        self.clear_filter_btn.setVisible(False)
        button_layout.addWidget(self.clear_filter_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        self.auto_scroller = AutoScroller(scroll)
        
        container = QWidget()
        self.user_layout = QVBoxLayout()
        self.user_layout.setContentsMargins(5, 5, 5, 5)
        self.user_layout.setSpacing(2)
        container.setLayout(self.user_layout)
        scroll.setWidget(container)
        
        self.user_layout.addStretch()
    
    def set_show_banned(self, show: bool):
        """Control whether banned users are shown (for parse mode)"""
        self.show_banned = show
    
    def _handle_user_click(self, username: str, ctrl_pressed: bool):
        """Handle user click with Ctrl modifier support"""
        if ctrl_pressed:
            # Toggle username in filter
            if username in self.filtered_usernames:
                self.filtered_usernames.remove(username)
            else:
                self.filtered_usernames.add(username)
        else:
            # Replace filter with single username
            if self.filtered_usernames == {username}:
                # If clicking the only filtered user, clear filter
                self.filtered_usernames = set()
            else:
                self.filtered_usernames = {username}
        
        # Update visual state
        for uname, widget in self.user_widgets.items():
            widget.set_filtered(uname in self.filtered_usernames)
        
        # Show/hide clear button
        self.clear_filter_btn.setVisible(bool(self.filtered_usernames))
        
        # Emit filter
        self.filter_requested.emit(self.filtered_usernames.copy())
    
    def clear_filter(self):
        """Clear all filters"""
        self.filtered_usernames = set()
        for widget in self.user_widgets.values():
            widget.set_filtered(False)
        self.clear_filter_btn.setVisible(False)
        self.filter_requested.emit(set())

    def update_filter_state(self, filtered_usernames: set):
        """Update filter state from external signal without emitting to avoid loops"""
        self.filtered_usernames = filtered_usernames.copy()
        for uname, widget in self.user_widgets.items():
            widget.set_filtered(uname in filtered_usernames)
        self.clear_filter_btn.setVisible(bool(filtered_usernames))
    
    def load_from_messages(self, messages):
        """Load users from chatlog messages with ban filtering"""
        self._clear_widgets()
        
        if not messages:
            return
        
        # Count messages per user
        counts = Counter(msg.username for msg in messages)
        
        # FILTER BANNED USERS - completely hide them unless in parse mode
        if self.ban_manager and not self.show_banned:
            # Remove banned users from counts
            filtered_counts = {}
            for username, count in counts.items():
                if not self.ban_manager.is_banned_by_username(username):
                    filtered_counts[username] = count
            counts = filtered_counts

        if not counts:
            # All users were banned or no messages
            empty_label = QLabel("No users to display")
            empty_label.setFont(get_font(FontType.TEXT))
            empty_label.setStyleSheet("color: #888888;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.user_layout.addWidget(empty_label)
            self.user_layout.addStretch()
            return

        sorted_users = sorted(counts.items(), key=lambda x: (-x[1], x[0].lower()))
        
        # Create widgets - all users shown here are NOT banned (or we're in parse mode)
        for username, count in sorted_users:
            try:
                user_id = self.cache.get_user_id(username)
                widget = ChatlogUserWidget(username, count, self.config, self.icons_path, user_id, self.user_tracker)
                widget.clicked.connect(self._handle_user_click)
                widget.profile_requested.connect(self.profile_requested.emit)
                widget.private_chat_requested.connect(self.private_chat_requested.emit)
                widget.paste_requested.connect(self.paste_requested.emit)
                widget.track_requested.connect(self.track_requested.emit)
                widget.set_filtered(username in self.filtered_usernames)
                self.user_widgets[username] = widget
                self.user_layout.insertWidget(self.user_layout.count() - 1, widget)
            except Exception as e:
                print(f"Error creating chatlog user widget: {e}")
        
        # Update clear button visibility
        self.clear_filter_btn.setVisible(bool(self.filtered_usernames))
    
    def update_theme(self):
        """Update colors based on theme"""
        is_dark = self.config.get("ui", "theme") == "dark"
        neutral_color = "#CCCCCC" if is_dark else "#666666"
        
        self.setUpdatesEnabled(False)
        for username, widget in list(self.user_widgets.items()):
            try:
                # Username gets its own precomputed color; count gets neutral theme color
                username_color = self.cache.get_username_color(username, is_dark)
                widget.username_label.setStyleSheet(f"color: {username_color};")
                widget.update_color(neutral_color)
            except (RuntimeError, AttributeError):
                pass
        self.setUpdatesEnabled(True)
    
    def clear_cache(self):
        """Clear cache - called when going back to messages"""
        pass

    def reset_filter(self):
        """Reset filter state (called when navigating dates)"""
        # Keep the filter active across date changes
        pass
    
    def _clear_widgets(self):
        """Clear user widgets"""
        self.user_widgets.clear()
        while self.user_layout.count() > 1:
            item = self.user_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        QApplication.processEvents()

    def cleanup(self):
        """Clean up resources"""
        self.auto_scroller.cleanup()
"""Chatlog userlist widget - shows users with message counts and filtering"""
from pathlib import Path
from collections import Counter
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QApplication
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor

from helpers.create import create_icon_button
from helpers.fonts import get_font, FontType


class ChatlogUserWidget(QWidget):
    """Single user widget for chatlog"""
    
    clicked = pyqtSignal(str, bool)  # username, ctrl_pressed
    
    def __init__(self, username, msg_count, config):
        super().__init__()
        self.username = username
        self.is_filtered = False
        
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(6)
        self.setLayout(layout)
        
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        # Username - use theme-dependent color
        is_dark = config.get("ui", "theme") == "dark"
        text_color = "#CCCCCC" if is_dark else "#666666"
        
        self.username_label = QLabel(username)
        self.username_label.setStyleSheet(f"color: {text_color};")
        self.username_label.setFont(get_font(FontType.TEXT))
        layout.addWidget(self.username_label, stretch=1)
        
        # Message count
        self.count_label = QLabel(f"{msg_count}")
        self.count_label.setFont(get_font(FontType.TEXT))
        self.count_label.setStyleSheet(f"color: {text_color};")
        layout.addWidget(self.count_label)
    
    def update_color(self, color: str):
        """Update colors without rebuilding widget"""
        self.username_label.setStyleSheet(f"color: {color};")
        self.count_label.setStyleSheet(f"color: {color};")
    
    def set_filtered(self, filtered: bool):
        """Update visual state when filtered"""
        self.is_filtered = filtered
        if filtered:
            self.setStyleSheet("background-color: rgba(226, 135, 67, 0.2); border-radius: 4px;")
        else:
            self.setStyleSheet("")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            self.clicked.emit(self.username, bool(ctrl_pressed))
        super().mousePressEvent(event)


class ChatlogUserlistWidget(QWidget):
    """Userlist for chatlog view with message counts and filtering"""
    
    filter_requested = pyqtSignal(set)  # Emit set of usernames to filter
    
    def __init__(self, config, icons_path, color_cache, ban_manager=None):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.color_cache = color_cache
        self.ban_manager = ban_manager
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
        button_layout.setContentsMargins(0, 1, 0, 0) # Slight top margin
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
    
    def load_from_messages(self, messages, user_id_resolver=None):
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
                widget = ChatlogUserWidget(username, count, self.config)
                widget.clicked.connect(self._handle_user_click)
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
        new_color = "#CCCCCC" if is_dark else "#666666"
        
        self.setUpdatesEnabled(False)
        for username, widget in list(self.user_widgets.items()):
            try:
                widget.update_color(new_color)
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
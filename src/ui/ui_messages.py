"""Messages display widget"""
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from helpers.color_contrast import optimize_color_contrast


class MessageLabel(QLabel):
    """Custom label for messages with click handling"""
    
    def __init__(self, text, login=None, input_field=None):
        super().__init__(text)
        self.login = login
        self.input_field = input_field
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        # Make username clickable
        if login and input_field:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def mousePressEvent(self, event):
        """Handle single click on username"""
        if self.login and self.input_field and event.button() == Qt.MouseButton.LeftButton:
            current = (self.input_field.text() or "").strip()
            existing = [t.strip() for t in current.split(',') if t.strip()]
            
            if self.login not in existing:
                new_list = existing + [self.login]
                self.input_field.setText(", ".join(new_list) + ", ")
            
            self.input_field.setFocus()
        
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double click on username"""
        if self.login and self.input_field:
            current = (self.input_field.text() or "").strip()
            existing = [t.strip() for t in current.split(',') if t.strip()]
            
            # Clear if exactly one username, otherwise replace with clicked username
            if len(existing) == 1:
                self.input_field.setText("")
            else:
                self.input_field.setText(f"{self.login}, ")
            
            self.input_field.setFocus()
        
        super().mouseDoubleClickEvent(event)


class MessagesWidget(QWidget):
    """Widget for displaying chat messages"""
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.input_field = None  # Will be set later
        self.messages = []
        self.max_messages = 100
        self.color_cache = {}  # will be set from ChatWindow
        
        # Get background color from config
        self.bg_color = config.get("ui", "theme")
        self.bg_hex = "#1E1E1E" if self.bg_color == "dark" else "#FFFFFF"
        
        self.setup_ui()

    def set_color_cache(self, cache: dict):
        """Set a shared color cache dict (shared with userlist)"""
        self.color_cache = cache
    
    def set_input_field(self, input_field):
        """Set the input field for username clicking"""
        self.input_field = input_field
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        self.setLayout(layout)
        
        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll_area)
        
        # Messages container
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout()
        self.messages_layout.setContentsMargins(5, 5, 5, 5)
        self.messages_layout.setSpacing(2)
        self.messages_layout.addStretch()
        self.messages_container.setLayout(self.messages_layout)
        
        self.scroll_area.setWidget(self.messages_container)
    
    def add_message(self, msg):
        """Add a message to the display"""
        # Format timestamp
        timestamp = getattr(msg, 'timestamp', None) or datetime.now()
        time_str = timestamp.strftime("%H:%M:%S")
        
        # Get login and color (use shared cache)
        login = msg.login if msg.login else "Unknown"
        if login not in self.color_cache:
            bg_color = getattr(msg, 'background', None)
            if bg_color:
                self.color_cache[login] = optimize_color_contrast(bg_color, self.bg_hex, target_ratio=4.5)
            else:
                self.color_cache[login] = "#AAAAAA"
        bg_color = self.color_cache[login]
        
        # Format message HTML
        html = f'''
        <span style="color: #999999;">{time_str}</span>
        <span style="color: {bg_color}; font-weight: bold;">{login}:</span>
        <span>{msg.body}</span>
        '''
        
        # Create message label
        message_label = MessageLabel(html, login, self.input_field)
        message_label.setFont(QFont(self.config.get("ui", "font_family"), 12))
        
        # Insert before stretch
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1,
            message_label
        )
        
        self.messages.append(message_label)
        
        # Limit messages
        if len(self.messages) > self.max_messages:
            old_msg = self.messages.pop(0)
            self.messages_layout.removeWidget(old_msg)
            old_msg.deleteLater()
        
        # Auto-scroll to bottom
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )
    
    def update_theme(self):
        """Update theme colors"""
        theme = self.config.get("ui", "theme")
        self.bg_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
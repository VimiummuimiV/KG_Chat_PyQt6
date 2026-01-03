"""Chat window with XMPP integration"""
import threading
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from helpers.config import Config
from helpers.create import create_icon_button, update_all_icons, set_theme
from themes.theme import ThemeManager
from core.xmpp import XMPPClient
from ui.ui_messages import MessagesWidget
from ui.ui_userlist import UserListWidget
from components.notification import show_notification


class SignalEmitter(QObject):
    """Thread-safe signal emitter for XMPP callbacks"""
    message_received = pyqtSignal(object)
    presence_received = pyqtSignal(object)


class ChatWindow(QWidget):
    def __init__(self, account=None):
        super().__init__()
        
        self.account = account
        self.xmpp_client = None
        self.signal_emitter = SignalEmitter()
        
        # Paths
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.icons_path = Path(__file__).parent.parent / "icons"
        
        # Config and theme
        self.config = Config(str(self.config_path))
        self.theme_manager = ThemeManager(self.config)
        self.theme_manager.apply_theme()
        set_theme(self.theme_manager.is_dark())
        
        # Initialize UI
        self.initializeUI()
        
        # Connect signals
        self.signal_emitter.message_received.connect(self.on_message)
        self.signal_emitter.presence_received.connect(self.on_presence)
        
        # Connect XMPP
        if account:
            self.connect_xmpp()
    
    def initializeUI(self):
        """Initialize the UI components"""
        # Window setup
        window_title = f"Chat - {self.account['login']}" if self.account else "Chat"
        self.setWindowTitle(window_title)
        self.resize(1500, 800)
        
        # Main layout
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        self.setLayout(main_layout)
        
        # Left side: messages + input
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)
        main_layout.addLayout(left_layout, stretch=3)
        
        # Messages widget
        self.messages_widget = MessagesWidget(self.config)
        left_layout.addWidget(self.messages_widget, stretch=1)
        
        # Input row
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        left_layout.addLayout(input_layout)
        
        # Input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.setFixedHeight(48)
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field, stretch=1)
        
        # Connect input field to messages widget
        self.messages_widget.set_input_field(self.input_field)
        
        # Send button
        self.send_button = create_icon_button(
            self.icons_path, "send.svg", "Send Message"
        )
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        
        # Theme toggle button
        is_dark = self.theme_manager.is_dark()
        theme_icon = "sun.svg" if is_dark else "moon.svg"
        theme_tooltip = "Switch to Light Mode" if is_dark else "Switch to Dark Mode"
        self.theme_button = create_icon_button(
            self.icons_path, theme_icon, theme_tooltip
        )
        self.theme_button.clicked.connect(self.toggle_theme)
        input_layout.addWidget(self.theme_button)
        
        # Toggle user list button
        self.toggle_userlist_button = create_icon_button(
            self.icons_path, "user.svg", "Toggle User List"
        )
        self.toggle_userlist_button.clicked.connect(self.toggle_user_list)
        input_layout.addWidget(self.toggle_userlist_button)
        
        # Right side: user list
        self.user_list_widget = UserListWidget(self.config, self.input_field)
        userlist_visible = self.config.get("ui", "userlist_visible")
        if userlist_visible is not None:
            self.user_list_widget.setVisible(userlist_visible)
        main_layout.addWidget(self.user_list_widget, stretch=1)
    
    def connect_xmpp(self):
        """Connect to XMPP server"""
        try:
            self.xmpp_client = XMPPClient(str(self.config_path))
            
            if not self.xmpp_client.connect(self.account):
                show_notification("Connection Failed", "Could not connect to XMPP server")
                return
            
            # Set callbacks
            self.xmpp_client.set_message_callback(self.message_callback)
            self.xmpp_client.set_presence_callback(self.presence_callback)
            
            # Join rooms
            rooms = self.xmpp_client.account_manager.get_rooms()
            for room in rooms:
                if room.get('auto_join'):
                    self.xmpp_client.join_room(room['jid'])
            
            # Start listening in background thread
            listen_thread = threading.Thread(
                target=self.xmpp_client.listen,
                daemon=True
            )
            listen_thread.start()
            
        except Exception as e:
            show_notification("Error", f"Connection error: {e}")
    
    def message_callback(self, msg):
        """Thread-safe message callback from XMPP"""
        self.signal_emitter.message_received.emit(msg)
    
    def presence_callback(self, pres):
        """Thread-safe presence callback from XMPP"""
        self.signal_emitter.presence_received.emit(pres)
    
    def on_message(self, msg):
        """Handle incoming message in main thread"""
        # Add to UI
        self.messages_widget.add_message(msg)
        
        # Show notification for messages from others
        try:
            is_from_other = (
                not getattr(msg, 'initial', False) and 
                msg.login and 
                msg.login != self.account.get('login')
            )
            if is_from_other:
                show_notification(msg.login, msg.body)
        except Exception as e:
            print(f"Notification error: {e}")
    
    def on_presence(self, pres):
        """Handle presence update in main thread"""
        if self.xmpp_client:
            users = self.xmpp_client.user_list.get_all()
            self.user_list_widget.update_users(users)
    
    def send_message(self):
        """Send message to XMPP"""
        text = self.input_field.text().strip()
        if text and self.xmpp_client:
            self.xmpp_client.send_message(text)
            self.input_field.clear()
    
    def toggle_user_list(self):
        """Toggle user list visibility"""
        visible = not self.user_list_widget.isVisible()
        self.user_list_widget.setVisible(visible)
        self.config.set("ui", "userlist_visible", value=visible)
    
    def toggle_theme(self):
        """Toggle between dark and light theme"""
        self.theme_manager.toggle_theme()
        is_dark = self.theme_manager.is_dark()
        
        set_theme(is_dark)
        
        # Update theme button
        theme_icon = "sun.svg" if is_dark else "moon.svg"
        self.theme_button._icon_name = theme_icon
        self.theme_button.setToolTip("Switch to Light Mode" if is_dark else "Switch to Dark Mode")
        
        update_all_icons()
        
        # Update widgets
        self.messages_widget.update_theme()
        self.user_list_widget.update_theme()
    
    def closeEvent(self, event):
        """Clean up on window close"""
        if self.xmpp_client:
            self.xmpp_client.disconnect()
        event.accept()
"""
XMPP Chat GUI Application
Desktop chat client with PyQt6
"""

import sys
import threading
import requests
from io import BytesIO
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QSplitter, QScrollArea, QFrame, QDialog, QComboBox,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QSize
from PyQt6.QtGui import QPixmap, QFont, QIcon, QTextCursor

from xmpp import XMPPClient
from accounts import AccountManager
from commands import AccountCommands


class SignalEmitter(QObject):
    """Signal emitter for thread-safe GUI updates"""
    message_received = pyqtSignal(object)
    presence_update = pyqtSignal(object)
    connection_status = pyqtSignal(bool, str)


class UserWidget(QWidget):
    """Widget for displaying a single user"""
    
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.user = user
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Avatar
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(40, 40)
        self.avatar_label.setStyleSheet("""
            QLabel {
                border: 2px solid #555;
                border-radius: 20px;
                background-color: #444;
            }
        """)
        
        # Load avatar if available
        if self.user.avatar:
            self.load_avatar(self.user.get_avatar_url())
        else:
            self.avatar_label.setText("👤")
            self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(self.avatar_label)
        
        # Username and game info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        username_label = QLabel(self.user.login)
        username_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        username_label.setStyleSheet("color: white;")
        info_layout.addWidget(username_label)
        
        if self.user.game_id:
            game_label = QLabel(f"🎮 Game #{self.user.game_id}")
            game_label.setFont(QFont("Arial", 8))
            game_label.setStyleSheet("color: #888;")
            info_layout.addWidget(game_label)
        
        layout.addLayout(info_layout, 1)
        
        # Status indicator
        status_label = QLabel("🟢")
        layout.addWidget(status_label)
        
        self.setLayout(layout)
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-radius: 5px;
                margin: 2px;
            }
            QWidget:hover {
                background-color: #3b3b3b;
            }
        """)
    
    def load_avatar(self, url):
        """Load avatar from URL"""
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                scaled_pixmap = pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, 
                                              Qt.TransformationMode.SmoothTransformation)
                self.avatar_label.setPixmap(scaled_pixmap)
        except:
            pass


class AccountDialog(QDialog):
    """Dialog for account selection and management"""
    
    def __init__(self, account_manager, parent=None):
        super().__init__(parent)
        self.account_manager = account_manager
        self.selected_account = None
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("Select Account")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Account selector
        accounts = self.account_manager.list_accounts()
        
        if accounts:
            label = QLabel("Select an account:")
            layout.addWidget(label)
            
            self.account_combo = QComboBox()
            for acc in accounts:
                self.account_combo.addItem(f"{acc['login']} (ID: {acc['user_id']})", acc)
            layout.addWidget(self.account_combo)
            
            # Connect button
            connect_btn = QPushButton("Connect")
            connect_btn.clicked.connect(self.accept)
            layout.addWidget(connect_btn)
        else:
            label = QLabel("No accounts found. Please add an account first.")
            layout.addWidget(label)
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def accept(self):
        """Save selected account"""
        self.selected_account = self.account_combo.currentData()
        super().accept()

class ChatWindow(QMainWindow):
    """Main chat window"""
    
    def __init__(self):
        super().__init__()
        self.xmpp = XMPPClient()
        self.commands = AccountCommands(self.xmpp.account_manager)
        self.signals = SignalEmitter()
        
        # Connect signals
        self.signals.message_received.connect(self.on_message)
        self.signals.presence_update.connect(self.on_presence)
        self.signals.connection_status.connect(self.on_connection_status)
        
        # Set callbacks
        self.xmpp.set_message_callback(self.handle_xmpp_message)
        self.xmpp.set_presence_callback(self.handle_xmpp_presence)
        
        self.setup_ui()
        self.show_account_dialog()
    
    def setup_ui(self):
        """Setup the main UI"""
        self.setWindowTitle("XMPP Chat")
        self.setGeometry(100, 100, 1200, 700)
        
        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QTextEdit {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 5px;
                padding: 10px;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 5px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8f;
            }
            QListWidget {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 5px;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # === LEFT PANEL: Messages ===
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        
        # Messages display
        self.messages_display = QTextEdit()
        self.messages_display.setReadOnly(True)
        left_layout.addWidget(self.messages_display, 1)
        
        # Input area
        input_layout = QHBoxLayout()
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field, 1)
        
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        
        left_layout.addLayout(input_layout)
        
        # === RIGHT PANEL: User List ===
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)
        
        # User list header
        users_header = QLabel("👥 ONLINE USERS")
        users_header.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                background-color: #2d2d30;
                border-radius: 5px;
            }
        """)
        right_layout.addWidget(users_header)
        
        # Scrollable user list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.user_list_widget = QWidget()
        self.user_list_layout = QVBoxLayout()
        self.user_list_layout.setSpacing(2)
        self.user_list_layout.addStretch()
        self.user_list_widget.setLayout(self.user_list_layout)
        
        scroll_area.setWidget(self.user_list_widget)
        right_layout.addWidget(scroll_area, 1)
        
        # User count
        self.user_count_label = QLabel("Total: 0")
        self.user_count_label.setStyleSheet("""
            QLabel {
                color: #888;
                font-size: 11px;
                padding: 5px;
            }
        """)
        right_layout.addWidget(self.user_count_label)
        
        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)  # Messages take 75%
        splitter.setStretchFactor(1, 1)  # Users take 25%
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.statusBar().showMessage("Disconnected")
        self.statusBar().setStyleSheet("color: #888;")
    
    def show_account_dialog(self):
        """Show account selection dialog"""
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            self.connect_xmpp(dialog.selected_account)
        else:
            QMessageBox.warning(self, "No Account", "No account selected. Exiting.")
            sys.exit(0)
    
    def connect_xmpp(self, account):
        """Connect to XMPP in background thread"""
        self.statusBar().showMessage("Connecting...")
        
        def connect_thread():
            try:
                if self.xmpp.connect(account):
                    rooms = self.xmpp.account_manager.get_rooms()
                    for room in rooms:
                        if room.get('auto_join'):
                            self.xmpp.join_room(room['jid'])
                    
                    self.signals.connection_status.emit(True, f"Connected as {account['login']}")
                    
                    # Start listening
                    self.xmpp.listen()
                else:
                    self.signals.connection_status.emit(False, "Connection failed")
            except Exception as e:
                self.signals.connection_status.emit(False, f"Error: {e}")
        
        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
    
    def on_connection_status(self, success, message):
        """Handle connection status update"""
        if success:
            self.statusBar().showMessage(message)
            self.statusBar().setStyleSheet("color: #4ec9b0;")
            self.add_system_message(message)
        else:
            self.statusBar().showMessage(message)
            self.statusBar().setStyleSheet("color: #f48771;")
            self.add_system_message(f"❌ {message}")
    
    def handle_xmpp_message(self, message):
        """Handle XMPP message from callback"""
        # Filter out own messages
        active_account = self.xmpp.account_manager.get_active_account()
        if active_account and message.login == active_account['login']:
            return
        
        self.signals.message_received.emit(message)
    
    def handle_xmpp_presence(self, presence):
        """Handle XMPP presence from callback"""
        self.signals.presence_update.emit(presence)
    
    def on_message(self, message):
        """Display received message"""
        sender = message.login if message.login else "Unknown"
        timestamp = message.timestamp.strftime("%H:%M") if message.timestamp else ""
        
        self.add_message(sender, message.body, timestamp)
    
    def on_presence(self, presence):
        """Handle presence update"""
        if presence.presence_type == 'unavailable':
            user = presence.login if presence.login else "User"
            self.add_system_message(f"👋 {user} left")
        elif presence.presence_type == 'available':
            user = presence.login if presence.login else "User"
            self.add_system_message(f"👋 {user} joined")
        
        # Update user list
        self.update_user_list()
    
    def add_message(self, sender, text, timestamp=""):
        """Add a message to the display"""
        cursor = self.messages_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        html = f"""
        <div style="margin: 5px 0; padding: 8px; background-color: #2d2d30; border-radius: 5px;">
            <span style="color: #4ec9b0; font-weight: bold;">{sender}</span>
            <span style="color: #888; font-size: 10px; margin-left: 10px;">{timestamp}</span>
            <div style="color: #cccccc; margin-top: 3px;">{text}</div>
        </div>
        """
        
        cursor.insertHtml(html)
        self.messages_display.setTextCursor(cursor)
        self.messages_display.ensureCursorVisible()
    
    def add_system_message(self, text):
        """Add a system message"""
        cursor = self.messages_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        html = f"""
        <div style="margin: 5px 0; padding: 5px; text-align: center;">
            <span style="color: #888; font-style: italic; font-size: 11px;">{text}</span>
        </div>
        """
        
        cursor.insertHtml(html)
        self.messages_display.setTextCursor(cursor)
        self.messages_display.ensureCursorVisible()
    
    def update_user_list(self):
        """Update the user list display"""
        # Clear existing widgets
        while self.user_list_layout.count() > 1:  # Keep the stretch
            item = self.user_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add user widgets
        users = self.xmpp.user_list.get_online()
        for user in sorted(users, key=lambda u: u.login.lower()):
            user_widget = UserWidget(user)
            self.user_list_layout.insertWidget(self.user_list_layout.count() - 1, user_widget)
        
        # Update count
        self.user_count_label.setText(f"Total: {len(users)}")
    
    def send_message(self):
        """Send message to XMPP"""
        text = self.input_field.text().strip()
        if not text:
            return
        
        if self.xmpp.send_message(text):
            # Show sent confirmation
            self.add_message("You", text, datetime.now().strftime("%H:%M"))
            self.input_field.clear()
        else:
            self.add_system_message("❌ Failed to send message")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern look
    
    window = ChatWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
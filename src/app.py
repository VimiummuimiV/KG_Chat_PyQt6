"""
XMPP Chat GUI Application
Desktop chat client with PyQt6 - Klavogonki style
"""

import sys
import threading
import requests
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QSplitter, 
    QScrollArea, QDialog, QComboBox, QMessageBox, QMenuBar, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QFont, QTextCursor, QAction

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
        layout.setContentsMargins(8, 4, 8, 4)
        
        # Avatar
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(32, 32)
        self.avatar_label.setStyleSheet("""
            QLabel {
                border: 1px solid #444;
                border-radius: 3px;
                background-color: #2a2a2a;
            }
        """)
        
        # Load avatar if available
        if self.user.avatar:
            self.load_avatar(self.user.get_avatar_url())
        else:
            self.avatar_label.setText("👤")
            self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.avatar_label.setStyleSheet("""
                QLabel {
                    border: 1px solid #444;
                    border-radius: 3px;
                    background-color: #2a2a2a;
                    font-size: 16px;
                }
            """)
        
        layout.addWidget(self.avatar_label)
        
        # Username with color
        username_label = QLabel(self.user.login)
        username_label.setFont(QFont("Arial", 10))
        color = self.user.background if self.user.background else "#cccccc"
        username_label.setStyleSheet(f"color: {color}; padding-left: 5px;")
        layout.addWidget(username_label, 1)
        
        # Game indicator
        if self.user.game_id:
            game_label = QLabel(f"🎮 {self.user.game_id}")
            game_label.setFont(QFont("Arial", 8))
            game_label.setStyleSheet("color: #888;")
            layout.addWidget(game_label)
        
        self.setLayout(layout)
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
            QWidget:hover {
                background-color: #2a2a2a;
            }
        """)
    
    def load_avatar(self, url):
        """Load avatar from URL"""
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                scaled = pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                                      Qt.TransformationMode.SmoothTransformation)
                self.avatar_label.setPixmap(scaled)
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
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #cccccc;
                font-size: 12px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #cccccc;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px;
            }
        """)
        
        layout = QVBoxLayout()
        
        accounts = self.account_manager.list_accounts()
        
        if accounts:
            label = QLabel("Select an account:")
            layout.addWidget(label)
            
            self.account_combo = QComboBox()
            for acc in accounts:
                self.account_combo.addItem(f"{acc['login']} (ID: {acc['user_id']})", acc)
            layout.addWidget(self.account_combo)
            
            connect_btn = QPushButton("Connect")
            connect_btn.clicked.connect(self.accept)
            layout.addWidget(connect_btn)
        else:
            label = QLabel("No accounts found.")
            layout.addWidget(label)
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def accept(self):
        self.selected_account = self.account_combo.currentData()
        super().accept()


class AddAccountDialog(QDialog):
    """Dialog for adding new account"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_id = None
        self.login = None
        self.password = None
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("Add Account")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #cccccc;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #cccccc;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("User ID:"))
        self.user_id_field = QLineEdit()
        layout.addWidget(self.user_id_field)
        
        layout.addWidget(QLabel("Login:"))
        self.login_field = QLineEdit()
        layout.addWidget(self.login_field)
        
        layout.addWidget(QLabel("Password:"))
        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_field)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def accept(self):
        self.user_id = self.user_id_field.text().strip()
        self.login = self.login_field.text().strip()
        self.password = self.password_field.text().strip()
        
        if self.user_id and self.login and self.password:
            super().accept()
        else:
            QMessageBox.warning(self, "Error", "All fields are required!")


class ChatWindow(QMainWindow):
    """Main chat window"""
    
    def __init__(self):
        super().__init__()
        self.xmpp = XMPPClient()
        self.commands = AccountCommands(self.xmpp.account_manager)
        self.signals = SignalEmitter()
        
        self.signals.message_received.connect(self.on_message)
        self.signals.presence_update.connect(self.on_presence)
        self.signals.connection_status.connect(self.on_connection_status)
        
        self.xmpp.set_message_callback(self.handle_xmpp_message)
        self.xmpp.set_presence_callback(self.handle_xmpp_presence)
        
        self.setup_ui()
        self.show_account_dialog()
    
    def setup_ui(self):
        """Setup the main UI"""
        self.setWindowTitle("KG Chat")
        self.setGeometry(100, 100, 1400, 800)
        
        # Dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QMenuBar {
                background-color: #2d2d30;
                color: #cccccc;
            }
            QMenuBar::item:selected {
                background-color: #3e3e42;
            }
            QMenu {
                background-color: #2d2d30;
                color: #cccccc;
                border: 1px solid #454545;
            }
            QMenu::item:selected {
                background-color: #0e639c;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: none;
                padding: 5px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8f;
            }
        """)
        
        # Menu bar
        menubar = self.menuBar()
        
        # Accounts menu
        accounts_menu = menubar.addMenu("Accounts")
        
        switch_action = QAction("Switch Account", self)
        switch_action.triggered.connect(self.switch_account_dialog)
        accounts_menu.addAction(switch_action)
        
        add_action = QAction("Add Account", self)
        add_action.triggered.connect(self.add_account_dialog)
        accounts_menu.addAction(add_action)
        
        remove_action = QAction("Remove Account", self)
        remove_action.triggered.connect(self.remove_account_dialog)
        accounts_menu.addAction(remove_action)
        
        accounts_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        accounts_menu.addAction(exit_action)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # === LEFT: Messages ===
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        
        self.messages_display = QTextEdit()
        self.messages_display.setReadOnly(True)
        left_layout.addWidget(self.messages_display, 1)
        
        # Input
        input_layout = QHBoxLayout()
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type message...")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field, 1)
        
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        
        left_layout.addLayout(input_layout)
        
        # === RIGHT: Users ===
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #252526;")
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)
        
        users_header = QLabel("Users")
        users_header.setStyleSheet("""
            QLabel {
                color: #888;
                font-size: 11px;
                font-weight: bold;
                padding: 10px;
                text-transform: uppercase;
            }
        """)
        right_layout.addWidget(users_header)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #252526;
            }
        """)
        
        self.user_list_widget = QWidget()
        self.user_list_layout = QVBoxLayout()
        self.user_list_layout.setSpacing(1)
        self.user_list_layout.setContentsMargins(0, 0, 0, 0)
        self.user_list_layout.addStretch()
        self.user_list_widget.setLayout(self.user_list_layout)
        self.user_list_widget.setStyleSheet("background-color: #252526;")
        
        scroll_area.setWidget(self.user_list_widget)
        right_layout.addWidget(scroll_area, 1)
        
        self.user_count_label = QLabel("Total: 0")
        self.user_count_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 10px;
                padding: 8px;
            }
        """)
        right_layout.addWidget(self.user_count_label)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        self.statusBar().showMessage("Disconnected")
        self.statusBar().setStyleSheet("background-color: #007acc; color: white; font-size: 11px;")
    
    def show_account_dialog(self):
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            self.connect_xmpp(dialog.selected_account)
        else:
            sys.exit(0)
    
    def switch_account_dialog(self):
        """Switch account"""
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            QMessageBox.information(self, "Restart Required", "Please restart the app to switch accounts.")
    
    def add_account_dialog(self):
        """Add new account"""
        dialog = AddAccountDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.xmpp.account_manager.add_account(dialog.user_id, dialog.login, dialog.password):
                QMessageBox.information(self, "Success", f"Account '{dialog.login}' added!")
            else:
                QMessageBox.warning(self, "Error", "Failed to add account!")
    
    def remove_account_dialog(self):
        """Remove account"""
        accounts = self.xmpp.account_manager.list_accounts()
        if not accounts:
            QMessageBox.information(self, "No Accounts", "No accounts to remove.")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Remove Account")
        dialog.setMinimumWidth(300)
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Select account to remove:"))
        
        combo = QComboBox()
        for acc in accounts:
            combo.addItem(f"{acc['login']}", acc)
        layout.addWidget(combo)
        
        btn_layout = QHBoxLayout()
        remove_btn = QPushButton("Remove")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        
        remove_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            acc = combo.currentData()
            if self.xmpp.account_manager.remove_account(acc['login']):
                QMessageBox.information(self, "Success", f"Account '{acc['login']}' removed!")
    
    def connect_xmpp(self, account):
        self.statusBar().showMessage("Connecting...")
        
        def connect_thread():
            try:
                if self.xmpp.connect(account):
                    rooms = self.xmpp.account_manager.get_rooms()
                    for room in rooms:
                        if room.get('auto_join'):
                            self.xmpp.join_room(room['jid'])
                    
                    self.signals.connection_status.emit(True, f"Connected as {account['login']}")
                    self.xmpp.listen()
                else:
                    self.signals.connection_status.emit(False, "Connection failed")
            except Exception as e:
                self.signals.connection_status.emit(False, f"Error: {e}")
        
        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
    
    def on_connection_status(self, success, message):
        if success:
            self.statusBar().showMessage(message)
            self.statusBar().setStyleSheet("background-color: #007acc; color: white;")
        else:
            self.statusBar().showMessage(message)
            self.statusBar().setStyleSheet("background-color: #ce3939; color: white;")
    
    def handle_xmpp_message(self, message):
        active_account = self.xmpp.account_manager.get_active_account()
        if active_account and message.login == active_account['login']:
            return
        
        self.signals.message_received.emit(message)
    
    def handle_xmpp_presence(self, presence):
        self.signals.presence_update.emit(presence)
    
    def on_message(self, message):
        """Display message with colored username"""
        sender = message.login if message.login else "Unknown"
        timestamp = message.timestamp.strftime("%H:%M:%S") if message.timestamp else ""
        color = message.background if message.background else "#cccccc"
        
        self.add_message(sender, message.body, timestamp, color)
    
    def on_presence(self, presence):
        """Silently update user list - no join/leave spam"""
        self.update_user_list()
    
    def add_message(self, sender, text, timestamp="", color="#cccccc"):
        """Add message with colored username"""
        cursor = self.messages_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Escape HTML
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        html = f"""
        <div style="margin: 2px 0; font-family: Consolas, monospace;">
            <span style="color: #888; font-size: 11px;">{timestamp}</span>
            <span style="color: {color}; font-weight: bold; margin-left: 10px;">{sender}</span>
            <span style="color: #cccccc; margin-left: 5px;">{text}</span>
        </div>
        """
        
        cursor.insertHtml(html)
        self.messages_display.setTextCursor(cursor)
        self.messages_display.ensureCursorVisible()
    
    def update_user_list(self):
        """Update user list"""
        while self.user_list_layout.count() > 1:
            item = self.user_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        users = self.xmpp.user_list.get_online()
        for user in sorted(users, key=lambda u: u.login.lower()):
            user_widget = UserWidget(user)
            self.user_list_layout.insertWidget(self.user_list_layout.count() - 1, user_widget)
        
        self.user_count_label.setText(f"Total: {len(users)}")
    
    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        
        if self.xmpp.send_message(text):
            timestamp = datetime.now().strftime("%H:%M:%S")
            active = self.xmpp.account_manager.get_active_account()
            color = "#fe3272"  # Your color
            self.add_message(active['login'], text, timestamp, color)
            self.input_field.clear()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = ChatWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
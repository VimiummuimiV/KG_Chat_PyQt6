"""
XMPP Chat GUI Application
Desktop chat client with PyQt6 - Klavogonki style
"""
import sys
import threading
import requests
import html # FIX: For escaping in messages
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextBrowser, QLineEdit, QPushButton, QLabel, QSplitter, # FIX: Changed QTextEdit to QTextBrowser
    QScrollArea, QDialog, QComboBox, QMessageBox, QMenuBar, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QUrl # FIX: Added QUrl
from PyQt6.QtGui import QPixmap, QFont, QTextCursor, QAction, QDesktopServices, QFontMetrics # FIX: Added QDesktopServices, QFontMetrics
from xmpp import XMPPClient
from accounts import AccountManager
from commands import AccountCommands
class SignalEmitter(QObject):
    """Signal emitter for thread-safe GUI updates"""
    message_received = pyqtSignal(object)
    presence_update = pyqtSignal(object)
    connection_status = pyqtSignal(bool, str)
    avatar_loaded = pyqtSignal(str, QPixmap) # JID, Pixmap
class UserWidget(QWidget):
    """Widget for displaying a single user"""
  
    def __init__(self, user, signal_emitter, parent=None):
        super().__init__(parent)
        self.user = user
        self.signal_emitter = signal_emitter
        self.zoom_factor = float(self.window().zoom_level) / 100.0 if self.window() else 1.0
        self.setup_ui()
      
        # Connect avatar loading signal
        self.signal_emitter.avatar_loaded.connect(self.on_avatar_loaded)
  
    def setup_ui(self):
        layout = QHBoxLayout()
        f = self.zoom_factor
        layout.setContentsMargins(int(8 * f), int(4 * f), int(8 * f), int(4 * f))
      
        # Avatar
        avatar_size = int(32 * f)
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(avatar_size, avatar_size)
        self.avatar_label.setStyleSheet(f"""
            QLabel {{
                border: 1px solid #444;
                border-radius: 3px;
                background-color: #2a2a2a;
            }}
        """)
      
        # Default avatar
        self.avatar_label.setText("👤")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setStyleSheet(f"""
            QLabel {{
                border: 1px solid #444;
                border-radius: 3px;
                background-color: #2a2a2a;
                font-size: {int(16 * f)}px;
            }}
        """)
      
        # Load avatar if available
        if self.user.avatar:
            self.load_avatar(self.user.get_avatar_url())
      
        layout.addWidget(self.avatar_label)
      
        # Username with color
        username_label = QLabel(self.user.login)
        username_label.setFont(QFont("Arial", int(10 * f)))
        color = self.user.background if self.user.background else "#cccccc"
        username_label.setStyleSheet(f"color: {color}; padding-left: {int(5 * f)}px;")
        layout.addWidget(username_label, 1)
      
        # Game indicator
        game_label = None
        if self.user.game_id:
            game_label = QLabel(f"🎮 {self.user.game_id}")
            game_label.setFont(QFont("Arial", int(8 * f)))
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
      
        # FIX: Use QFontMetrics for exact minimum width calculation
        fm = QFontMetrics(username_label.font())
        username_width = fm.horizontalAdvance(self.user.login) + int(5 * f) # padding-left
      
        game_width = 0
        if game_label:
            game_fm = QFontMetrics(game_label.font())
            game_width = game_fm.horizontalAdvance(game_label.text()) + int(5 * f) # spacing
       
        min_width = int(8 * f) + avatar_size + int(5 * f) + username_width + game_width + int(8 * f) # left margin + avatar + padding + username + game + right margin
        self.setMinimumWidth(max(int(200 * f), min_width))
  
    def load_avatar(self, url):
        """Load avatar from URL in background thread"""
        if not url:
            return
      
        # Full URL is already provided by get_avatar_url
        full_url = url
      
        window = self.window()
        if full_url in window.avatar_cache:
            self.avatar_label.setPixmap(window.avatar_cache[full_url])
            self.avatar_label.setText("") # Clear emoji
            return
      
        def load_in_thread():
            try:
                print(f"🔄 Loading avatar: {full_url}")
                response = requests.get(full_url, timeout=5)
              
                if response.status_code == 200:
                    from PyQt6.QtCore import QByteArray
                    pixmap = QPixmap()
                    byte_array = QByteArray(response.content)
                  
                    if pixmap.loadFromData(byte_array):
                        # Crop to square and scale
                        size = min(pixmap.width(), pixmap.height())
                        if size > 0:
                            x = (pixmap.width() - size) // 2
                            y = (pixmap.height() - size) // 2
                            square = pixmap.copy(x, y, size, size)
                            avatar_size = self.avatar_label.width()  # Use current size
                            scaled = square.scaled(avatar_size, avatar_size, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
                            # Emit signal to update UI in main thread
                            self.signal_emitter.avatar_loaded.emit(self.user.jid, scaled)
                            window.avatar_cache[full_url] = scaled
                            print(f"✓ Avatar loaded for {self.user.login}")
                        else:
                            print(f"✗ Invalid dimensions for {self.user.login}")
                    else:
                        print(f"✗ Failed to load image for {self.user.login}")
                else:
                    print(f"✗ HTTP {response.status_code} for {self.user.login}")
            except Exception as e:
                print(f"✗ Avatar error for {self.user.login}: {e}")
      
        thread = threading.Thread(target=load_in_thread, daemon=True)
        thread.start()
  
    def on_avatar_loaded(self, jid, pixmap):
        """Handle avatar loaded in main thread"""
        if jid == self.user.jid:
            self.avatar_label.setPixmap(pixmap)
            self.avatar_label.setText("") # Clear emoji
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
        self.avatar_cache = {}
      
        self.zoom_level = 100 # Default zoom level
      
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
            QTextBrowser {
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
      
        # View menu
        view_menu = menubar.addMenu("View")
      
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(zoom_in_action)
      
        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(zoom_out_action)
      
        reset_zoom_action = QAction("Reset Zoom", self)
        reset_zoom_action.setShortcut("Ctrl+0")
        reset_zoom_action.triggered.connect(self.reset_zoom)
        view_menu.addAction(reset_zoom_action)
      
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
      
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
      
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
      
        # === LEFT: Messages ===
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
      
        self.messages_display = QTextBrowser() # FIX: Changed to QTextBrowser
        # Removed setReadOnly(True) as QTextBrowser is read-only by default
        self.messages_display.setOpenExternalLinks(False) # FIX: Changed to setOpenExternalLinks(False)
        self.messages_display.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction) # FIX: Enable links and selection
        self.messages_display.anchorClicked.connect(self.handle_link_clicked) # FIX: Changed to anchorClicked
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
        self.right_panel = QWidget()
        self.right_panel.setStyleSheet("background-color: #252526;")
        right_layout = QVBoxLayout()
        self.right_panel.setLayout(right_layout)
      
        self.users_header = QLabel("Users")
        self.users_header.setStyleSheet("""
            QLabel {
                color: #888;
                font-size: 11px;
                font-weight: bold;
                padding: 10px;
                text-transform: uppercase;
            }
        """)
        right_layout.addWidget(self.users_header)
      
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
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
      
        self.scroll_area.setWidget(self.user_list_widget)
        right_layout.addWidget(self.scroll_area, 1)
      
        self.user_count_label = QLabel("Total: 0")
        self.user_count_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 10px;
                padding: 8px;
            }
        """)
        right_layout.addWidget(self.user_count_label)
      
        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
      
        main_layout.addWidget(self.splitter)
      
        # Status bar with zoom slider
        status_widget = QWidget()
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(5, 2, 5, 2)
        status_widget.setLayout(status_layout)
      
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: white; font-size: 11px;")
        status_layout.addWidget(self.status_label, 1)
      
        # Zoom controls
        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet("color: white; font-size: 11px; margin-right: 5px;")
        status_layout.addWidget(zoom_label)
      
        from PyQt6.QtWidgets import QSlider
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(50)
        self.zoom_slider.setMaximum(200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 4px;
                background: #333;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0e639c;
                border: 1px solid #0e639c;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #1177bb;
            }
        """)
        status_layout.addWidget(self.zoom_slider)
      
        self.zoom_percent_label = QLabel("100%")
        self.zoom_percent_label.setStyleSheet("color: white; font-size: 11px; margin-left: 5px; min-width: 40px;")
        status_layout.addWidget(self.zoom_percent_label)
      
        self.statusBar().addPermanentWidget(status_widget, 1)
        self.statusBar().setStyleSheet("background-color: #007acc;")
  
    # FIX: Updated handler for anchorClicked (receives QUrl)
    def handle_link_clicked(self, url: QUrl):
        link = url.toString()
        if link.startswith("user:"):
            username = link[5:]
            self.input_field.setText(f"{username}, ")
            self.input_field.setFocus()
        else:
            QDesktopServices.openUrl(url)
  
    def show_account_dialog(self):
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            self.connect_xmpp(dialog.selected_account)
        else:
            self.status_label.setText("Disconnected")
            sys.exit(0)
  
    def switch_account_dialog(self):
        """Switch account"""
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            self.disconnect_xmpp()
            self.connect_xmpp(dialog.selected_account)
  
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
        self.status_label.setText("Connecting...")
      
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
  
    def disconnect_xmpp(self):
        self.xmpp.disconnect()
        self.messages_display.clear()
        while self.user_list_layout.count() > 1:
            item = self.user_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.xmpp.user_list.clear()
        self.user_count_label.setText("Total: 0")
        self.status_label.setText("Disconnected")
        self.statusBar().setStyleSheet("background-color: #ce3939;")
  
    def on_connection_status(self, success, message):
        if success:
            self.status_label.setText(message)
            self.statusBar().setStyleSheet("background-color: #007acc;")
            # Force initial userlist update
            self.update_user_list()
        else:
            self.status_label.setText(message)
            self.statusBar().setStyleSheet("background-color: #ce3939;")
  
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
        # Update immediately
        self.update_user_list()
        # Also schedule another update after 100ms to catch any delayed updates
        QTimer.singleShot(100, self.update_user_list)
  
    def add_message(self, sender, text, timestamp="", color="#cccccc"):
        """Add message with colored username - each on new line"""
        cursor = self.messages_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
      
        # FIX: Use html.escape for safety (text already partially escaped, but consistent)
        sender_html = html.escape(sender)
        text = html.escape(text)
      
        # Insert newline before message for proper separation
        cursor.insertText("\n")
      
        # Insert timestamp
        cursor.insertHtml(f'<span style="color: #666; font-size: 11px;">{timestamp}</span> ')
      
        # FIX: Insert username as clickable link
        cursor.insertHtml(f'<a href="user:{sender_html}" style="color: {color}; font-weight: bold; text-decoration: none;">{sender_html}</a> ')
      
        # Insert message text
        cursor.insertHtml(f'<span style="color: #ccc;">{text}</span>')
      
        self.messages_display.setTextCursor(cursor)
        self.messages_display.ensureCursorVisible()
  
    def update_user_list(self):
        """Update user list"""
        # Clear existing widgets
        while self.user_list_layout.count() > 1:
            item = self.user_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
      
        users = self.xmpp.user_list.get_online()
        print(f"🔍 Updating user list: {len(users)} users online")
      
        max_width = 0
        for user in sorted(users, key=lambda u: u.login.lower()):
            print(f" 👤 Adding user: {user.login} (avatar: {user.avatar})")
            user_widget = UserWidget(user, self.signals, self)
            self.user_list_layout.insertWidget(self.user_list_layout.count() - 1, user_widget)
            # Track maximum width needed
            max_width = max(max_width, user_widget.minimumWidth())
      
        # Set minimum width for entire user list widget
        self.user_list_widget.setMinimumWidth(max_width)
      
        self.user_count_label.setText(f"Total: {len(users)}")
        print(f"✓ User list updated")
        
        # Set right panel width to fit content
        adj_width = max_width + 20
        self.right_panel.setMinimumWidth(adj_width)
        self.right_panel.setMaximumWidth(adj_width)
  
    def zoom_in(self):
        """Increase zoom level"""
        self.zoom_level = min(200, self.zoom_level + 10)
        self.apply_zoom()
  
    def zoom_out(self):
        """Decrease zoom level"""
        self.zoom_level = max(50, self.zoom_level - 10)
        self.apply_zoom()
  
    def reset_zoom(self):
        """Reset zoom to 100%"""
        self.zoom_level = 100
        self.apply_zoom()
  
    def on_zoom_slider_changed(self, value):
        """Handle zoom slider change"""
        self.zoom_level = value
        self.apply_zoom()
  
    def apply_zoom(self):
        """Apply zoom level to interface"""
        # Update slider if changed via keyboard
        self.zoom_slider.setValue(self.zoom_level)
        self.zoom_percent_label.setText(f"{self.zoom_level}%")
      
        # Calculate font size based on zoom
        f = self.zoom_level / 100.0
        base_font_size = 13
        scaled_font_size = int(base_font_size * f)
      
        # Apply to messages display
        font = self.messages_display.font()
        font.setPointSize(scaled_font_size)
        self.messages_display.setFont(font)
      
        # Apply to input field
        input_font = self.input_field.font()
        input_font.setPointSize(scaled_font_size)
        self.input_field.setFont(input_font)
        
        # Update headers and labels
        header_font_size = int(11 * f)
        self.users_header.setStyleSheet(f"""
            QLabel {{
                color: #888;
                font-size: {header_font_size}px;
                font-weight: bold;
                padding: {int(10 * f)}px;
                text-transform: uppercase;
            }}
        """)
        
        count_font_size = int(10 * f)
        self.user_count_label.setStyleSheet(f"""
            QLabel {{
                color: #666;
                font-size: {count_font_size}px;
                padding: {int(8 * f)}px;
            }}
        """)
        
        # Rebuild user list to apply zoom
        self.update_user_list()
  
    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
      
        if self.xmpp.send_message(text):
            timestamp = datetime.now().strftime("%H:%M:%S")
            active = self.xmpp.account_manager.get_active_account()
            color = "#fe3272" # Your color
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
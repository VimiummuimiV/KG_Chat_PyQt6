"""
XMPP Chat GUI Application
Desktop chat client with PyQt6 - Klavogonki style
"""
import sys
import threading
import requests
import html
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextBrowser, QLineEdit, QPushButton, QLabel, QSplitter,
    QScrollArea, QDialog, QComboBox, QMessageBox, QMenuBar, QMenu, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QUrl, QByteArray
from PyQt6.QtGui import (
    QPixmap, QFont, QTextCursor, QAction, QDesktopServices,
    QFontMetrics, QPainter, QBrush, QColor
)
from xmpp import XMPPClient
from accounts import AccountManager
from commands import AccountCommands


class SignalEmitter(QObject):
    message_received = pyqtSignal(object)
    presence_update = pyqtSignal(object)
    connection_status = pyqtSignal(bool, str)
    avatar_loaded = pyqtSignal(str, QPixmap)  # JID, Pixmap


class UserWidget(QWidget):
    def __init__(self, user, signal_emitter, parent=None):
        super().__init__(parent)
        self.user = user
        self.signal_emitter = signal_emitter
        self.zoom_factor = self.window().zoom_level / 100.0 if self.window() else 1.0
        self.setup_ui()
        self.signal_emitter.avatar_loaded.connect(self.on_avatar_loaded)

        if self.user.avatar:
            self.load_avatar(self.user.get_avatar_url())

    def setup_ui(self):
        f = self.zoom_factor
        layout = QHBoxLayout()
        layout.setContentsMargins(int(8 * f), int(4 * f), int(8 * f), int(4 * f))

        avatar_size = int(32 * f)
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(avatar_size, avatar_size)
        self.avatar_label.setStyleSheet(f"""
            QLabel {{
                border: 1px solid #444;
                border-radius: {int(3 * f)}px;
                background-color: #2a2a2a;
            }}
        """)

        # Default avatar
        self.avatar_label.setText("👤")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFont(QFont("Arial", int(16 * f)))

        layout.addWidget(self.avatar_label)

        username_label = QLabel(self.user.login)
        username_label.setFont(QFont("Arial", int(10 * f)))
        color = self.user.background if self.user.background else "#cccccc"
        username_label.setStyleSheet(f"color: {color}; padding-left: {int(5 * f)}px;")
        layout.addWidget(username_label, 1)

        game_label = None
        if self.user.game_id:
            game_label = QLabel(f"🎮 {self.user.game_id}")
            game_label.setFont(QFont("Arial", int(8 * f)))
            game_label.setStyleSheet("color: #888;")
            layout.addWidget(game_label)

        self.setLayout(layout)
        self.setStyleSheet("""
            QWidget { background-color: transparent; }
            QWidget:hover { background-color: #2a2a2a; }
        """)

        fm = QFontMetrics(username_label.font())
        username_width = fm.horizontalAdvance(self.user.login) + int(5 * f)

        game_width = 0
        if game_label:
            game_fm = QFontMetrics(game_label.font())
            game_width = game_fm.horizontalAdvance(game_label.text()) + int(5 * f)

        min_width = int(8 * f) + avatar_size + int(5 * f) + username_width + game_width + int(8 * f)
        self.setMinimumWidth(max(int(200 * f), min_width))

    def load_avatar(self, url):
        if not url:
            return

        full_url = url
        window = self.window()
        if full_url in window.avatar_cache:
            self.apply_avatar(window.avatar_cache[full_url])
            return

        def load_in_thread():
            try:
                response = requests.get(full_url, timeout=5)
                if response.status_code != 200:
                    return

                pixmap = QPixmap()
                if pixmap.loadFromData(QByteArray(response.content)):
                    size = min(pixmap.width(), pixmap.height())
                    if size > 0:
                        x = (pixmap.width() - size) // 2
                        y = (pixmap.height() - size) // 2
                        square = pixmap.copy(x, y, size, size)
                        avatar_size = int(32 * self.zoom_factor)
                        scaled = square.scaled(avatar_size, avatar_size,
                                               Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                               Qt.TransformationMode.SmoothTransformation)
                        cropped = scaled.copy((scaled.width() - avatar_size) // 2,
                                              (scaled.height() - avatar_size) // 2,
                                              avatar_size, avatar_size)

                        radius = int(3 * self.zoom_factor)
                        mask = QPixmap(avatar_size, avatar_size)
                        mask.fill(Qt.GlobalColor.transparent)
                        painter = QPainter(mask)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                        painter.setBrush(QBrush(QColor("white")))
                        painter.drawRoundedRect(0, 0, avatar_size, avatar_size, radius, radius)
                        painter.end()
                        cropped.setMask(mask.mask())

                        self.signal_emitter.avatar_loaded.emit(self.user.jid, cropped)
                        window.avatar_cache[full_url] = cropped
            except Exception:
                pass  # Silent fail

        threading.Thread(target=load_in_thread, daemon=True).start()

    def apply_avatar(self, pixmap):
        self.avatar_label.setPixmap(pixmap)
        self.avatar_label.setText("")
        self.avatar_label.setScaledContents(True)  # To ensure it fills the container

    def on_avatar_loaded(self, jid, pixmap):
        if jid == self.user.jid:
            self.apply_avatar(pixmap)


class AccountDialog(QDialog):
    def __init__(self, account_manager, parent=None):
        super().__init__(parent)
        self.account_manager = account_manager
        self.selected_account = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Select Account")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #cccccc; font-size: 12px; }
            QPushButton { background-color: #0e639c; color: white; border: none; border-radius: 3px; padding: 8px 15px; font-size: 12px; }
            QPushButton:hover { background-color: #1177bb; }
            QComboBox { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555; border-radius: 3px; padding: 5px; }
        """)

        layout = QVBoxLayout()
        accounts = self.account_manager.list_accounts()

        if accounts:
            layout.addWidget(QLabel("Select an account:"))
            self.account_combo = QComboBox()
            for acc in accounts:
                self.account_combo.addItem(f"{acc['login']} (ID: {acc['user_id']})", acc)
            layout.addWidget(self.account_combo)
            connect_btn = QPushButton("Connect")
            connect_btn.clicked.connect(self.accept)
            layout.addWidget(connect_btn)
        else:
            layout.addWidget(QLabel("No accounts found."))
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)

        self.setLayout(layout)

    def accept(self):
        self.selected_account = self.account_combo.currentData()
        super().accept()


class AddAccountDialog(QDialog):
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
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #cccccc; font-size: 12px; }
            QLineEdit { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555; border-radius: 3px; padding: 8px; font-size: 12px; }
            QPushButton { background-color: #0e639c; color: white; border: none; border-radius: 3px; padding: 8px 15px; font-size: 12px; }
            QPushButton:hover { background-color: #1177bb; }
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
    def __init__(self):
        super().__init__()
        self.xmpp = XMPPClient()
        self.commands = AccountCommands(self.xmpp.account_manager)
        self.signals = SignalEmitter()
        self.avatar_cache = {}
        self.zoom_level = 100
        self.previous_users = set()  # For join/leave detection

        self.signals.message_received.connect(self.on_message)
        self.signals.presence_update.connect(self.on_presence)
        self.signals.connection_status.connect(self.on_connection_status)

        self.xmpp.set_message_callback(self.handle_xmpp_message)
        self.xmpp.set_presence_callback(self.handle_xmpp_presence)

        self.setup_ui()
        self.show_account_dialog()

    def setup_ui(self):
        self.setWindowTitle("KG Chat")
        self.setGeometry(100, 100, 1400, 800)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QMenuBar { background-color: #2d2d30; color: #cccccc; }
            QMenuBar::item:selected { background-color: #3e3e42; }
            QMenu { background-color: #2d2d30; color: #cccccc; border: 1px solid #454545; }
            QMenu::item:selected { background-color: #0e639c; }
            QTextBrowser { background-color: #1e1e1e; color: #cccccc; border: none; padding: 5px; font-family: 'Consolas', 'Monaco', monospace; }
            QLineEdit { background-color: #252526; color: #cccccc; border: 1px solid #3e3e42; border-radius: 3px; padding: 8px; }
            QPushButton { background-color: #0e639c; color: white; border: none; border-radius: 3px; padding: 8px 20px; font-weight: bold; }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:pressed { background-color: #0d5a8f; }
        """)

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

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - chat
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.messages_display = QTextBrowser()
        self.messages_display.setOpenExternalLinks(False)
        self.messages_display.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.messages_display.anchorClicked.connect(self.handle_link_clicked)
        left_layout.addWidget(self.messages_display, 1)

        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type message...")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field, 1)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        left_layout.addLayout(input_layout)

        # Right panel - users
        self.right_panel = QWidget()
        self.right_panel.setStyleSheet("background-color: #252526;")
        right_layout = QVBoxLayout(self.right_panel)

        self.users_header = QLabel("Users")
        self.users_header.setStyleSheet("color: #888; font-weight: bold; padding: 10px; text-transform: uppercase;")
        right_layout.addWidget(self.users_header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("border: none; background-color: #252526;")

        self.user_list_widget = QWidget()
        self.user_list_layout = QVBoxLayout(self.user_list_widget)
        self.user_list_layout.setSpacing(1)
        self.user_list_layout.setContentsMargins(0, 0, 0, 0)
        self.user_list_layout.addStretch()
        self.user_list_widget.setStyleSheet("background-color: #252526;")

        self.scroll_area.setWidget(self.user_list_widget)
        right_layout.addWidget(self.scroll_area, 1)

        self.user_count_label = QLabel("Total: 0")
        self.user_count_label.setStyleSheet("color: #666; padding: 8px;")
        right_layout.addWidget(self.user_count_label)

        self.splitter.addWidget(left)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self.splitter)

        # Status bar with zoom
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(5, 2, 5, 2)

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: white;")
        status_layout.addWidget(self.status_label, 1)

        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet("color: white; margin-right: 5px;")
        status_layout.addWidget(zoom_label)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(50, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #555; height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #0e639c; border: 1px solid #0e639c; width: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { background: #1177bb; }
        """)
        status_layout.addWidget(self.zoom_slider)

        self.zoom_percent_label = QLabel("100%")
        self.zoom_percent_label.setStyleSheet("color: white; margin-left: 5px;")
        status_layout.addWidget(self.zoom_percent_label)

        self.statusBar().addPermanentWidget(status_widget)
        self.statusBar().setStyleSheet("background-color: #007acc;")

    def handle_link_clicked(self, url: QUrl):
        link = url.toString()
        if link.startswith("user:"):
            username = link[5:]
            current = self.input_field.text().rstrip()
            self.input_field.setText(f"{current} {username}, " if current else f"{username}, ")
            self.input_field.setFocus()
        else:
            QDesktopServices.openUrl(url)

    def show_account_dialog(self):
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            self.connect_xmpp(dialog.selected_account)
        else:
            sys.exit(0)

    def switch_account_dialog(self):
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            self.disconnect_xmpp()
            self.connect_xmpp(dialog.selected_account)

    def add_account_dialog(self):
        dialog = AddAccountDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            success = self.xmpp.account_manager.add_account(dialog.user_id, dialog.login, dialog.password)
            QMessageBox.information(self, "Success" if success else "Error",
                                    f"Account '{dialog.login}' {'added' if success else 'failed'}!")

    def remove_account_dialog(self):
        accounts = self.xmpp.account_manager.list_accounts()
        if not accounts:
            QMessageBox.information(self, "Info", "No accounts to remove.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Remove Account")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select account to remove:"))
        combo = QComboBox()
        for acc in accounts:
            combo.addItem(acc['login'], acc)
        layout.addWidget(combo)

        btn_layout = QHBoxLayout()
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(remove_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            acc = combo.currentData()
            if self.xmpp.account_manager.remove_account(acc['login']):
                QMessageBox.information(self, "Success", f"Account '{acc['login']}' removed!")

    def connect_xmpp(self, account):
        self.status_label.setText("Connecting...")
        def thread_func():
            try:
                if self.xmpp.connect(account):
                    for room in self.xmpp.account_manager.get_rooms():
                        if room.get('auto_join'):
                            self.xmpp.join_room(room['jid'])
                    self.signals.connection_status.emit(True, f"Connected as {account['login']}")
                    self.xmpp.listen()
                else:
                    self.signals.connection_status.emit(False, "Connection failed")
            except Exception as e:
                self.signals.connection_status.emit(False, str(e))
        threading.Thread(target=thread_func, daemon=True).start()

    def disconnect_xmpp(self):
        self.xmpp.disconnect()
        self.messages_display.clear()
        while self.user_list_layout.count() > 1:
            item = self.user_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.xmpp.user_list.clear()
        self.previous_users.clear()
        self.user_count_label.setText("Total: 0")
        self.status_label.setText("Disconnected")
        self.statusBar().setStyleSheet("background-color: #ce3939;")

    def on_connection_status(self, success, msg):
        self.status_label.setText(msg)
        self.statusBar().setStyleSheet("background-color: #007acc;" if success else "#ce3939;")
        if success:
            self.previous_users.clear()
            self.update_user_list()

    def handle_xmpp_message(self, message):
        active = self.xmpp.account_manager.get_active_account()
        if active and message.login == active['login']:
            return
        self.signals.message_received.emit(message)

    def handle_xmpp_presence(self, presence):
        self.signals.presence_update.emit(presence)

    def on_message(self, message):
        sender = message.login or "Unknown"
        ts = message.timestamp.strftime("%H:%M:%S") if message.timestamp else ""
        color = message.background or "#cccccc"
        self.add_message(sender, message.body, ts, color)

    def on_presence(self, presence):
        self.update_user_list()
        QTimer.singleShot(100, self.update_user_list)

    def add_message(self, sender, text, timestamp="", color="#cccccc"):
        cursor = self.messages_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("\n")

        sender_html = html.escape(sender)
        text_html = html.escape(text)

        if timestamp:
            cursor.insertHtml(f'<span style="color: #666;">{timestamp}</span> ')

        cursor.insertHtml(f'<a href="user:{sender_html}" style="color: {color}; font-weight: bold; text-decoration: none;">{sender_html}</a> ')
        cursor.insertHtml(f'<span style="color: #ccc;">{text_html}</span>')

        self.messages_display.setTextCursor(cursor)
        self.messages_display.ensureCursorVisible()

    def update_user_list(self):
        current_logins = {u.login for u in self.xmpp.user_list.get_online()}

        joined = current_logins - self.previous_users
        left = self.previous_users - current_logins

        for login in joined:
            print(f"Joined: {login}")
        for login in left:
            print(f"Left: {login}")

        self.previous_users = current_logins.copy()

        while self.user_list_layout.count() > 1:
            item = self.user_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        users = sorted(self.xmpp.user_list.get_online(), key=lambda u: u.login.lower())
        max_width = 0
        for user in users:
            widget = UserWidget(user, self.signals, self)
            self.user_list_layout.insertWidget(self.user_list_layout.count() - 1, widget)
            max_width = max(max_width, widget.minimumWidth())

        self.user_list_widget.setMinimumWidth(max_width + 20)
        self.right_panel.setMinimumWidth(max_width + 40)
        self.right_panel.setMaximumWidth(max_width + 40)

        self.user_count_label.setText(f"Total: {len(users)}")

    def zoom_in(self):
        self.zoom_level = min(200, self.zoom_level + 10)
        self.apply_zoom()

    def zoom_out(self):
        self.zoom_level = max(50, self.zoom_level - 10)
        self.apply_zoom()

    def reset_zoom(self):
        self.zoom_level = 100
        self.apply_zoom()

    def on_zoom_slider_changed(self, value):
        self.zoom_level = value
        self.apply_zoom()

    def apply_zoom(self):
        f = self.zoom_level / 100.0
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(self.zoom_level)
        self.zoom_slider.blockSignals(False)
        self.zoom_percent_label.setText(f"{self.zoom_level}%")

        # Messages font (including HTML content)
        base_size = 13
        scaled_size = int(base_size * f)
        font = QFont("Consolas", scaled_size)
        self.messages_display.document().setDefaultFont(font)
        self.messages_display.setFont(font)

        # Input field
        self.input_field.setFont(QFont("", scaled_size))

        # Headers
        self.users_header.setStyleSheet(f"color: #888; font-size: {int(11 * f)}px; font-weight: bold; padding: {int(10 * f)}px; text-transform: uppercase;")
        self.user_count_label.setStyleSheet(f"color: #666; font-size: {int(10 * f)}px; padding: {int(8 * f)}px;")

        # Rebuild user list with new zoom
        self.update_user_list()

    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        if self.xmpp.send_message(text):
            ts = datetime.now().strftime("%H:%M:%S")
            active = self.xmpp.account_manager.get_active_account()
            self.add_message(active['login'], text, ts, "#fe3272")
            self.input_field.clear()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = ChatWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
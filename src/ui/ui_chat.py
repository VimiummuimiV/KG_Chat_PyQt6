import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from helpers.config import Config
from helpers.create import create_icon_button


class ChatWindow(QWidget):
    def __init__(self, account=None):
        super().__init__()
        
        self.account = account
        
        # Paths
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.icons_path = Path(__file__).parent.parent / "icons"
        
        # Load configuration
        self.config = Config(self.config_path)

        # Initialize UI
        self.initializeUI()
    
    def set_account(self, account):
        self.account = account
        if account:
            self.setWindowTitle(f"Chat - {account['login']}")

    def toggle_user_list(self):
        visible = not self.user_list.isVisible()
        self.user_list.setVisible(visible)
        self.config.set("ui", "userlist_visible", value=visible)

    def initializeUI(self):
        # Load all config values
        font_family = self.config.get("ui", "font_family")
        font_size = self.config.get("ui", "font_size")
        userlist_visible = self.config.get("ui", "userlist_visible")
        
        # Window setup
        window_title = f"Chat - {self.account['login']}" if self.account else "Chat"
        self.setWindowTitle(window_title)
        self.resize(1500, 800)
        app_font = QFont(font_family, font_size)
        self.setFont(app_font)

        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # Left layout: messages + input
        left_layout = QVBoxLayout()
        main_layout.addLayout(left_layout, stretch=3)

        # Messages
        self.messages_area = QListWidget()
        self.messages_area.setFont(app_font)
        left_layout.addWidget(self.messages_area, stretch=1)

        # Input
        input_layout = QHBoxLayout()
        left_layout.addLayout(input_layout)

        self.input_field = QLineEdit()
        self.input_field.setFont(app_font)
        self.input_field.setFixedHeight(48)
        self.input_field.setStyleSheet("padding: 0 10px;")
        input_layout.addWidget(self.input_field, stretch=1)

        # Send message button
        self.send_button = create_icon_button(self.icons_path, "send.svg", tooltip="Send Message")
        input_layout.addWidget(self.send_button)

        # Toggle user list button
        self.toggle_userlist_button = create_icon_button(self.icons_path, "user.svg", tooltip="Toggle User List")
        input_layout.addWidget(self.toggle_userlist_button)

        # Right layout: user list
        self.user_list = QListWidget()
        self.user_list.setFont(app_font)
        main_layout.addWidget(self.user_list, stretch=1)
        
        self.user_list.setVisible(userlist_visible)

        # Signals
        self.toggle_userlist_button.clicked.connect(self.toggle_user_list)
        
        self.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatWindow()
    sys.exit(app.exec())
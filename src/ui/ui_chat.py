import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget
)
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, QSize

from helpers.config import Config
from helpers.create import create_icon_button, update_icon_button
from themes.theme import ThemeManager


class ChatWindow(QWidget):
    def __init__(self, account=None):
        super().__init__()
        
        self.account = account
        
        # Paths
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.icons_path = Path(__file__).parent.parent / "icons"
        
        # Load configuration
        self.config = Config(self.config_path)
        
        # Initialize theme manager
        self.theme_manager = ThemeManager(self.config)
        self.theme_manager.apply_theme()

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
    
    def toggle_theme(self):
        """Toggle between dark and light theme"""
        new_theme = self.theme_manager.toggle_theme()
        is_dark = self.theme_manager.is_dark()
        
        # Update ALL icon buttons with proper colorization for new theme
        if is_dark:
            update_icon_button(self.theme_button, self.icons_path, "sun.svg", "Switch to Light Mode", is_dark_theme=is_dark)
        else:
            update_icon_button(self.theme_button, self.icons_path, "moon.svg", "Switch to Dark Mode", is_dark_theme=is_dark)
        
        # Re-colorize other buttons for the new theme
        update_icon_button(self.send_button, self.icons_path, "send.svg", "Send Message", is_dark_theme=is_dark)
        update_icon_button(self.toggle_userlist_button, self.icons_path, "user.svg", "Toggle User List", is_dark_theme=is_dark)

    def initializeUI(self):
        # Load all config values
        font_family = self.config.get("ui", "font_family")
        font_size = self.config.get("ui", "font_size")
        userlist_visible = self.config.get("ui", "userlist_visible")
        
        # Window setup
        window_title = f"Chat - {self.account['login']}" if self.account else "Chat"
        self.setWindowTitle(window_title)
        self.resize(1500, 800)

        # Font from config
        app_font = QFont(font_family, font_size)
        self.setFont(app_font)

        # Main layout
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
        is_dark = self.theme_manager.is_dark()
        self.send_button = create_icon_button(self.icons_path, "send.svg", tooltip="Send Message", is_dark_theme=is_dark)
        input_layout.addWidget(self.send_button)

        # Theme toggle button
        theme_icon = "sun.svg" if is_dark else "moon.svg"
        theme_tooltip = "Switch to Light Mode" if is_dark else "Switch to Dark Mode"
        self.theme_button = create_icon_button(self.icons_path, theme_icon, tooltip=theme_tooltip, is_dark_theme=is_dark)
        self.theme_button.clicked.connect(self.toggle_theme)
        input_layout.addWidget(self.theme_button)

        # Toggle user list button
        self.toggle_userlist_button = create_icon_button(self.icons_path, "user.svg", tooltip="Toggle User List", is_dark_theme=is_dark)
        self.toggle_userlist_button.clicked.connect(self.toggle_user_list)
        input_layout.addWidget(self.toggle_userlist_button)

        # Right layout: user list
        self.user_list = QListWidget()
        self.user_list.setFont(app_font)
        main_layout.addWidget(self.user_list, stretch=1)
        
        self.user_list.setVisible(userlist_visible)
        
        self.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatWindow()
    sys.exit(app.exec())
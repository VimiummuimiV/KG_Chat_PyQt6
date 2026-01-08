import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QFrame, QMessageBox, QApplication, QStackedWidget
)
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from helpers.create import create_icon_button, set_theme, _render_svg_icon
from helpers.load import load_avatar_by_id, make_rounded_pixmap
from helpers.config import Config
from core.accounts import AccountManager
from themes.theme import ThemeManager


class AccountWindow(QWidget):
    # Signal emitted when account is successfully connected
    account_connected = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        
        # Paths
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.icons_path = Path(__file__).parent.parent / "icons"
        
        # Config and theme
        self.config = Config(str(self.config_path))
        self.theme_manager = ThemeManager(self.config)
        self.theme_manager.apply_theme()
        
        # Account manager
        self.account_manager = AccountManager(str(self.config_path))
        
        # Initialize UI
        self.initializeUI()
        self.load_accounts()
    
    def initializeUI(self):
        # Window setup
        self.setWindowTitle("Account Manager")
        self.setFixedWidth(550)
        self.setMinimumHeight(120)
        self.setMaximumHeight(120)
        
        # Set initial theme state for icons
        set_theme(self.theme_manager.is_dark())
        
        # Font
        app_font = QFont("Montserrat", 12)
        self.setFont(app_font)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        self.setLayout(main_layout)
        
        # Stacked widget to switch between Connect and Create sections
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)
        
        # Create both pages
        self.connect_page = self.create_connect_page()
        self.create_page = self.create_create_page()
        
        self.stacked_widget.addWidget(self.connect_page)
        self.stacked_widget.addWidget(self.create_page)
        
        # Show connect page by default
        self.stacked_widget.setCurrentIndex(0)
        
        # Add stretch at the bottom
        main_layout.addStretch()
    
    def create_connect_page(self):
        """Create the Connect section page"""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        page.setLayout(layout)
        
        # ===== CONNECT SECTION =====
        connect_label = QLabel("🔓 Connect")
        connect_label.setFont(QFont("Montserrat", 14, QFont.Weight.Bold))
        layout.addWidget(connect_label)
        
        # Connect row: Avatar + Dropdown + Connect + Remove + Add User
        connect_row = QHBoxLayout()
        connect_row.setSpacing(8)
        
        # Avatar
        self.account_avatar = create_icon_button(
            self.icons_path, 
            "user.svg", 
            tooltip="Account"
        )
        self.account_avatar.setStyleSheet("QPushButton { background: transparent; border: none; }")
        connect_row.addWidget(self.account_avatar)
        
        # Account dropdown
        self.account_dropdown = QComboBox()
        self.account_dropdown.setFont(QFont("Montserrat", 12))
        self.account_dropdown.setMinimumHeight(48)
        self.account_dropdown.setMaximumHeight(48)
        self.account_dropdown.currentIndexChanged.connect(self.update_avatar)
        connect_row.addWidget(self.account_dropdown, stretch=1)
        
        # Connect button
        self.connect_button = create_icon_button(
            self.icons_path, 
            "login.svg", 
            tooltip="Connect to chat"
        )
        self.connect_button.clicked.connect(self.on_connect)
        connect_row.addWidget(self.connect_button)
        
        # Remove button
        self.remove_button = create_icon_button(
            self.icons_path, 
            "trash.svg", 
            tooltip="Remove account"
        )
        self.remove_button.clicked.connect(self.on_remove_account)
        connect_row.addWidget(self.remove_button)
        
        # Add user button
        self.add_user_button = create_icon_button(
            self.icons_path, 
            "add-user.svg", 
            tooltip="Create new account"
        )
        self.add_user_button.clicked.connect(self.show_create_page)
        connect_row.addWidget(self.add_user_button)
        
        layout.addLayout(connect_row)
        
        return page
    
    def create_create_page(self):
        """Create the Create Account section page"""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        page.setLayout(layout)
        
        # ===== CREATE SECTION =====
        create_label = QLabel("➕ Create")
        create_label.setFont(QFont("Montserrat", 14, QFont.Weight.Bold))
        layout.addWidget(create_label)
        
        # Create row: Go Back + Username + Password + Save
        create_row = QHBoxLayout()
        create_row.setSpacing(8)
        
        # Go back button
        self.go_back_button = create_icon_button(
            self.icons_path, 
            "go-back.svg", 
            tooltip="Go back to Connect"
        )
        self.go_back_button.clicked.connect(self.show_connect_page)
        create_row.addWidget(self.go_back_button)
        
        # Username field
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setMinimumHeight(48)
        self.username_input.setMaximumHeight(48)
        self.username_input.setFont(QFont("Montserrat", 12))
        create_row.addWidget(self.username_input, stretch=1)
        
        # Password field
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(48)
        self.password_input.setMaximumHeight(48)
        self.password_input.setFont(QFont("Montserrat", 12))
        create_row.addWidget(self.password_input, stretch=1)
        
        # Create/Save button
        self.create_button = create_icon_button(
            self.icons_path, 
            "save.svg", 
            tooltip="Create account"
        )
        self.create_button.clicked.connect(self.on_create_account)
        create_row.addWidget(self.create_button)
        
        layout.addLayout(create_row)
        
        return page
    
    def show_connect_page(self):
        """Navigate to Connect page"""
        self.stacked_widget.setCurrentIndex(0)
    
    def show_create_page(self):
        """Navigate to Create page"""
        self.stacked_widget.setCurrentIndex(1)
    
    def load_accounts(self):
        self.account_dropdown.clear()
        accounts = self.account_manager.list_accounts()
        
        if not accounts:
            self.account_dropdown.addItem("No accounts available")
            self.connect_button.setEnabled(False)
            self.remove_button.setEnabled(False)
            return
        
        self.connect_button.setEnabled(True)
        self.remove_button.setEnabled(True)
        
        # Find active account index
        active_index = 0
        for i, account in enumerate(accounts):
            display_text = f"{account['login']} (ID: {account['user_id']})"
            self.account_dropdown.addItem(display_text, account)
            if account.get('active'):
                active_index = i
        
        # Set active account as current
        self.account_dropdown.setCurrentIndex(active_index)
    
    def update_avatar(self):
        account = self.account_dropdown.currentData()
        if not account or not account.get('user_id'):
            # Reset to default user icon
            icon = _render_svg_icon(self.icons_path / "user.svg", 30)
            self.account_avatar.setIcon(icon)
            self.account_avatar.setIconSize(QSize(30, 30))
            self.account_avatar.setStyleSheet("QPushButton { background: transparent; border: none; }")
            return
        
        pixmap = load_avatar_by_id(account['user_id'])
        if pixmap:
            # Make rounded pixmap with 48x48 size to match button
            rounded = make_rounded_pixmap(pixmap, 48, radius=8)
            self.account_avatar.setIcon(QIcon(rounded))
            self.account_avatar.setIconSize(QSize(48, 48))
            self.account_avatar.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0; }")
        else:
            # Fallback to default icon
            icon = _render_svg_icon(self.icons_path / "user.svg", 30)
            self.account_avatar.setIcon(icon)
            self.account_avatar.setIconSize(QSize(30, 30))
            self.account_avatar.setStyleSheet("QPushButton { background: transparent; border: none; }")
    
    def on_connect(self):
        if self.account_dropdown.count() == 0 or self.account_dropdown.currentText() == "No accounts available":
            QMessageBox.warning(self, "No Account", "Please create an account first.")
            return
        
        # Get selected account
        account = self.account_dropdown.currentData()
        if account:
            # Emit signal with account data
            self.account_connected.emit(account)
    
    def on_remove_account(self):
        if self.account_dropdown.count() == 0 or self.account_dropdown.currentText() == "No accounts available":
            QMessageBox.warning(self, "No Account", "No account to remove.")
            return
        
        # Confirm removal
        account = self.account_dropdown.currentData()
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove account '{account['login']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove account
            if self.account_manager.remove_account(account['login']):
                QMessageBox.information(self, "Success", "Account removed successfully.")
                self.load_accounts()
            else:
                QMessageBox.critical(self, "Error", "Failed to remove account.")
    
    def on_create_account(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        # Validate inputs
        if not username or not password:
            QMessageBox.warning(self, "Invalid Input", "Username and password are required.")
            return
        
        # Import auth module
        from core.auth import authenticate
        
        # Show progress
        self.create_button.setEnabled(False)
        QApplication.processEvents()  # Update UI
        
        # Authenticate and get user data
        user_data = authenticate(username, password)
        
        # Re-enable button
        self.create_button.setEnabled(True)
        self.create_button.setToolTip("Create account")
        
        if not user_data or not user_data.get('id'):
            QMessageBox.critical(self, "Authentication Failed", "Invalid username or password.")
            return
        
        # Add account with extracted data
        success = self.account_manager.add_account(
            user_id=str(user_data['id']),
            login=user_data['login'],
            password=user_data['pass'],
            set_active=True
        )
        
        if success:
            QMessageBox.information(self, "Success", f"Account '{username}' connected successfully!")
            # Clear input fields
            self.username_input.clear()
            self.password_input.clear()
            # Reload accounts
            self.load_accounts()
            # Navigate back to connect page
            self.show_connect_page()
        else:
            QMessageBox.critical(self, "Error", "Failed to save account. Account may already exist.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AccountWindow()
    window.show()
    sys.exit(app.exec())
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QFrame, QMessageBox, QApplication
)
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from helpers.create import create_icon_button
from helpers.load import load_avatar_by_id
from core.accounts import AccountManager


class AccountWindow(QWidget):
    # Signal emitted when account is successfully connected
    account_connected = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        
        # Paths
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.icons_path = Path(__file__).parent.parent / "icons"
        
        # Account manager
        self.account_manager = AccountManager(str(self.config_path))
        
        # Initialize UI
        self.initializeUI()
        self.load_accounts()
    
    def initializeUI(self):
        # Window setup
        self.setWindowTitle("Account Manager")
        self.setFixedWidth(550)
        self.setMinimumHeight(200)
        self.setMaximumHeight(200)
        
        # Font
        app_font = QFont("Montserrat", 12)
        self.setFont(app_font)
        
        # Main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # ===== CONNECT SECTION =====
        connect_label = QLabel("🔓 Connect")
        connect_label.setFont(QFont("Montserrat", 14, QFont.Weight.Bold))
        main_layout.addWidget(connect_label)
        
        # Connect row: Avatar + Dropdown + Connect + Remove
        connect_row = QHBoxLayout()
        
        # Avatar
        self.account_avatar = create_icon_button(self.icons_path, "user.svg", tooltip="Account")
        self.account_avatar.setEnabled(False)
        connect_row.addWidget(self.account_avatar)
        
        # Account dropdown - uses stretch to fill available space
        self.account_dropdown = QComboBox()
        self.account_dropdown.setFont(app_font)
        self.account_dropdown.setMinimumHeight(46)
        self.account_dropdown.currentIndexChanged.connect(self.on_account_changed)
        connect_row.addWidget(self.account_dropdown, stretch=1)
        
        # Connect button (icon-based)
        self.connect_button = create_icon_button(self.icons_path, "login.svg", tooltip="Connect to chat")
        self.connect_button.clicked.connect(self.on_connect)
        connect_row.addWidget(self.connect_button)
        
        # Remove button (icon-based)
        self.remove_button = create_icon_button(self.icons_path, "trash.svg", tooltip="Remove account")
        self.remove_button.clicked.connect(self.on_remove_account)
        connect_row.addWidget(self.remove_button)
        
        main_layout.addLayout(connect_row)
        
        # ===== CREATE SECTION =====
        create_label = QLabel("➕ Create")
        create_label.setFont(QFont("Montserrat", 14, QFont.Weight.Bold))
        main_layout.addWidget(create_label)
        
        # Create row: User ID + Username + Password + Save
        create_row = QHBoxLayout()
        create_row.setSpacing(10)
        
        # User ID field - smaller stretch factor
        self.userid_input = QLineEdit()
        self.userid_input.setPlaceholderText("Id")
        self.userid_input.setMinimumHeight(46)
        create_row.addWidget(self.userid_input, stretch=1)
        
        # Username field - larger stretch factor
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setMinimumHeight(46)
        create_row.addWidget(self.username_input, stretch=2)
        
        # Password field - larger stretch factor
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(46)
        create_row.addWidget(self.password_input, stretch=2)
        
        # Create button (icon-based)
        self.create_button = create_icon_button(self.icons_path, "save.svg", tooltip="Create account")
        self.create_button.clicked.connect(self.on_create_account)
        create_row.addWidget(self.create_button)
        
        main_layout.addLayout(create_row)
        
        # Add stretch at the bottom
        main_layout.addStretch()
    
    def load_accounts(self):
        self.account_dropdown.clear()
        accounts = self.account_manager.list_accounts()
        
        if not accounts:
            self.account_dropdown.addItem("No accounts available")
            self.connect_button.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.account_avatar.setEnabled(False)
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
        
        # Load avatar for active account
        self.on_account_changed()
    
    def on_account_changed(self):
        # Load avatar when account selection changes
        account = self.account_dropdown.currentData()
        
        if not account or not account.get('user_id'):
            # No valid account - fallback to icon
            self.account_avatar.setIcon(QIcon(str(self.icons_path / "user.svg")))
            self.account_avatar.setEnabled(False)
            return
        
        # Try to load avatar
        pixmap = load_avatar_by_id(account['user_id'])
        
        if pixmap:
            # Avatar loaded successfully - set it and enable button
            self.account_avatar.setIcon(QIcon(pixmap))
            self.account_avatar.setIconSize(QSize(40, 40))
            self.account_avatar.setEnabled(True)
        else:
            # No avatar - fallback to icon and disable
            self.account_avatar.setIcon(QIcon(str(self.icons_path / "user.svg")))
            self.account_avatar.setIconSize(QSize(30, 30))
            self.account_avatar.setEnabled(False)
    
    def on_connect(self):
        if self.account_dropdown.count() == 0 or self.account_dropdown.currentText() == "No accounts available":
            QMessageBox.warning(self, "No Account", "Please create an account first.")
            return
        
        # Get selected account
        account = self.account_dropdown.currentData()
        if account:
            # Emit signal with account data
            self.account_connected.emit(account)
            print(f"✅ Selected account: {account['login']}")
    
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
        user_id = self.userid_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        # Validate inputs
        if not user_id or not username or not password:
            QMessageBox.warning(self, "Invalid Input", "All fields are required.")
            return
        
        if not user_id.isdigit():
            QMessageBox.warning(self, "Invalid Input", "User ID must be numeric.")
            return
        
        # Add account
        success = self.account_manager.add_account(
            user_id=user_id,
            login=username,
            password=password,
            set_active=True  # Make new account active
        )
        
        if success:
            QMessageBox.information(self, "Success", f"Account '{username}' created successfully!")
            # Clear input fields
            self.userid_input.clear()
            self.username_input.clear()
            self.password_input.clear()
            # Reload accounts
            self.load_accounts()
        else:
            QMessageBox.critical(self, "Error", "Failed to create account. Username may already exist.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AccountWindow()
    window.show()
    sys.exit(app.exec())
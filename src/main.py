import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

# Add src directory to path if running from root
src_path = Path(__file__).parent
if src_path.name == 'src':
    sys.path.insert(0, str(src_path))
else:
    sys.path.insert(0, str(src_path / 'src'))

from ui.ui_accounts import AccountWindow
from ui.ui_chat import ChatWindow


class Application:
    def __init__(self):
        self.app = QApplication(sys.argv)
        
        # Set application font
        app_font = QFont("Montserrat", 12)
        self.app.setFont(app_font)
        
        # Windows
        self.account_window = None
        self.chat_window = None
        
    def run(self):
        # Run the application - start with account window
        self.show_account_window()
        return self.app.exec()
    
    def show_account_window(self):
        # Show account selection window
        self.account_window = AccountWindow()
        self.account_window.account_connected.connect(self.on_account_connected)
        self.account_window.show()
    
    def on_account_connected(self, account):
        # Close account window
        if self.account_window:
            self.account_window.close()
            self.account_window = None
        
        # Open chat window with selected account
        self.show_chat_window(account)
    
    def show_chat_window(self, account):
        self.chat_window = ChatWindow(account=account)
        self.chat_window.show()


def main():
    """Application entry point"""
    application = Application()
    sys.exit(application.run())


if __name__ == "__main__":
    main()
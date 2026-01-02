"""Main application entry point - coordinates all windows"""
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
    """Main application coordinator - manages window sequence"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        
        # Set application font
        app_font = QFont("Montserrat", 12)
        self.app.setFont(app_font)
        
        # Windows
        self.account_window = None
        self.chat_window = None
        
        # XMPP client (to be initialized later)
        self.xmpp_client = None
        
    def run(self):
        """Run the application - start with account window"""
        self.show_account_window()
        return self.app.exec()
    
    def show_account_window(self):
        """Show account selection window (first window)"""
        print("🚀 Starting application...")
        
        self.account_window = AccountWindow()
        self.account_window.account_connected.connect(self.on_account_connected)
        self.account_window.show()
    
    def on_account_connected(self, account):
        """
        Handle successful account selection
        Triggered when user clicks 'Connect' button
        """
        print(f"\n✅ Account selected: {account['login']} (ID: {account['user_id']})")
        
        # Close account window
        if self.account_window:
            self.account_window.close()
            self.account_window = None
        
        # Open chat window with selected account
        self.show_chat_window(account)
    
    def show_chat_window(self, account):
        """Show main chat window (second window)"""
        print(f"🎨 Opening chat window...")
        
        # Create chat window with account
        self.chat_window = ChatWindow(account=account)
        self.chat_window.show()
        
        # TODO: Initialize XMPP connection
        # self.init_xmpp_connection(account)
    
    def init_xmpp_connection(self, account):
        """
        Initialize XMPP connection with selected account
        This will be implemented to connect to the chat server
        """
        print(f"🔌 Connecting to XMPP server...")
        
        # Example implementation:
        # from core.xmpp import XMPPClient
        # 
        # self.xmpp_client = XMPPClient()
        # 
        # if self.xmpp_client.connect(account):
        #     print(f"✅ Connected to XMPP as {account['login']}")
        #     
        #     # Join default rooms
        #     rooms = self.xmpp_client.account_manager.get_rooms()
        #     for room in rooms:
        #         if room.get('auto_join'):
        #             self.xmpp_client.join_room(room['jid'])
        #     
        #     # Set up callbacks for messages and presence
        #     self.xmpp_client.set_message_callback(self.on_message_received)
        #     self.xmpp_client.set_presence_callback(self.on_presence_update)
        #     
        #     # Start listening in a separate thread
        #     import threading
        #     listen_thread = threading.Thread(target=self.xmpp_client.listen, daemon=True)
        #     listen_thread.start()
        # else:
        #     print("❌ Failed to connect to XMPP")
    
    def on_message_received(self, message):
        """Handle incoming messages from XMPP"""
        if self.chat_window:
            # Add message to chat window
            display_text = f"{message.login}: {message.body}"
            self.chat_window.messages_area.addItem(display_text)
    
    def on_presence_update(self, presence):
        """Handle presence updates from XMPP"""
        if self.chat_window:
            # Update user list
            pass


def main():
    """Application entry point"""
    application = Application()
    sys.exit(application.run())


if __name__ == "__main__":
    main()
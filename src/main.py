import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QFont, QIcon, QAction, QPixmap, QPainter
from PyQt6.QtCore import Qt, QLockFile, QDir
from PyQt6.QtSvg import QSvgRenderer

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
        
        # Single instance lock
        self.lock_file = QLockFile(QDir.tempPath() + "/xmpp_chat.lock")
        if not self.lock_file.tryLock(100):
            QMessageBox.warning(
                None,
                "Already Running",
                "KG Chat is already running.\nCheck your system tray."
            )
            sys.exit(0)
        
        self.app.setFont(QFont("Montserrat", 12))
        
        # Set global application icon
        self.icons_path = Path(__file__).parent / "icons"
        self.app.setWindowIcon(self._get_icon())
        
        self.account_window = None
        self.chat_window = None
        self.tray_icon = None
        self.setup_system_tray()
        
    def setup_system_tray(self):
        """Setup system tray icon and menu"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("⚠️ System tray not available")
            return
        
        self.tray_icon = QSystemTrayIcon(self._get_icon(), self.app)
        self.tray_icon.setToolTip("KG Chat")
        self.tray_icon.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        
        # Create menu
        menu = QMenu()
        menu_items = [
            ("Show", self.show_window),
            ("Hide", self.hide_window),
            (None, None),
            ("Switch Account", self.show_account_switcher),
            (None, None),
            ("Exit", self.exit_application)
        ]
        for label, handler in menu_items:
            if label:
                action = QAction(label, self.app)
                action.triggered.connect(handler)
                menu.addAction(action)
            else:
                menu.addSeparator()
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
    
    def _get_icon(self):
        """Get orange chat icon for windows and tray"""
        icon_file = self.icons_path / "chat.svg"
        if not icon_file.exists():
            return self.app.style().standardIcon(self.app.style().StandardPixmap.SP_ComputerIcon)
        
        # Render SVG with orange color
        with open(icon_file, 'r') as f:
            svg = f.read().replace('fill="currentColor"', 'fill="#e28743"')
        
        renderer = QSvgRenderer()
        renderer.load(svg.encode('utf-8'))
        pixmap = QPixmap(256, 256)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        return QIcon(pixmap)
    
    def show_window(self):
        """Show the active window"""
        window = self.chat_window if self.chat_window and not self.chat_window.isVisible() else self.account_window
        if window and not window.isVisible():
            window.show()
            window.activateWindow()
            window.raise_()
    
    def hide_window(self):
        """Hide the active window"""
        for window in [self.chat_window, self.account_window]:
            if window and window.isVisible():
                window.hide()
                break
    
    def show_account_switcher(self):
        """Show account switcher window"""
        # Close chat window if open
        if self.chat_window:
            try:
                if self.chat_window.xmpp_client:
                    self.chat_window.xmpp_client.disconnect()
            except Exception:
                pass
            self.chat_window.close()
            self.chat_window.deleteLater()
            self.chat_window = None
        
        # Show account window
        self.show_account_window()
    
    def exit_application(self):
        """Exit the application completely"""
        if self.chat_window and self.chat_window.xmpp_client:
            try:
                self.chat_window.xmpp_client.disconnect()
            except Exception:
                pass
        if self.tray_icon:
            self.tray_icon.hide()
        
        # Release lock file
        if hasattr(self, 'lock_file'):
            self.lock_file.unlock()
        
        self.app.quit()
        
    def run(self):
        """Run the application - start with account window"""
        self.show_account_window()
        return self.app.exec()
    
    def show_account_window(self):
        """Show account selection window"""
        self.account_window = AccountWindow()
        self.account_window.account_connected.connect(self.on_account_connected)
        self.account_window.show()
    
    def on_account_connected(self, account):
        """Close account window and open chat"""
        if self.account_window:
            self.account_window.close()
            self.account_window = None
        self.show_chat_window(account)
    
    def show_chat_window(self, account):
        """Open chat window with tray support"""
        self.chat_window = ChatWindow(account=account, app_controller=self)
        self.chat_window.set_tray_mode(True)
        self.chat_window.show()


def main():
    """Application entry point"""
    application = Application()
    sys.exit(application.run())


if __name__ == "__main__":
    main()
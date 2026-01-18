import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QFont, QIcon, QAction, QPixmap, QPainter, QColor
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
from helpers.fonts import load_fonts, set_application_font
from helpers.config import Config
from helpers.username_color_manager import(
    change_username_color,
    reset_username_color,
    update_from_server
)
from core.accounts import AccountManager


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

        load_fonts()
        set_application_font(self.app)

        # Set global application icon
        self.icons_path = Path(__file__).parent / "icons"
        self.app.setWindowIcon(self._get_icon())

        # Initialize account manager and config
        self.config_path = Path(__file__).parent / "settings" / "config.json"
        self.account_manager = AccountManager(str(self.config_path))
        self.config = Config(str(self.config_path))

        self.account_window = None
        self.chat_window = None
        self.tray_icon = None
        self.color_menu = None
        self.reset_color_action = None
        self.sound_menu = None
        self.voice_sound_action = None
        self.mention_beep_action = None
        
        self.setup_system_tray()

    def setup_system_tray(self):
        """Setup system tray icon and menu"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("⚠️ System tray not available")
            return

        self.tray_icon = QSystemTrayIcon(self._get_icon(), self.app)
        self.tray_icon.setToolTip("KG Chat")
        self.tray_icon.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)

        # Create the main menu
        menu = QMenu()
       
        # Add menu items
        menu.addAction(QAction("Switch Account", self.app, triggered=self.show_account_switcher))
        menu.addSeparator()
       
        # Create Color Management submenu
        self._setup_color_menu(menu)
       
        menu.addSeparator()
        
        # Create Sound Management submenu
        self._setup_sound_menu(menu)
        
        menu.addSeparator()
        menu.addAction(QAction("Exit", self.app, triggered=self.exit_application))

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _setup_color_menu(self, parent_menu: QMenu):
        """Setup color management submenu"""
        self.color_menu = parent_menu.addMenu("Color Management")
       
        # Create actions for the submenu
        change_color_action = QAction("Change Username Color", self.app)
        change_color_action.triggered.connect(self.handle_change_username_color)
        self.color_menu.addAction(change_color_action)
       
        # Reset action - will be shown/hidden dynamically
        self.reset_color_action = QAction("Reset to Original", self.app)
        self.reset_color_action.triggered.connect(self.handle_reset_username_color)
        self.color_menu.addAction(self.reset_color_action)
       
        update_color_action = QAction("Update from Server", self.app)
        update_color_action.triggered.connect(self.handle_update_from_server)
        self.color_menu.addAction(update_color_action)
       
        # Connect to aboutToShow to update menu visibility
        self.color_menu.aboutToShow.connect(self.update_color_menu)

    def _setup_sound_menu(self, parent_menu: QMenu):
        """Setup sound management submenu"""
        self.sound_menu = parent_menu.addMenu("Sound Management")
        
        # Voice sound (TTS) toggle action
        self.voice_sound_action = QAction("Voice Sound", self.app, checkable=True)
        self.voice_sound_action.triggered.connect(
            lambda: self._on_sound_toggled("tts_enabled", self.voice_sound_action)
        )
        self.sound_menu.addAction(self.voice_sound_action)
        
        # Mention beep toggle action
        self.mention_beep_action = QAction("Mention Beep", self.app, checkable=True)
        self.mention_beep_action.triggered.connect(
            lambda: self._on_sound_toggled("mention_sound_enabled", self.mention_beep_action)
        )
        self.sound_menu.addAction(self.mention_beep_action)
        
        # Connect to aboutToShow to update menu state
        self.sound_menu.aboutToShow.connect(self.update_sound_menu)
        
        # Load initial states
        self.update_sound_menu()

    def update_color_menu(self):
        """Update the color menu to show/hide Reset option based on custom_background"""
        if not self.chat_window or not self.chat_window.account:
            # No account connected - hide reset option
            self.reset_color_action.setVisible(False)
            return
       
        # Show reset only if custom_background exists
        has_custom_bg = bool(self.chat_window.account.get('custom_background'))
        self.reset_color_action.setVisible(has_custom_bg)

    def update_sound_menu(self):
        """Update sound menu to reflect current config state"""
        # Update voice sound (TTS) state
        voice_enabled = self.config.get("sound", "tts_enabled")
        if voice_enabled is None:
            voice_enabled = False
        self.voice_sound_action.setChecked(voice_enabled)
        
        # Update mention beep state
        mention_enabled = self.config.get("sound", "mention_sound_enabled")
        if mention_enabled is None:
            mention_enabled = True
        self.mention_beep_action.setChecked(mention_enabled)

    def _on_sound_toggled(self, config_key: str, action: QAction):
        """Handle sound toggle from tray menu"""
        enabled = action.isChecked()
        
        # Save to config
        self.config.set("sound", config_key, value=enabled)
        
        # Update chat window's config instance directly if it exists
        if self.chat_window:
            self.chat_window.config.data = self.config.data

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

    def show_account_switcher(self):
        """Show account switcher window"""
        # Close chat window if open
        if self.chat_window:
            try:
                # Disable auto-reconnect before closing
                self.chat_window.disable_reconnect()

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
        if self.chat_window:
            self.chat_window.really_close = True
            self.chat_window.close()
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

    def _refresh_own_username_color(self, operation_func):
        """Execute operation and refresh own username color in UI if successful."""
        if not self.chat_window or not self.chat_window.account:
            QMessageBox.warning(None, "No Account", "Please connect to an account first.")
            return
       
        success = operation_func(
            None, # No parent for tray
            self.account_manager,
            self.chat_window.account,
            self.chat_window.cache
        )
       
        if not success:
            return
       
        # Refresh account data to update custom_background/avatar state
        updated_account = self.account_manager.get_account_by_chat_username(
            self.chat_window.account['chat_username']
        )
       
        if not updated_account:
            return
       
        previous_avatar = self.chat_window.account.get('avatar')
        self.chat_window.account.update(updated_account)
       
        effective_bg = updated_account.get('custom_background') or updated_account.get('background')
        own_login = updated_account['chat_username']
        own_id = updated_account['user_id']
       
        # Clear color cache
        self.chat_window.cache.clear_colors()
       
        # Clear avatar cache if changed
        if updated_account.get('avatar') != previous_avatar:
            self.chat_window.cache._avatar_cache.pop(own_id, None)
       
        # Update userlist own user
        own_user = next(
            (u for u in self.chat_window.xmpp_client.user_list.users.values()
            if u.login == own_login),
            None
        )
        if own_user:
            own_user.background = effective_bg
            self.chat_window.user_list_widget.add_users(users=[own_user])
       
        # Update messages
        own_messages_updated = False
        for msg_data in self.chat_window.messages_widget.model._messages:
            if msg_data.username == own_login:
                msg_data.background_color = effective_bg
                own_messages_updated = True
       
        if own_messages_updated:
            self.chat_window.messages_widget._force_recalculate()

    def handle_change_username_color(self):
        """Handle Change Username Color from tray menu."""
        self._refresh_own_username_color(change_username_color)

    def handle_reset_username_color(self):
        """Handle Reset to Original from tray menu."""
        self._refresh_own_username_color(reset_username_color)

    def handle_update_from_server(self):
        """Handle Update from Server from tray menu."""
        self._refresh_own_username_color(update_from_server)

def main():
    """Application entry point"""
    application = Application()
    sys.exit(application.run())


if __name__ == "__main__":
    main()

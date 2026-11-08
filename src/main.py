import ctypes
import sys
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, pyqtSlot, QDir, QLockFile, QMetaObject, QObject, Qt, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon


QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

# Add src directory to path
_src_path = Path(__file__).parent
sys.path.insert(0, str(_src_path if _src_path.name == 'src' else _src_path / 'src'))

from components.button import render_svg_icon
from components.tray_badge import TrayIconWithBadge
from core.state.accounts import AccountManager
from helpers.config import Config, get_config_path
from helpers.data import get_data_dir
from helpers.fonts.font_scaler import FontScaler
from helpers.fonts.fonts import (
    FontType,
    get_font,
    load_fonts,
    set_application_font,
    set_config,
    set_font_scaler,
)
from helpers.system import hotkey_manager as hotkey
from helpers.system.power_monitor import power_monitor
from helpers.translate import on_language_changed, set_language, tr
from helpers.users.ban_manager import BanManager
from helpers.users.pronunciation_manager import PronunciationManager
from helpers.users.user_tracker import UserTracker
from helpers.users.username_color_manager import change_username_color, reset_username_color
from ui.account.ui_accounts import AccountWindow
from ui.chat.ui_chat import ChatWindow
from ui.notification.popup_manager import popup_manager


class Application(QObject):
    _toggle_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self._toggle_signal.connect(self._toggle_chat_visibility)
        self._is_initial_launch = True

        # Set Windows taskbar icon (must be done before any windows are created)
        if sys.platform == 'win32':
            try:
                # Set App User Model ID for Windows taskbar grouping
                myappid = 'kgchat.messenger.app.1.0'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception as e:
                print(f"⚠️ Failed to set Windows App ID: {e}")

        # Single instance lock
        self._lock_file = QLockFile(QDir.tempPath() + "/xmpp_chat.lock")
        if not self._lock_file.tryLock(100):
            QMessageBox.warning(
                None,
                tr("Already Running", "Уже запущено"),
                tr("KG Chat is already running.\nCheck your system tray.",
                   "КГ Чат уже запущен.\nПроверьте системный трей.")
            )
            sys.exit(0)

        # Initialize data path (user data lives under KG_Chat_Data/data)
        self.data_path = get_data_dir("data")

        # Initialize account manager and config
        self.config_path = get_config_path()
        self.account_manager = AccountManager(str(self.config_path))
        self.config = Config(self.config_path)
        set_config(self.config)
        set_language(self.config.get("ui", "language") or "en")

        # Initialize font scaler
        self.font_scaler = FontScaler(self.config)
        set_font_scaler(self.font_scaler)

        load_fonts()
        set_application_font(self.app)

        # Initialize icons path FIRST
        self.icons_path = Path(__file__).parent / "icons"

        # Set global application icon EARLY - before any windows are created
        # Uses chat.ico for taskbar/dock on all platforms
        app_icon = self._get_app_icon()
        self.app.setWindowIcon(app_icon)

        # Initialize tray badge manager
        self._tray_badge = TrayIconWithBadge(self.icons_path)
        self._unread_count = 0

        # Initialize pronunciation manager
        self.pronunciation_manager = PronunciationManager(self.data_path)
        # Initialize ban manager
        self.ban_manager = BanManager(self.data_path)
        # Initialize user tracker
        self.user_tracker = UserTracker(self.data_path, self.config)

        self._account_window = None
        self.chat_window = None
        self._tray_icon = None

        self._color_menu = None
        self._reset_color_action = None

        self._sound_menu = None
        self._voice_sound_action = None
        self._effects_sound_action = None
        self._pronunciation_action = None

        self._notification_enabled_action = None

        self._ban_list_action = None

        power_monitor.resumed.connect(self._on_system_resumed)
        power_monitor.start()

        self._setup_system_tray()

    def _setup_system_tray(self):
        """Setup system tray icon and menu"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("⚠️ System tray not available")
            return

        self._tray_icon = QSystemTrayIcon(self._get_icon(self._unread_count), self.app)
        self._tray_icon.activated.connect(lambda r: self._toggle_chat_visibility(ignore_active=True) if r == QSystemTrayIcon.ActivationReason.Trigger else None)

        icon = lambda name: render_svg_icon(self.icons_path / name, 16)

        menu = QMenu()
        menu.setFont(get_font(FontType.UI))

        self._show_action = QAction(icon("door-open.svg"), "", self.app)
        self._show_action.triggered.connect(self._show_from_tray)
        menu.addAction(self._show_action)
        menu.addSeparator()

        self._switch_action = QAction(icon("user-switch.svg"), "", self.app)
        self._switch_action.triggered.connect(self.show_account_switcher)
        menu.addAction(self._switch_action)
        menu.addSeparator()

        self._setup_color_menu(menu, icon)
        menu.addSeparator()
        self._setup_sound_menu(menu, icon)
        menu.addSeparator()
        self._setup_notification_menu(menu, icon)
        menu.addSeparator()

        self._ban_list_action = QAction(icon("user-blocked.svg"), "", self.app)
        self._ban_list_action.triggered.connect(self._handle_ban_list)
        menu.addAction(self._ban_list_action)

        menu.addSeparator()
        self._exit_action = QAction(icon("door-closed.svg"), "", self.app)
        self._exit_action.triggered.connect(self.exit_application)
        menu.addAction(self._exit_action)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.show()
        self._retranslate_tray()
        on_language_changed(self._retranslate_tray)

    def _setup_color_menu(self, parent_menu: QMenu, icon):
        self._color_menu = parent_menu.addMenu("")
        self._color_menu.setIcon(icon("palette.svg"))
        self._change_color_action = QAction(icon("palette.svg"), "", self.app)
        self._change_color_action.triggered.connect(self._handle_change_username_color)
        self._color_menu.addAction(self._change_color_action)
        self._reset_color_action = QAction(icon("go-back.svg"), "", self.app)
        self._reset_color_action.triggered.connect(self._handle_reset_username_color)
        self._color_menu.addAction(self._reset_color_action)
        self._color_menu.aboutToShow.connect(self._update_color_menu)

    def _setup_sound_menu(self, parent_menu: QMenu, icon):
        self._sound_menu = parent_menu.addMenu("")
        self._sound_menu.setIcon(icon("volume-up.svg"))
        self._sound_menu.addSeparator()
        self._voice_sound_action = QAction("", self.app, checkable=True)
        self._voice_sound_action.triggered.connect(
            lambda: self._on_sound_toggled("tts_enabled", self._voice_sound_action)
        )
        self._sound_menu.addAction(self._voice_sound_action)
        self._effects_sound_action = QAction("", self.app, checkable=True)
        self._effects_sound_action.triggered.connect(
            lambda: self._on_sound_toggled("effects_enabled", self._effects_sound_action)
        )
        self._sound_menu.addAction(self._effects_sound_action)
        self._sound_menu.addSeparator()
        self._pronunciation_action = QAction(icon("user-voice.svg"), "", self.app)
        self._pronunciation_action.triggered.connect(self._handle_pronunciation_manager)
        self._sound_menu.addAction(self._pronunciation_action)
        self._sound_menu.aboutToShow.connect(self.update_sound_menu)
        self.update_sound_menu()

    def _setup_notification_menu(self, parent_menu: QMenu, icon):
        self._notification_enabled_action = QAction("", self.app, checkable=True)
        muted = self.config.get("notification", "muted") or False
        self._notification_enabled_action.setChecked(not muted)
        self._notification_enabled_action.triggered.connect(self._on_notification_enabled_toggled)
        parent_menu.addAction(self._notification_enabled_action)

    def _retranslate_tray(self, _code=None):
        if not self._tray_icon:
            return
        self._tray_icon.setToolTip(tr("KG Chat", "КГ Чат"))
        self._show_action.setText(tr("Show Chat", "Показать чат"))
        self._switch_action.setText(tr("Switch Account", "Сменить аккаунт"))
        self._color_menu.setTitle(tr("Color", "Цвет"))
        self._change_color_action.setText(tr("Change Username Color", "Изменить цвет имени"))
        self._reset_color_action.setText(tr("Reset to Original", "Сбросить на исходный"))
        self._sound_menu.setTitle(tr("Sound", "Звук"))
        self._voice_sound_action.setText(tr("Voice Sound", "Голосовой звук"))
        self._effects_sound_action.setText(tr("Sound Effects", "Звуковые эффекты"))
        self._pronunciation_action.setText(tr("Username Pronunciation", "Произношение имён"))
        self._notification_enabled_action.setText(tr("Notifications", "Уведомления"))
        self._ban_list_action.setText(tr("Ban List", "Список забаненных"))
        self._exit_action.setText(tr("Exit", "Выход"))

    def _update_color_menu(self):
        """Update the color menu to show/hide Reset option based on custom_background"""
        if not self.chat_window or not self.chat_window.account:
            # No account connected - hide reset option
            self._reset_color_action.setVisible(False)
            return

        # Show reset only if custom_background exists
        has_custom_bg = bool(self.chat_window.account.get('custom_background'))
        self._reset_color_action.setVisible(has_custom_bg)

    def update_sound_menu(self):
        """Update sound menu to reflect current config state"""
        # Update voice sound (TTS) state
        voice_enabled = self.config.get("sound", "tts_enabled")
        if voice_enabled is None:
            voice_enabled = False
        self._voice_sound_action.setChecked(voice_enabled)

        # Update effects sound state
        effects_enabled = self.config.get("sound", "effects_enabled")
        if effects_enabled is None:
            effects_enabled = True
        self._effects_sound_action.setChecked(effects_enabled)

    def update_notification_menu(self):
        """Sync tray Notifications checkbox with config muted state."""
        if not self._notification_enabled_action:
            return
        muted = self.config.get("notification", "muted") or False
        self._notification_enabled_action.blockSignals(True)
        self._notification_enabled_action.setChecked(not muted)
        self._notification_enabled_action.blockSignals(False)

    def _on_sound_toggled(self, config_key: str, action: QAction):
        """Handle sound toggle from tray menu"""
        enabled = action.isChecked()

        # Save to config
        self.config.set("sound", config_key, value=enabled)

        # Update chat window's config instance directly if it exists
        if self.chat_window:
            self.chat_window.config.data = self.config.data
            # Ensure chat window reflects the new sound-related state immediately
            if config_key == 'tts_enabled' and hasattr(self.chat_window, 'update_voice_button_state'):
                self.chat_window.update_voice_button_state()
            if config_key == 'effects_enabled' and hasattr(self.chat_window, 'update_effects_button_state'):
                self.chat_window.update_effects_button_state()

    def _on_notification_enabled_toggled(self, checked: bool):
        """Tray Notifications checkbox: checked = enabled (not muted)."""
        muted = not checked
        self.config.set("notification", "muted", value=muted)

        if self.chat_window:
            self.chat_window.config.data = self.config.data
            if hasattr(self.chat_window, "apply_notification_muted"):
                self.chat_window.apply_notification_muted(muted)
            elif hasattr(self.chat_window, "sync_notification_state"):
                self.chat_window.sync_notification_state()
        else:
            popup_manager.set_muted(muted)

    def _get_app_icon(self):
        """Get the main application icon - chat.ico for taskbar/dock"""
        ico_path = self.icons_path / "chat.ico"
        return QIcon(str(ico_path))

    def _get_icon(self, count: int = 0):
        """Get chat icon with optional message count badge"""
        return self._tray_badge.create_icon(count)

    def increment_unread(self):
        """Increment unread message count and update tray icon"""
        self._unread_count += 1
        if self._tray_icon:
            self._tray_icon.setIcon(self._get_icon(self._unread_count))

    def reset_unread(self):
        """Reset unread message count and update tray icon"""
        self._unread_count = 0
        if self._tray_icon:
            self._tray_icon.setIcon(self._get_icon(0))

    def _force_window_to_foreground(self, window):
        """Force window to foreground with platform-specific handling"""
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        window.activateWindow()
        window.raise_()

        # Windows: Force window to foreground
        if sys.platform == 'win32':
            try:
                hwnd = int(window.winId())
                user_library = ctypes.windll.user32
                foreground_hwnd = user_library.GetForegroundWindow()

                if foreground_hwnd != hwnd:
                    foreground_thread = user_library.GetWindowThreadProcessId(foreground_hwnd, None)
                    this_thread = ctypes.windll.kernel32.GetCurrentThreadId()

                    if foreground_thread != this_thread:
                        user_library.AttachThreadInput(foreground_thread, this_thread, True)

                    user_library.BringWindowToTop(hwnd)
                    user_library.SetForegroundWindow(hwnd)

                    if foreground_thread != this_thread:
                        user_library.AttachThreadInput(foreground_thread, this_thread, False)
            except Exception as e:
                print(f"⚠️ Could not force window to foreground: {e}")

    def _reveal_window(self, window):
        """Show window if hidden, then raise to foreground."""
        if not window:
            return
        if not window.isVisible():
            window.setWindowOpacity(0)
            window.show()
            QTimer.singleShot(50, lambda: window.setWindowOpacity(1))
        self._force_window_to_foreground(window)

    def _show_window(self):
        """Show and raise the active window (chat preferred, else account)."""
        window = self.chat_window or self._account_window
        self._reveal_window(window)
        if window is self.chat_window:
            self.reset_unread()

    def _show_from_tray(self):
        """Tray menu → Show Chat."""
        self._show_window()

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
        self._show_account_window()

    def _on_system_resumed(self):
        """OS woke from sleep/hibernation - force the chat connection to restore now"""
        if self.chat_window:
            self.chat_window.handle_system_resume()

    def exit_application(self):
        """Exit the application completely"""
        hotkey.hotkey_manager.unregister()

        # Mark chat window as really closing immediately to avoid auto-reconnect races
        if self.chat_window:
            try:
                self.chat_window.really_close = True
            except Exception:
                pass

        # Ensure auto-reconnect is disabled so closing doesn't trigger reconnection
        if self.chat_window:
            try:
                self.chat_window.disable_reconnect()
            except Exception:
                pass

        if self.chat_window and self.chat_window.xmpp_client:
            try:
                self.chat_window.xmpp_client.disconnect()
            except Exception:
                pass
        if self.chat_window:
            self.chat_window.close()
        if self._tray_icon:
            self._tray_icon.hide()

        # Release lock file
        if hasattr(self, '_lock_file'):
            self._lock_file.unlock()

        power_monitor.stop()
        self.app.quit()

    def run(self):
        """Run the application - check auto-login or show account window"""
        # Setup global hotkey after Qt is fully initialized
        self._setup_global_hotkey()

        # Check if auto-login is enabled
        auto_login = self.config.get("startup", "auto_login")

        if auto_login:
            # Get active account and connect directly
            active_account = self.account_manager.get_active_account()

            if active_account:
                print(f"🔑 Auto-login enabled, connecting to {active_account['chat_username']}")
                self._show_chat_window(active_account)
            else:
                # No active account, show account window
                print("⚠️ Auto-login enabled but no active account found")
                self._show_account_window()
        else:
            # Normal flow - show account window
            self._show_account_window()

        return self.app.exec()

    def _show_account_window(self):
        """Show account selection window"""
        self._account_window = AccountWindow(config=self.config)
        self._account_window.account_connected.connect(self._on_account_connected)
        self._account_window.setWindowOpacity(0)
        self._account_window.show()
        QTimer.singleShot(50, lambda: self._account_window.setWindowOpacity(1))

    def _on_account_connected(self, account):
        """Close account window and open chat"""
        if self._account_window:
            self._account_window.close()
            self._account_window = None
        self._show_chat_window(account)

    def _show_chat_window(self, account):
        """Open chat window with tray support"""
        self.chat_window = ChatWindow(
            account=account, 
            app_controller=self,
            pronunciation_manager=self.pronunciation_manager,
            ban_manager=self.ban_manager,
            user_tracker=self.user_tracker
        )
        self.chat_window.set_tray_mode(True)

        # Connect font size changes to refresh UI
        self.font_scaler.font_size_changed.connect(self.chat_window.on_font_size_changed)

        # Initialize popup_manager mode and muted state from config
        notification_mode = self.config.get("notification", "mode")
        if notification_mode:
            popup_manager.set_notification_mode(notification_mode)

        notification_muted = self.config.get("notification", "muted")
        if notification_muted:
            popup_manager.set_muted(notification_muted)

        # Initialize notification button icon to match config state
        if hasattr(self.chat_window, 'button_panel') and hasattr(self.chat_window.button_panel, 'update_notification_button_icon'):
            self.chat_window.button_panel.update_notification_button_icon()

        # === Respect "Start minimized" ONLY on initial launch ===
        # On account switch we ALWAYS show the window
        if self._is_initial_launch and self.config.get("startup", "start_minimized"):
            print("🪟 Starting minimized to tray")
            self._is_initial_launch = False
        else:
            # Normal behavior - show the window
            self.chat_window.setWindowOpacity(0)
            self.chat_window.show()
            QTimer.singleShot(50, lambda: self.chat_window.setWindowOpacity(1))
            self._is_initial_launch = False

    def refresh_own_username_color(self, operation_func):
        """Execute operation and refresh own username color in UI if successful."""
        if not self.chat_window or not self.chat_window.account:
            QMessageBox.warning(
                None,
                tr("No Account", "Нет аккаунта"),
                tr("Please connect to an account first.", "Сначала подключитесь к аккаунту.")
            )
            return

        success = operation_func(
            self.chat_window,
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

        # Update own color in cache
        self.chat_window.cache.update_user(own_id, own_login, effective_bg)

        # Clear avatar cache if changed
        if updated_account.get('avatar') != previous_avatar:
            self.chat_window.cache.remove_avatar(own_id)

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
        for msg_data in self.chat_window.messages_widget.model.stored_messages:
            if msg_data.username == own_login:
                msg_data.background_color = effective_bg
                own_messages_updated = True

        if own_messages_updated:
            self.chat_window.messages_widget.force_recalculate()

    def _handle_change_username_color(self):
        """Handle Change Username Color from tray menu."""
        self.refresh_own_username_color(change_username_color)

    def _handle_reset_username_color(self):
        """Handle Reset to Original from tray menu."""
        self.refresh_own_username_color(reset_username_color)

    def _check_chat_ready(self, feature):
        if not self.chat_window or not self.chat_window.account:
            QMessageBox.information(
                None,
                tr("Chat Not Open", "Чат не открыт"),
                tr(f"Please connect to an account first to manage {feature}.",
                f"Сначала подключитесь к аккаунту, чтобы управлять: {feature}.")
            )
            return False
        return True

    def _focus_chat_window(self):
        """Show and focus the chat window."""
        self._reveal_window(self.chat_window)

    def _handle_pronunciation_manager(self):
        """Handle Username Pronunciation from tray menu"""
        if not self._check_chat_ready(tr("username pronunciations", "произношением имён")):
            return
        self._focus_chat_window()
        self.chat_window.show_pronunciation_view()

    def _handle_ban_list(self):
        if not self._check_chat_ready(tr("the ban list", "списком забаненных")):
            return
        self._focus_chat_window()
        self.chat_window.show_ban_list_view()

    def _setup_global_hotkey(self):
        """Register the show/hide hotkey using the combo saved in settings (or the default)."""
        hotkey.hotkey_manager.activated.connect(self._on_hotkey_activated)
        combo = self.config.get("hotkey", "combo") or hotkey.DEFAULT_HOTKEY
        hotkey.hotkey_manager.register(combo)

    def _on_hotkey_activated(self):
        """Handle the global show/hide hotkey, called on the Qt thread."""
        QMetaObject.invokeMethod(self, "_toggle_chat_visibility", Qt.ConnectionType.QueuedConnection)

    @pyqtSlot()
    def _toggle_chat_visibility(self, ignore_active=False):
        """Toggle visibility of the active window"""
        window = self.chat_window or self._account_window
        if not window:
            return

        # Cache the active state BEFORE any window operations to avoid race conditions
        is_visible = window.isVisible()
        is_active = window.isActiveWindow()

        # Determine if we should hide the window
        should_hide = is_visible and (ignore_active or is_active)

        if should_hide:
            if window == self.chat_window:
                window.clear_new_messages_marker()
                window.teardown_presence_log_widget()
            window.hide()
        else:
            self._reveal_window(window)
            if window == self.chat_window:
                self.reset_unread()
                # Clear input field to remove any stray characters from hotkey
                if hasattr(window, 'input_field') and window.input_field:
                    QTimer.singleShot(50, window.input_field.clear)


def main():
    """Application entry point"""
    application = Application()
    sys.exit(application.run())


if __name__ == "__main__":
    main()

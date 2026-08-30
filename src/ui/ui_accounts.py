import json
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QMessageBox, QApplication, QCheckBox
)
from PyQt6.QtGui import QFont, QIcon, QPixmap, QKeyEvent, QGuiApplication
from PyQt6.QtCore import Qt, pyqtSignal, QSize, pyqtSlot, QEvent

from helpers.create import create_icon_button, set_theme, _render_svg_icon
from helpers.help import HelpPanel
from helpers.load import make_rounded_pixmap
from helpers.cache import get_cache
from helpers.config import Config
from helpers.fonts import get_font, FontType
from helpers.startup_manager import StartupManager
from core.accounts import AccountManager
from themes.theme import ThemeManager
from helpers.username_color_manager import (
    change_username_color,
    reset_username_color,
)
from ui.ui_settings import fill_resource_combo
from helpers.translate import tr, on_language_changed, TranslatableMixin


def _add_account_from_auth_data(account_manager, user_data: dict) -> bool:
    cookies = user_data.get('cookies')
    cookies_json = json.dumps(cookies) if cookies else None
    added = account_manager.add_account(
        user_id=str(user_data['id']),
        chat_username=user_data['login'],
        chat_password=user_data['pass'],
        avatar=user_data.get('avatar'),
        background=user_data.get('background'),
        session_cookies=cookies_json,
        set_active=True,
    )
    if not added and cookies_json:
        # Account already exists — still refresh its session cookies from this login
        account_manager.update_session_cookies(user_data['login'], cookies_json)
    return added


class AccountWindow(TranslatableMixin, QWidget):
    account_connected = pyqtSignal(dict)
    _avatar_loaded = pyqtSignal(str, QPixmap)

    def __init__(self, config=None):
        super().__init__()
        self._init_translatable()

        # Paths
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.icons_path = Path(__file__).parent.parent / "icons"

        # Config and theme
        self.config = config if config is not None else Config(str(self.config_path))
        self.theme_manager = ThemeManager(self.config)
        self.theme_manager.apply_theme()

        # Account manager
        self.account_manager = AccountManager(str(self.config_path))
        self.cache = get_cache()

        # Startup manager
        self.startup_manager = StartupManager()

        # Track current avatar loading to avoid race conditions
        self.current_loading_user_id = None

        # Get standard input height from config
        self.input_height = self._get_config('input_height', 48)

        self._avatar_loaded.connect(self._set_avatar)

        # Initialize UI
        self.initializeUI()
        self.load_accounts()

        # Set initial window height for Connect page
        self._adjust_window_height()

        # Force layout activation so width() reflects the real content size
        # (before the first show(), a top-level widget still has its
        # placeholder default size, which throws off centering)
        self.adjustSize()

        # Center window on screen now that its size is finalized
        self._center_on_screen()

        # Ensure the window itself holds focus so Tab reaches event() immediately
        self.setFocus()

        # Help panel
        self.help_panel = HelpPanel(self)

        on_language_changed(self._retranslate)

    def _get_config(self, key, default):
        """Safely get config value with default fallback"""
        if hasattr(self.config, 'data') and self.config.data:
            return self.config.data.get(key, default)
        return default

    def _set_input_height(self, widget):
        """Set standard height for input widgets"""
        widget.setFixedHeight(self.input_height)

    def initializeUI(self):
        window_title = tr("Account Manager", "Менеджер аккаунтов")
        self.setWindowTitle(window_title)
        self._register_tr(self.setWindowTitle, window_title)
        self.setMinimumWidth(280)
        set_theme(self.theme_manager.is_dark())
        self.setFont(get_font(FontType.UI))

        spacing = self._get_config('spacing', 10)
        margin = self._get_config('margin', 15)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(spacing)
        main_layout.setContentsMargins(margin, margin, margin, margin)
        self.setLayout(main_layout)

        # ===== CONNECT SECTION =====
        connect_text = tr("🔑 Connect", "🔑 Подключение")
        connect_label = QLabel(connect_text)
        connect_label.setFont(get_font(FontType.HEADER))
        main_layout.addWidget(connect_label)
        self._register_tr(connect_label.setText, connect_text)

        # Account selection row
        account_row = QHBoxLayout()
        account_row.setSpacing(self._get_config('spacing', 8))

        # Avatar
        avatar_tooltip = tr("Account", "Аккаунт")
        self.account_avatar = create_icon_button(
            self.icons_path, "user.svg", tooltip=avatar_tooltip
        )
        self._register_tr(self.account_avatar.setToolTip, avatar_tooltip)
        self.account_avatar.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.account_avatar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        account_row.addWidget(self.account_avatar)

        # Account dropdown
        self.account_dropdown = QComboBox()
        self.account_dropdown.setFont(get_font(FontType.UI))
        self._set_input_height(self.account_dropdown)
        self.account_dropdown.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.account_dropdown.currentIndexChanged.connect(self.update_avatar)

        # Offset dropdown popup to not cover the border
        original_show_popup = self.account_dropdown.showPopup
        def offset_popup():
            original_show_popup()
            popup = self.account_dropdown.view().window()
            if popup:
                pos = popup.pos()
                popup.move(pos.x(), pos.y() + 3)
        self.account_dropdown.showPopup = offset_popup
        account_row.addWidget(self.account_dropdown, stretch=1)
        main_layout.addLayout(account_row)

        # Actions row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(self._get_config('spacing', 8))

        # Connect button
        connect_button_tooltip = tr("Connect to chat (Enter / E)", "Подключиться к чату (Enter / E)")
        self.connect_button = create_icon_button(
            self.icons_path, "login.svg", tooltip=connect_button_tooltip
        )
        self.connect_button.clicked.connect(self.on_connect)
        self.connect_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        actions_row.addWidget(self.connect_button)
        self._register_tr(self.connect_button.setToolTip, connect_button_tooltip)

        # Color picker button
        color_button_tooltip = tr(
            "Username color (C: pick | Ctrl+C/Click: reset)",
            "Цвет ника (C: выбрать | Ctrl+C/клик: сбросить)",
        )
        self.color_button = create_icon_button(
            self.icons_path, "palette.svg",
            tooltip=color_button_tooltip
        )
        self.color_button.installEventFilter(self)
        self.color_button.clicked.connect(self.on_color_picker)
        self.color_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        actions_row.addWidget(self.color_button)
        self._register_tr(self.color_button.setToolTip, color_button_tooltip)

        # Remove button
        remove_button_tooltip = tr("Remove account (D)", "Удалить аккаунт (D)")
        self.remove_button = create_icon_button(
            self.icons_path, "trash.svg", tooltip=remove_button_tooltip
        )
        self.remove_button.clicked.connect(self.on_remove_account)
        self.remove_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        actions_row.addWidget(self.remove_button)
        self._register_tr(self.remove_button.setToolTip, remove_button_tooltip)

        # Web login button
        web_login_tooltip = tr("Add account via browser login (W)", "Добавить аккаунт через вход в браузере (W)")
        self.web_login_button = create_icon_button(
            self.icons_path, "globe.svg", tooltip=web_login_tooltip
        )
        self.web_login_button.clicked.connect(self.on_web_login)
        self.web_login_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        actions_row.addWidget(self.web_login_button)
        self._register_tr(self.web_login_button.setToolTip, web_login_tooltip)

        main_layout.addLayout(actions_row)

        # Auto-login checkbox
        auto_login_text = tr("1. Auto-login", "1. Автовход")
        self.auto_login_checkbox = QCheckBox(auto_login_text)
        self.auto_login_checkbox.setFont(get_font(FontType.UI))
        self.auto_login_checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.auto_login_checkbox.stateChanged.connect(self.on_auto_login_changed)
        self._register_tr(self.auto_login_checkbox.setText, auto_login_text)
        
        # Load current auto-login state
        auto_login = self.config.get("startup", "auto_login")
        if auto_login is None:
            auto_login = False
        self.auto_login_checkbox.setChecked(auto_login)
        main_layout.addWidget(self.auto_login_checkbox)

        # Start minimized to tray checkbox
        start_minimized_text = tr("2. Start minimized", "2. Запуск свёрнутым")
        self.start_minimized_checkbox = QCheckBox(start_minimized_text)
        self.start_minimized_checkbox.setFont(get_font(FontType.UI))
        self.start_minimized_checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.start_minimized_checkbox.stateChanged.connect(self.on_start_minimized_changed)
        self._register_tr(self.start_minimized_checkbox.setText, start_minimized_text)
        
        # Load current start minimized state
        start_minimized = self.config.get("startup", "start_minimized")
        if start_minimized is None:
            start_minimized = False
        self.start_minimized_checkbox.setChecked(start_minimized)
        main_layout.addWidget(self.start_minimized_checkbox)
        # Start with system checkbox
        start_with_system_text = tr("3. Start with system", "3. Запуск с системой")
        self.start_with_system_checkbox = QCheckBox(start_with_system_text)
        self.start_with_system_checkbox.setFont(get_font(FontType.UI))
        self.start_with_system_checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.start_with_system_checkbox.stateChanged.connect(self.on_start_with_system_changed)
        self._register_tr(self.start_with_system_checkbox.setText, start_with_system_text)

        # Load current start with system state
        self.start_with_system_checkbox.setChecked(self.startup_manager.is_enabled())
        main_layout.addWidget(self.start_with_system_checkbox)

        resource_row = QHBoxLayout()
        resource_row.setSpacing(self._get_config('spacing', 8))
        resource_label_text = tr("XMPP resource", "XMPP-ресурс")
        resource_label = QLabel(resource_label_text)
        resource_label.setFont(get_font(FontType.UI))
        resource_row.addWidget(resource_label, stretch=1)
        self._register_tr(resource_label.setText, resource_label_text)
        self.resource_combo = QComboBox()
        self.resource_combo.setFont(get_font(FontType.UI))
        self._set_input_height(self.resource_combo)
        self.resource_combo.setFixedWidth(100)
        self.resource_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        fill_resource_combo(
            self.resource_combo,
            self.config.get("server", "resource") or "web",
        )
        self.resource_combo.currentIndexChanged.connect(self.on_resource_changed)
        resource_row.addWidget(self.resource_combo)
        main_layout.addLayout(resource_row)

        main_layout.addStretch()

    _KEY_ACTION = {
        Qt.Key.Key_Return: 'connect',
        Qt.Key.Key_Enter:  'connect',
        Qt.Key.Key_E:      'connect',
        Qt.Key.Key_C:      'color',
        Qt.Key.Key_D:      'remove',
        Qt.Key.Key_W:      'web_login',
        Qt.Key.Key_1:      'toggle_1',
        Qt.Key.Key_2:      'toggle_2',
        Qt.Key.Key_3:      'toggle_3',
    }

    def event(self, ev):
        if (isinstance(ev, QKeyEvent)
                and ev.type() == QEvent.Type.KeyPress
                and ev.key() == Qt.Key.Key_Tab):
            count = self.account_dropdown.count()
            if count > 1:
                next_index = (self.account_dropdown.currentIndex() + 1) % count
                self.account_dropdown.setCurrentIndex(next_index)
            return True
        return super().event(ev)

    def keyPressEvent(self, event):
        key   = event.key()
        mods  = event.modifiers()
        ctrl  = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        if key == Qt.Key.Key_F1:
            self.help_panel.show_for_context('accounts_connect')
            return

        # Ignore combinations with other modifiers (Alt, Meta, ...)
        if mods and not ctrl and not shift:
            return super().keyPressEvent(event)

        vk = self._KEY_ACTION.get(key) or self._KEY_ACTION.get(event.nativeVirtualKey())
        if not vk:
            return super().keyPressEvent(event)

        if vk == 'connect':
            self.on_connect()
        elif vk == 'color':
            if ctrl:
                self.on_reset_color()
            else:
                self.on_color_picker()
        elif vk == 'remove':
            self.on_remove_account()
        elif vk == 'web_login':
            self.on_web_login()
        elif vk == 'toggle_1':
            self.auto_login_checkbox.setChecked(not self.auto_login_checkbox.isChecked())
        elif vk == 'toggle_2':
            self.start_minimized_checkbox.setChecked(not self.start_minimized_checkbox.isChecked())
        elif vk == 'toggle_3':
            self.start_with_system_checkbox.setChecked(not self.start_with_system_checkbox.isChecked())

    def _adjust_window_height(self):
        margins = self._get_config('margin', 30)
        label_height = self._get_config('label_height', 35)
        main_spacing = self._get_config('spacing', 10)
        button_padding = self._get_config('button_padding', 10)
        checkbox_height = 25
        total_height = (
            margins +
            label_height +
            main_spacing +
            self.input_height +
            main_spacing +
            self.input_height +
            main_spacing +
            checkbox_height +
            main_spacing +
            checkbox_height +
            main_spacing +
            checkbox_height +
            main_spacing +
            self.input_height +
            button_padding
        )
        self.setFixedHeight(total_height)

    def _center_on_screen(self):
        """Center the window on the current (or primary) screen."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(geo.center())
        self.move(frame.topLeft())

    def eventFilter(self, obj, event):
        if (hasattr(self, 'color_button')
                and obj == self.color_button
                and event.type() == QEvent.Type.MouseButtonPress):
            if event.button() == Qt.MouseButton.LeftButton:
                modifiers = QApplication.keyboardModifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    self.on_reset_color()
                    return True
        return super().eventFilter(obj, event)

    def on_color_picker(self):
        account = self.account_dropdown.currentData()
        if not account:
            QMessageBox.warning(self,
                tr("No Account", "Нет аккаунта"),
                tr("Please select an account first.", "Сначала выберите аккаунт.")
            )
            return
        success = change_username_color(self, self.account_manager, account, self.cache)
        if success:
            self.load_accounts()

    def on_reset_color(self):
        account = self.account_dropdown.currentData()
        if not account:
            QMessageBox.warning(self,
                tr("No Account", "Нет аккаунта"),
                tr("Please select an account first.", "Сначала выберите аккаунт.")
            )
            return
        success = reset_username_color(self, self.account_manager, account, self.cache)
        if success:
            self.load_accounts()


    def on_resource_changed(self, _index: int = 0):
        value = self.resource_combo.currentData()
        if value is None:
            return
        tip = self.resource_combo.itemData(
            self.resource_combo.currentIndex(), Qt.ItemDataRole.ToolTipRole
        )
        self.resource_combo.setToolTip(tip or "")
        previous = self.config.get("server", "resource") or "web"
        if value == previous:
            return
        self.config.set("server", "resource", value=value)
        print(f"📡 XMPP resource changed: {previous} → {value}")

    def on_auto_login_changed(self, state):
        auto_login = (state == Qt.CheckState.Checked.value)
        self.config.set("startup", "auto_login", value=auto_login)
        print(f"🔑 Auto-login {'enabled' if auto_login else 'disabled'}")

    def on_start_minimized_changed(self, state):
        start_minimized = (state == Qt.CheckState.Checked.value)
        self.config.set("startup", "start_minimized", value=start_minimized)
        print(f"🪟 Start minimized {'enabled' if start_minimized else 'disabled'}")

    def on_start_with_system_changed(self, state):
        start_with_system = (state == Qt.CheckState.Checked.value)
        if start_with_system:
            success = self.startup_manager.enable()
            if success:
                print("✅ Start with system enabled")
            else:
                QMessageBox.warning(
                    self, tr("Error", "Ошибка"),
                          tr("Failed to enable start with system. Please check permissions.",
                             "Не удалось включить запуск с системой. Проверьте права доступа.")
                )
                self.start_with_system_checkbox.setChecked(False)
        else:
            success = self.startup_manager.disable()
            if success:
                print("❌ Start with system disabled")
            else:
                QMessageBox.warning(
                    self, tr("Error", "Ошибка"),
                          tr("Failed to disable start with system. Please check permissions.",
                             "Не удалось отключить запуск с системой. Проверьте права доступа.")
                )
                self.start_with_system_checkbox.setChecked(True)

    def load_accounts(self):
        self.account_dropdown.clear()
        accounts = self.account_manager.list_accounts()

        if not accounts:
            self.account_dropdown.addItem(tr("No accounts available", "Нет доступных аккаунтов"))
            self.connect_button.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.color_button.setEnabled(False)
            return

        self.connect_button.setEnabled(True)
        self.remove_button.setEnabled(True)
        self.color_button.setEnabled(True)

        # Find active account index
        active_index = 0
        for i, account in enumerate(accounts):
            display_text = account['chat_username']
            self.account_dropdown.addItem(display_text, account)
            if account.get('active'):
                active_index = i

        # Set active account as current
        self.account_dropdown.setCurrentIndex(active_index)

    def update_avatar(self):
        account = self.account_dropdown.currentData()
        if account and account.get('chat_username'):
            self.account_manager.switch_account(account['chat_username'])

        if not account or not account.get('user_id'):
            # Reset to default user icon
            self.current_loading_user_id = None
            icon = _render_svg_icon(self.icons_path / "user.svg", 30)
            self.account_avatar.setIcon(icon)
            self.account_avatar.setIconSize(QSize(30, 30))
            self.account_avatar.setStyleSheet("QPushButton { background: transparent; border: none; }")
            return

        user_id = account['user_id']

        # Set this as the current loading user - prevents race conditions
        self.current_loading_user_id = user_id

        # Try to get from cache first
        cached_avatar = self.cache.get_avatar(user_id)
        if cached_avatar:
            # Only set if this is still the current user
            if self.current_loading_user_id == user_id:
                self._set_avatar(user_id, cached_avatar)
        else:
            # Set placeholder first
            icon = _render_svg_icon(self.icons_path / "user.svg", 30)
            self.account_avatar.setIcon(icon)
            self.account_avatar.setIconSize(QSize(30, 30))

            # Load async with race condition check
            def avatar_callback(uid: str, pixmap: QPixmap):
                # Only emit signal if this is still the current user being viewed
                if uid == self.current_loading_user_id:
                    self._avatar_loaded.emit(uid, pixmap)

            self.cache.load_avatar_async(user_id, avatar_callback, timeout=3)

    @pyqtSlot(str, QPixmap)
    def _set_avatar(self, user_id: str, pixmap: QPixmap):
        if user_id != self.current_loading_user_id:
            return

        if pixmap and not pixmap.isNull():
            rounded = make_rounded_pixmap(pixmap, 48, radius=8)
            self.account_avatar.setIcon(QIcon(rounded))
            self.account_avatar.setIconSize(QSize(48, 48))
            self.account_avatar.setStyleSheet(
                "QPushButton { background: transparent; border: none; padding: 0; }"
            )
        else:
            # Fallback to default icon
            icon = _render_svg_icon(self.icons_path / "user.svg", 30)
            self.account_avatar.setIcon(icon)
            self.account_avatar.setIconSize(QSize(30, 30))
            self.account_avatar.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def on_web_login(self):
        """Open browser login dialog to add an account."""
        from core.web_auth import LoginWebView
        dlg = LoginWebView(self)
        dlg.login_success.connect(self._on_web_login_success)
        dlg.exec()

    def _on_web_login_success(self, user_data: dict):
        if not user_data.get('id'):
            QMessageBox.critical(self,
                tr("Error", "Ошибка"),
                tr("Could not retrieve account data.", "Не удалось получить данные аккаунта.")
            )
            return
        added = _add_account_from_auth_data(self.account_manager, user_data)
        existing = self.account_manager.get_account_by_chat_username(user_data['login'])
        if added or existing:
            self.load_accounts()
        else:
            QMessageBox.critical(self,
                tr("Error", "Ошибка"),
                tr("Failed to save account.", "Не удалось сохранить аккаунт.")
            )

    def on_connect(self):
        if self.account_dropdown.count() == 0:
            QMessageBox.warning(self,
                tr("No Account", "Нет аккаунта"),
                tr("Please create an account first.", "Сначала создайте аккаунт.")
            )
            return

        # Get selected account
        account = self.account_dropdown.currentData()
        if account:
            # Emit signal with account data
            self.account_connected.emit(account)

    def on_remove_account(self):
        if self.account_dropdown.count() == 0:
            QMessageBox.warning(self,
                tr("No Account", "Нет аккаунта"),
                tr("No account to remove.", "Нет аккаунта для удаления.")
            )
            return

        # Confirm removal
        account = self.account_dropdown.currentData()
        reply = QMessageBox.question(
            self,
            tr("Confirm Removal", "Подтверждение удаления"),
            tr(
                f"Are you sure you want to remove account '{account['chat_username']}'?",
                f"Вы уверены, что хотите удалить аккаунт «{account['chat_username']}»?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Remove account
            if self.account_manager.remove_account(account['chat_username']):
                QMessageBox.information(self,
                    tr("Success", "Готово"),
                    tr("Account removed successfully.", "Аккаунт успешно удалён.")
                )
                self.load_accounts()
            else:
                QMessageBox.critical(self,
                    tr("Error", "Ошибка"),
                    tr("Failed to remove account.", "Не удалось удалить аккаунт.")
                )

    def _retranslate(self, _code=None):
        self._retranslate_all()
        self.load_accounts()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AccountWindow()
    window.show()
    sys.exit(app.exec())
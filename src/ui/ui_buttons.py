"""Scrollable side button panel for ChatWindow"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel,
    QGraphicsOpacityEffect, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal

from helpers.config import Config
from components.presence_badge import apply_counter_style
from helpers.create import (
    create_icon_button,
    _render_svg_icon,
    set_visual_active
)
from helpers.scroll.scrollable_buttons import ScrollableButtonContainer
from helpers.data import open_in_file_manager
from helpers.translate import tr, on_language_changed


class ButtonPanel(QWidget):
    """Vertical scrollable button panel with drag and wheel scroll support"""
    
    # Signals for button actions
    toggle_userlist_requested = pyqtSignal()
    switch_account_requested = pyqtSignal()
    show_banlist_requested = pyqtSignal()
    show_tracker_requested = pyqtSignal()
    toggle_voice_requested = pyqtSignal()
    pronunciation_requested = pyqtSignal()
    toggle_effects_requested = pyqtSignal()
    toggle_notification_requested = pyqtSignal()

    # Color management (change / reset / update from server)
    change_color_requested = pyqtSignal()
    reset_color_requested = pyqtSignal()

    toggle_theme_requested = pyqtSignal()
    reset_window_size_requested = pyqtSignal()
    show_window_presets_requested = pyqtSignal()
    toggle_always_on_top_requested = pyqtSignal()
    show_settings_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    reconnect_requested = pyqtSignal()
    join_room_requested = pyqtSignal()
    search_requested = pyqtSignal()

    def __init__(self, config: Config, icons_path: Path, theme_manager):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.theme_manager = theme_manager
        
        # Button references
        self.toggle_userlist_button = None
        self.switch_account_button = None
        self.ban_button = None
        self.tracker_button = None
        self.voice_button = None
        self.effects_button = None
        self.notification_button = None
        self.color_button = None
        self.theme_button = None
        self.reset_size_button = None
        self.always_on_top_button = None
        self.settings_button = None
        self.exit_button = None

        self._init_ui()
        self._create_buttons()
        on_language_changed(self._retranslate)

    def _init_ui(self):
        """Initialize the scrollable button panel UI"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setLayout(main_layout)

        # Scrollable container (vertical) – handles wheel + MMB drag internally
        self._scroll_container = ScrollableButtonContainer(
            Qt.Orientation.Vertical, config=self.config
        )

        main_layout.addWidget(self._scroll_container)

        # Set fixed width based on button size + margins from config
        button_size = 48
        btn_cfg = self.config.get("ui", "buttons") or {}
        if isinstance(btn_cfg, dict):
            button_size = btn_cfg.get("button_size", button_size)

        panel_margin = self.config.get("ui", "margins", "widget") or 5
        self.setFixedWidth(button_size + panel_margin * 2)

    def _create_button(self, icon_name: str, tooltip: str, callback):
        """Helper to create and add a button with consistent pattern"""
        button = create_icon_button(self.icons_path, icon_name, tooltip, config=self.config)
        button.clicked.connect(callback)
        self.add_button(button)
        return button

    def _get_notification_tooltip(self) -> str:
        muted = self.config.get("notification", "muted") or False
        if muted:
            return tr("Notifications: Disabled (N)", "Уведомления: выкл (N)")
        return tr("Notifications: Enabled (N)", "Уведомления: вкл (N)")

    def _get_effects_icon(self) -> str:
        """Get current effects icon based on state"""
        enabled = self.config.get("sound", "effects_enabled")
        if enabled is None:
            enabled = True
        return "volume-up.svg" if enabled else "volume-mute.svg"

    def _get_effects_tooltip(self) -> str:
        """Get current effects tooltip based on state"""
        enabled = self.config.get("sound", "effects_enabled")
        if enabled is None:
            enabled = True
        return (
            tr("Sound Effects: Enabled (M)", "Звуковые эффекты: вкл (M)")
            if enabled else
            tr("Sound Effects: Disabled (M)", "Звуковые эффекты: выкл (M)")
        )

    def _get_pin_icon(self) -> str:
        """Get current pin icon based on always-on-top state"""
        enabled = self.config.get("ui", "always_on_top") or False
        return "pin.svg" if enabled else "unpin.svg"

    def _get_pin_tooltip(self) -> str:
        enabled = self.config.get("ui", "always_on_top") or False
        return (
            tr("Always on Top: Enabled (T)", "Поверх всех окон: вкл (T)")
            if enabled else
            tr("Always on Top: Disabled (T)", "Поверх всех окон: выкл (T)")
        )

    def _tracker_base_tooltip(self) -> str:
        return tr("User Tracker (Ctrl+Shift+U)", "Трекер пользователей (Ctrl+Shift+U)")

    def _create_buttons(self):
        """Create all buttons for the panel"""
        self.toggle_userlist_button = self._create_button(
            "user.svg",
            tr("Toggle User List (U)", "Список пользователей (U)"),
            self.toggle_userlist_requested.emit
        )
        self.toggle_userlist_button._is_visually_active = True

        self.switch_account_button = self._create_button(
            "user-switch.svg",
            tr("Switch Account (Ctrl+U)", "Сменить аккаунт (Ctrl+U)"),
            self.switch_account_requested.emit
        )

        self.ban_button = self._create_button(
            "user-blocked.svg",
            tr("Show Ban List (B)", "Список забаненных (B)"),
            lambda: self.show_banlist_requested.emit()
        )

        self.tracker_button = self._create_button(
            "user-star.svg",
            self._tracker_base_tooltip(),
            lambda: self.show_tracker_requested.emit()
        )
        self._tracker_unread = 0
        self._tracker_last_type = "join"
        self._tracker_badge = QLabel(self.tracker_button)
        self._tracker_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tracker_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        apply_counter_style(
            self._tracker_badge, "join",
            is_dark=self.theme_manager.is_dark(),
        )
        self._tracker_badge.hide()
        self._apply_tracker_enabled_state()

        self.join_room_button = self._create_button(
            "chat-new.svg",
            tr("Join / Create Room (Ctrl+J)", "Войти / создать комнату (Ctrl+J)"),
            lambda: self.join_room_requested.emit()
        )

        self.search_button = self._create_button(
            "search.svg",
            tr("Toggle search (S / Ctrl+F)", "Поиск (S / Ctrl+F)"),
            lambda: self.search_requested.emit()
        )

        self.voice_button = self._create_button(
            "user-voice.svg",
            tr("Toggle Voice Sound (V) (RMB for Username Pronunciation (P))",
               "Голосовой звук (V) (ПКМ — произношение имён (P))"),
            lambda: self.toggle_voice_requested.emit()
        )
        self.voice_button.installEventFilter(self)

        effects_icon = self._get_effects_icon()
        self.effects_button = self._create_button(
            effects_icon,
            self._get_effects_tooltip(),
            lambda: self.toggle_effects_requested.emit()
        )

        # Notification mute toggle (on/off); single icon, dimmed when disabled
        self.notification_button = self._create_button(
            "notification.svg",
            self._get_notification_tooltip(),
            lambda: self.toggle_notification_requested.emit()
        )
        muted = self.config.get("notification", "muted") or False
        self.set_button_state(self.notification_button, not muted)

        self.color_button = self._create_button(
            "palette.svg",
            tr("Username color (C: pick | Ctrl+C/Click: reset)",
               "Цвет имени (C: выбрать | Ctrl+C/клик: сбросить)"),
            lambda: self.change_color_requested.emit()
        )
        # Install event filter to capture Ctrl+Click / Shift+Click
        self.color_button.installEventFilter(self)

        is_dark = self.theme_manager.is_dark()
        theme_icon = "moon.svg" if is_dark else "sun.svg"
        self.theme_button = self._create_button(
            theme_icon,
            self._theme_tooltip(is_dark),
            self.toggle_theme_requested.emit
        )

        self.reset_size_button = self._create_button(
            "aspect-ratio.svg",
            tr("Reset Window Size and Position to Default (R) (RMB for Presets)",
               "Сбросить размер и позицию окна (R) (ПКМ — пресеты)"),
            lambda: self.reset_window_size_requested.emit()
        )
        # Install event filter for RMB click (presets)
        self.reset_size_button.installEventFilter(self)

        pin_icon = self._get_pin_icon()
        self.always_on_top_button = self._create_button(
            pin_icon,
            self._get_pin_tooltip(),
            lambda: self.toggle_always_on_top_requested.emit()
        )

        self.settings_button = self._create_button(
            "settings.svg",
            tr("Settings (Ctrl+,)", "Настройки (Ctrl+,)"),
            lambda: self.show_settings_requested.emit()
        )

        self.data_folder_button = self._create_button(
            "folder.svg",
            tr("Open Data Folder (KG_Chat_Data)", "Открыть папку данных (KG_Chat_Data)"),
            lambda: open_in_file_manager(),
        )

        self.exit_button = self._create_button(
            "door-closed.svg",
            tr("Exit Application", "Выход"),
            lambda: self.exit_requested.emit()
        )

        self.reconnect_button = self._create_button(
            "reload.svg",
            tr("Reconnect to Chat", "Переподключиться к чату"),
            lambda: self.reconnect_requested.emit()
        )
        self.reconnect_button.setVisible(False)

    def _theme_tooltip(self, is_dark: bool) -> str:
        if is_dark:
            return tr("Switch to Light Mode (Ctrl+T)", "Переключить на светлую тему (Ctrl+T)")
        return tr("Switch to Dark Mode (Ctrl+T)", "Переключить на тёмную тему (Ctrl+T)")

    def _retranslate(self, _code=None):
        if self.toggle_userlist_button:
            self.toggle_userlist_button.setToolTip(
                tr("Toggle User List (U)", "Список пользователей (U)"))
        if self.switch_account_button:
            self.switch_account_button.setToolTip(
                tr("Switch Account (Ctrl+U)", "Сменить аккаунт (Ctrl+U)"))
        if self.ban_button:
            self.ban_button.setToolTip(
                tr("Show Ban List (B)", "Список забаненных (B)"))
        if self.join_room_button:
            self.join_room_button.setToolTip(
                tr("Join / Create Room (Ctrl+J)", "Войти / создать комнату (Ctrl+J)"))
        if self.search_button:
            self.search_button.setToolTip(
                tr("Toggle search (S / Ctrl+F)", "Поиск (S / Ctrl+F)"))
        if self.voice_button:
            self.voice_button.setToolTip(
                tr("Toggle Voice Sound (V) (RMB for Username Pronunciation (P))",
                   "Голосовой звук (V) (ПКМ — произношение имён (P))"))
        if self.color_button:
            self.color_button.setToolTip(
                tr("Username color (C: pick | Ctrl+C/Click: reset)",
                   "Цвет имени (C: выбрать | Ctrl+C/клик: сбросить)"))
        if self.reset_size_button:
            self.reset_size_button.setToolTip(
                tr("Reset Window Size and Position to Default (R) (RMB for Presets)",
                   "Сбросить размер и позицию окна (R) (ПКМ — пресеты)"))
        if self.settings_button:
            self.settings_button.setToolTip(tr("Settings (Ctrl+,)", "Настройки (Ctrl+,)"))
        if self.data_folder_button:
            self.data_folder_button.setToolTip(
                tr("Open Data Folder (KG_Chat_Data)", "Открыть папку данных (KG_Chat_Data)"))
        if self.exit_button:
            self.exit_button.setToolTip(tr("Exit Application", "Выход"))
        if self.reconnect_button:
            self.reconnect_button.setToolTip(
                tr("Reconnect to Chat", "Переподключиться к чату"))

        self.update_notification_button_icon()
        self.update_effects_button_icon()
        self.update_pin_button_icon()
        self.update_theme_button_icon()
        self._refresh_tracker_badge()

    def set_button_state(self, button, is_active: bool):
        """Set visual state for any button without disabling it"""
        set_visual_active(button, is_active)

    def _tracker_enabled(self) -> bool:
        value = self.config.get("user_tracker", "enabled")
        return True if value is None else bool(value)

    def _apply_tracker_enabled_state(self):
        enabled = self._tracker_enabled()
        set_visual_active(self.tracker_button, enabled)
        if not enabled:
            self._tracker_badge.hide()
        else:
            self._refresh_tracker_badge()

    def bump_tracker_unread(self, event_type: str = None):
        if not self._tracker_enabled():
            return
        self._tracker_unread += 1
        if event_type:
            self._tracker_last_type = event_type
        self._refresh_tracker_badge()

    def clear_tracker_unread(self):
        self._tracker_unread = 0
        self._refresh_tracker_badge()

    def refresh_tracker_badge_style(self):
        """Re-apply dim/badge after settings change (enabled, show_unread_badge, size)."""
        self._apply_tracker_enabled_state()

    def _refresh_tracker_badge(self):
        n = self._tracker_unread
        base = self._tracker_base_tooltip()
        enabled = self._tracker_enabled()
        show = self.config.get("user_tracker", "show_unread_badge")
        if show is None:
            show = True
        if not enabled or n <= 0 or not show:
            self._tracker_badge.hide()
            if not enabled:
                tip = tr(f"{base} — tracking disabled", f"{base} — отслеживание выкл")
            elif n <= 0:
                tip = base
            else:
                tip = tr(f"{base} — {n} new", f"{base} — {n} новых")
            self.tracker_button.setToolTip(tip)
            return
        size = self.config.get("ui", "chat", "badge_font_size")
        try:
            size = int(size) if size is not None else 9
        except (TypeError, ValueError):
            size = 9
        size = max(8, min(18, size))
        apply_counter_style(
            self._tracker_badge, self._tracker_last_type, font_size=size,
            is_dark=self.theme_manager.is_dark(),
        )
        self._tracker_badge.setText("99+" if n > 99 else str(n))
        self._tracker_badge.adjustSize()
        self._tracker_badge.move(1, self.tracker_button.height() - self._tracker_badge.height() - 1)
        self._tracker_badge.show()
        self._tracker_badge.raise_()
        self.tracker_button.setToolTip(tr(f"{base} — {n} new", f"{base} — {n} новых"))

    def update_theme_button_icon(self):
        """Update theme button icon after theme change"""
        if not self.theme_button:
            return
        is_dark = self.theme_manager.is_dark()
        self.theme_button._icon_name = "moon.svg" if is_dark else "sun.svg"
        self.theme_button.setToolTip(self._theme_tooltip(is_dark))

    def update_notification_button_icon(self):
        """Dim notification button when muted; keep the same notification.svg icon."""
        if not self.notification_button:
            return
        muted = self.config.get("notification", "muted") or False
        self.set_button_state(self.notification_button, not muted)
        self.notification_button.setToolTip(self._get_notification_tooltip())

    def update_effects_button_icon(self):
        """Update effects button icon after state change"""
        if not self.effects_button:
            return
        new_icon_name = self._get_effects_icon()
        self.effects_button._icon_name = new_icon_name
        new_icon = _render_svg_icon(self.icons_path / new_icon_name, self.effects_button._icon_size)
        self.effects_button.setIcon(new_icon)
        self.effects_button.setToolTip(self._get_effects_tooltip())

    def update_pin_button_icon(self):
        """Update pin button icon after always-on-top state change"""
        if not self.always_on_top_button:
            return
        new_icon_name = self._get_pin_icon()
        self.always_on_top_button._icon_name = new_icon_name
        new_icon = _render_svg_icon(
            self.icons_path / new_icon_name, self.always_on_top_button._icon_size
        )
        self.always_on_top_button.setIcon(new_icon)
        self.always_on_top_button.setToolTip(self._get_pin_tooltip())

    def add_button(self, button):
        """Add a button to the panel (before the stretch)"""
        self._scroll_container.add_widget(button)

    def remove_button(self, button):
        """Remove a button from the panel"""
        self._scroll_container.remove_widget(button)

    def clear_buttons(self):
        """Remove all buttons from the panel"""
        self._scroll_container.clear_widgets()

    def eventFilter(self, obj, event):
        """Handle specialized button clicks (RMB, Ctrl+Click, Shift+Click)"""
        # Handle reset_size_button RMB click -> open presets dialog
        if obj == self.reset_size_button and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self.show_window_presets_requested.emit()
                return True
        
        # Handle color button special clicks
        if obj == self.color_button and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                modifiers = QApplication.keyboardModifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    self.reset_color_requested.emit()
                    return True

        # Handle voice button RMB click -> open Username Pronunciation
        if obj == self.voice_button and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self.pronunciation_requested.emit()
                return True

        return super().eventFilter(obj, event)

    def update_theme(self):
        pass

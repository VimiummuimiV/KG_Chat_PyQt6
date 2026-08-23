"""Scrollable side button panel for ChatWindow"""
from pathlib import Path
from PyQt6.QtWidgets import(
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
    update_color_requested = pyqtSignal()

    toggle_theme_requested = pyqtSignal()
    reset_window_size_requested = pyqtSignal()
    show_window_presets_requested = pyqtSignal()
    toggle_always_on_top_requested = pyqtSignal()
    show_settings_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    reconnect_requested = pyqtSignal()
    join_room_requested = pyqtSignal()
    
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
            return "Notifications: Disabled (N)"
        return "Notifications: Enabled (N)"
    
    def _get_effects_icon(self) -> str:
        """Get current effects icon based on state"""
        enabled = self.config.get("sound", "effects_enabled")
        if enabled is None:
            enabled = True  # Default to enabled
        return "volume-up.svg" if enabled else "volume-mute.svg"
    
    def _get_effects_tooltip(self) -> str:
        """Get current effects tooltip based on state"""
        enabled = self.config.get("sound", "effects_enabled")
        if enabled is None:
            enabled = True
        return "Sound Effects: Enabled (M)" if enabled else "Sound Effects: Disabled (M)"
    
    def _get_pin_icon(self) -> str:
        """Get current pin icon based on always-on-top state"""
        enabled = self.config.get("ui", "always_on_top") or False
        return "pin.svg" if enabled else "unpin.svg"
    
    def _get_pin_tooltip(self) -> str:
        """Get current pin tooltip based on always-on-top state"""
        enabled = self.config.get("ui", "always_on_top") or False
        return "Always on Top: Enabled (T)" if enabled else "Always on Top: Disabled (T)"
    
    def _create_buttons(self):
        """Create all buttons for the panel"""
        # Toggle userlist button
        self.toggle_userlist_button = self._create_button(
            "user.svg",
            "Toggle User List (U)",
            self.toggle_userlist_requested.emit
        )
        self.toggle_userlist_button._is_visually_active = True
        
        # Switch account button
        self.switch_account_button = self._create_button(
            "user-switch.svg",
            "Switch Account (Ctrl+U)",
            self.switch_account_requested.emit
        )

        # Ban List button
        self.ban_button = self._create_button(
            "user-blocked.svg",
            "Show Ban List (B)",
            lambda: self.show_banlist_requested.emit()
        )

        self.tracker_button = self._create_button(
            "user-star.svg",
            "User Tracker (Ctrl+Shift+U)",
            lambda: self.show_tracker_requested.emit()
        )
        self._tracker_unread = 0
        self._tracker_last_type = "join"
        self._tracker_badge = QLabel(self.tracker_button)
        self._tracker_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tracker_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        apply_counter_style(self._tracker_badge, "join")
        self._tracker_badge.hide()

        self.join_room_button = self._create_button(
            "chat-new.svg",
            "Join / Create Room",
            lambda: self.join_room_requested.emit()
        )

        # Voice toggle button
        self.voice_button = self._create_button(
            "user-voice.svg",
            "Toggle Voice Sound (V) (Ctrl+Click to open Username Pronunciation (P))",
            lambda: self.toggle_voice_requested.emit()
        )
        # Install event filter to catch Ctrl+Click for pronunciation
        self.voice_button.installEventFilter(self)

        # Effects sound toggle
        effects_icon = self._get_effects_icon()
        effects_tooltip = self._get_effects_tooltip()
        self.effects_button = self._create_button(
            effects_icon,
            effects_tooltip,
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

        # Color picker button
        self.color_button = self._create_button(
            "palette.svg",
            "Change username color (C | Ctrl+C/Click: Reset | Shift+C/Click: Update from Server)",
            lambda: self.change_color_requested.emit()
        )
        # Install event filter to capture Ctrl+Click / Shift+Click
        self.color_button.installEventFilter(self)

        # Theme button
        is_dark = self.theme_manager.is_dark()
        theme_icon = "moon.svg" if is_dark else "sun.svg"
        theme_tooltip = "Switch to Light Mode (Ctrl+T)" if is_dark else "Switch to Dark Mode (Ctrl+T)"
        self.theme_button = self._create_button(theme_icon, theme_tooltip, self.toggle_theme_requested.emit)

        # Reset window size button
        self.reset_size_button = self._create_button(
            "aspect-ratio.svg",
            "Reset Window Size and Position to Default (R) (RMB for Presets)",
            lambda: self.reset_window_size_requested.emit()
        )
        # Install event filter for RMB click (presets)
        self.reset_size_button.installEventFilter(self)
        
        # Always on top button
        pin_icon = self._get_pin_icon()
        pin_tooltip = self._get_pin_tooltip()
        self.always_on_top_button = self._create_button(
            pin_icon,
            pin_tooltip,
            lambda: self.toggle_always_on_top_requested.emit()
        )

        # Settings button
        self.settings_button = self._create_button(
            "settings.svg",
            "Settings",
            lambda: self.show_settings_requested.emit()
        )

        # Exit application button
        self.exit_button = self._create_button(
            "door-closed.svg",
            "Exit Application",
            lambda: self.exit_requested.emit()
        )

        # Manual reconnect button (hidden by default, shown when auto-reconnect fails)
        self.reconnect_button = self._create_button(
            "reload.svg",
            "Reconnect to Chat",
            lambda: self.reconnect_requested.emit()
        )
        self.reconnect_button.setVisible(False)
    
    def set_button_state(self, button, is_active: bool):
        """Set visual state for any button without disabling it"""
        set_visual_active(button, is_active)

    def bump_tracker_unread(self, event_type: str = None):
        self._tracker_unread += 1
        if event_type:
            self._tracker_last_type = event_type
        self._refresh_tracker_badge()

    def clear_tracker_unread(self):
        self._tracker_unread = 0
        self._refresh_tracker_badge()

    def refresh_tracker_badge_style(self):
        """Re-apply badge visibility/size/color - call when related settings change,
        so an already-visible badge updates without waiting for the next event."""
        self._refresh_tracker_badge()

    def _refresh_tracker_badge(self):
        n = self._tracker_unread
        base = "User Tracker (Ctrl+Shift+U)"
        show = self.config.get("user_tracker", "show_badge")
        if show is None:
            show = True
        if n <= 0 or not show:
            self._tracker_badge.hide()
            self.tracker_button.setToolTip(base if n <= 0 else f"{base} — {n} new")
            return
        size = self.config.get("user_tracker", "badge_font_size")
        try:
            size = int(size) if size is not None else 9
        except (TypeError, ValueError):
            size = 9
        apply_counter_style(self._tracker_badge, self._tracker_last_type, font_size=size)
        self._tracker_badge.setText("99+" if n > 99 else str(n))
        self._tracker_badge.adjustSize()
        self._tracker_badge.move(1, self.tracker_button.height() - self._tracker_badge.height() - 1)
        self._tracker_badge.show()
        self._tracker_badge.raise_()
        self.tracker_button.setToolTip(f"{base} — {n} new")

    def update_theme_button_icon(self):
        """Update theme button icon after theme change"""
        is_dark = self.theme_manager.is_dark()
        self.theme_button._icon_name = "moon.svg" if is_dark else "sun.svg"
        self.theme_button.setToolTip("Switch to Light Mode (Ctrl+T)" if is_dark else "Switch to Dark Mode (Ctrl+T)")
    
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
        new_tooltip = self._get_effects_tooltip()
        
        # Update icon name
        self.effects_button._icon_name = new_icon_name
        
        # Render and set the new icon
        new_icon = _render_svg_icon(self.icons_path / new_icon_name, self.effects_button._icon_size)
        self.effects_button.setIcon(new_icon)
        
        # Update tooltip
        self.effects_button.setToolTip(new_tooltip)
    
    def update_pin_button_icon(self):
        """Update pin button icon after always-on-top state change"""
        if not self.always_on_top_button:
            return
        
        new_icon_name = self._get_pin_icon()
        new_tooltip = self._get_pin_tooltip()
        
        # Update icon name
        self.always_on_top_button._icon_name = new_icon_name
        
        # Render and set the new icon
        new_icon = _render_svg_icon(self.icons_path / new_icon_name, self.always_on_top_button._icon_size)
        self.always_on_top_button.setIcon(new_icon)
        
        # Update tooltip
        self.always_on_top_button.setToolTip(new_tooltip)
    
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
        
        # Handle color button special clicks (Ctrl+Click / Shift+Click)
        if obj == self.color_button and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                modifiers = QApplication.keyboardModifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    self.reset_color_requested.emit()
                    return True
                elif modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self.update_color_requested.emit()
                    return True

        # Handle voice button Ctrl+Click -> open Username Pronunciation
        if obj == self.voice_button and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                modifiers = QApplication.keyboardModifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    self.pronunciation_requested.emit()
                    return True

        return super().eventFilter(obj, event)
    
    def update_theme(self):
        pass
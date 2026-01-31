"""Scrollable side button panel for ChatWindow"""
from pathlib import Path
from PyQt6.QtWidgets import(
    QWidget, QVBoxLayout, QScrollArea, QFrame,
    QGraphicsOpacityEffect, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QWheelEvent, QMouseEvent

from helpers.config import Config
from helpers.create import create_icon_button, _render_svg_icon


class ButtonPanel(QWidget):
    """Vertical scrollable button panel with drag and wheel scroll support"""
    
    # Signals for button actions
    toggle_userlist_requested = pyqtSignal()
    toggle_theme_requested = pyqtSignal()
    switch_account_requested = pyqtSignal()
    toggle_voice_requested = pyqtSignal()
    pronunciation_requested = pyqtSignal()
    show_banlist_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    toggle_effects_requested = pyqtSignal()
    toggle_notification_requested = pyqtSignal()
    # Color management (change / reset / update from server)
    change_color_requested = pyqtSignal()
    reset_color_requested = pyqtSignal()
    update_color_requested = pyqtSignal()
    
    def __init__(self, config: Config, icons_path: Path, theme_manager):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.theme_manager = theme_manager
        
        # Drag scroll state
        self._drag_start_pos = None
        self._scroll_start_value = None
        self._is_dragging = False
        
        # Button references
        self.toggle_userlist_button = None
        self.switch_account_button = None
        self.theme_button = None
        self.notification_button = None
        self.color_button = None
        self.voice_button = None
        self.effects_button = None
        self.ban_button = None
        self.exit_button = None
        
        self._init_ui()
        self._create_buttons()
    
    def _init_ui(self):
        """Initialize the scrollable button panel UI"""
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setLayout(main_layout)
        
        # Create scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Container for buttons
        self.button_container = QWidget()
        self.button_layout = QVBoxLayout()
        button_spacing = self.config.get("ui", "buttons", "spacing") or 8
        self.button_layout.setSpacing(button_spacing)
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.button_layout.addStretch()  # Push buttons to top
        self.button_container.setLayout(self.button_layout)
        
        self.scroll_area.setWidget(self.button_container)
        main_layout.addWidget(self.scroll_area)
        
        # Enable mouse tracking for drag scroll
        self.scroll_area.viewport().installEventFilter(self)
        
        # Set fixed width based on button size and margins from config
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
    
    def _get_notification_icon(self) -> str:
        """Get current notification icon based on state"""
        mode = self.config.get("notification", "mode") or "stack"
        muted = self.config.get("notification", "muted") or False
        
        if muted:
            return "notification-disabled.svg"
        elif mode == "replace":
            return "notification-replace-mode.svg"
        else:  # stack
            return "notification-stack-mode.svg"
    
    def _get_notification_tooltip(self) -> str:
        """Get current notification tooltip based on state"""
        mode = self.config.get("notification", "mode") or "stack"
        muted = self.config.get("notification", "muted") or False
        
        if muted:
            return "Notifications: Muted (Click to enable Stack mode)"
        elif mode == "replace":
            return "Notifications: Replace mode (Click to mute)"
        else:  # stack
            return "Notifications: Stack mode (Click to switch to Replace)"
    
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
        return "Effects Sound: Enabled (Click to disable)" if enabled else "Effects Sound: Disabled (Click to enable)"
    
    def _create_buttons(self):
        """Create all buttons for the panel"""
        # Toggle userlist button
        self.toggle_userlist_button = self._create_button(
            "user.svg",
            "Toggle User List",
            self.toggle_userlist_requested.emit
        )
        self.toggle_userlist_button._is_visually_active = True
        
        # Switch account button
        self.switch_account_button = self._create_button(
            "user-switch.svg",
            "Switch Account",
            self.switch_account_requested.emit
        )

        # Ban List button
        self.ban_button = self._create_button(
            "user-blocked.svg",
            "Show Ban List",
            lambda: self.show_banlist_requested.emit()
        )

        # Voice toggle button
        self.voice_button = self._create_button(
            "user-voice.svg",
            "Toggle Voice Sound (Ctrl+Click to open Username Pronunciation)",
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

        # Notification toggle button (3-state cycle: Stack → Replace → Muted)
        notification_icon = self._get_notification_icon()
        notification_tooltip = self._get_notification_tooltip()
        self.notification_button = self._create_button(
            notification_icon,
            notification_tooltip,
            lambda: self.toggle_notification_requested.emit()
        )

        # Color picker button
        self.color_button = self._create_button(
            "palette.svg",
            "Change username color (Ctrl+Click to Reset, Shift+Click to Update from Server)",
            lambda: self.change_color_requested.emit()
        )
        # Install event filter to capture Ctrl+Click / Shift+Click
        self.color_button.installEventFilter(self)

        # Theme button
        is_dark = self.theme_manager.is_dark()
        theme_icon = "moon.svg" if is_dark else "sun.svg"
        theme_tooltip = "Switch to Light Mode" if is_dark else "Switch to Dark Mode"
        self.theme_button = self._create_button(theme_icon, theme_tooltip, self.toggle_theme_requested.emit)

        # Exit application button
        self.exit_button = self._create_button(
            "door-open.svg",
            "Exit Application",
            lambda: self.exit_requested.emit()
        )
    
    def set_button_state(self, button, is_active: bool):
        """Set visual state for any button without disabling it"""
        if not button:
            return
        
        button._is_visually_active = is_active
        
        if is_active:
            button.setGraphicsEffect(None)
        else:
            opacity_effect = QGraphicsOpacityEffect()
            opacity_effect.setOpacity(0.5)
            button.setGraphicsEffect(opacity_effect)
    
    def update_theme_button_icon(self):
        """Update theme button icon after theme change"""
        is_dark = self.theme_manager.is_dark()
        self.theme_button._icon_name = "moon.svg" if is_dark else "sun.svg"
        self.theme_button.setToolTip("Switch to Light Mode" if is_dark else "Switch to Dark Mode")
    
    def update_notification_button_icon(self):
        """Update notification button icon after state change"""
        if not self.notification_button:
            return
        
        new_icon_name = self._get_notification_icon()
        new_tooltip = self._get_notification_tooltip()
        
        # Update icon name
        self.notification_button._icon_name = new_icon_name
        
        # Render and set the new icon
        new_icon = _render_svg_icon(self.icons_path / new_icon_name, self.notification_button._icon_size)
        self.notification_button.setIcon(new_icon)
        
        # Update tooltip
        self.notification_button.setToolTip(new_tooltip)
    
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
    
    def add_button(self, button):
        """Add a button to the panel (before the stretch)"""
        count = self.button_layout.count()
        self.button_layout.insertWidget(count - 1, button)
    
    def remove_button(self, button):
        """Remove a button from the panel"""
        self.button_layout.removeWidget(button)
        button.setParent(None)
    
    def clear_buttons(self):
        """Remove all buttons from the panel"""
        while self.button_layout.count() > 1:  # Keep the stretch
            item = self.button_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
    
    def eventFilter(self, obj, event):
        """Handle mouse wheel, drag scrolling and specialized button clicks"""
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

        if obj == self.scroll_area.viewport():
            if event.type() == QEvent.Type.Wheel:
                return self._handle_wheel(event)
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.MiddleButton:
                    return self._handle_mouse_press(event)
            elif event.type() == QEvent.Type.MouseMove:
                return self._handle_mouse_move(event)
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.MiddleButton:
                    return self._handle_mouse_release(event)
        
        return super().eventFilter(obj, event)
    
    def _handle_wheel(self, event: QWheelEvent) -> bool:
        """Handle mouse wheel scrolling"""
        scrollbar = self.scroll_area.verticalScrollBar()
        delta = event.angleDelta().y()
        scroll_amount = -delta // 2
        scrollbar.setValue(scrollbar.value() + scroll_amount)
        return True
    
    def _handle_mouse_press(self, event: QMouseEvent) -> bool:
        """Handle mouse press for drag scrolling"""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_dragging = True
            self._drag_start_pos = event.pos()
            self._scroll_start_value = self.scroll_area.verticalScrollBar().value()
            self.scroll_area.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return True
        return False
    
    def _handle_mouse_move(self, event: QMouseEvent) -> bool:
        """Handle mouse move for drag scrolling"""
        if self._is_dragging and self._drag_start_pos is not None:
            delta = event.pos() - self._drag_start_pos
            scrollbar = self.scroll_area.verticalScrollBar()
            scrollbar.setValue(self._scroll_start_value - delta.y())
            return True
        return False
    
    def _handle_mouse_release(self, event: QMouseEvent) -> bool:
        """Handle mouse release to end drag scrolling"""
        if event.button() == Qt.MouseButton.MiddleButton and self._is_dragging:
            self._is_dragging = False
            self._drag_start_pos = None
            self._scroll_start_value = None
            self.scroll_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            return True
        return False
    
    def update_theme(self):
        """Update theme for all buttons in the panel"""
        pass

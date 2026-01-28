"""Scrollable side button panel for ChatWindow"""
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame
from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QWheelEvent, QMouseEvent

from helpers.config import Config
from helpers.create import create_icon_button


class ButtonPanel(QWidget):
    """Vertical scrollable button panel with drag and wheel scroll support"""
    
    # Signals for button actions
    toggle_userlist_requested = pyqtSignal()
    toggle_theme_requested = pyqtSignal()
    
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
        self.theme_button = None
        
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
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
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
        # Default to large button size (48px) to match create_icon_button defaults
        button_size = 48
        
        # Try to read from config (matching create_icon_button logic)
        btn_cfg = self.config.get("ui", "buttons") or {}
        if isinstance(btn_cfg, dict):
            button_size = btn_cfg.get("button_size", button_size)
        
        # Get widget margin from config
        panel_margin = self.config.get("ui", "margins", "widget") or 5
        
        self.setFixedWidth(button_size + panel_margin * 2)
    
    def _create_buttons(self):
        """Create all buttons for the panel"""
        # Toggle userlist button
        self.toggle_userlist_button = create_icon_button(
            self.icons_path,
            "user.svg",
            "Toggle User List",
            config=self.config
        )
        self.toggle_userlist_button.clicked.connect(self.toggle_userlist_requested.emit)
        self.add_button(self.toggle_userlist_button)

        # Switch account button
        self.switch_account_button = create_icon_button(
            self.icons_path,
            "switch_user.svg",
            "Switch Account",
            config=self.config
        )
        self.switch_account_button.clicked.connect(self._on_switch_account)
        self.add_button(self.switch_account_button)
        
        # Theme button
        is_dark = self.theme_manager.is_dark()
        theme_icon = "moon.svg" if is_dark else "sun.svg"
        self.theme_button = create_icon_button(
            self.icons_path,
            theme_icon,
            "Switch to Light Mode" if is_dark else "Switch to Dark Mode",
            config=self.config
        )
        self.theme_button.clicked.connect(self.toggle_theme_requested.emit)
        self.add_button(self.theme_button)
    
    def update_theme_button_icon(self):
        """Update theme button icon after theme change"""
        is_dark = self.theme_manager.is_dark()
        self.theme_button._icon_name = "moon.svg" if is_dark else "sun.svg"
        self.theme_button.setToolTip("Switch to Light Mode" if is_dark else "Switch to Dark Mode")
    
    def add_button(self, button):
        """Add a button to the panel (before the stretch)"""
        # Insert before the stretch item (which is always last)
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
        """Handle mouse wheel and drag scrolling"""
        if obj == self.scroll_area.viewport():
            if event.type() == QEvent.Type.Wheel:
                return self._handle_wheel(event)
            elif event.type() == QEvent.Type.MouseButtonPress:
                return self._handle_mouse_press(event)
            elif event.type() == QEvent.Type.MouseMove:
                return self._handle_mouse_move(event)
            elif event.type() == QEvent.Type.MouseButtonRelease:
                return self._handle_mouse_release(event)
        
        return super().eventFilter(obj, event)
    
    def _handle_wheel(self, event: QWheelEvent) -> bool:
        """Handle mouse wheel scrolling"""
        scrollbar = self.scroll_area.verticalScrollBar()
        
        # Get wheel delta (positive = scroll up, negative = scroll down)
        delta = event.angleDelta().y()
        
        # Calculate scroll amount (adjust multiplier for scroll speed)
        scroll_amount = -delta // 2  # Divide by 2 for smoother scrolling
        
        # Apply scroll
        new_value = scrollbar.value() + scroll_amount
        scrollbar.setValue(new_value)
        
        return True  # Event handled
    
    def _handle_mouse_press(self, event: QMouseEvent) -> bool:
        """Handle mouse press for drag scrolling"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.pos()
            self._scroll_start_value = self.scroll_area.verticalScrollBar().value()
            self.scroll_area.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return True
        return False
    
    def _handle_mouse_move(self, event: QMouseEvent) -> bool:
        """Handle mouse move for drag scrolling"""
        if self._is_dragging and self._drag_start_pos is not None:
            # Calculate distance moved
            delta = event.pos() - self._drag_start_pos
            
            # Update scroll position (invert Y to make drag feel natural)
            scrollbar = self.scroll_area.verticalScrollBar()
            new_value = self._scroll_start_value - delta.y()
            scrollbar.setValue(new_value)
            
            return True
        return False
    
    def _handle_mouse_release(self, event: QMouseEvent) -> bool:
        """Handle mouse release to end drag scrolling"""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            self._drag_start_pos = None
            self._scroll_start_value = None
            self.scroll_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            return True
        return False
    
    def update_theme(self):
        """Update theme for all buttons in the panel"""
        # Buttons will update themselves via update_all_icons()
        pass
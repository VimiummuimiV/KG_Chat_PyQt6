"""Help panel for video player and image viewer with styled keyboard shortcuts and mouse controls"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


# ============================================================================
# HELPER COMPONENTS (REUSABLE STYLED LABELS)
# ============================================================================

class KeyLabel(QLabel):
    """Styled label for keyboard keys"""
    
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                color: #00d4ff;
                border: 1px solid #00d4ff;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
                font-family: monospace;
            }
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(60)


class DescriptionLabel(QLabel):
    """Styled label for descriptions"""
    
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
                padding: 4px 8px;
            }
        """)


class SectionLabel(QLabel):
    """Styled label for section headers"""
    
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet("""
            QLabel {
                color: #4dd999;
                padding: 12px 0px 8px 0px;
                line-height: 1.5;
            }
        """)
        self.setMinimumHeight(35)


class Separator(QFrame):
    """Horizontal separator line"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setStyleSheet("""
            QFrame {
                color: #404040;
                margin: 8px 0px;
            }
        """)


class MouseActionLabel(QLabel):
    """Styled label for mouse actions"""
    
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                color: #ffa500;
                border: 1px solid #ffa500;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
            }
        """)
        self.setMinimumWidth(120)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


# ============================================================================
# HELP PANEL CLASS
# ============================================================================

class HelpPanel(QWidget):
    """Enhanced help panel showing keyboard shortcuts and mouse controls"""
    
    def __init__(self, parent=None, viewer_type: str = "video"):
        """
        Initialize help panel
        
        Args:
            parent: Parent widget
            viewer_type: Type of viewer ("video" or "image")
        """
        super().__init__(parent)
        self.viewer_type = viewer_type
        
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(f"{viewer_type.title()} Player Help" if viewer_type == "video" else f"{viewer_type.title()} Viewer Help")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        # Dark theme background
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)
        
        # Title
        title_text = "Video Player Controls" if viewer_type == "video" else "Image Viewer Controls"
        title = QLabel(title_text)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("QLabel { color: #00d4ff; padding-bottom: 10px; }")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)
        
        # Get controls based on viewer type
        keyboard_shortcuts, mouse_controls = self._get_controls()
        
        # Keyboard shortcuts section
        main_layout.addWidget(SectionLabel("⌨️ Keyboard Shortcuts"))
        main_layout.addWidget(Separator())
        
        for key, description in keyboard_shortcuts:
            row = QHBoxLayout()
            row.setSpacing(12)
            row.addWidget(KeyLabel(key))
            row.addWidget(DescriptionLabel(description), 1)
            main_layout.addLayout(row)
        
        # Mouse controls section
        main_layout.addSpacing(10)
        main_layout.addWidget(SectionLabel("🖱️ Mouse Controls"))
        main_layout.addWidget(Separator())
        
        for action, description in mouse_controls:
            row = QHBoxLayout()
            row.setSpacing(12)
            row.addWidget(MouseActionLabel(action))
            row.addWidget(DescriptionLabel(description), 1)
            main_layout.addLayout(row)
        
        # Footer
        main_layout.addSpacing(10)
        footer = QLabel("Press F1 or Esc to close")
        footer.setStyleSheet("""
            QLabel {
                color: #808080;
                font-size: 11px;
                font-style: italic;
                padding-top: 10px;
            }
        """)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(footer)
        
        self.adjustSize()
        self.setFixedSize(self.size())
    
    def _get_controls(self):
        """Get keyboard shortcuts and mouse controls based on viewer type"""
        if self.viewer_type == "video":
            return VIDEO_KEYBOARD_SHORTCUTS, VIDEO_MOUSE_CONTROLS
        else:
            return IMAGE_KEYBOARD_SHORTCUTS, IMAGE_MOUSE_CONTROLS
    
    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() in (Qt.Key.Key_F1, Qt.Key.Key_Escape):
            self.hide()
        else:
            super().keyPressEvent(event)


# ============================================================================
# CONTROLS DEFINITIONS (BOTTOM OF FILE)
# ============================================================================

# Video Player Controls
VIDEO_KEYBOARD_SHORTCUTS = [
    ("Space", "Play / Pause"),
    ("F", "Toggle Fullscreen"),
    ("M", "Mute / Unmute"),
    ("J", "Seek backward 10s"),
    ("L", "Seek forward 10s"),
    ("Esc", "Exit fullscreen / Close"),
    ("F1", "Show / Hide this help"),
]

VIDEO_MOUSE_CONTROLS = [
    ("Click video", "Play / Pause"),
    ("Double-click", "Toggle Fullscreen"),
    ("Wheel on video", "Seek ±5 seconds"),
    ("Wheel on progress", "Seek ±5 seconds"),
    ("Wheel on volume", "Adjust volume ±5%"),
    ("Hover volume", "Show volume slider"),
]

# Image Viewer Controls
IMAGE_KEYBOARD_SHORTCUTS = [
    ("Space", "Close image"),
    ("Esc", "Close image"),
    ("F1", "Show / Hide this help"),
]

IMAGE_MOUSE_CONTROLS = [
    ("Left drag", "Pan / Move image"),
    ("Ctrl + Left drag", "Scale image (up/down)"),
    ("Wheel", "Zoom in / out"),
    ("Right click", "Close image"),
]
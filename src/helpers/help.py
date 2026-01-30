"""Help panel for video player and image viewer with styled keyboard shortcuts and mouse controls"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt
from pathlib import Path

from helpers.config import Config


class HelpPanel(QWidget):
    """Compact help panel showing keyboard shortcuts and mouse controls"""
    
    def __init__(self, parent=None, viewer_type: str = "video"):
        super().__init__(parent)
        self.viewer_type = viewer_type
        
        config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.config = Config(str(config_path))
        
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(f"{viewer_type.title()} {'Player' if viewer_type == 'video' else 'Viewer'} Help")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        self._build()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.config = Config(str(Path(__file__).parent.parent / "settings" / "config.json"))
        self._build()
    
    def _build(self):
        """Build/rebuild UI with current theme"""
        # Clear existing layout
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                child = old_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    self._clear_layout(child.layout())
            QWidget().setLayout(old_layout)
        
        theme = self.config.get("ui", "theme") or "dark"
        is_dark = (theme == "dark")
        
        # Professional muted color palette
        if is_dark:
            bg = "#1e1e1e"
            title = "#6bb6d6"      # Muted cyan
            section = "#6ba885"    # Muted green
            text = "#c8c8c8"       # Softer white
            footer = "#888888"     # Medium gray
            sep = "#404040"
            kb_bg = "#5a8fb4"      # Muted blue
            kb_text = "#1a1a1a"
            mouse_bg = "#c9954d"   # Muted amber
            mouse_text = "#1a1a1a"
        else:
            bg = "#ffffff"
            title = "#3a8fb0"      # Muted cyan
            section = "#4a9570"    # Muted green
            text = "#4a4a4a"       # Softer black
            footer = "#707070"     # Medium gray
            sep = "#d0d0d0"
            kb_bg = "#7ba8c7"      # Soft blue
            kb_text = "#1a1a1a"
            mouse_bg = "#d9a866"   # Soft orange
            mouse_text = "#1a1a1a"
        
        self.setStyleSheet(f"QWidget {{background-color: {bg};}}")
        
        # Create new layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        
        # Title
        title_label = QLabel(f"{'Video Player' if self.viewer_type == 'video' else 'Image Viewer'} Controls")
        title_label.setStyleSheet(f"color: {title}; font-size: 14px; font-weight: bold; padding-bottom: 8px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        kb, mouse = (VIDEO_KB, VIDEO_MOUSE) if self.viewer_type == "video" else (IMAGE_KB, IMAGE_MOUSE)
        
        # Keyboard section
        kb_section = QLabel("Keyboard Shortcuts")
        kb_section.setStyleSheet(f"color: {section}; font-size: 13px; font-weight: bold; padding: 8px 0 4px 0;")
        layout.addWidget(kb_section)
        
        kb_sep = QFrame()
        kb_sep.setFrameShape(QFrame.Shape.HLine)
        kb_sep.setStyleSheet(f"color: {sep}; margin: 4px 0;")
        layout.addWidget(kb_sep)
        
        for key, desc in kb:
            layout.addLayout(self._row(key, desc, kb_bg, kb_text, 60, text))
        
        # Mouse section
        layout.addSpacing(8)
        
        mouse_section = QLabel("Mouse Controls")
        mouse_section.setStyleSheet(f"color: {section}; font-size: 13px; font-weight: bold; padding: 8px 0 4px 0;")
        layout.addWidget(mouse_section)
        
        mouse_sep = QFrame()
        mouse_sep.setFrameShape(QFrame.Shape.HLine)
        mouse_sep.setStyleSheet(f"color: {sep}; margin: 4px 0;")
        layout.addWidget(mouse_sep)
        
        for action, desc in mouse:
            layout.addLayout(self._row(action, desc, mouse_bg, mouse_text, 110, text))
        
        # Footer
        footer_label = QLabel("Press F1 or Esc to close")
        footer_label.setStyleSheet(f"color: {footer}; font-size: 11px; font-style: italic; padding-top: 8px;")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer_label)
        
        self.adjustSize()
        self.setFixedSize(self.size())
    
    def _clear_layout(self, layout):
        """Recursively clear a layout"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())
    
    def _row(self, key_text, desc_text, badge_bg, badge_text, min_width, desc_color):
        row = QHBoxLayout()
        row.setSpacing(10)
        
        key = QLabel(key_text)
        key.setStyleSheet(f"background-color: {badge_bg}; color: {badge_text}; border-radius: 4px; padding: 3px 8px; font-weight: bold;")
        key.setMinimumWidth(min_width)
        key.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        desc = QLabel(desc_text)
        desc.setStyleSheet(f"color: {desc_color}; font-size: 12px; padding: 3px 8px;")
        
        row.addWidget(key)
        row.addWidget(desc, 1)
        return row
    
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_F1, Qt.Key.Key_Escape):
            self.hide()
        else:
            super().keyPressEvent(event)


VIDEO_KB = [
    ("Space", "Play / Pause"),
    ("F", "Toggle Fullscreen"),
    ("M", "Mute / Unmute"),
    ("J", "Seek backward 10s"),
    ("L", "Seek forward 10s"),
    ("Esc", "Exit fullscreen / Close"),
    ("F1", "Show / Hide this help"),
]

VIDEO_MOUSE = [
    ("Click video", "Play / Pause"),
    ("Double-click", "Toggle Fullscreen"),
    ("Wheel on video", "Seek ±5 seconds"),
    ("Wheel on progress", "Seek ±5 seconds"),
    ("Wheel on volume", "Adjust volume ±5%"),
    ("Hover volume", "Show volume slider"),
    ("Right click", "Close video"),
]

IMAGE_KB = [
    ("Space", "Close image"),
    ("Esc", "Close image"),
    ("F1", "Show / Hide this help"),
]

IMAGE_MOUSE = [
    ("Left drag", "Pan / Move image"),
    ("Ctrl + Left drag", "Scale image (up/down)"),
    ("Wheel", "Zoom in / out"),
    ("Right click", "Close image"),
]
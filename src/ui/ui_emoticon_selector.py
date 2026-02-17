"""Emoticon selector widget for choosing emoticons"""
from pathlib import Path
from typing import List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QScrollArea, QGridLayout, QLabel, QStackedWidget, QApplication
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QMovie, QCursor, QIcon

from helpers.emoticons import EmoticonManager


class EmoticonButton(QPushButton):
    """Button displaying an animated emoticon"""
    emoticon_clicked = pyqtSignal(str, bool)

    def __init__(self, emoticon_path: Path, emoticon_name: str, is_dark: bool):
        super().__init__()
        self.emoticon_name = emoticon_name
        self.emoticon_path = emoticon_path
        self.is_dark = is_dark
        self.movie = None

        self.setFixedSize(QSize(60, 60))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(f":{emoticon_name}:")

        self._update_style()
        self._load_emoticon()

    def _update_style(self):
        hover_bg = "rgba(255, 255, 255, 0.1)" if self.is_dark else "rgba(0, 0, 0, 0.1)"
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                padding: 2px;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                border-radius: 4px;
            }}
        """)

    def _load_emoticon(self):
        """Load and animate the emoticon GIF"""
        if not self.emoticon_path.exists():
            return
       
        # Create QMovie and parent to QApplication to prevent garbage collection
        self.movie = QMovie(str(self.emoticon_path))
        try:
            # Parent to QApplication instance to keep alive
            self.movie.setParent(QApplication.instance())
        except:
            # Fallback to button if QApplication not available
            self.movie.setParent(self)
       
        # Set cache mode first for better performance
        self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
       
        # Set speed to 100% (default)
        self.movie.setSpeed(100)
       
        # Get first frame to set icon size
        if self.movie.jumpToFrame(0):
            pixmap = self.movie.currentPixmap()
            if not pixmap.isNull():
                self.setIcon(QIcon(pixmap))
                self.setIconSize(pixmap.size())
       
        # Connect frame updates
        self.movie.frameChanged.connect(self._on_frame_changed)
       
        # Start animation
        self.movie.start()
       
        # Verify it's running
        if self.movie.state() != QMovie.MovieState.Running:
            # Try starting again if it didn't start
            self.movie.jumpToFrame(0)
            self.movie.start()

    def _on_frame_changed(self, frame_number):
        """Update button icon when movie frame changes"""
        if self.movie:
            pixmap = self.movie.currentPixmap()
            if not pixmap.isNull():
                self.setIcon(QIcon(pixmap))

    def mousePressEvent(self, event):
        """Handle click with Ctrl detection"""
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            self.emoticon_clicked.emit(self.emoticon_name, bool(ctrl_pressed))
        super().mousePressEvent(event)

    def resume_animation(self):
        """Resume animation - force restart or recreate if missing"""
        if not self.movie:
            self._load_emoticon()
            return

        self.movie.stop()
        self.movie.jumpToFrame(0)
        self.movie.start()
        if self.movie.state() != QMovie.MovieState.Running:
            self.movie.start()

    def update_theme(self, new_path: Path, is_dark: bool):
        """Update button for new theme"""
        self.is_dark = is_dark
        self._update_style()
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.emoticon_path = new_path
        self._load_emoticon()

    def cleanup(self):
        """Clean up movie resources"""
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None

class EmoticonGroup(QWidget):
    """Widget for displaying a group of emoticons"""
    emoticon_clicked = pyqtSignal(str, bool)

    def __init__(self, group_name: str, emoticons: List[tuple], is_dark: bool):
        super().__init__()
        self.group_name = group_name
        self.is_dark = is_dark
        self.buttons = []

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.setLayout(layout)
       
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(scroll)
       
        # Container with grid
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        container.setLayout(container_layout)
        scroll.setWidget(container)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        container_layout.addLayout(grid)
        container_layout.addStretch()
       
        # Add emoticons (6 per row)
        cols = 6
        for idx, (name, path) in enumerate(emoticons):
            if not self._is_valid(path):
                continue

            row, col = idx // cols, idx % cols
            btn = EmoticonButton(path, name, self.is_dark)
            btn.emoticon_clicked.connect(self.emoticon_clicked.emit)
            self.buttons.append(btn)
            grid.addWidget(btn, row, col, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def _is_valid(self, path: Path) -> bool:
        """Quick validation"""
        try:
            return path.exists() and path.stat().st_size > 100
        except:
            return False

    def resume_animations(self):
        """Resume all button animations"""
        for btn in self.buttons:
            btn.resume_animation()

    def update_theme(self, manager: EmoticonManager, is_dark: bool):
        """Update group for new theme"""
        self.is_dark = is_dark
        for btn in self.buttons:
            new_path = manager.get_emoticon_path(btn.emoticon_name)
            btn.update_theme(new_path, is_dark)

    def cleanup(self):
        """Clean up all buttons"""
        for btn in self.buttons:
            btn.cleanup()

class EmoticonSelectorWidget(QWidget):
    """Widget for selecting emoticons with icon-based navigation"""
    emoticon_selected = pyqtSignal(str)

    def __init__(self, config, emoticon_manager: EmoticonManager, icons_path: Path):
        super().__init__()
        self.config = config
        self.emoticon_manager = emoticon_manager
        self.icons_path = icons_path

        self.recent_emoticons = config.get("ui", "recent_emoticons") or []
        self.group_indices = {}
        self.nav_buttons = {}
        self.recent_buttons = []
        self.group_widgets = []

        self._init_ui()
       
        # Restore visibility
        visible = config.get("ui", "emoticon_selector_visible")
        self.setVisible(visible if visible is not None else False)

    def _init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
       
        # Get theme colors
        theme = self.config.get("ui", "theme")
        self.is_dark_theme = (theme == "dark")

        if self.is_dark_theme:
            bg_color = "#1b1b1b"
            content_bg = "#1b1b1b"
            border_color = "#3D3D3D"
        else:
            bg_color = "#EEEEEE"
            content_bg = "#EEEEEE"
            border_color = "#CCCCCC"

        self.setStyleSheet(f"""
            EmoticonSelectorWidget {{
                background: {bg_color};
                border: 2px solid {border_color};
                border-radius: 10px;
            }}
        """)
       
        # Navigation bar
        self.nav_container = QWidget()
        self.nav_container.setStyleSheet(f"""
            QWidget {{
                background: {bg_color};
                border: none;
                border-bottom: 1px solid {border_color};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(10, 10, 10, 10)
        nav_layout.setSpacing(6)
        self.nav_container.setLayout(nav_layout)
        layout.addWidget(self.nav_container)
       
        # Install event filter for wheel navigation
        self.nav_container.installEventFilter(self)
       
        # Create nav buttons
        self._create_nav_button("⭐", "recent", "Recent", nav_layout, active=True)

        for group_name, (emoji, key) in {
            'Army': ('🪖', 'army'),
            'Boys': ('👦', 'boys'),
            'Christmas': ('🎄', 'christmas'),
            'Girls': ('👧', 'girls'),
            'Halloween': ('🎃', 'halloween'),
            'Inlove': ('❤️', 'inlove')
        }.items():
            self._create_nav_button(emoji, key, group_name, nav_layout)

        nav_layout.addStretch()
       
        # Content area
        self.content_container = QWidget()
        self.content_container.setStyleSheet(f"""
            QWidget {{
                background: {content_bg};
                border: none;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }}
        """)
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.content_container.setLayout(content_layout)
        layout.addWidget(self.content_container, stretch=1)
       
        # Stacked widget
        self.stacked_content = QStackedWidget()
        self.stacked_content.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        content_layout.addWidget(self.stacked_content, stretch=1)
       
        # Add content
        self._create_recent_content()
        self._create_group_contents()

    def _create_nav_button(self, emoji: str, key: str, tooltip: str, layout: QHBoxLayout, active: bool = False):
        """Create a navigation button"""
        btn = QPushButton(emoji)
        btn.setFixedSize(48, 48)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip(tooltip)

        self._update_nav_button_style(btn, active)
        btn.clicked.connect(lambda: self._switch_to_group(key))
        self.nav_buttons[key] = btn
        layout.addWidget(btn)

    def _update_nav_button_style(self, btn: QPushButton, active: bool):
        accent = "#e28743" if self.is_dark_theme else "#154c79"
        active_bg = "#303134" if self.is_dark_theme else "#E0E0E0"
        inactive_bg = "#1b1b1b" if self.is_dark_theme else "#EEEEEE"
        hover_bg = "#3A3B3F" if self.is_dark_theme else "#D0D0D0"
        hover_border = "#555" if self.is_dark_theme else "#999"

        style = f"""
            QPushButton {{
                background: {active_bg if active else inactive_bg};
                border: 2px solid {accent if active else 'transparent'};
                border-radius: 8px;
                font-size: 22px;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                {'' if active else f'border: 2px solid {hover_border};'}
            }}
        """
        btn.setStyleSheet(style)

    def _create_recent_content(self):
        """Create recent emoticons content"""
        self.recent_widget = QWidget()
        recent_layout = QVBoxLayout()
        recent_layout.setContentsMargins(8, 8, 8, 8)
        recent_layout.setSpacing(8)
        self.recent_widget.setLayout(recent_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        recent_layout.addWidget(scroll)

        self.recent_container = QWidget()
        self.recent_layout = QVBoxLayout()
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(0)
        self.recent_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.recent_container.setLayout(self.recent_layout)
        scroll.setWidget(self.recent_container)

        self.recent_grid = QGridLayout()
        self.recent_grid.setSpacing(6)
        self.recent_grid.setContentsMargins(0, 0, 0, 0)
        self.recent_grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.recent_layout.addLayout(self.recent_grid)
        self.recent_layout.addStretch()

        self._populate_recent_emoticons()

        self.group_indices['recent'] = self.stacked_content.count()
        self.stacked_content.addWidget(self.recent_widget)

    def _populate_recent_emoticons(self):
        """Populate recent emoticons grid"""
        # Clean up old buttons
        for btn in self.recent_buttons:
            btn.cleanup()
        self.recent_buttons.clear()
       
        # Clear existing widgets
        while self.recent_grid.count():
            item = self.recent_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
       
        # Add recent (6 per row)
        cols = 6
        for idx, name in enumerate(self.recent_emoticons):
            path = self.emoticon_manager.get_emoticon_path(name)
            if not path:
                continue

            row, col = idx // cols, idx % cols
            btn = EmoticonButton(path, name, self.is_dark_theme)
            btn.emoticon_clicked.connect(self._on_emoticon_clicked)
            self.recent_buttons.append(btn)
            self.recent_grid.addWidget(btn, row, col, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
       
        # Placeholder if empty
        if not self.recent_emoticons:
            placeholder = QLabel("No recent emoticons yet")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #888; padding: 20px;")
            self.recent_grid.addWidget(placeholder, 0, 0, 1, 6)

    def _create_group_contents(self):
        """Create content for each emoticon group"""
        groups = self.emoticon_manager.get_groups()

        for group_name in ['Army', 'Boys', 'Christmas', 'Girls', 'Halloween', 'Inlove']:
            if group_name not in groups:
                continue

            group_widget = EmoticonGroup(group_name, groups[group_name], self.is_dark_theme)
            group_widget.emoticon_clicked.connect(self._on_emoticon_clicked)
            self.group_widgets.append(group_widget)

            key = group_name.lower()
            self.group_indices[key] = self.stacked_content.count()
            self.stacked_content.addWidget(group_widget)

    def _switch_to_group(self, key: str):
        """Switch to a different group"""
        current_idx = self.stacked_content.currentIndex()
        for btn_key, btn in self.nav_buttons.items():
            is_active = (btn_key == key)
            self._update_nav_button_style(btn, is_active)

        if key in self.group_indices:
            self.stacked_content.setCurrentIndex(self.group_indices[key])

    def eventFilter(self, obj, event):
        """Handle mouse wheel events on navigation container"""
        if obj == self.nav_container and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            current_idx = self.stacked_content.currentIndex()
            total = self.stacked_content.count()

            new_idx = (current_idx - 1) % total if delta > 0 else (current_idx + 1) % total

            for key, idx in self.group_indices.items():
                if idx == new_idx:
                    self._switch_to_group(key)
                    break

            return True

        return super().eventFilter(obj, event)

    def _on_emoticon_clicked(self, emoticon_name: str, ctrl_pressed: bool):
        """Handle emoticon button click"""
        self._add_to_recent(emoticon_name)
        self.emoticon_selected.emit(emoticon_name)

        if ctrl_pressed:
            self.setVisible(False)
            self.config.set("ui", "emoticon_selector_visible", value=False)

    def _add_to_recent(self, emoticon_name: str):
        """Add emoticon to recent list"""
        if emoticon_name in self.recent_emoticons:
            self.recent_emoticons.remove(emoticon_name)

        self.recent_emoticons.insert(0, emoticon_name)
        self.recent_emoticons = self.recent_emoticons[:20]

        self.config.set("ui", "recent_emoticons", value=self.recent_emoticons)
        self._populate_recent_emoticons()

    def update_theme(self):
        """Update theme colors"""
        theme = self.config.get("ui", "theme")
        self.is_dark_theme = (theme == "dark")
    
        # Update emoticon manager theme
        self.emoticon_manager.set_theme(self.is_dark_theme)
    
        # Update colors
        if self.is_dark_theme:
            bg_color = "#1b1b1b"
            border_color = "#3D3D3D"
            content_bg = "#1b1b1b"
        else:
            bg_color = "#EEEEEE"
            border_color = "#CCCCCC"
            content_bg = "#EEEEEE"

        self.setStyleSheet(f"""
            EmoticonSelectorWidget {{
                background: {bg_color};
                border: 2px solid {border_color};
                border-radius: 10px;
            }}
        """)

        if hasattr(self, 'nav_container'):
            self.nav_container.setStyleSheet(f"""
                QWidget {{
                    background: {bg_color};
                    border: none;
                    border-bottom: 1px solid {border_color};
                    border-top-left-radius: 10px;
                    border-top-right-radius: 10px;
                }}
            """)
        if hasattr(self, 'content_container'):
            self.content_container.setStyleSheet(f"""
                QWidget {{
                    background: {content_bg};
                    border: none;
                    border-bottom-left-radius: 10px;
                    border-bottom-right-radius: 10px;
                }}
            """)

        current_idx = self.stacked_content.currentIndex()
        for key, btn in self.nav_buttons.items():
            is_active = (self.group_indices.get(key) == current_idx)
            self._update_nav_button_style(btn, is_active)

        for group_widget in self.group_widgets:
            group_widget.update_theme(self.emoticon_manager, self.is_dark_theme)

        for btn in self.recent_buttons:
            new_path = self.emoticon_manager.get_emoticon_path(btn.emoticon_name)
            btn.update_theme(new_path, self.is_dark_theme)

        if 'recent' in self.group_indices:
            self._switch_to_group('recent')

    def toggle_visibility(self):
        """Toggle visibility and save state"""
        new_visible = not self.isVisible()
        self.setVisible(new_visible)
        self.config.set("ui", "emoticon_selector_visible", value=new_visible)

        if new_visible:
            QTimer.singleShot(50, self.resume_animations)

    def resume_animations(self):
        """Resume all emoticon animations in the selector"""
        for btn in self.recent_buttons:
            btn.resume_animation()
        for group_widget in self.group_widgets:
            group_widget.resume_animations()

    def cleanup(self):
        """Clean up all emoticon buttons"""
        for btn in self.recent_buttons:
            btn.cleanup()
        for widget in self.group_widgets:
            widget.cleanup()
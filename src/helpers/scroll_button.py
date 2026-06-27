"""Reusable scroll-to-bottom button controller for list views"""
from pathlib import Path
from PyQt6.QtWidgets import QListView, QGraphicsOpacityEffect
from PyQt6.QtCore import QObject, QTimer, QPropertyAnimation, QEvent, pyqtSignal
from helpers.config import Config
from helpers.create import create_icon_button
from helpers.scroll import scroll

OPACITY_DEFAULT = 0.35
OPACITY_HOVER   = 1.0
FADE_DURATION   = 180  # ms


class ScrollToBottomButton(QObject):
    """Floating scroll-to-bottom icon button for QListView."""
    clicked_scroll = pyqtSignal()
    
    def __init__(self, list_view: QListView, parent=None):
        super().__init__(parent)  # Parent the QObject properly
        self.list_view = list_view
        
        # Paths
        base_path = Path(__file__).parent.parent
        icons_path = base_path / "icons"
        config_path = base_path / "settings" / "config.json"
        
        # Load config
        self.config = Config(str(config_path))
        
        # Create themed icon button
        self.button = create_icon_button(
            icons_path=icons_path,
            icon_name="arrow-down.svg",
            tooltip="Scroll to bottom",
            size_type="large",
            config=self.config
        )
        self.button.setParent(parent)  # Parent the actual button widget
        self.button.hide()

        # Opacity effect shared by all animations
        self._effect = QGraphicsOpacityEffect(self.button)
        self._effect.setOpacity(0.0)
        self.button.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(FADE_DURATION)
        self.button.installEventFilter(self)

        # Scroll threshold
        self.hide_threshold = int(self.config.get("ui", "scroll_button_threshold") or 100)
        
        # Scroll detection
        if self.list_view:
            self.list_view.verticalScrollBar().valueChanged.connect(self._on_scroll)
        
        # Position update timer
        self.position_timer = QTimer(self)  # Parent timer to the QObject
        self.position_timer.timeout.connect(self._update_position)
        self.position_timer.start(100)
        
        # Click behavior
        self.button.clicked.connect(self._scroll_to_bottom)
    
    def _animate_opacity(self, target: float):
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(target)
        self._anim.start()

    def eventFilter(self, obj, event):
        if obj is self.button:
            if event.type() == QEvent.Type.Enter:
                self._animate_opacity(OPACITY_HOVER)
            elif event.type() == QEvent.Type.Leave:
                self._animate_opacity(OPACITY_DEFAULT)
        return super().eventFilter(obj, event)

    def _on_scroll(self, value: int):
        """Show/hide button based on scroll position"""
        if not self.list_view:
            return
        scrollbar = self.list_view.verticalScrollBar()
        far_from_bottom = scrollbar.maximum() - value > self.hide_threshold

        if far_from_bottom and not self.button.isVisible():
            self.button.show()
            self._animate_opacity(OPACITY_DEFAULT)
        elif not far_from_bottom and self.button.isVisible():
            self._anim.finished.connect(self._hide_after_fade)
            self._animate_opacity(0.0)

    def _hide_after_fade(self):
        self._anim.finished.disconnect(self._hide_after_fade)
        self.button.hide()
    
    def _update_position(self):
        """Keep button centered vertically and aligned right"""
        if not self.list_view or not self.button.isVisible():
            return
        try:
            padding = 10 
            viewport = self.list_view.viewport()
            
            # Right aligned
            x = viewport.width() - self.button.width() - padding
            
            # Center vertically in viewport (not considering offsets)
            y = (viewport.height() - self.button.height()) // 2
            
            # Map viewport position to list_view coordinates
            viewport_pos = viewport.mapTo(self.list_view, viewport.rect().topLeft())
            
            # Apply the viewport offset to both x and y
            final_x = viewport_pos.x() + x
            final_y = viewport_pos.y() + y
            
            self.button.move(final_x, final_y)
        except RuntimeError:
            pass
    
    def _scroll_to_bottom(self):
        """Scroll the list view to bottom"""
        if not self.list_view:
            return
        scroll(self.list_view, mode="bottom", delay=0)
        self.clicked_scroll.emit()
    
    def cleanup(self):
        """Stop timers and disconnect signals"""
        if self.position_timer:
            self.position_timer.stop()
        if self.list_view:
            try:
                self.list_view.verticalScrollBar().valueChanged.disconnect(
                    self._on_scroll
                )
            except (RuntimeError, TypeError):
                pass
        if self.button:
            self.button.hide()
            self.button.setParent(None)

"""Font size scaler for real-time font adjustments via Ctrl+Scroll or Ctrl+Plus/Minus"""
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication


class FontScaler(QObject):
    """
    Manages text font size scaling with Ctrl+Scroll or Ctrl+Plus/Minus.
    Header font remains unchanged.
    """
    
    # Signal emitted when font sizes change
    font_size_changed = pyqtSignal()
    
    # Font size constraints for text only
    TEXT_MIN = 12
    TEXT_MAX = 24
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # Load initial text size from config
        self._text_size = self.config.get("ui", "text_font_size") or 17
        
        # Validate size
        self._validate_size()
    
    def _validate_size(self):
        """Ensure size is within bounds"""
        self._text_size = max(self.TEXT_MIN, min(self.TEXT_MAX, self._text_size))
    
    def get_text_size(self) -> int:
        """Get current text font size"""
        return self._text_size
    
    def scale_up(self):
        """Increase font size by 1 point"""
        if self._text_size < self.TEXT_MAX:
            self._text_size += 1
            self._save()
    
    def scale_down(self):
        """Decrease font size by 1 point"""
        if self._text_size > self.TEXT_MIN:
            self._text_size -= 1
            self._save()
    
    def _save(self):
        """Save to config and notify listeners"""
        self.config.set("ui", "text_font_size", value=self._text_size)
        self.font_size_changed.emit()


def install_font_scaler(widget, font_scaler: FontScaler):
    """
    Install font scaling on a widget via event filter.
    Captures Ctrl+MiddleMouseScroll and Ctrl+Plus/Minus events.
    
    Args:
        widget: QWidget to install scaler on (typically main window)
        font_scaler: FontScaler instance to use
    """
    from PyQt6.QtCore import QEvent, Qt
    
    class FontScaleFilter(QObject):
        def eventFilter(self, obj, event):
            # Handle mouse wheel events (Ctrl + Scroll)
            if event.type() == QEvent.Type.Wheel:
                modifiers = QApplication.keyboardModifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    # Ctrl is pressed - handle font scaling
                    angle_delta = event.angleDelta().y()
                    
                    if angle_delta > 0:
                        # Scroll up - increase font
                        font_scaler.scale_up()
                    elif angle_delta < 0:
                        # Scroll down - decrease font
                        font_scaler.scale_down()
                    
                    # Consume the event
                    return True
            
            # Handle keyboard events (Ctrl + Plus/Minus)
            elif event.type() == QEvent.Type.KeyPress:
                modifiers = QApplication.keyboardModifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    key = event.key()
                    
                    # Ctrl + Plus or Ctrl + = (since + is Shift + =)
                    if key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
                        font_scaler.scale_up()
                        return True
                    
                    # Ctrl + Minus
                    elif key == Qt.Key.Key_Minus:
                        font_scaler.scale_down()
                        return True
            
            return super().eventFilter(obj, event)
    
    filter_obj = FontScaleFilter(widget)
    widget.installEventFilter(filter_obj)
    
    # Store reference to prevent garbage collection
    if not hasattr(widget, '_font_scale_filters'):
        widget._font_scale_filters = []
    widget._font_scale_filters.append(filter_obj)
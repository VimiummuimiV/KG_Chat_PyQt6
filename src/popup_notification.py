from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QCursor, QPainter, QPainterPath, QRegion
from typing import List


class PopupNotification(QWidget):
    
    def __init__(self, title: str, message: str, manager, duration: int = 15000):
        super().__init__()
        self.manager = manager
        self.duration = duration
        self.is_hovered = False
        self.cursor_moved = False
        self.initial_cursor_pos = None
        self.hide_timer = None
        self.cursor_check_timer = None
        
        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # For rounded corners
        self.setObjectName("popup_notification")
        
        # Enable mouse tracking for hover detection
        self.setMouseTracking(True)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        
        # Title and message on same line
        message_text = f"<b>{title}:</b> {message}"
        self.message_label = QLabel(message_text)
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("popup_message")
        self.message_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout.addWidget(self.message_label)
        
        # Add shadow for better visibility
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(Qt.GlobalColor.black)
        self.setGraphicsEffect(shadow)
        
        # Start invisible
        self.setWindowOpacity(0.0)
        self.show()
        
        # Position and animate
        QTimer.singleShot(0, self._position)
        QTimer.singleShot(0, self._animate_in)
        
        # Start cursor monitoring
        self.initial_cursor_pos = QCursor.pos()
        self._start_cursor_monitoring()
    
    def paintEvent(self, event):
        """Custom paint to ensure rounded corners work"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Create rounded rectangle path
        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF(), 10, 10)
        
        # Fill with background color from stylesheet
        painter.fillPath(path, self.palette().window())
        
        # Draw border
        painter.setPen(self.palette().mid().color())
        painter.drawPath(path)
    
    def _position(self):
        """Position managed by PopupManager"""
        pass  # Manager handles this
    
    def _start_cursor_monitoring(self):
        """Monitor cursor movement to detect when to start hide timer"""
        self.cursor_check_timer = QTimer(self)
        self.cursor_check_timer.timeout.connect(self._check_cursor_movement)
        self.cursor_check_timer.start(100)  # Check every 100ms
    
    def _check_cursor_movement(self):
        """Check if cursor has moved significantly"""
        if self.cursor_moved:
            return
        
        current_pos = QCursor.pos()
        if self.initial_cursor_pos:
            distance = (current_pos - self.initial_cursor_pos).manhattanLength()
            if distance > 50:  # Moved more than 50 pixels
                self.cursor_moved = True
                self.cursor_check_timer.stop()
                self._start_hide_timer()
    
    def _start_hide_timer(self):
        """Start the 5-second timer before hiding"""
        if not self.is_hovered:
            self.hide_timer = QTimer(self)
            self.hide_timer.setSingleShot(True)
            self.hide_timer.timeout.connect(self._animate_out)
            self.hide_timer.start(5000)
    
    def _animate_in(self):
        """Fade in animation"""
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.start()
    
    def _animate_out(self):
        """Fade out animation (5 seconds)"""
        if self.is_hovered:
            return  # Don't hide if hovered
        
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(5000)  # 5 seconds fade
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.finished.connect(self._on_close)
        self.fade_out.start()
    
    def _on_close(self):
        """Clean up and notify manager"""
        self.manager.remove_popup(self)
        self.close()
    
    def enterEvent(self, event):
        """Mouse entered - stop hiding"""
        self.is_hovered = True
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        if hasattr(self, 'fade_out') and self.fade_out.state() == QPropertyAnimation.State.Running:
            self.fade_out.stop()
            self.setWindowOpacity(1.0)
    
    def leaveEvent(self, event):
        """Mouse left - restart hide timer"""
        self.is_hovered = False
        if self.cursor_moved:
            self._start_hide_timer()
    
    def mousePressEvent(self, event):
        """Click to dismiss"""
        self._on_close()
        if self.parent():
            self.parent().raise_()
            self.parent().activateWindow()


class PopupManager:
    
    def __init__(self):
        self.popups: List[PopupNotification] = []
        self.gap = 10  # Gap between popups
    
    def show_notification(self, title: str, message: str, duration: int = 15000):
        """Create and show a new notification"""
        popup = PopupNotification(title, message, self, duration)
        self.popups.append(popup)
        self._reposition_all()
        return popup
    
    def remove_popup(self, popup: PopupNotification):
        """Remove popup and reposition remaining ones"""
        if popup in self.popups:
            self.popups.remove(popup)
            self._reposition_all()
    
    def _reposition_all(self):
        """Stack all popups vertically"""
        if not self.popups:
            return
        
        screen = self.popups[0].screen().availableGeometry()
        width = min(int(screen.width() * 0.4), 400)
        x = screen.x() + (screen.width() - width) // 2
        
        current_y = screen.y() + 20  # Initial top margin
        
        for popup in self.popups:
            height = popup.sizeHint().height()
            popup.setGeometry(x, current_y, width, height)
            current_y += height + self.gap


# Global manager instance
popup_manager = PopupManager()


def show_notification(title: str, message: str, duration: int = 15000):
    return popup_manager.show_notification(title, message, duration)
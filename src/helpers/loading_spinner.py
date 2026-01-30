"""Shared loading spinner widget for async operations"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QPainter, QPen, QColor


class LoadingSpinner(QWidget):
    """A simple loading spinner widget"""
    
    def __init__(self, parent=None, size=60):
        super().__init__(parent)
        self.spinner_size = size
        self.setFixedSize(size, size)
        self._angle = 0
        
        self.animation = QPropertyAnimation(self, b"angle")
        self.animation.setDuration(1200)
        self.animation.setStartValue(0)
        self.animation.setEndValue(360)
        self.animation.setLoopCount(-1)
        
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    
    @pyqtProperty(int)
    def angle(self):
        return self._angle
    
    @angle.setter
    def angle(self, value):
        self._angle = value
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center = self.spinner_size / 2
        bg_radius, inner_radius = self.spinner_size * 0.42, self.spinner_size * 0.32
        line_width = max(2, int(self.spinner_size * 0.06))
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(5, 5, 5))
        painter.drawEllipse(int(center - bg_radius), int(center - bg_radius), int(bg_radius * 2), int(bg_radius * 2))
        
        painter.setPen(QPen(QColor(66, 133, 244), line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(int(center - inner_radius), int(center - inner_radius),
                       int(inner_radius * 2), int(inner_radius * 2), self._angle * 16, 270 * 16)
    
    def start(self):
        """Start the spinner animation"""
        self.animation.start()
        self.show()
    
    def stop(self):
        """Stop and hide the spinner"""
        self.animation.stop()
        self.hide()
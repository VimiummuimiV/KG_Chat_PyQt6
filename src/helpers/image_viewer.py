"""Image hover preview widget - displays images on URL hover like Imagus"""
import re
from typing import Optional
import requests

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject, QThread, QPropertyAnimation, pyqtProperty, QBuffer, QIODevice, QPointF
from PyQt6.QtGui import QPixmap, QMovie, QCursor, QPainter, QPen, QColor


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


class ImageLoadWorker(QObject):
    """Worker for loading images in background thread"""
    finished = pyqtSignal(str, bytes, bool)
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._should_stop = False
    
    def run(self):
        if self._should_stop:
            return
        try:
            response = requests.get(self.url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
            self.finished.emit(self.url, response.content if response.status_code == 200 and not self._should_stop else b'', 
                             response.status_code != 200)
        except Exception as e:
            print(f"Failed to load {self.url}: {e}")
            self.finished.emit(self.url, b'', True)
    
    def stop(self):
        self._should_stop = True


class ImageHoverView(QWidget):
    """Fullscreen viewport for image view with internal image transformations"""
    
    IMAGE_PATTERNS = [
        re.compile(r'https?://[^\s<>"]+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^\s<>"]*)?', re.IGNORECASE),
        re.compile(r'https?://.*\.(?:giphy|tenor|gfycat)\.com/[^\s<>"]+', re.IGNORECASE),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_url = self.current_movie = self.current_pixmap = None
        self.load_thread, self.load_worker = None, None
        
        screen = QApplication.primaryScreen()
        self.screen_rect = screen.availableGeometry()
        
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setGeometry(self.screen_rect)
        self.hide()
        
        self.loading_spinner = LoadingSpinner(None, 60)
        
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_spinner_position)
        self.target_pos = None
        
        # Image transformation and interaction state
        self.image_offset, self.image_scale = QPointF(0, 0), 1.0
        self.dragging, self.scaling, self.last_mouse_pos = False, False, None
    
    def paintEvent(self, event):
        """Paint the image with current transformations"""
        pixmap = (self.current_movie.currentPixmap() if self.current_movie else self.current_pixmap) if (self.current_movie or self.current_pixmap) else None
        if not pixmap or pixmap.isNull():
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(self.image_offset)
        painter.scale(self.image_scale, self.image_scale)
        painter.drawPixmap(0, 0, pixmap)
    
    @staticmethod
    def is_image_url(url: str) -> bool:
        return any(p.search(url or '') for p in ImageHoverView.IMAGE_PATTERNS)
    
    @staticmethod
    def extract_image_url(url: str) -> Optional[str]:
        if not url:
            return None
        for pattern in ImageHoverView.IMAGE_PATTERNS:
            if match := pattern.search(url):
                return match.group(0)
        return None
    
    def _calc_spinner_position(self, cursor_pos: QPoint):
        """Calculate spinner position near cursor"""
        offset, w, h = 20, self.loading_spinner.width(), self.loading_spinner.height()
        x = cursor_pos.x() - w - offset if cursor_pos.x() + offset + w > self.screen_rect.right() else cursor_pos.x() + offset
        y = cursor_pos.y() - h - offset if cursor_pos.y() + offset + h > self.screen_rect.bottom() else cursor_pos.y() + offset
        return QPoint(max(self.screen_rect.left(), x), max(self.screen_rect.top(), y))
    
    def _center_image(self, pixmap: QPixmap):
        """Center image in viewport at initial scale"""
        img_w, img_h = pixmap.width(), pixmap.height()
        self.image_scale = min(self.screen_rect.width() * 0.95 / img_w, self.screen_rect.height() * 0.95 / img_h, 1.0)
        scaled_w, scaled_h = img_w * self.image_scale, img_h * self.image_scale
        self.image_offset = QPointF((self.width() - scaled_w) / 2, (self.height() - scaled_h) / 2)
    
    def _stop_spinner(self):
        """Stop and hide loading spinner"""
        self.loading_spinner.animation.stop()
        self.loading_spinner.hide()
    
    def _show_widget(self):
        """Show and focus widget"""
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
    
    def show_preview(self, url: str, cursor_pos: QPoint):
        image_url = self.extract_image_url(url)
        if not image_url or (self.current_url == image_url and self.isVisible()):
            return
        
        self.hide_preview()
        self.current_url = image_url
        self.loading_spinner.move(self._calc_spinner_position(cursor_pos))
        self.loading_spinner.animation.start()
        self.loading_spinner.show()
        self._load_image(image_url)
        self.target_pos = cursor_pos
        self.position_timer.start(16)
    
    def _load_image(self, url: str):
        """Start loading image in background thread"""
        if self.load_worker:
            self.load_worker.stop()
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.quit()
            self.load_thread.wait(1000)
        
        self.load_worker = ImageLoadWorker(url)
        self.load_thread = QThread()
        self.load_worker.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.load_worker.run)
        self.load_worker.finished.connect(self._on_image_loaded)
        self.load_worker.finished.connect(self.load_thread.quit)
        self.load_thread.start()
    
    def _on_image_loaded(self, url: str, data: bytes, is_error: bool):
        """Handle loaded image data"""
        if is_error or url != self.current_url:
            return self._stop_spinner()
        
        try:
            is_gif = url.lower().endswith('.gif') or data.startswith(b'GIF')
            
            if is_gif:
                movie = QMovie()
                movie.setParent(QApplication.instance())
                movie.setCacheMode(QMovie.CacheMode.CacheAll)
                buffer = QBuffer()
                buffer.setParent(movie)
                buffer.setData(data)
                buffer.open(QIODevice.OpenModeFlag.ReadOnly)
                movie.setDevice(buffer)
                movie.jumpToFrame(0)
                
                if movie.isValid() and not (frame := movie.currentPixmap()).isNull():
                    self._stop_spinner()
                    self.current_movie, self.current_pixmap = movie, None
                    self._center_image(frame)
                    movie.frameChanged.connect(self.update)
                    movie.start()
                    self._show_widget()
                else:
                    self._stop_spinner()
            else:
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                
                if not pixmap.isNull():
                    self._stop_spinner()
                    self.current_pixmap, self.current_movie = pixmap, None
                    self._center_image(pixmap)
                    self._show_widget()
                else:
                    self._stop_spinner()
        except Exception as e:
            print(f"Error displaying image: {e}")
            self._stop_spinner()
    
    def _update_spinner_position(self):
        """Update spinner position to follow cursor"""
        if self.target_pos and self.loading_spinner.isVisible():
            cursor_pos = QCursor.pos()
            if abs(cursor_pos.x() - self.target_pos.x()) > 5 or abs(cursor_pos.y() - self.target_pos.y()) > 5:
                self.target_pos = cursor_pos
                self.loading_spinner.move(self._calc_spinner_position(cursor_pos))
    
    def _apply_zoom(self, new_scale: float, pivot: QPointF):
        """Apply zoom transformation around pivot point"""
        if not (0.1 <= new_scale <= 10.0):
            return
        point_before = (pivot - self.image_offset) / self.image_scale
        self.image_scale = new_scale
        self.image_offset = pivot - point_before * self.image_scale
        self.update()
    
    def wheelEvent(self, event):
        """Handle mouse wheel for zoom"""
        if self.current_pixmap or self.current_movie:
            self._apply_zoom(self.image_scale * (1.15 if event.angleDelta().y() > 0 else 0.87), event.position())
            event.accept()

    def mousePressEvent(self, event):
        """Handle mouse press for dragging or scaling"""
        if event.button() == Qt.MouseButton.LeftButton:
            is_ctrl = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
            self.scaling, self.dragging = bool(is_ctrl), not is_ctrl
            self.last_mouse_pos = event.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.hide_preview()
            event.accept()
        
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging or scaling"""
        if not self.last_mouse_pos:
            return
        
        delta = event.position() - self.last_mouse_pos
        
        if self.dragging:
            self.image_offset += delta
            self.update()
        elif self.scaling:
            self._apply_zoom(max(0.1, min(self.image_scale * (1.0 - delta.y() * 0.003), 10.0)),
                           QPointF(self.width() / 2, self.height() / 2))
        
        self.last_mouse_pos = event.position()
        event.accept()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if event.button() == Qt.MouseButton.LeftButton and (self.dragging or self.scaling):
            self.dragging = self.scaling = False
            self.last_mouse_pos = None
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept()
    
    def keyPressEvent(self, event):
        """Handle Space and ESC keys to hide preview"""
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            self.hide_preview()
            event.accept()
    
    def hide_preview(self):
        """Hide preview and reset state"""
        self.position_timer.stop()
        self._stop_spinner()
        
        if self.load_worker:
            self.load_worker.stop()
        
        if self.current_movie:
            self.current_movie.stop()
            try:
                self.current_movie.frameChanged.disconnect(self.update)
            except:
                pass
            self.current_movie.deleteLater()
        
        self.current_movie = self.current_pixmap = self.current_url = self.target_pos = self.last_mouse_pos = None
        self.image_offset, self.image_scale = QPointF(0, 0), 1.0
        self.dragging = self.scaling = False
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.hide()
    
    def cleanup(self):
        """Cleanup resources"""
        self.hide_preview()
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.quit()
            self.load_thread.wait(1000)

"""Image hover preview widget - displays images on URL hover like Imagus"""
import re
from typing import Optional
import requests

from PyQt6.QtWidgets import QLabel, QApplication, QWidget
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject, QThread, QPropertyAnimation, pyqtProperty, QBuffer, QIODevice, QPointF
from PyQt6.QtGui import QPixmap, QMovie, QCursor, QPainter, QPen, QColor, QWheelEvent, QMouseEvent, QKeyEvent, QTransform


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
        
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | 
                          Qt.WindowType.WindowStaysOnTopHint)
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
        bg_radius = self.spinner_size * 0.42
        inner_radius = self.spinner_size * 0.32
        line_width = max(2, int(self.spinner_size * 0.06))
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(5, 5, 5))
        painter.drawEllipse(int(center - bg_radius), int(center - bg_radius), 
                          int(bg_radius * 2), int(bg_radius * 2))
        
        painter.setPen(QPen(QColor(66, 133, 244), line_width,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(int(center - inner_radius), int(center - inner_radius),
                       int(inner_radius * 2), int(inner_radius * 2),
                       self._angle * 16, 270 * 16)


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
            response = requests.get(self.url, headers={'User-Agent': 'Mozilla/5.0'}, 
                                  timeout=60, stream=False)
            if not self._should_stop and response.status_code == 200:
                self.finished.emit(self.url, response.content, False)
            else:
                self.finished.emit(self.url, b'', True)
        except Exception as e:
            print(f"Failed to load {self.url}: {e}")
            self.finished.emit(self.url, b'', True)
    
    def stop(self):
        self._should_stop = True


class ImageHoverPreview(QWidget):
    """Fullscreen viewport for image preview with internal image transformations"""
    
    IMAGE_PATTERNS = [
        re.compile(r'https?://[^\s<>"]+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^\s<>"]*)?', re.IGNORECASE),
        re.compile(r'https?://(?:www\.)?imgur\.com/[a-zA-Z0-9]+', re.IGNORECASE),
        re.compile(r'https?://.*\.(?:giphy|tenor|gfycat)\.com/[^\s<>"]+', re.IGNORECASE),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_url = None
        self.current_movie = None
        self.current_pixmap = None
        self.cache = {}
        self.load_thread = None
        self.load_worker = None
        
        screen = QApplication.primaryScreen()
        self.screen_rect = screen.availableGeometry()
        
        # Viewport is always fullscreen
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | 
                          Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setGeometry(self.screen_rect)
        self.hide()
        
        self.loading_spinner = LoadingSpinner(None, 60)
        
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_spinner_position)
        self.target_pos = None
        
        # Image transformation state
        self.image_offset = QPointF(0, 0)  # Position of image within viewport
        self.image_scale = 1.0  # Scale factor of image
        
        # Interaction state
        self.dragging = False
        self.scaling = False
        self.last_mouse_pos = None
    
    def paintEvent(self, event):
        """Paint the image with current transformations"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # Get current pixmap
        if self.current_movie:
            pixmap = self.current_movie.currentPixmap()
        elif self.current_pixmap:
            pixmap = self.current_pixmap
        else:
            return
        
        if pixmap.isNull():
            return
        
        # Apply transformations
        painter.translate(self.image_offset)
        painter.scale(self.image_scale, self.image_scale)
        
        # Draw the image at origin (transformations handle positioning)
        painter.drawPixmap(0, 0, pixmap)
    
    @staticmethod
    def is_image_url(url: str) -> bool:
        return any(p.search(url or '') for p in ImageHoverPreview.IMAGE_PATTERNS)
    
    @staticmethod
    def extract_image_url(url: str) -> Optional[str]:
        if not url:
            return None
        for pattern in ImageHoverPreview.IMAGE_PATTERNS:
            if match := pattern.search(url):
                matched = match.group(0)
                if 'imgur.com' in matched and not matched.startswith('https://i.imgur.com'):
                    img_id = matched.split('/')[-1].split('?')[0]
                    return f"https://i.imgur.com/{img_id}.jpg"
                return matched
        return None
    
    def _calc_spinner_position(self, cursor_pos: QPoint):
        """Calculate spinner position near cursor"""
        offset = 20
        x, y = cursor_pos.x() + offset, cursor_pos.y() + offset
        
        if x + self.loading_spinner.width() > self.screen_rect.right():
            x = cursor_pos.x() - self.loading_spinner.width() - offset
        if y + self.loading_spinner.height() > self.screen_rect.bottom():
            y = cursor_pos.y() - self.loading_spinner.height() - offset
        
        return QPoint(max(self.screen_rect.left(), x), max(self.screen_rect.top(), y))
    
    def _center_image(self, pixmap: QPixmap):
        """Center image in viewport at initial scale"""
        img_w, img_h = pixmap.width(), pixmap.height()
        max_w, max_h = int(self.screen_rect.width() * 0.95), int(self.screen_rect.height() * 0.95)
        
        # Calculate initial scale to fit on screen
        self.image_scale = min(max_w / img_w, max_h / img_h, 1.0)
        
        # Center the scaled image
        scaled_w = img_w * self.image_scale
        scaled_h = img_h * self.image_scale
        
        self.image_offset = QPointF(
            (self.width() - scaled_w) / 2,
            (self.height() - scaled_h) / 2
        )
    
    def show_preview(self, url: str, cursor_pos: QPoint):
        image_url = self.extract_image_url(url)
        if not image_url:
            return
        
        if self.current_url == image_url and self.isVisible():
            return
        
        if image_url in self.cache:
            self._display_cached(image_url, cursor_pos)
            return
        
        self.hide_preview()
        self.current_url = image_url
        self.loading_spinner.move(self._calc_spinner_position(cursor_pos))
        self.loading_spinner.animation.start()
        self.loading_spinner.show()
        self._load_image(image_url)
        
        self.target_pos = cursor_pos
        self.position_timer.start(16)
    
    def _display_cached(self, url: str, cursor_pos: QPoint):
        self.current_url = url
        data, is_gif = self.cache[url]
        
        if is_gif:
            self.current_movie = data
            self.current_pixmap = None
            self._center_image(data.currentPixmap())
            data.frameChanged.connect(self.update)
            data.start()
        else:
            self.current_pixmap = data
            self.current_movie = None
            self._center_image(data)
        
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
    
    def _load_image(self, url: str):
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
        if is_error or url != self.current_url:
            self.loading_spinner.animation.stop()
            self.loading_spinner.hide()
            return
        
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
                    self.loading_spinner.animation.stop()
                    self.loading_spinner.hide()
                    
                    self.current_movie = movie
                    self.current_pixmap = None
                    self._center_image(frame)
                    movie.frameChanged.connect(self.update)
                    movie.start()
                    
                    self.show()
                    self.raise_()
                    self.activateWindow()
                    self.setFocus(Qt.FocusReason.OtherFocusReason)
                    
                    if len(self.cache) < 20:
                        self.cache[url] = (movie, True)
                else:
                    self.loading_spinner.animation.stop()
                    self.loading_spinner.hide()
            else:
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                
                if not pixmap.isNull():
                    self.loading_spinner.animation.stop()
                    self.loading_spinner.hide()
                    
                    self.current_pixmap = pixmap
                    self.current_movie = None
                    self._center_image(pixmap)
                    
                    self.show()
                    self.raise_()
                    self.activateWindow()
                    self.setFocus(Qt.FocusReason.OtherFocusReason)
                    
                    if len(self.cache) < 20:
                        self.cache[url] = (pixmap, False)
                else:
                    self.loading_spinner.animation.stop()
                    self.loading_spinner.hide()
        except Exception as e:
            print(f"Error displaying image: {e}")
            self.loading_spinner.animation.stop()
            self.loading_spinner.hide()
    
    def _update_spinner_position(self):
        """Update spinner position to follow cursor"""
        if self.target_pos and self.loading_spinner.isVisible():
            cursor_pos = QCursor.pos()
            if abs(cursor_pos.x() - self.target_pos.x()) > 5 or abs(cursor_pos.y() - self.target_pos.y()) > 5:
                self.target_pos = cursor_pos
                self.loading_spinner.move(self._calc_spinner_position(cursor_pos))
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zoom"""
        if not (self.current_pixmap or self.current_movie):
            return
        
        # Zoom towards mouse position
        mouse_pos = event.position()
        
        # Calculate zoom factor
        delta = event.angleDelta().y()
        zoom_factor = 1.15 if delta > 0 else 0.87
        
        new_scale = self.image_scale * zoom_factor
        
        # Clamp scale
        if not (0.1 <= new_scale <= 10.0):
            return
        
        # Adjust offset to zoom towards mouse position
        # Point under mouse before zoom
        point_before = (mouse_pos - self.image_offset) / self.image_scale
        
        # Apply new scale
        self.image_scale = new_scale
        
        # Point under mouse after zoom (should be same logical point)
        point_after = point_before * self.image_scale
        
        # Adjust offset
        self.image_offset = mouse_pos - point_after
        
        self.update()
        event.accept()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for dragging (LMB) or scaling (Ctrl+LMB)"""
        if event.button() == Qt.MouseButton.LeftButton:
            is_ctrl = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
            self.scaling = bool(is_ctrl)
            self.dragging = not is_ctrl
            self.last_mouse_pos = event.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for dragging or scaling"""
        if not self.last_mouse_pos:
            return super().mouseMoveEvent(event)
        
        current_pos = event.position()
        delta = current_pos - self.last_mouse_pos
        
        if self.dragging:
            # Pan the image
            self.image_offset += delta
            self.update()
        elif self.scaling:
            # Vertical movement controls scale (up = zoom in, down = zoom out)
            zoom_amount = -delta.y() * 0.003
            new_scale = self.image_scale * (1.0 + zoom_amount)
            new_scale = max(0.1, min(new_scale, 10.0))
            
            # Zoom towards center of viewport
            center = QPointF(self.width() / 2, self.height() / 2)
            point_before = (center - self.image_offset) / self.image_scale
            
            self.image_scale = new_scale
            
            point_after = point_before * self.image_scale
            self.image_offset = center - point_after
            
            self.update()
        
        self.last_mouse_pos = current_pos
        event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release to stop dragging or scaling"""
        if event.button() == Qt.MouseButton.LeftButton and (self.dragging or self.scaling):
            self.dragging = False
            self.scaling = False
            self.last_mouse_pos = None
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click to hide preview"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide_preview()
        event.accept()
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle Space and ESC keys to hide preview"""
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            self.hide_preview()
        event.accept()
    
    def hide_preview(self):
        self.position_timer.stop()
        self.loading_spinner.animation.stop()
        self.loading_spinner.hide()
        
        if self.load_worker:
            self.load_worker.stop()
        
        if self.current_movie:
            if self.current_movie not in [v[0] for v in self.cache.values()]:
                self.current_movie.stop()
            try:
                self.current_movie.frameChanged.disconnect(self.update)
            except:
                pass
        
        self.current_movie = None
        self.current_pixmap = None
        self.current_url = None
        self.target_pos = None
        
        # Reset transformations
        self.image_offset = QPointF(0, 0)
        self.image_scale = 1.0
        
        # Reset interaction state
        self.dragging = False
        self.scaling = False
        self.last_mouse_pos = None
        
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.hide()
    
    def cleanup(self):
        self.hide_preview()
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.quit()
            self.load_thread.wait(1000)
        for data, is_gif in self.cache.values():
            if is_gif:
                data.stop()
                data.deleteLater()
        self.cache.clear()
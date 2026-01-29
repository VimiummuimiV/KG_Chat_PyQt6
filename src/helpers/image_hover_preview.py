"""Image hover preview widget - displays images on URL hover like Imagus"""
import re
from typing import Optional
import requests

from PyQt6.QtWidgets import QLabel, QApplication, QWidget
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject, QThread, QPropertyAnimation, pyqtProperty, QBuffer, QIODevice
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


class ImageHoverPreview(QLabel):
    """Floating image preview widget that follows mouse cursor"""
    
    IMAGE_PATTERNS = [
        re.compile(r'https?://[^\s<>"]+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^\s<>"]*)?', re.IGNORECASE),
        re.compile(r'https?://(?:www\.)?imgur\.com/[a-zA-Z0-9]+', re.IGNORECASE),
        re.compile(r'https?://.*\.(?:giphy|tenor|gfycat)\.com/[^\s<>"]+', re.IGNORECASE),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_url = None
        self.current_movie = None
        self.cache = {}
        self.load_thread = None
        self.load_worker = None
        
        screen = QApplication.primaryScreen()
        self.screen_rect = screen.availableGeometry()
        
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | 
                          Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("QLabel { background-color: transparent; border: none; padding: 0px; }")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)
        self.hide()
        
        self.loading_spinner = LoadingSpinner(None, 60)
        
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_position_smooth)
        self.target_pos = None
    
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
    
    def _calc_position(self, cursor_pos: QPoint, widget):
        """Calculate position for any widget"""
        offset = 20
        x, y = cursor_pos.x() + offset, cursor_pos.y() + offset
        
        if x + widget.width() > self.screen_rect.right():
            x = cursor_pos.x() - widget.width() - offset
        if y + widget.height() > self.screen_rect.bottom():
            y = cursor_pos.y() - widget.height() - offset
        
        return QPoint(max(self.screen_rect.left(), x), max(self.screen_rect.top(), y))
    
    def show_preview(self, url: str, cursor_pos: QPoint):
        image_url = self.extract_image_url(url)
        if not image_url:
            return
        
        if self.current_url == image_url and self.isVisible():
            self.move(self._calc_position(cursor_pos, self))
            return
        
        if image_url in self.cache:
            self._display_cached(image_url, cursor_pos)
            return
        
        self.hide_preview()
        self.current_url = image_url
        self.loading_spinner.move(self._calc_position(cursor_pos, self.loading_spinner))
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
            self.setMovie(data)
            self._resize_to_fit_image(data.currentPixmap(), cursor_pos)
            data.start()
        else:
            self.current_movie = None
            self._resize_to_fit_image(data, cursor_pos)
            self.setPixmap(data)
        
        self.show()
        self.target_pos = cursor_pos
        self.position_timer.start(16)
    
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
                    pos = self.loading_spinner.pos()
                    self.loading_spinner.animation.stop()
                    self.loading_spinner.hide()
                    self._resize_to_fit_image(frame, QCursor.pos())
                    self.move(pos)
                    self.current_movie = movie
                    self.setMovie(movie)
                    movie.start()
                    self.show()
                    if len(self.cache) < 20:
                        self.cache[url] = (movie, True)
                else:
                    self.loading_spinner.animation.stop()
                    self.loading_spinner.hide()
            else:
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                
                if not pixmap.isNull():
                    pos = self.loading_spinner.pos()
                    self.loading_spinner.animation.stop()
                    self.loading_spinner.hide()
                    self._resize_to_fit_image(pixmap, QCursor.pos())
                    self.move(pos)
                    self.setPixmap(pixmap)
                    self.current_movie = None
                    self.show()
                    if len(self.cache) < 20:
                        self.cache[url] = (pixmap, False)
                else:
                    self.loading_spinner.animation.stop()
                    self.loading_spinner.hide()
        except Exception as e:
            print(f"Error displaying image: {e}")
            self.loading_spinner.animation.stop()
            self.loading_spinner.hide()
    
    def _resize_to_fit_image(self, pixmap: QPixmap, cursor_pos: QPoint):
        img_w, img_h = pixmap.width(), pixmap.height()
        max_w, max_h = int(self.screen_rect.width() * 0.9), int(self.screen_rect.height() * 0.9)
        
        scale = 1.0
        if img_w > max_w or img_h > max_h:
            scale = min(max_w / img_w, max_h / img_h)
        
        self.setFixedSize(int(img_w * scale), int(img_h * scale))
        self.setScaledContents(scale < 1.0)
    
    def _update_position_smooth(self):
        if self.target_pos:
            cursor_pos = QCursor.pos()
            if abs(cursor_pos.x() - self.target_pos.x()) > 5 or abs(cursor_pos.y() - self.target_pos.y()) > 5:
                self.target_pos = cursor_pos
                if self.loading_spinner.isVisible():
                    self.loading_spinner.move(self._calc_position(cursor_pos, self.loading_spinner))
                elif self.isVisible():
                    self.move(self._calc_position(cursor_pos, self))
    
    def hide_preview(self):
        self.position_timer.stop()
        self.loading_spinner.animation.stop()
        self.loading_spinner.hide()
        
        if self.load_worker:
            self.load_worker.stop()
        if self.current_movie and self.current_movie not in [v[0] for v in self.cache.values()]:
            self.current_movie.stop()
        
        self.current_movie = None
        self.setMovie(None)
        self.setPixmap(QPixmap())
        self.current_url = None
        self.target_pos = None
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
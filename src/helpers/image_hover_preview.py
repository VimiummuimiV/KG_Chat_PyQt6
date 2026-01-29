"""Image hover preview widget - displays images on URL hover like Imagus"""
import re
from typing import Optional
import requests
from io import BytesIO

from PyQt6.QtWidgets import QLabel, QApplication
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QPixmap, QMovie, QCursor


class ImageLoadWorker(QObject):
    """Worker for loading images in background thread using requests"""
    finished = pyqtSignal(str, bytes, bool)  # url, data, is_error
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._should_stop = False
    
    def run(self):
        """Load image data from URL"""
        if self._should_stop:
            return
            
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(self.url, headers=headers, timeout=10, stream=True)
            
            if self._should_stop:
                return
            
            if response.status_code == 200:
                # Read data in chunks to allow cancellation
                data = BytesIO()
                for chunk in response.iter_content(chunk_size=8192):
                    if self._should_stop:
                        return
                    data.write(chunk)
                
                self.finished.emit(self.url, data.getvalue(), False)
            else:
                self.finished.emit(self.url, b'', True)
        except Exception as e:
            print(f"Failed to load image: {e}")
            self.finished.emit(self.url, b'', True)
    
    def stop(self):
        """Stop loading"""
        self._should_stop = True


class ImageHoverPreview(QLabel):
    """Floating image preview widget that follows mouse cursor"""
    
    # Image URL patterns - captures ANY image URL from any source
    IMAGE_PATTERNS = [
        # Direct image links from ANY domain with common image extensions
        re.compile(r'https?://[^\s<>"]+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^\s<>"]*)?', re.IGNORECASE),
        # Imgur (non-direct links)
        re.compile(r'https?://(?:www\.)?imgur\.com/[a-zA-Z0-9]+', re.IGNORECASE),
        # Giphy, Tenor, Gfycat
        re.compile(r'https?://.*\.(?:giphy|tenor|gfycat)\.com/[^\s<>"]+', re.IGNORECASE),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_url = None
        self.current_movie = None
        self.cache = {}  # Simple cache: url -> (pixmap/movie, is_gif)
        self.load_thread = None
        self.load_worker = None
        
        # Get screen geometry
        screen = QApplication.primaryScreen()
        self.screen_rect = screen.availableGeometry()
        
        # Setup widget
        self.setWindowFlags(Qt.WindowType.ToolTip | 
                           Qt.WindowType.FramelessWindowHint |
                           Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("""
            QLabel {
                background-color: #2D2D2D;
                border: 2px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)
        self.hide()
        
        # Loading indicator
        self.loading_text = "Loading..."
        
        # Hide delay timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_preview)
        
        # Position update timer
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_position_smooth)
        self.target_pos = None
    
    @staticmethod
    def is_image_url(url: str) -> bool:
        """Check if URL points to an image"""
        if not url:
            return False
        
        for pattern in ImageHoverPreview.IMAGE_PATTERNS:
            if pattern.search(url):
                return True
        
        return False
    
    @staticmethod
    def extract_image_url(url: str) -> Optional[str]:
        """Extract direct image URL from various hosting services"""
        if not url:
            return None
        
        # Check all patterns
        for pattern in ImageHoverPreview.IMAGE_PATTERNS:
            match = pattern.search(url)
            if match:
                matched_url = match.group(0)
                
                # Special handling for imgur (convert to direct link)
                if 'imgur.com' in matched_url and not matched_url.startswith('https://i.imgur.com'):
                    img_id = matched_url.split('/')[-1].split('?')[0]
                    return f"https://i.imgur.com/{img_id}.jpg"
                
                return matched_url
        
        return None
    
    def show_preview(self, url: str, cursor_pos: QPoint):
        """Show preview for URL at cursor position"""
        image_url = self.extract_image_url(url)
        if not image_url:
            return
        
        # If already showing same URL, just update position
        if self.current_url == image_url and self.isVisible():
            self._update_position(cursor_pos)
            return
        
        # New URL - check cache first
        if image_url in self.cache:
            self._display_cached(image_url, cursor_pos)
            return
        
        # Show loading state
        self.hide_preview()
        self.current_url = image_url
        self.setText(self.loading_text)
        self.setFixedSize(150, 40)
        self._update_position(cursor_pos)
        self.show()
        
        # Start loading in background
        self._load_image(image_url)
        
        # Start position following
        self.target_pos = cursor_pos
        self.position_timer.start(16)  # ~60 FPS
    
    def _display_cached(self, url: str, cursor_pos: QPoint):
        """Display cached image"""
        self.current_url = url
        data, is_gif = self.cache[url]
        
        if is_gif:
            self.current_movie = data
            self.setMovie(data)
            first_frame = data.currentPixmap()
            if not first_frame.isNull():
                self._resize_and_position(first_frame, cursor_pos)
            data.start()
        else:
            self.current_movie = None
            self._resize_and_position(data, cursor_pos)
            self.setPixmap(data)
        
        self.show()
        self.target_pos = cursor_pos
        self.position_timer.start(16)
    
    def _load_image(self, url: str):
        """Load image using requests in background thread"""
        # Cancel previous load if any
        if self.load_worker:
            self.load_worker.stop()
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.quit()
            self.load_thread.wait(1000)
        
        # Create new worker and thread
        self.load_worker = ImageLoadWorker(url)
        self.load_thread = QThread()
        self.load_worker.moveToThread(self.load_thread)
        
        self.load_thread.started.connect(self.load_worker.run)
        self.load_worker.finished.connect(self._on_image_loaded)
        self.load_worker.finished.connect(self.load_thread.quit)
        
        self.load_thread.start()
    
    def _on_image_loaded(self, url: str, data: bytes, is_error: bool):
        """Handle loaded image data"""
        if is_error or url != self.current_url or not self.isVisible():
            return
        
        try:
            # Detect if GIF
            is_gif = url.lower().endswith('.gif') or data.startswith(b'GIF')
            
            if is_gif:
                # Create QMovie for animated GIF
                movie = QMovie()
                movie.setParent(QApplication.instance())
                movie.setCacheMode(QMovie.CacheMode.CacheAll)
                
                # Load from data
                from PyQt6.QtCore import QBuffer, QIODevice
                buffer = QBuffer()
                buffer.setData(data)
                buffer.open(QIODevice.OpenModeFlag.ReadOnly)
                movie.setDevice(buffer)
                
                if movie.isValid():
                    first_frame = movie.currentPixmap()
                    if not first_frame.isNull():
                        self._resize_and_position(first_frame, self.target_pos or QCursor.pos())
                        self.current_movie = movie
                        self.setMovie(movie)
                        movie.start()
                        
                        # Cache it
                        if len(self.cache) < 20:  # Limit cache size
                            self.cache[url] = (movie, True)
            else:
                # Load static image
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                
                if not pixmap.isNull():
                    self._resize_and_position(pixmap, self.target_pos or QCursor.pos())
                    self.setPixmap(pixmap)
                    self.current_movie = None
                    
                    # Cache it
                    if len(self.cache) < 20:  # Limit cache size
                        self.cache[url] = (pixmap, False)
        
        except Exception as e:
            print(f"Error displaying image: {e}")
            self.hide_preview()
    
    def _resize_and_position(self, pixmap: QPixmap, cursor_pos: QPoint):
        """Resize widget to fit pixmap within screen bounds, maintaining aspect ratio"""
        img_w, img_h = pixmap.width(), pixmap.height()
        
        # Maximum dimensions: 90% of screen size to leave margins
        max_w = int(self.screen_rect.width() * 0.9)
        max_h = int(self.screen_rect.height() * 0.9)
        
        # Calculate scaling factor to fit within screen while maintaining aspect ratio
        scale_w = max_w / img_w if img_w > max_w else 1.0
        scale_h = max_h / img_h if img_h > max_h else 1.0
        scale = min(scale_w, scale_h)
        
        # Apply scaling only if needed
        if scale < 1.0:
            final_w = int(img_w * scale)
            final_h = int(img_h * scale)
        else:
            # Display at original size (1:1)
            final_w = img_w
            final_h = img_h
        
        # Set widget size (add padding for border)
        self.setFixedSize(final_w + 8, final_h + 8)
        
        # Update position
        self._update_position(cursor_pos)
    
    def _update_position(self, cursor_pos: QPoint):
        """Update preview position relative to cursor, keeping it fully on screen"""
        offset = 20  # Offset from cursor
        
        # Initial position (bottom-right of cursor)
        x = cursor_pos.x() + offset
        y = cursor_pos.y() + offset
        
        # Keep within screen bounds
        if x + self.width() > self.screen_rect.right():
            # Move to left of cursor
            x = cursor_pos.x() - self.width() - offset
        
        if y + self.height() > self.screen_rect.bottom():
            # Move above cursor
            y = cursor_pos.y() - self.height() - offset
        
        # Ensure not off left/top edges
        x = max(self.screen_rect.left(), x)
        y = max(self.screen_rect.top(), y)
        
        self.move(x, y)
        self.target_pos = cursor_pos
    
    def _update_position_smooth(self):
        """Smooth position update for following cursor"""
        if self.target_pos:
            cursor_pos = QCursor.pos()
            # Only update if cursor moved
            if (abs(cursor_pos.x() - self.target_pos.x()) > 5 or 
                abs(cursor_pos.y() - self.target_pos.y()) > 5):
                self._update_position(cursor_pos)
    
    def hide_preview(self):
        """Hide preview and cleanup"""
        self.position_timer.stop()
        self.hide_timer.stop()
        
        # Stop loading if in progress
        if self.load_worker:
            self.load_worker.stop()
        
        if self.current_movie and self.current_movie not in [v[0] for v in self.cache.values()]:
            # Only stop if not cached (cached ones should keep running)
            self.current_movie.stop()
        
        self.current_movie = None
        self.setMovie(None)
        self.setPixmap(QPixmap())
        self.setText("")
        self.current_url = None
        self.target_pos = None
        self.hide()
    
    def cleanup(self):
        """Cleanup resources"""
        self.hide_preview()
        
        # Stop any running thread
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.quit()
            self.load_thread.wait(1000)
        
        # Cleanup cache
        for data, is_gif in self.cache.values():
            if is_gif:
                data.stop()
                data.deleteLater()
        self.cache.clear()
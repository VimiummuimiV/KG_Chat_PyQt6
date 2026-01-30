"""Video hover preview widget with full playback controls"""
import re
from typing import Optional
from pathlib import Path
import requests

from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout, QVBoxLayout, QSlider, QLabel
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject, QThread, QUrl, QPointF
from PyQt6.QtGui import QCursor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from helpers.loading_spinner import LoadingSpinner
from helpers.create import create_icon_button


class VideoLoadWorker(QObject):
    """Worker for loading videos in background thread"""
    finished = pyqtSignal(str, bytes, bool)
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._should_stop = False
    
    def run(self):
        if self._should_stop:
            return
        try:
            response = requests.get(self.url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60, stream=True)
            if response.status_code == 200 and not self._should_stop:
                # For video, we'll stream directly from URL instead of downloading
                self.finished.emit(self.url, b'', False)
            else:
                self.finished.emit(self.url, b'', True)
        except Exception as e:
            print(f"Failed to load {self.url}: {e}")
            self.finished.emit(self.url, b'', True)
    
    def stop(self):
        self._should_stop = True


class VideoHoverView(QWidget):
    """Fullscreen viewport for video playback with controls"""
    
    VIDEO_PATTERNS = [
        re.compile(r'https?://[^\s<>"]+\.(?:mp4|webm|ogg|mov|avi|mkv|flv|wmv|m4v)(?:\?[^\s<>"]*)?', re.IGNORECASE),
        re.compile(r'https?://.*\.(?:streamable|vimeo)\.com/[^\s<>"]+', re.IGNORECASE),
    ]
    
    def __init__(self, parent=None, icons_path: Path = None, config=None):
        super().__init__(parent)
        self.icons_path = icons_path or Path("assets/icons")
        self.config = config
        self.current_url = None
        self.load_thread, self.load_worker = None, None
        
        screen = QApplication.primaryScreen()
        self.screen_rect = screen.availableGeometry()
        
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setGeometry(self.screen_rect)
        self.hide()
        
        # Loading spinner
        self.loading_spinner = LoadingSpinner(None, 60)
        
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_spinner_position)
        self.target_pos = None
        
        # Media player setup
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        self.video_widget = QVideoWidget()
        self.media_player.setVideoOutput(self.video_widget)
        
        # Controls
        self._setup_ui()
        self._setup_controls()
        
        # Control visibility timer
        self.controls_timer = QTimer()
        self.controls_timer.setSingleShot(True)
        self.controls_timer.timeout.connect(self._hide_controls)
        self.controls_visible = True
        
        # Media player signals
        self.media_player.positionChanged.connect(self._update_position)
        self.media_player.durationChanged.connect(self._update_duration)
        self.media_player.playbackStateChanged.connect(self._update_play_button)
        
        # Volume from config or default
        default_volume = 0.5
        if config:
            default_volume = config.get("ui", "video", "default_volume") or 0.5
        self.audio_output.setVolume(default_volume)
        self.volume_slider.setValue(int(default_volume * 100))
        
        self._was_muted = False
    
    def _setup_ui(self):
        """Setup the UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Video widget takes full space
        layout.addWidget(self.video_widget)
        
        # Controls container at bottom
        self.controls_container = QWidget()
        self.controls_container.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 180);
            }
        """)
        controls_layout = QVBoxLayout(self.controls_container)
        controls_layout.setContentsMargins(10, 5, 10, 5)
        
        # Progress slider
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #555;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #4DA6FF;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #4DA6FF;
                border-radius: 3px;
            }
        """)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        controls_layout.addWidget(self.progress_slider)
        
        # Bottom controls row
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(5)
        
        # Play/Pause button
        self.play_button = create_icon_button(
            self.icons_path,
            "play.svg",
            "Play/Pause (Space)",
            size_type="large",
            config=self.config
        )
        self.play_button.clicked.connect(self._toggle_play)
        bottom_row.addWidget(self.play_button)
        
        # Time labels
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("color: white; font-size: 12px;")
        bottom_row.addWidget(self.time_label)
        
        bottom_row.addStretch()
        
        # Volume button
        self.volume_button = create_icon_button(
            self.icons_path,
            "volume-up.svg",
            "Mute/Unmute (M)",
            size_type="large",
            config=self.config
        )
        self.volume_button.clicked.connect(self._toggle_mute)
        bottom_row.addWidget(self.volume_button)
        
        # Volume slider
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #555;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: white;
                border-radius: 2px;
            }
        """)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        bottom_row.addWidget(self.volume_slider)
        
        controls_layout.addLayout(bottom_row)
        layout.addWidget(self.controls_container)
    
    def _setup_controls(self):
        """Setup control button states"""
        self.play_button.setEnabled(False)
        self.progress_slider.setEnabled(False)
    
    def _toggle_play(self):
        """Toggle play/pause"""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()
    
    def _toggle_mute(self):
        """Toggle mute/unmute"""
        is_muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not is_muted)
        self._update_volume_button()
    
    def _on_volume_changed(self, value: int):
        """Handle volume slider changes"""
        volume = value / 100.0
        self.audio_output.setVolume(volume)
        self._update_volume_button()
    
    def _update_volume_button(self):
        """Update volume button icon based on mute state and level"""
        is_muted = self.audio_output.isMuted()
        volume = self.audio_output.volume()
        
        # Determine icon based on state
        if is_muted or volume == 0:
            icon_name = "volume-mute.svg"
        elif volume < 0.5:
            icon_name = "volume-down.svg"
        else:
            icon_name = "volume-up.svg"
        
        # Update button icon
        from helpers.create import _render_svg_icon
        self.volume_button.setIcon(_render_svg_icon(self.icons_path / icon_name, self.volume_button._icon_size))
        self.volume_button._icon_name = icon_name
    
    def _update_play_button(self, state):
        """Update play button icon based on playback state"""
        from helpers.create import _render_svg_icon
        
        if state == QMediaPlayer.PlaybackState.PlayingState:
            icon_name = "stop.svg"
            tooltip = "Stop (Space)"
        else:
            icon_name = "play.svg"
            tooltip = "Play (Space)"
        
        self.play_button.setIcon(_render_svg_icon(self.icons_path / icon_name, self.play_button._icon_size))
        self.play_button._icon_name = icon_name
        self.play_button.setToolTip(tooltip)
    
    def _on_slider_pressed(self):
        """Pause updates when user is dragging slider"""
        self.media_player.positionChanged.disconnect(self._update_position)
    
    def _on_slider_released(self):
        """Seek to position when slider is released"""
        position = self.progress_slider.value()
        self.media_player.setPosition(position)
        self.media_player.positionChanged.connect(self._update_position)
    
    def _update_position(self, position):
        """Update slider and time label as video plays"""
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)
        
        duration = self.media_player.duration()
        self.time_label.setText(f"{self._format_time(position)} / {self._format_time(duration)}")
    
    def _update_duration(self, duration):
        """Update slider range when duration is known"""
        self.progress_slider.setRange(0, duration)
        self.time_label.setText(f"0:00 / {self._format_time(duration)}")
    
    def _format_time(self, ms: int) -> str:
        """Format milliseconds to MM:SS or HH:MM:SS"""
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        hours = minutes // 60
        minutes = minutes % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    @staticmethod
    def is_video_url(url: str) -> bool:
        """Check if URL is a video"""
        return any(p.search(url or '') for p in VideoHoverView.VIDEO_PATTERNS)
    
    @staticmethod
    def extract_video_url(url: str) -> Optional[str]:
        """Extract video URL from text"""
        if not url:
            return None
        for pattern in VideoHoverView.VIDEO_PATTERNS:
            if match := pattern.search(url):
                return match.group(0)
        return None
    
    def _calc_spinner_position(self, cursor_pos: QPoint):
        """Calculate spinner position near cursor"""
        offset, w, h = 20, self.loading_spinner.width(), self.loading_spinner.height()
        x = cursor_pos.x() - w - offset if cursor_pos.x() + offset + w > self.screen_rect.right() else cursor_pos.x() + offset
        y = cursor_pos.y() - h - offset if cursor_pos.y() + offset + h > self.screen_rect.bottom() else cursor_pos.y() + offset
        return QPoint(max(self.screen_rect.left(), x), max(self.screen_rect.top(), y))
    
    def _stop_spinner(self):
        """Stop and hide loading spinner"""
        self.loading_spinner.stop()
    
    def _show_widget(self):
        """Show and focus widget"""
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._show_controls()
    
    def show_preview(self, url: str, cursor_pos: QPoint):
        """Show video preview for URL"""
        video_url = self.extract_video_url(url)
        if not video_url or (self.current_url == video_url and self.isVisible()):
            return
        
        self.hide_preview()
        self.current_url = video_url
        self.loading_spinner.move(self._calc_spinner_position(cursor_pos))
        self.loading_spinner.start()
        self._load_video(video_url)
        self.target_pos = cursor_pos
        self.position_timer.start(16)
    
    def _load_video(self, url: str):
        """Load video from URL"""
        # QMediaPlayer can stream from URL directly
        self._stop_spinner()
        self.media_player.setSource(QUrl(url))
        self.play_button.setEnabled(True)
        self.progress_slider.setEnabled(True)
        self._show_widget()
        
        # Auto-play
        self.media_player.play()
    
    def _update_spinner_position(self):
        """Update spinner position to follow cursor"""
        if self.target_pos and self.loading_spinner.isVisible():
            cursor_pos = QCursor.pos()
            if abs(cursor_pos.x() - self.target_pos.x()) > 5 or abs(cursor_pos.y() - self.target_pos.y()) > 5:
                self.target_pos = cursor_pos
                self.loading_spinner.move(self._calc_spinner_position(cursor_pos))
    
    def _show_controls(self):
        """Show controls and reset hide timer"""
        self.controls_container.show()
        self.controls_visible = True
        self.controls_timer.start(3000)  # Hide after 3 seconds of inactivity
    
    def _hide_controls(self):
        """Hide controls"""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.controls_container.hide()
            self.controls_visible = False
    
    def mouseMoveEvent(self, event):
        """Show controls on mouse move"""
        self._show_controls()
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle clicks - toggle play on video area, close on right-click"""
        if event.button() == Qt.MouseButton.LeftButton:
            # If clicked outside controls, toggle play
            if not self.controls_container.geometry().contains(event.pos()):
                self._toggle_play()
        elif event.button() == Qt.MouseButton.RightButton:
            self.hide_preview()
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        key = event.key()
        
        # Space: Play/Pause
        if key == Qt.Key.Key_Space:
            self._toggle_play()
            event.accept()
        
        # ESC: Close
        elif key == Qt.Key.Key_Escape:
            self.hide_preview()
            event.accept()
        
        # M: Mute/Unmute
        elif key == Qt.Key.Key_M:
            self._toggle_mute()
            event.accept()
        
        # J / Left Arrow: Seek backward 10 seconds
        elif key in (Qt.Key.Key_J, Qt.Key.Key_Left):
            new_pos = max(0, self.media_player.position() - 10000)
            self.media_player.setPosition(new_pos)
            event.accept()
        
        # L / Right Arrow: Seek forward 10 seconds
        elif key in (Qt.Key.Key_L, Qt.Key.Key_Right):
            new_pos = min(self.media_player.duration(), self.media_player.position() + 10000)
            self.media_player.setPosition(new_pos)
            event.accept()
        
        # Up Arrow: Volume up
        elif key == Qt.Key.Key_Up:
            new_volume = min(100, self.volume_slider.value() + 5)
            self.volume_slider.setValue(new_volume)
            event.accept()
        
        # Down Arrow: Volume down
        elif key == Qt.Key.Key_Down:
            new_volume = max(0, self.volume_slider.value() - 5)
            self.volume_slider.setValue(new_volume)
            event.accept()
        
        # K: Play/Pause (YouTube style)
        elif key == Qt.Key.Key_K:
            self._toggle_play()
            event.accept()
        
        # Comma / Period: Frame by frame (when paused)
        elif key in (Qt.Key.Key_Comma, Qt.Key.Key_Period) and self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            step = 100 if key == Qt.Key.Key_Period else -100
            new_pos = max(0, min(self.media_player.duration(), self.media_player.position() + step))
            self.media_player.setPosition(new_pos)
            event.accept()
        
        # 0-9: Seek to percentage
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            percentage = (key - Qt.Key.Key_0) / 10.0
            new_pos = int(self.media_player.duration() * percentage)
            self.media_player.setPosition(new_pos)
            event.accept()
    
    def wheelEvent(self, event):
        """Handle mouse wheel for volume"""
        delta = 5 if event.angleDelta().y() > 0 else -5
        new_volume = max(0, min(100, self.volume_slider.value() + delta))
        self.volume_slider.setValue(new_volume)
        event.accept()
    
    def hide_preview(self):
        """Hide preview and reset state"""
        self.position_timer.stop()
        self._stop_spinner()
        
        if self.load_worker:
            self.load_worker.stop()
        
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        
        self.current_url = self.target_pos = None
        self.play_button.setEnabled(False)
        self.progress_slider.setEnabled(False)
        self.progress_slider.setValue(0)
        self.time_label.setText("0:00 / 0:00")
        
        self.controls_timer.stop()
        self._show_controls()
        
        self.hide()
    
    def cleanup(self):
        """Cleanup resources"""
        self.hide_preview()
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.quit()
            self.load_thread.wait(1000)
        self.media_player.deleteLater()
        self.audio_output.deleteLater()
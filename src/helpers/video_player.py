"""Video player widget - displays videos in a movable window"""
import re
from typing import Optional
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel
from PyQt6.QtCore import Qt, QTimer, QUrl, QPoint
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from helpers.loading_spinner import LoadingSpinner
from helpers.create import create_icon_button, _render_svg_icon


class VideoPlayer(QWidget):
    """Video player in a movable window"""
    
    VIDEO_PATTERNS = [
        re.compile(r'https?://[^\s<>"]+\.(?:mp4|webm|ogg|mov|avi|mkv|flv|wmv|m4v)(?:\?[^\s<>"]*)?', re.IGNORECASE),
    ]
    
    def __init__(self, parent=None, icons_path: Path = None, config=None):
        super().__init__(parent)
        self.icons_path = icons_path or Path(__file__).parent.parent / "icons"
        self.config = config
        self.current_url = None
        
        # Window setup
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Video Player")
        self.resize(800, 600)
        
        # Media player
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        self.video_widget = QVideoWidget()
        self.media_player.setVideoOutput(self.video_widget)
        
        # Setup UI
        self._setup_ui()
        
        # Set volume from config
        volume = 0.5
        if config:
            volume = config.get("video", "volume") or 0.5
        self.audio_output.setVolume(volume)
        self.volume_slider.setValue(int(volume * 100))
        
        # Signals
        self.media_player.positionChanged.connect(self._update_position)
        self.media_player.durationChanged.connect(self._update_duration)
        self.media_player.playbackStateChanged.connect(self._update_play_button)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
        
        # Loading spinner
        self.loading_spinner = LoadingSpinner(self, 60)
        self.loading_spinner.hide()
        
        # Track if we're loading
        self.is_loading = False
    
    def _setup_ui(self):
        """Setup the UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Video widget
        layout.addWidget(self.video_widget)
        
        # Controls - single row with config-based spacing
        controls = QWidget()
        
        # Get button size from config
        button_size = 48
        if self.config:
            btn_cfg = self.config.get("ui", "buttons", "large_button") or {}
            button_size = btn_cfg.get("button_size", 48)
        
        # Get spacing from config
        button_spacing = 8
        if self.config:
            button_spacing = self.config.get("ui", "buttons", "spacing") or 8
        
        # Get margins from config
        margin = 5
        if self.config:
            margin = self.config.get("ui", "margins", "widget") or 5
        
        # Set controls widget to exact button height
        controls.setFixedHeight(button_size)
        
        controls_layout = QHBoxLayout(controls)
        # Set margins to match button height - no extra vertical space
        controls_layout.setContentsMargins(margin * 2, 0, margin * 2, 0)
        controls_layout.setSpacing(button_spacing)
        
        # 1. Play/Stop button
        self.play_button = create_icon_button(
            self.icons_path, "play.svg", "Play (Space)", "large", self.config
        )
        self.play_button.clicked.connect(self._toggle_play)
        controls_layout.addWidget(self.play_button)
        
        # 2. Volume button
        self.volume_button = create_icon_button(
            self.icons_path, "volume-up.svg", "Mute (M)", "large", self.config
        )
        self.volume_button.clicked.connect(self._toggle_mute)
        self.volume_button.installEventFilter(self)
        controls_layout.addWidget(self.volume_button)
        
        # Volume slider (hidden by default, shown on hover) - no extra container
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMaximumWidth(80)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.installEventFilter(self)
        self.volume_slider.hide()
        controls_layout.addWidget(self.volume_slider)
        
        # 3. Time label
        self.time_label = QLabel("0:00 / 0:00")
        controls_layout.addWidget(self.time_label)
        
        # 4. Progress slider (takes remaining space)
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        controls_layout.addWidget(self.progress_slider)
        
        # 5. Fullscreen button
        self.fullscreen_button = create_icon_button(
            self.icons_path, "fullscreen.svg", "Fullscreen (F)", "large", self.config
        )
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        controls_layout.addWidget(self.fullscreen_button)
        
        layout.addWidget(controls)
    
    @staticmethod
    def is_video_url(url: str) -> bool:
        return any(p.search(url or '') for p in VideoPlayer.VIDEO_PATTERNS)
    
    def show_video(self, url: str, cursor_pos: QPoint = None):
        """Load and show video with loading spinner"""
        if self.current_url == url and self.isVisible():
            return
        
        self.current_url = url
        self.is_loading = True
        
        # Show loading spinner
        if cursor_pos:
            self._show_loading_spinner(cursor_pos)
        else:
            self._show_loading_spinner_center()
        
        self.media_player.setSource(QUrl(url))
        self.show()
        self.raise_()
        self.activateWindow()
        self.media_player.play()
    
    def _show_loading_spinner(self, cursor_pos: QPoint):
        """Show loading spinner near cursor"""
        spinner_pos = self._calc_spinner_position(cursor_pos)
        self.loading_spinner.move(spinner_pos)
        self.loading_spinner.start()
    
    def _show_loading_spinner_center(self):
        """Show loading spinner in center of video player"""
        center_x = (self.width() - self.loading_spinner.width()) // 2
        center_y = (self.height() - self.loading_spinner.height()) // 2
        self.loading_spinner.move(center_x, center_y)
        self.loading_spinner.start()
    
    def _calc_spinner_position(self, cursor_pos: QPoint):
        """Calculate spinner position near cursor within window bounds"""
        offset = 20
        w, h = self.loading_spinner.width(), self.loading_spinner.height()
        
        # Convert global cursor position to widget-relative position
        local_pos = self.mapFromGlobal(cursor_pos)
        
        # Calculate position with offset, checking bounds
        x = local_pos.x() - w - offset if local_pos.x() + offset + w > self.width() else local_pos.x() + offset
        y = local_pos.y() - h - offset if local_pos.y() + offset + h > self.height() else local_pos.y() + offset
        
        # Ensure within bounds
        x = max(0, min(x, self.width() - w))
        y = max(0, min(y, self.height() - h))
        
        return QPoint(x, y)
    
    def _on_media_status_changed(self, status):
        """Handle media status changes to hide loading spinner"""
        if status in (QMediaPlayer.MediaStatus.BufferedMedia, 
                      QMediaPlayer.MediaStatus.EndOfMedia,
                      QMediaPlayer.MediaStatus.InvalidMedia):
            self.is_loading = False
            self.loading_spinner.stop()
    
    def _toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()
    
    def _toggle_mute(self):
        self.audio_output.setMuted(not self.audio_output.isMuted())
        self._update_volume_button()
    
    def _on_volume_changed(self, value: int):
        """Update volume and save to config"""
        volume = value / 100.0
        self.audio_output.setVolume(volume)
        self._update_volume_button()
        
        # Save to config
        if self.config:
            self.config.set("video", "volume", value=volume)
    
    def eventFilter(self, obj, event):
        """Handle hover and wheel events on volume button and slider"""
        if obj == self.volume_button:
            if event.type() == event.Type.Enter:
                self.volume_slider.show()
            elif event.type() == event.Type.Leave:
                # Small delay before hiding
                QTimer.singleShot(500, self._check_hide_volume_slider)
            elif event.type() == event.Type.Wheel:
                delta = 5 if event.angleDelta().y() > 0 else -5
                new_volume = max(0, min(100, self.volume_slider.value() + delta))
                self.volume_slider.setValue(new_volume)
                return True
        elif obj == self.volume_slider:
            if event.type() == event.Type.Leave:
                # Small delay before hiding
                QTimer.singleShot(500, self._check_hide_volume_slider)
        
        return super().eventFilter(obj, event)
    
    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            icon_name = "fullscreen.svg"
        else:
            self.showFullScreen()
            icon_name = "exit-fullscreen.svg"
        
        self.fullscreen_button.setIcon(_render_svg_icon(self.icons_path / icon_name, self.fullscreen_button._icon_size))
        self.fullscreen_button._icon_name = icon_name
    
    def _update_volume_button(self):
        is_muted = self.audio_output.isMuted()
        volume = self.audio_output.volume()
        
        if is_muted or volume == 0:
            icon_name = "volume-mute.svg"
        elif volume < 0.5:
            icon_name = "volume-down.svg"
        else:
            icon_name = "volume-up.svg"
        
        self.volume_button.setIcon(_render_svg_icon(self.icons_path / icon_name, self.volume_button._icon_size))
        self.volume_button._icon_name = icon_name
    
    def _check_hide_volume_slider(self):
        """Hide volume slider if mouse is not over volume button or slider"""
        if not self.volume_button.underMouse() and not self.volume_slider.underMouse():
            self.volume_slider.hide()
    
    def _update_play_button(self, state):
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
        self.media_player.positionChanged.disconnect(self._update_position)
    
    def _on_slider_released(self):
        self.media_player.setPosition(self.progress_slider.value())
        self.media_player.positionChanged.connect(self._update_position)
    
    def _update_position(self, position):
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)
        
        duration = self.media_player.duration()
        self.time_label.setText(f"{self._format_time(position)} / {self._format_time(duration)}")
    
    def _update_duration(self, duration):
        self.progress_slider.setRange(0, duration)
    
    def _format_time(self, ms: int) -> str:
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        hours = minutes // 60
        minutes = minutes % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    def keyPressEvent(self, event):
        key = event.key()
        
        if key == Qt.Key.Key_Space:
            self._toggle_play()
        elif key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        elif key == Qt.Key.Key_F:
            self._toggle_fullscreen()
        elif key == Qt.Key.Key_M:
            self._toggle_mute()
        elif key == Qt.Key.Key_J:
            new_pos = max(0, self.media_player.position() - 10000)
            self.media_player.setPosition(new_pos)
        elif key == Qt.Key.Key_L:
            new_pos = min(self.media_player.duration(), self.media_player.position() + 10000)
            self.media_player.setPosition(new_pos)
        else:
            super().keyPressEvent(event)
    
    def _disconnect_signals(self):
        """Disconnect all media player signals"""
        for signal, slot in [
            (self.media_player.positionChanged, self._update_position),
            (self.media_player.durationChanged, self._update_duration),
            (self.media_player.playbackStateChanged, self._update_play_button),
            (self.media_player.mediaStatusChanged, self._on_media_status_changed)
        ]:
            try:
                signal.disconnect(slot)
            except:
                pass
    
    def closeEvent(self, event):
        self._disconnect_signals()
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.is_loading = False
        self.loading_spinner.stop()
        super().closeEvent(event)
    
    def cleanup(self):
        self._disconnect_signals()
        self.close()
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.media_player.deleteLater()
        self.audio_output.deleteLater()
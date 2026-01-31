"""Video player widget - displays videos in a movable window with YouTube support"""

import re
import os
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, QGraphicsView, QGraphicsScene
from PyQt6.QtCore import (
    Qt, QTimer, QUrl, QPoint, QSize, QRectF, QSizeF,
    QPropertyAnimation, QSequentialAnimationGroup, QParallelAnimationGroup,
    QPauseAnimation, QEasingCurve, QEvent, pyqtSignal, QObject, QThread
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaMetaData
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtGui import QPainter, QColor, QResizeEvent, QKeyEvent

from helpers.loading_spinner import LoadingSpinner
from helpers.create import create_icon_button, _render_svg_icon
from helpers.help import HelpPanel


# Suppress FFmpeg warnings
os.environ['AV_LOG_FORCE_NOCOLOR'] = '1'
os.environ['FFREPORT'] = 'level=32'


class YouTubeExtractor(QObject):
    """Compact YouTube stream extractor with adaptive quality"""
    finished = pyqtSignal(str, str, bool)  # stream_url, resolution, error
    
    def __init__(self, url: str, target_height: int = 1080):
        super().__init__()
        self.url = url
        self.target_height = target_height
        self._stop = False
    
    def run(self):
        if self._stop:
            return
        try:
            import yt_dlp
            
            # Adaptive quality: prefer higher quality based on target
            # Use 'best' format with height constraint for maximum quality
            format_str = f'bestvideo[height<={self.target_height}]+bestaudio/best[height<={self.target_height}]/best'
            
            opts = {
                'format': format_str,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                if not self._stop:
                    info = ydl.extract_info(self.url, download=False)
                    if not self._stop and (stream_url := info.get('url')):
                        # Get actual resolution
                        height = info.get('height', 0)
                        width = info.get('width', 0)
                        resolution = f"{height}p" if height else "Unknown"
                        if width and height:
                            resolution = f"{width}x{height}"
                        
                        self.finished.emit(stream_url, resolution, False)
                    else:
                        self.finished.emit('', '', True)
        except Exception as e:
            if not self._stop:
                print(f"YouTube extraction failed: {e}")
                self.finished.emit('', '', True)
    
    def stop(self):
        self._stop = True


class OverlayIcon(QWidget):
    """Overlay icon with animated fade in/out and scale"""
    
    def __init__(self, parent=None, icons_path: Path = None, size: int = 160):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.icons_path = icons_path or Path(__file__).parent.parent / "icons"
        self.size = size
        self.pixmap = None
        self._anim_group = None
        
    def paintEvent(self, event):
        if not self.pixmap:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Background circle
        center = self.width() // 2
        painter.setBrush(QColor(5, 5, 5, 128))
        painter.drawEllipse(center - self.size // 2, center - self.size // 2, self.size, self.size)
        
        # Icon (80% of container size)
        icon_size = int(self.size * 0.8)
        offset = (self.width() - icon_size) // 2
        painter.drawPixmap(offset, offset, icon_size, icon_size, self.pixmap)
    
    def show_icon(self, icon_name: str, proxy_widget):
        """Show icon with fade in/out animation"""
        icon_size = int(self.size * 0.8)
        icon = _render_svg_icon(self.icons_path / icon_name, icon_size)
        self.pixmap = icon.pixmap(QSize(icon_size, icon_size))
        self.update()
        
        if self._anim_group and self._anim_group.state() == QSequentialAnimationGroup.State.Running:
            self._anim_group.stop()
        
        proxy_widget.setTransformOriginPoint(proxy_widget.boundingRect().center())
        proxy_widget.setOpacity(0)
        proxy_widget.setScale(1.0)
        proxy_widget.show()
        
        self._anim_group = QSequentialAnimationGroup()
        
        # Fade in
        fade_in = QPropertyAnimation(proxy_widget, b"opacity")
        fade_in.setDuration(100)
        fade_in.setStartValue(0)
        fade_in.setEndValue(1)
        fade_in.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim_group.addAnimation(fade_in)
        
        self._anim_group.addAnimation(QPauseAnimation(200))
        
        # Fade out + scale
        out_group = QParallelAnimationGroup()
        fade_out = QPropertyAnimation(proxy_widget, b"opacity")
        fade_out.setDuration(400)
        fade_out.setStartValue(1)
        fade_out.setEndValue(0)
        fade_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        scale_out = QPropertyAnimation(proxy_widget, b"scale")
        scale_out.setDuration(400)
        scale_out.setStartValue(1.0)
        scale_out.setEndValue(1.5)
        scale_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        out_group.addAnimation(fade_out)
        out_group.addAnimation(scale_out)
        self._anim_group.addAnimation(out_group)
        self._anim_group.finished.connect(proxy_widget.hide)
        self._anim_group.start()


class VideoPlayer(QWidget):
    """Video player in a movable window with YouTube support"""
    
    VIDEO_PATTERNS = [
        re.compile(r'https?://[^\s<>"]+\.(?:mp4|webm|ogg|mov|avi|mkv|flv|wmv|m4v)(?:\?[^\s<>"]*)?', re.IGNORECASE),
        re.compile(r'https?://(?:www\.|m\.)?(?:youtube\.com/(?:shorts/|live/|watch\?v=|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})', re.IGNORECASE),
    ]

    def __init__(self, parent=None, icons_path: Path = None, config=None):
        super().__init__(parent)
        self.icons_path = icons_path or Path(__file__).parent.parent / "icons"
        self.config = config
        self.current_url = None
        self._signals_connected = False
        self._ui_ready = False
        self._slider_pressed = False
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._toggle_play)
        
        # YouTube extraction
        self.yt_thread = None
        self.yt_worker = None
        
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Video Player")
        self.setMinimumSize(400, 300)
        self.resize(800, 600)
        
        # Media player
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        # Video view
        self.video_view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.video_view.setScene(self.scene)
        self.video_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.media_player.setVideoOutput(self.video_item)
        
        # Overlay icon
        self.overlay_icon = OverlayIcon(icons_path=self.icons_path)
        self.overlay_proxy = self.scene.addWidget(self.overlay_icon)
        self.overlay_proxy.setVisible(False)
        self.overlay_proxy.setZValue(1)
        
        # Help panel
        self.help_panel = HelpPanel(self, viewer_type="video")
        
        self._setup_ui()
        self._ui_ready = True
        
        # Install event filters after UI ready
        for widget in [self.video_view, self.volume_button, self.volume_slider, self.progress_slider]:
            widget.installEventFilter(self)
        
        # Set volume
        volume = (self.config.get("video", "volume") if self.config else None) or 0.5
        self.audio_output.setVolume(volume)
        self.volume_slider.setValue(int(volume * 100))
        
        self._connect_signals()
        
        # Loading spinner
        self.loading_spinner = LoadingSpinner(None, 60)
        self.loading_spinner.hide()
        self.is_loading = False
    
    def _connect_signals(self):
        """Connect media player signals"""
        if not self._signals_connected:
            self.media_player.positionChanged.connect(self._update_position)
            self.media_player.durationChanged.connect(self._update_duration)
            self.media_player.playbackStateChanged.connect(self._update_play_button)
            self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
            self.media_player.metaDataChanged.connect(self._on_meta_data_changed)
            self._signals_connected = True

    def _setup_ui(self):
        """Setup the UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.video_view)
        
        # Get config values
        btn_cfg = self.config.get("ui", "buttons", "large_button") if self.config else None
        button_size = (btn_cfg.get("button_size") if btn_cfg else None) or 48
        spacing = (self.config.get("ui", "buttons", "spacing") if self.config else None) or 8
        
        # Controls
        controls = QWidget()
        controls.setFixedHeight(button_size)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(spacing)
        
        # Buttons
        self.play_button = create_icon_button(self.icons_path, "play.svg", "Play (Space/K)", "large", self.config)
        self.play_button.clicked.connect(self._toggle_play)
        
        self.volume_button = create_icon_button(self.icons_path, "volume-up.svg", "Mute (M)", "large", self.config)
        self.volume_button.clicked.connect(self._toggle_mute)
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMaximumWidth(80)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.hide()
        
        self.time_label = QLabel("0:00 / 0:00")
        
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        
        # Resolution label (compact, next to time)
        self.resolution_label = QLabel("")
        self.resolution_label.setStyleSheet("color: #888; font-size: 11px;")
        self.resolution_label.setVisible(False)
        
        self.fullscreen_button = create_icon_button(self.icons_path, "fullscreen.svg", "Fullscreen (F)", "large", self.config)
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        
        for w in [self.play_button, self.volume_button, self.volume_slider, self.time_label, 
                  self.resolution_label, self.progress_slider, self.fullscreen_button]:
            controls_layout.addWidget(w)
        
        layout.addWidget(controls)

    def _on_slider_pressed(self):
        """Handle slider press - stop position updates"""
        self._slider_pressed = True

    def _on_slider_released(self):
        """Handle slider release - seek to position"""
        self._slider_pressed = False
        self.media_player.setPosition(self.progress_slider.value())

    def _on_meta_data_changed(self):
        """Handle video metadata and adjust window size"""
        resolution = self.media_player.metaData().value(QMediaMetaData.Key.Resolution)
        if resolution and not resolution.isEmpty():
            w, h = resolution.width(), resolution.height()
            self.scene.setSceneRect(0, 0, w, h)
            self.video_item.setSize(QSizeF(w, h))
            self._update_overlay_position()
            self.video_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._fit_window_to_video(w, h)
            
            # Update resolution label
            self.resolution_label.setText(f"{w}x{h}")
            self.resolution_label.setVisible(True)
    
    def _fit_window_to_video(self, video_w: int, video_h: int):
        """Adjust window to match video aspect ratio within limits"""
        if video_w <= 0 or video_h <= 0:
            return
        
        MAX_W, MAX_H = 1920, 1080
        btn_cfg = self.config.get("ui", "buttons", "large_button") if self.config else None
        controls_h = (btn_cfg.get("button_size") if btn_cfg else None) or 48
        
        aspect = video_w / video_h
        
        if video_h > MAX_H:
            win_h, win_w = MAX_H, int(MAX_H * aspect)
        elif video_w > MAX_W:
            win_w, win_h = MAX_W, int(MAX_W / aspect)
        else:
            win_w, win_h = video_w, video_h
        
        self.resize(win_w, win_h + controls_h)
        
        # Center window on screen after resize
        screen_geo = self.screen().availableGeometry()
        window_geo = self.frameGeometry()
        window_geo.moveCenter(screen_geo.center())
        self.move(window_geo.topLeft())

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.video_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._update_overlay_position()

    def _update_overlay_position(self):
        """Center overlay in video"""
        video_size = self.video_item.size()
        if video_size.isEmpty():
            video_size = QSizeF(self.video_view.width(), self.video_view.height())
        
        x = (video_size.width() - self.overlay_icon.size) / 2
        y = (video_size.height() - self.overlay_icon.size) / 2
        self.overlay_proxy.setGeometry(QRectF(x, y, self.overlay_icon.size, self.overlay_icon.size))

    @staticmethod
    def is_video_url(url: str) -> bool:
        return any(p.search(url or '') for p in VideoPlayer.VIDEO_PATTERNS)
    
    @staticmethod
    def is_youtube_url(url: str) -> bool:
        return bool(re.search(
            r'https?://(?:www\.|m\.)?(?:youtube\.com/(?:shorts/|live/|watch\?v=|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})',
            url or '', re.IGNORECASE
        ))

    def show_video(self, url: str, cursor_pos: QPoint = None):
        """Load and show video with loading spinner (supports YouTube)"""
        if self.current_url == url and self.isVisible():
            return
        
        self.current_url = url
        self.is_loading = True
        self.resolution_label.setVisible(False)
        
        # Position and show spinner
        if cursor_pos:
            spinner_pos = LoadingSpinner.calculate_position(
                cursor_pos, self.loading_spinner.width(), self.loading_spinner.screen().availableGeometry()
            )
            self.loading_spinner.move(spinner_pos)
        else:
            screen_geo = self.loading_spinner.screen().availableGeometry()
            x = (screen_geo.width() - self.loading_spinner.width()) // 2
            y = (screen_geo.height() - self.loading_spinner.height()) // 2
            self.loading_spinner.move(x, y)
        
        self.loading_spinner.start()
        
        # Center window
        if not self.isVisible():
            screen_geo = self.screen().availableGeometry()
            window_geo = self.frameGeometry()
            window_geo.moveCenter(screen_geo.center())
            self.move(window_geo.topLeft())
        
        self.show()
        self.raise_()
        self.activateWindow()
        
        if not self._signals_connected:
            self._connect_signals()
        
        # YouTube or direct video
        if self.is_youtube_url(url):
            self._load_youtube(url)
        else:
            self.media_player.setSource(QUrl(url))
            self.media_player.play()
    
    def _load_youtube(self, url: str):
        """Extract and play YouTube stream with adaptive quality"""
        if self.yt_worker:
            self.yt_worker.stop()
        if self.yt_thread and self.yt_thread.isRunning():
            self.yt_thread.quit()
            self.yt_thread.wait(1000)
        
        # Request higher quality: 1080p minimum, prefer 1440p or 2160p if available
        target_height = 2160  # Request up to 4K, yt-dlp will get best available
        
        self.yt_worker = YouTubeExtractor(url, target_height)
        self.yt_thread = QThread()
        self.yt_worker.moveToThread(self.yt_thread)
        self.yt_thread.started.connect(self.yt_worker.run)
        self.yt_worker.finished.connect(self._on_youtube_ready)
        self.yt_worker.finished.connect(self.yt_thread.quit)
        self.yt_thread.start()
    
    def _on_youtube_ready(self, stream_url: str, resolution: str, error: bool):
        """Handle extracted YouTube stream"""
        if error or not stream_url:
            print(f"YouTube extraction failed")
            self.loading_spinner.stop()
            self.is_loading = False
            return
        
        # Update resolution label
        if resolution:
            self.resolution_label.setText(f"YT {resolution}")
            self.resolution_label.setVisible(True)
        
        self.media_player.setSource(QUrl(stream_url))
        self.media_player.play()

    def _on_media_status_changed(self, status):
        """Handle media status changes to hide loading spinner"""
        if status in (QMediaPlayer.MediaStatus.BufferedMedia,
                      QMediaPlayer.MediaStatus.EndOfMedia,
                      QMediaPlayer.MediaStatus.InvalidMedia):
            self.is_loading = False
            self.loading_spinner.stop()

    def _toggle_play(self):
        """Toggle play/pause and show overlay"""
        is_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.media_player.pause() if is_playing else self.media_player.play()
        self._update_overlay_position()
        self.overlay_icon.show_icon("stop.svg" if is_playing else "play.svg", self.overlay_proxy)

    def _toggle_mute(self):
        self.audio_output.setMuted(not self.audio_output.isMuted())
        self._update_volume_button()

    def _on_volume_changed(self, value: int):
        volume = value / 100.0
        self.audio_output.setVolume(volume)
        self._update_volume_button()
        if self.config:
            self.config.set("video", "volume", value=volume)

    def eventFilter(self, obj, event):
        """Handle hover and wheel events"""
        if not self._ui_ready:
            return super().eventFilter(obj, event)
        
        event_type = event.type()
        
        if obj == self.volume_button:
            if event_type == QEvent.Type.Enter:
                self.volume_slider.show()
            elif event_type == QEvent.Type.Leave:
                QTimer.singleShot(500, self._check_hide_volume_slider)
            elif event_type == QEvent.Type.Wheel:
                self._adjust_volume(event.angleDelta().y())
                return True
        
        elif obj == self.volume_slider and event_type == QEvent.Type.Leave:
            QTimer.singleShot(500, self._check_hide_volume_slider)
        
        elif obj in (self.progress_slider, self.video_view) and event_type == QEvent.Type.Wheel:
            self._seek_video(event.angleDelta().y())
            return True
        
        elif obj == self.video_view and event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                # Right-click closes the video player
                self.close()
                return True
            elif event.button() == Qt.MouseButton.LeftButton:
                # Start timer for single click, will be cancelled if double-click occurs
                self._click_timer.start(250)  # 250ms delay to detect double-click
                return True
        
        elif obj == self.video_view and event_type == QEvent.Type.MouseButtonDblClick:
            if event.button() == Qt.MouseButton.LeftButton:
                # Cancel single-click timer and toggle fullscreen instead
                self._click_timer.stop()
                self._toggle_fullscreen()
                return True
        
        return super().eventFilter(obj, event)
    
    def _adjust_volume(self, delta: int):
        change = 5 if delta > 0 else -5
        self.volume_slider.setValue(max(0, min(100, self.volume_slider.value() + change)))
    
    def _seek_video(self, delta: int):
        seek_ms = 5000 if delta > 0 else -5000
        new_pos = max(0, min(self.media_player.duration(), self.media_player.position() + seek_ms))
        self.media_player.setPosition(new_pos)

    def _toggle_fullscreen(self):
        is_fullscreen = self.isFullScreen()
        self.showNormal() if is_fullscreen else self.showFullScreen()
        
        icon_name = "fullscreen.svg" if is_fullscreen else "fullscreen-exit.svg"
        icon = _render_svg_icon(self.icons_path / icon_name, self.fullscreen_button._icon_size)
        self.fullscreen_button.setIcon(icon)
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
        
        icon = _render_svg_icon(self.icons_path / icon_name, self.volume_button._icon_size)
        self.volume_button.setIcon(icon)
        self.volume_button._icon_name = icon_name

    def _check_hide_volume_slider(self):
        if not self.volume_button.underMouse() and not self.volume_slider.underMouse():
            self.volume_slider.hide()

    def _update_play_button(self, state):
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        icon_name = "stop.svg" if is_playing else "play.svg"
        tooltip = "Stop (Space/K)" if is_playing else "Play (Space/K)"
        
        icon = _render_svg_icon(self.icons_path / icon_name, self.play_button._icon_size)
        self.play_button.setIcon(icon)
        self.play_button._icon_name = icon_name
        self.play_button.setToolTip(tooltip)

    def _update_position(self, position):
        """Update position slider and time label"""
        if not self._slider_pressed:
            self.progress_slider.setValue(position)
        duration = self.media_player.duration()
        self.time_label.setText(f"{self._format_time(position)} / {self._format_time(duration)}")

    def _update_duration(self, duration):
        self.progress_slider.setRange(0, duration)

    @staticmethod
    def _format_time(ms: int) -> str:
        seconds = ms // 1000
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts - layout independent"""
        key = event.key()
        
        if key == Qt.Key.Key_F1:
            if self.help_panel.isVisible():
                self.help_panel.hide()
            else:
                help_geo = self.help_panel.frameGeometry()
                help_geo.moveCenter(self.frameGeometry().center())
                self.help_panel.move(help_geo.topLeft())
                self.help_panel.show()
                self.help_panel.raise_()
        elif key == Qt.Key.Key_Space or event.text().lower() == 'k':
            self._toggle_play()
        elif key == Qt.Key.Key_Escape:
            self.showNormal() if self.isFullScreen() else self.close()
        elif event.text().lower() == 'f':
            self._toggle_fullscreen()
        elif event.text().lower() == 'm':
            self._toggle_mute()
        elif event.text().lower() == 'j':
            new_pos = max(0, self.media_player.position() - 5000)
            self.media_player.setPosition(new_pos)
        elif event.text().lower() == 'l':
            new_pos = min(self.media_player.duration(), self.media_player.position() + 5000)
            self.media_player.setPosition(new_pos)
        else:
            super().keyPressEvent(event)

    def _disconnect_signals(self):
        """Safely disconnect all signals"""
        if self._signals_connected:
            signals = [
                (self.media_player.positionChanged, self._update_position),
                (self.media_player.durationChanged, self._update_duration),
                (self.media_player.playbackStateChanged, self._update_play_button),
                (self.media_player.mediaStatusChanged, self._on_media_status_changed),
                (self.media_player.metaDataChanged, self._on_meta_data_changed),
            ]
            for signal, slot in signals:
                try:
                    signal.disconnect(slot)
                except TypeError:
                    pass
            self._signals_connected = False

    def closeEvent(self, event):
        """Clean up on close"""
        if self.yt_worker:
            self.yt_worker.stop()
        if self.yt_thread and self.yt_thread.isRunning():
            self.yt_thread.quit()
            self.yt_thread.wait(1000)
        
        self._disconnect_signals()
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.is_loading = False
        self.loading_spinner.stop()
        if self.help_panel:
            self.help_panel.close()
        super().closeEvent(event)

    def cleanup(self):
        """Full cleanup of resources"""
        if self.yt_worker:
            self.yt_worker.stop()
            try:
                self.yt_worker.finished.disconnect()
            except:
                pass
            self.yt_worker = None
        
        if self.yt_thread:
            if self.yt_thread.isRunning():
                self.yt_thread.quit()
                if not self.yt_thread.wait(500):
                    self.yt_thread.terminate()
                    self.yt_thread.wait(100)
            self.yt_thread.deleteLater()
            self.yt_thread = None
        
        self._disconnect_signals()
        self.close()
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.media_player.deleteLater()
        self.audio_output.deleteLater()
        if self.loading_spinner:
            self.loading_spinner.deleteLater()
        if self.help_panel:
            self.help_panel.deleteLater()
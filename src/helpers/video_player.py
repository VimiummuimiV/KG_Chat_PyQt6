"""Video player widget - displays videos in a movable window with YouTube support"""

import re
import os
from pathlib import Path

from PyQt6.QtWidgets import(
    QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, 
    QGraphicsView, QGraphicsScene, QMenu
)
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


# YouTube quality presets
YOUTUBE_QUALITIES = [
    (144, "144p"), (240, "240p"), (360, "360p"), (480, "480p"),
    (720, "720p"), (1080, "1080p"), (1440, "1440p"), 
    (2160, "2160p (4K)"), (4320, "4320p (8K)")
]


class YouTubeExtractor(QObject):
    """YouTube stream extractor with quality selection"""
    finished = pyqtSignal(str, str, bool)  # stream_url, actual_resolution, error
    formats_available = pyqtSignal(list)  # available_formats [(height, label), ...]
    
    def __init__(self, url: str, target_height: int = 1080, fetch_formats: bool = False):
        super().__init__()
        self.url = url
        self.target_height = target_height
        self.fetch_formats = fetch_formats
        self._stop = False
    
    def run(self):
        if self._stop:
            return
        try:
            import yt_dlp
            
            if self.fetch_formats:
                # Fast format list extraction (no stream URL)
                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {'youtube': {'player_client': ['android']}},
                }
                
                with yt_dlp.YoutubeDL(opts) as ydl:
                    if not self._stop:
                        info = ydl.extract_info(self.url, download=False)
                        formats = info.get('formats', [])
                        heights = {fmt.get('height') for fmt in formats 
                                 if fmt.get('vcodec', 'none') != 'none' and fmt.get('height')}
                        
                        available = [(h, label) for h, label in YOUTUBE_QUALITIES if h in heights]
                        if not available and heights:
                            available = [(h, f"{h}p") for h in sorted(heights)]
                        
                        self.formats_available.emit(available)
                return
            
            # Fast stream extraction - just get the URL
            format_selector = (
                f'bestvideo[height<={self.target_height}]+bestaudio/'
                f'best[height<={self.target_height}]/'
                f'best'
            )
            
            opts = {
                'format': format_selector,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'extractor_args': {'youtube': {'player_client': ['android']}},
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                if not self._stop:
                    info = ydl.extract_info(self.url, download=False)
                    
                    if not self._stop and (stream_url := info.get('url')):
                        height = info.get('height', 0)
                        width = info.get('width', 0)
                        resolution = f"{width}x{height}" if width and height else f"{height}p" if height else "Unknown"
                        
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
        
        # Background circle
        center = self.width() // 2
        painter.setBrush(QColor(5, 5, 5, 128))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center - self.size // 2, center - self.size // 2, self.size, self.size)
        
        # Icon
        icon_size = int(self.size * 0.8)
        offset = (self.width() - icon_size) // 2
        painter.drawPixmap(offset, offset, icon_size, icon_size, self.pixmap)
    
    def show_icon(self, icon_name: str, proxy_widget):
        """Show icon with fade in/out animation"""
        icon_size = int(self.size * 0.8)
        self.pixmap = _render_svg_icon(self.icons_path / icon_name, icon_size).pixmap(QSize(icon_size, icon_size))
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
        self._anim_group.addAnimation(fade_in)
        self._anim_group.addAnimation(QPauseAnimation(200))
        
        # Fade out + scale
        out_group = QParallelAnimationGroup()
        fade_out = QPropertyAnimation(proxy_widget, b"opacity")
        fade_out.setDuration(400)
        fade_out.setStartValue(1)
        fade_out.setEndValue(0)
        
        scale_out = QPropertyAnimation(proxy_widget, b"scale")
        scale_out.setDuration(400)
        scale_out.setStartValue(1.0)
        scale_out.setEndValue(1.5)
        
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
        self.is_youtube = False
        self._signals_connected = False
        self._ui_ready = False
        self._slider_pressed = False
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._toggle_play)
        
        # YouTube extraction
        self.yt_thread = None
        self.yt_worker = None
        self.preferred_quality = (self.config.get("video", "youtube_quality") if self.config else None) or 1080
        self.available_formats = []  # Track available formats for current video
        
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Video Player")
        self.setMinimumSize(400, 300)
        self.resize(960, 720)
        
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
        
        # Left side controls
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
        
        # Current resolution label (YouTube only)
        self.current_quality_label = QLabel("")
        self.current_quality_label.setStyleSheet("color: #888; font-size: 11px;")
        self.current_quality_label.setVisible(False)
        
        # Progress slider (center, stretches)
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        
        # Right side controls
        self.quality_button = create_icon_button(self.icons_path, "settings.svg", "Quality", "large", self.config)
        self.quality_button.clicked.connect(self._show_quality_menu)
        self.quality_button.setVisible(False)
        
        self.fullscreen_button = create_icon_button(self.icons_path, "fullscreen.svg", "Fullscreen (F)", "large", self.config)
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        
        for w in [self.play_button, self.volume_button, self.volume_slider, self.time_label,
                  self.current_quality_label, self.progress_slider, self.quality_button, self.fullscreen_button]:
            controls_layout.addWidget(w)
        
        layout.addWidget(controls)

    def _show_quality_menu(self):
        """Show quality selection menu for YouTube videos"""
        if not self.is_youtube:
            return
        
        # Fetch formats if not already available
        if not self.available_formats:
            # Quick format fetch
            if self.yt_thread and self.yt_thread.isRunning():
                return  # Already loading
            
            self.yt_worker = YouTubeExtractor(self.current_url, self.preferred_quality, fetch_formats=True)
            self.yt_thread = QThread()
            self.yt_worker.moveToThread(self.yt_thread)
            self.yt_thread.started.connect(self.yt_worker.run)
            self.yt_worker.formats_available.connect(self._on_formats_available)
            self.yt_worker.formats_available.connect(self.yt_thread.quit)
            self.yt_thread.finished.connect(lambda: self._show_quality_menu())  # Show menu after formats loaded
            self.yt_thread.start()
            return
        
        menu = QMenu(self)
        
        # Show only available formats
        for height, label in self.available_formats:
            action = menu.addAction(label)
            if height == self.preferred_quality:
                action.setCheckable(True)
                action.setChecked(True)
            action.triggered.connect(lambda checked, h=height: self._change_quality(h))
        
        # Position menu above button
        button_pos = self.quality_button.mapToGlobal(QPoint(0, 0))
        menu_height = menu.sizeHint().height()
        menu.exec(QPoint(button_pos.x(), button_pos.y() - menu_height))

    def _change_quality(self, new_height: int):
        """Change YouTube quality and resume from current position"""
        if not self.is_youtube or new_height == self.preferred_quality:
            return
        
        # Save current position
        current_pos = self.media_player.position()
        was_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        
        # Update preference
        self.preferred_quality = new_height
        if self.config:
            self.config.set("video", "youtube_quality", value=new_height)
        
        # Reload with new quality
        self._load_youtube(self.current_url, resume_position=current_pos, auto_play=was_playing)

    def _on_slider_pressed(self):
        """Handle slider press - stop position updates"""
        self._slider_pressed = True

    def _on_slider_released(self):
        """Handle slider release - seek to position"""
        self._slider_pressed = False
        self.media_player.setPosition(self.progress_slider.value())

    def _on_meta_data_changed(self):
        """Handle video metadata and adjust window size to match aspect ratio"""
        resolution = self.media_player.metaData().value(QMediaMetaData.Key.Resolution)
        if resolution and not resolution.isEmpty():
            w, h = resolution.width(), resolution.height()
            self.scene.setSceneRect(0, 0, w, h)
            self.video_item.setSize(QSizeF(w, h))
            self._update_overlay_position()
            self.video_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            
            # Adjust window to match video aspect ratio
            if not self.isFullScreen():
                self._fit_window_to_video(w, h)

    def _fit_window_to_video(self, video_w: int, video_h: int):
        """Adjust window to match video aspect ratio perfectly"""
        if video_w <= 0 or video_h <= 0:
            return
        
        screen_geo = self.screen().availableGeometry()
        MAX_W, MAX_H = int(screen_geo.width() * 0.9), int(screen_geo.height() * 0.9)
        controls_h = (self.config.get("ui", "buttons", "large_button", "button_size") if self.config else None) or 48
        
        aspect = video_w / video_h
        win_w, win_h = video_w, video_h
        
        if win_h > MAX_H:
            win_h, win_w = MAX_H, int(MAX_H * aspect)
        if win_w > MAX_W:
            win_w, win_h = MAX_W, int(MAX_W / aspect)
        
        self.resize(win_w, win_h + controls_h)
        
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
        """Load and show video with loading spinner"""
        if self.current_url == url and self.isVisible():
            return
        
        self.current_url = url
        self.is_youtube = self.is_youtube_url(url)
        self.quality_button.setVisible(self.is_youtube)
        self.current_quality_label.setVisible(self.is_youtube)
        self.is_loading = True
        
        # Position spinner
        if cursor_pos:
            spinner_pos = LoadingSpinner.calculate_position(
                cursor_pos, self.loading_spinner.width(), self.loading_spinner.screen().availableGeometry()
            )
            self.loading_spinner.move(spinner_pos)
        else:
            screen_geo = self.loading_spinner.screen().availableGeometry()
            self.loading_spinner.move(
                (screen_geo.width() - self.loading_spinner.width()) // 2,
                (screen_geo.height() - self.loading_spinner.height()) // 2
            )
        
        self.loading_spinner.start()
        
        # Center and show window
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
        
        # Load video
        if self.is_youtube:
            self._load_youtube(url)
        else:
            self.media_player.setSource(QUrl(url))
            self.media_player.play()
    
    def _load_youtube(self, url: str, resume_position: int = 0, auto_play: bool = True):
        """Extract and play YouTube stream with selected quality - fast!"""
        if self.yt_worker:
            self.yt_worker.stop()
        if self.yt_thread and self.yt_thread.isRunning():
            self.yt_thread.quit()
            self.yt_thread.wait(1000)
        
        # Just get the stream URL - don't fetch formats list
        self.yt_worker = YouTubeExtractor(url, self.preferred_quality, fetch_formats=False)
        self.yt_thread = QThread()
        self.yt_worker.moveToThread(self.yt_thread)
        self.yt_thread.started.connect(self.yt_worker.run)
        
        # Handle stream URL only
        self.yt_worker.finished.connect(
            lambda stream_url, res, err: self._on_youtube_ready(stream_url, res, err, resume_position, auto_play)
        )
        self.yt_worker.finished.connect(self.yt_thread.quit)
        self.yt_thread.start()
    
    def _on_formats_available(self, formats: list):
        """Store available formats for quality menu"""
        self.available_formats = formats
    
    def _on_youtube_ready(self, stream_url: str, resolution: str, error: bool, 
                          resume_position: int = 0, auto_play: bool = True):
        """Handle extracted YouTube stream"""
        if error or not stream_url:
            print(f"YouTube extraction failed")
            self.loading_spinner.stop()
            self.is_loading = False
            return
        
        # Display current resolution
        self.current_quality_label.setText(resolution)
        self.quality_button.setToolTip(f"Quality: {resolution}")
        
        self.media_player.setSource(QUrl(stream_url))
        
        if resume_position > 0:
            # Resume from saved position
            def seek_after_buffered():
                self.media_player.setPosition(resume_position)
                self.media_player.mediaStatusChanged.disconnect(seek_after_buffered)
            
            self.media_player.mediaStatusChanged.connect(seek_after_buffered)
        
        if auto_play:
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
                self.close()
                return True
            elif event.button() == Qt.MouseButton.LeftButton:
                self._click_timer.start(250)
                return True
        
        elif obj == self.video_view and event_type == QEvent.Type.MouseButtonDblClick:
            if event.button() == Qt.MouseButton.LeftButton:
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

    def _update_button_icon(self, button, icon_name, tooltip=None):
        """Update button icon and tooltip"""
        icon = _render_svg_icon(self.icons_path / icon_name, button._icon_size)
        button.setIcon(icon)
        button._icon_name = icon_name
        if tooltip:
            button.setToolTip(tooltip)

    def _toggle_fullscreen(self):
        is_fullscreen = self.isFullScreen()
        self.showNormal() if is_fullscreen else self.showFullScreen()
        icon_name = "fullscreen.svg" if is_fullscreen else "fullscreen-exit.svg"
        self._update_button_icon(self.fullscreen_button, icon_name)

    def _update_volume_button(self):
        volume = self.audio_output.volume()
        if self.audio_output.isMuted() or volume == 0:
            icon_name = "volume-mute.svg"
        elif volume < 0.5:
            icon_name = "volume-down.svg"
        else:
            icon_name = "volume-up.svg"
        self._update_button_icon(self.volume_button, icon_name)

    def _update_play_button(self, state):
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        icon_name = "stop.svg" if is_playing else "play.svg"
        tooltip = "Stop (Space/K)" if is_playing else "Play (Space/K)"
        self._update_button_icon(self.play_button, icon_name, tooltip)

    def _check_hide_volume_slider(self):
        if not self.volume_button.underMouse() and not self.volume_slider.underMouse():
            self.volume_slider.hide()

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
            self.yt_worker = None
        
        if self.yt_thread and self.yt_thread.isRunning():
            self.yt_thread.quit()
            self.yt_thread.wait(500) or self.yt_thread.terminate()
            self.yt_thread.deleteLater()
            self.yt_thread = None
        
        self._disconnect_signals()
        self.close()
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        
        for obj in [self.media_player, self.audio_output, self.loading_spinner, self.help_panel]:
            if obj:
                obj.deleteLater()
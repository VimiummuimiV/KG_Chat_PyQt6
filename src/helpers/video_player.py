"""Video player widget - displays videos in a movable window"""
import re
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget
from PyQt6.QtCore import(
    Qt, QTimer, QUrl, QPoint, QRect, QSize, pyqtProperty,
    QPropertyAnimation, QSequentialAnimationGroup, QParallelAnimationGroup,
    QPauseAnimation, QEasingCurve, QEvent, QRectF, QSizeF
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaMetaData
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QResizeEvent
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from helpers.loading_spinner import LoadingSpinner
from helpers.create import create_icon_button, _render_svg_icon

class OverlayIcon(QWidget):
    """Overlay icon with animated fade in/out and scale"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.pixmap = None
        self.base_size = 160
        self.base_icon_size = 128
        self.max_scale = 1.5

    def paintEvent(self, event):
        if not self.pixmap:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        # Background ellipse
        draw_rect = QRect(
            int((self.width() - self.base_size) / 2),
            int((self.height() - self.base_size) / 2),
            self.base_size,
            self.base_size
        )
        painter.setBrush(QColor(5, 5, 5, 128))
        painter.drawEllipse(draw_rect)
        # Icon pixmap
        icon_rect = QRect(
            int((self.width() - self.base_icon_size) / 2),
            int((self.height() - self.base_icon_size) / 2),
            self.base_icon_size,
            self.base_icon_size
        )
        painter.drawPixmap(icon_rect, self.pixmap)

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

        # Video view setup
        self.video_view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.video_view.setScene(self.scene)
        self.video_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.media_player.setVideoOutput(self.video_item)

        # Overlay icon
        self.overlay_icon = OverlayIcon()
        self.overlay_proxy = self.scene.addWidget(self.overlay_icon)
        self.overlay_proxy.setVisible(False)
        self.overlay_proxy.setZValue(1)

        # Setup UI
        self._setup_ui()

        # Install event filter on video view
        self.video_view.installEventFilter(self)

        # Set volume from config
        volume = self.config.get("video", "volume") if self.config else None
        volume = volume or 0.5
        self.audio_output.setVolume(volume)
        self.volume_slider.setValue(int(volume * 100))

        # Connect signals
        self.media_player.positionChanged.connect(self._update_position)
        self.media_player.durationChanged.connect(self._update_duration)
        self.media_player.playbackStateChanged.connect(self._update_play_button)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.media_player.metaDataChanged.connect(self._on_meta_data_changed)

        # Loading spinner
        self.loading_spinner = LoadingSpinner(self, 60)
        self.loading_spinner.hide()
        self.is_loading = False

    def _setup_ui(self):
        """Setup the UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Video view
        layout.addWidget(self.video_view)

        # Get config values
        button_size = 48
        spacing = 8

        if self.config:
            btn_cfg = self.config.get("ui", "buttons", "large_button") or {}
            button_size = btn_cfg.get("button_size", 48)
            spacing = self.config.get("ui", "buttons", "spacing") or 8

        # Controls container - height includes button + top/bottom margins
        controls = QWidget()
        controls_height = button_size
        controls.setFixedHeight(controls_height)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(spacing)

        # Play/Stop button
        self.play_button = create_icon_button(
            self.icons_path, "play.svg", "Play (Space)", "large", self.config
        )
        self.play_button.clicked.connect(self._toggle_play)
        controls_layout.addWidget(self.play_button)

        # Volume button
        self.volume_button = create_icon_button(
            self.icons_path, "volume-up.svg", "Mute (M)", "large", self.config
        )
        self.volume_button.clicked.connect(self._toggle_mute)
        self.volume_button.installEventFilter(self)
        controls_layout.addWidget(self.volume_button)

        # Volume slider
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMaximumWidth(80)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.installEventFilter(self)
        self.volume_slider.hide()
        controls_layout.addWidget(self.volume_slider)

        # Time label
        self.time_label = QLabel("0:00 / 0:00")
        controls_layout.addWidget(self.time_label)

        # Progress slider
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        self.progress_slider.installEventFilter(self)
        controls_layout.addWidget(self.progress_slider)

        # Fullscreen button
        self.fullscreen_button = create_icon_button(
            self.icons_path, "fullscreen.svg", "Fullscreen (F)", "large", self.config
        )
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        controls_layout.addWidget(self.fullscreen_button)
        layout.addWidget(controls)

    def _on_meta_data_changed(self):
        resolution = self.media_player.metaData().value(QMediaMetaData.Key.Resolution)
        if resolution and not resolution.isEmpty():
            self.scene.setSceneRect(0, 0, resolution.width(), resolution.height())
            self.video_item.setSize(QSizeF(resolution.width(), resolution.height()))
            self.video_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.video_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

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
            screen = self.screen().availableGeometry()
            spinner_pos = LoadingSpinner.calculate_position(
                cursor_pos, self.loading_spinner.width(), screen
            )
            self.loading_spinner.move(self.mapFromGlobal(spinner_pos))
        else:
            # Center spinner
            x = (self.width() - self.loading_spinner.width()) // 2
            y = (self.height() - self.loading_spinner.height()) // 2
            self.loading_spinner.move(x, y)
        self.loading_spinner.start()
        self.media_player.setSource(QUrl(url))
        self.show()
        self.raise_()
        self.activateWindow()
        self.media_player.play()

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
        self._show_overlay()

    def _toggle_mute(self):
        self.audio_output.setMuted(not self.audio_output.isMuted())
        self._update_volume_button()

    def _on_volume_changed(self, value: int):
        """Update volume and save to config"""
        volume = value / 100.0
        self.audio_output.setVolume(volume)
        self._update_volume_button()
        if self.config:
            self.config.set("video", "volume", value=volume)

    def eventFilter(self, obj, event):
        """Handle hover and wheel events"""
        if obj == self.volume_button:
            if event.type() == QEvent.Type.Enter:
                self.volume_slider.show()
            elif event.type() == QEvent.Type.Leave:
                QTimer.singleShot(500, self._check_hide_volume_slider)
            elif event.type() == QEvent.Type.Wheel:
                delta = 5 if event.angleDelta().y() > 0 else -5
                new_volume = max(0, min(100, self.volume_slider.value() + delta))
                self.volume_slider.setValue(new_volume)
                return True
        elif obj == self.volume_slider:
            if event.type() == QEvent.Type.Leave:
                QTimer.singleShot(500, self._check_hide_volume_slider)
        elif obj == self.progress_slider:
            if event.type() == QEvent.Type.Wheel:
                delta = 5000 if event.angleDelta().y() > 0 else -5000
                current_pos = self.media_player.position()
                duration = self.media_player.duration()
                new_pos = max(0, min(duration, current_pos + delta))
                self.media_player.setPosition(new_pos)
                return True
        elif obj == self.video_view:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._toggle_play()
                return True
        return super().eventFilter(obj, event)

    def _show_overlay(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            icon_name = "play.svg"  # Shown when starting playback
        else:
            icon_name = "stop.svg"  # Shown when pausing; adjust if using "pause.svg"
        icon_size = QSize(self.overlay_icon.base_icon_size, self.overlay_icon.base_icon_size)
        icon = _render_svg_icon(self.icons_path / icon_name, icon_size)
        self.overlay_icon.pixmap = icon.pixmap(icon_size)
        self.overlay_icon.update()

        # Compute size for geometry in scene coordinates
        video_size = self.video_item.size()
        if video_size.isEmpty():
            # Fallback if size not available yet
            video_size = QSizeF(self.video_view.width(), self.video_view.height())
        base_size = self.overlay_icon.base_size
        x = (video_size.width() - base_size) / 2
        y = (video_size.height() - base_size) / 2
        self.overlay_proxy.setGeometry(QRectF(x, y, base_size, base_size))
        self.overlay_proxy.setTransformOriginPoint(self.overlay_proxy.boundingRect().center())
        self.overlay_proxy.setOpacity(0)
        self.overlay_proxy.setScale(1.0)
        self.overlay_proxy.show()
        # Appear animation (fade in)
        appear_anim = QPropertyAnimation(self.overlay_proxy, b"opacity")
        appear_anim.setDuration(100)
        appear_anim.setStartValue(0)
        appear_anim.setEndValue(1)
        appear_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        # Pause
        pause = QPauseAnimation(200)
        # Out animation (scale up + fade out)
        out_group = QParallelAnimationGroup()
        fade_out = QPropertyAnimation(self.overlay_proxy, b"opacity")
        fade_out.setDuration(400)
        fade_out.setStartValue(1)
        fade_out.setEndValue(0)
        fade_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        out_group.addAnimation(fade_out)
        scale_out = QPropertyAnimation(self.overlay_proxy, b"scale")
        scale_out.setDuration(400)
        scale_out.setStartValue(1.0)
        scale_out.setEndValue(self.overlay_icon.max_scale)
        scale_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        out_group.addAnimation(scale_out)
        # Main animation group
        anim_group = QSequentialAnimationGroup()
        anim_group.addAnimation(appear_anim)
        anim_group.addAnimation(pause)
        anim_group.addAnimation(out_group)
        anim_group.finished.connect(self.overlay_proxy.hide)
        anim_group.start()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            icon_name = "fullscreen.svg"
        else:
            self.showFullScreen()
            icon_name = "fullscreen-exit.svg"
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
        icon = _render_svg_icon(self.icons_path / icon_name, self.play_button._icon_size)
        self.play_button.setIcon(icon)
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
        signals = [
            (self.media_player.positionChanged, self._update_position),
            (self.media_player.durationChanged, self._update_duration),
            (self.media_player.playbackStateChanged, self._update_play_button),
            (self.media_player.mediaStatusChanged, self._on_media_status_changed),
            (self.media_player.metaDataChanged, self._on_meta_data_changed)
        ]
        for signal, slot in signals:
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
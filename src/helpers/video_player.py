"""Video player widget - launches mpvnet player for video URLs"""
import re
import subprocess
import platform
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import QPoint, QTimer, Qt

from components.loading_spinner import LoadingSpinner
from helpers.translate import tr


def _link(url: str) -> str:
    """HTML link whose display text is the URL itself (language-independent)."""
    return f'<a href="{url}">{url}</a>'


class VideoPlayer(QWidget):
    """Video player that launches mpvnet for playback"""
    
    VIDEO_PATTERNS = [
        # Direct video files
        re.compile(
            r'https?://[^\s<>"]+\.(?:mp4|webm|ogg|mov|avi|mkv|flv|wmv|m4v)(?:\?[^\s<>"]*)?',
            re.IGNORECASE
        ),
        # YouTube
        re.compile(
            r'https?://(?:www\.|m\.)?(?:'
            r'youtube\.com/(?:shorts/|live/|watch\?v=|embed/)|'
            r'youtu\.be/'
            r')[a-zA-Z0-9_-]{11}',
            re.IGNORECASE
        ),
        # RuTube
        re.compile(
            r'https?://(?:www\.)?rutube\.ru/video/[a-f0-9]{32}/?',
            re.IGNORECASE
        ),
        # VK / VK Video
        re.compile(
            r'https?://(?:www\.)?(?:vkvideo\.ru|vk\.com)/(?:video|clip)-?\d+_\d+',
            re.IGNORECASE
        ),
        # Vimeo
        re.compile(
            r'https?://(?:www\.)?vimeo\.com/(?:\d+|showcase/\d+/video/\d+)',
            re.IGNORECASE
        ),
        # Twitch
        re.compile(
            r'https?://(?:www\.)?twitch\.tv/(?:videos/\d+|[^/\s<>"]+)',
            re.IGNORECASE
        ),
        # Kick
        re.compile(
            r'https?://(?:www\.)?kick\.com/[^/\s<>?"#]+',
            re.IGNORECASE
        ),
        # OK / Odnoklassniki
        re.compile(
            r'https?://(?:www\.)?ok\.ru/video/\d+',
            re.IGNORECASE
        ),
        # Dzen
        re.compile(
            r'https?://(?:www\.)?dzen\.ru/video/watch/[^?\s<>"]+',
            re.IGNORECASE
        ),
        # Pikabu
        re.compile(
            r'https?://(?:www\.)?pikabu\.ru/[^?\s<>"]+',
            re.IGNORECASE
        ),
    ]

    def __init__(self, parent=None, icons_path: Path = None, config=None):
        super().__init__(parent)
        self.hide()  # never painted - stays hidden so it can't eat viewport clicks
        self.config = config
        self.current_url = None
        self.mpv_path = self._find_mpv()
        self.ytdlp_path = self._find_ytdlp()
        self.mpv_process = None  # Track the mpv process
        
        # Loading spinner
        self.loading_spinner = LoadingSpinner(None, 60)
        self.loading_spinner.hide()
        self.is_loading = False
    
    def _find_mpv(self) -> str:
        """Find mpvnet/mpv executable cross-platform"""
        # Check PATH first
        for exe in ['mpvnet', 'mpv']:
            if path := shutil.which(exe):
                return path
        
        system = platform.system()
        
        if system == 'Windows':
            # Search common Windows directories for mpvnet.exe and mpv.exe
            search_dirs = [
                Path.home() / 'AppData/Local/Programs',
                Path('C:/Program Files'),
                Path('C:/Program Files (x86)'),
            ]
            
            for search_dir in search_dirs:
                if search_dir.exists():
                    # Look for both mpvnet.exe and mpv.exe in subdirectories (max 2 levels deep)
                    for exe_name in ['mpvnet.exe', 'mpv.exe']:
                        for path in search_dir.glob(f'*/{exe_name}'):
                            return str(path)
                        for path in search_dir.glob(f'*/*/{exe_name}'):
                            return str(path)
        
        elif system == 'Darwin':
            # macOS: check Homebrew paths
            for path in [Path('/opt/homebrew/bin/mpv'), Path('/usr/local/bin/mpv')]:
                if path.exists():
                    return str(path)
        
        elif system == 'Linux':
            # Linux: check common install paths
            for path in [Path('/usr/bin/mpv'), Path('/usr/local/bin/mpv'), Path.home() / '.local/bin/mpv']:
                if path.exists():
                    return str(path)
        
        return 'mpv'  # Fallback

    @staticmethod
    def _app_base_dir() -> Path:
        """Project root dir (handles both source layout and frozen/PyInstaller builds)"""
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).resolve().parent
        # this file lives in <root>/helpers/, bin/ is one level up in <root>/
        return Path(__file__).resolve().parent.parent

    _YTDLP_BUNDLED_NAMES = {'Windows': 'yt-dlp.exe', 'Darwin': 'yt-dlp_macos', 'Linux': 'yt-dlp_linux'}

    def _find_ytdlp(self) -> str | None:
        """Find yt-dlp: prefer a standalone build bundled with the app, fall back to PATH"""
        system = platform.system()
        bundled_name = self._YTDLP_BUNDLED_NAMES.get(system)
        if bundled_name:
            base_dir = self._app_base_dir()
            for candidate in (base_dir / 'bin' / bundled_name, base_dir / bundled_name):
                if candidate.exists():
                    return str(candidate)
        return shutil.which('yt-dlp')

    @staticmethod
    def is_video_url(url: str) -> bool:
        """Check if URL is a video URL"""
        return any(p.search(url or '') for p in VideoPlayer.VIDEO_PATTERNS)

    def _show_error_dialog(self, title: str, text: str, informative_text: str, icon=QMessageBox.Icon.Warning):
        """Helper function to show error dialogs"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setInformativeText(informative_text)
        msg_box.setTextFormat(Qt.TextFormat.RichText)  # Enable HTML links
        msg_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)  # Make links clickable
        
        # Add Copy and OK buttons
        copy_button = msg_box.addButton(tr("Copy", "Копировать"), QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton(QMessageBox.StandardButton.Ok)
        
        msg_box.exec()
        
        # If Copy button was clicked, copy the plain text to clipboard
        if msg_box.clickedButton() == copy_button:
            from PyQt6.QtWidgets import QApplication
            # Strip HTML tags for plain text copy
            plain_text = f"{text}\n\n{informative_text}"
            plain_text = re.sub(r'<br>', '\n', plain_text)
            plain_text = re.sub(r'<[^>]+>', '', plain_text)
            QApplication.clipboard().setText(plain_text)

    def _show_mpv_error(self):
        """Show a graphical error dialog when mpv is not found"""
        system = platform.system()

        # Base message with official site
        official_site = _link("https://mpv.io/installation/")
        install_msg = tr(
            f'Please install MPV from the official site:<br>{official_site}',
            f'Установите MPV с официального сайта:<br>{official_site}'
        )

        # Add platform-specific additional options
        if system == 'Windows':
            mpvnet = _link("https://github.com/mpvnet-player/mpv.net/releases/")
            winbuild = _link("https://github.com/zhongfly/mpv-winbuild/releases/")
            dotnet = _link("https://dotnet.microsoft.com/en-us/download/dotnet/")
            install_msg += tr(
                f'<br><br><b>Windows builds:</b><br>{mpvnet}<br>'
                f'or<br>{winbuild}'
                f'<br><br><b>.NET SDK</b> (required for mpv.net):<br>{dotnet}',
                f'<br><br><b>Сборки для Windows:</b><br>{mpvnet}<br>'
                f'или<br>{winbuild}'
                f'<br><br><b>.NET SDK</b> (нужен для mpv.net):<br>{dotnet}'
            )
        elif system == 'Darwin':
            install_msg += tr(
                '<br><br><b>macOS:</b> brew install mpv',
                '<br><br><b>macOS:</b> brew install mpv'
            )
        else:
            install_msg += tr(
                '<br><br><b>Linux:</b> sudo apt install mpv<br>(or use your distro\'s package manager)',
                '<br><br><b>Linux:</b> sudo apt install mpv<br>(или менеджер пакетов вашего дистрибутива)'
            )

        # Add custom GUI options
        uosc = _link("https://github.com/tomasklaen/uosc/releases/")
        modernz = _link("https://github.com/Samillion/ModernZ/releases/")
        install_msg += tr(
            f'<br><br><b>Custom GUI (optional):</b><br>{uosc}<br>or<br>{modernz}',
            f'<br><br><b>Сторонний GUI (опционально):</b><br>{uosc}<br>или<br>{modernz}'
        )
        
        # Show graphical dialog
        self._show_error_dialog(
            tr("Video Player Not Found", "Видеоплеер не найден"),
            tr("MPV video player is not installed.", "Видеоплеер MPV не установлен."),
            install_msg
        )

    def _close_previous_mpv(self):
        """Close previous mpv instance if running"""
        if not self.mpv_process or self.mpv_process.poll() is not None:
            return
        
        try:
            if platform.system() == 'Windows':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.mpv_process.pid)],
                              capture_output=True, timeout=2)
            else:
                self.mpv_process.terminate()
                self.mpv_process.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, Exception):
            try:
                self.mpv_process.kill()
            except Exception:
                pass
        finally:
            self.mpv_process = None

    def show_video(self, url: str, cursor_pos: QPoint = None, force_log: bool = False):
        """Launch mpv player with the video URL."""
        self.current_url = url
        
        # Check if mpv is available
        if not self.mpv_path or not shutil.which(self.mpv_path):
            self._show_mpv_error()
            return
        
        # Close previous mpv instance if running
        self._close_previous_mpv()
        
        self.is_loading = True
        
        # Position and show spinner
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
        
        # Launch mpv in a separate process
        try:
            log_enabled = force_log or bool(self.config and self.config.get("player", "log"))
            log_path = self._debug_log_path(url) if log_enabled else None
            mpv_cmd = self._build_mpv_command(url, log_path=log_path)

            kwargs = {
                'stdin': subprocess.DEVNULL,
                'stdout': subprocess.DEVNULL,
                'stderr': subprocess.DEVNULL
            }
            if platform.system() == 'Windows':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            self.mpv_process = subprocess.Popen(mpv_cmd, **kwargs)

            # Stop spinner after brief delay (mpv is launching)
            QTimer.singleShot(1000, self._stop_loading)

        except Exception as e:
            print(f"Failed to launch mpv: {e}")
            self._stop_loading()
            self.mpv_process = None

            self._show_error_dialog(
                tr("Video Player Error", "Ошибка видеоплеера"),
                tr("Failed to launch video player.", "Не удалось запустить видеоплеер."),
                tr(f"Error: {str(e)}", f"Ошибка: {str(e)}"),
                QMessageBox.Icon.Critical
            )

    @staticmethod
    def _debug_log_path(url: str) -> Path:
        """Return a timestamped debug log path for the video source."""
        log_dir = Path.home() / "Desktop" / "mpv-debug"
        log_dir.mkdir(parents=True, exist_ok=True)

        host = urlparse(url or "").hostname or "source"
        host = host.lower().rstrip(".")

        aliases = {
            "youtube.com": "YouTube",
            "youtu.be": "YouTube",
            "pikabu.ru": "Pikabu",
            "twitch.tv": "Twitch",
            "kick.com": "Kick",
            "vk.ru": "VK",
            "vkvideo.ru": "VKVideo",
            "vimeo.com": "Vimeo",
            "rutube.ru": "RuTube",
            "dzen.ru": "Dzen",
            "ok.ru": "OK",
        }

        resource = next(
            (
                name
                for domain, name in aliases.items()
                if host == domain or host.endswith(f".{domain}")
            ),
            host.split(".")[0] or "Source",
        )
        resource = re.sub(r"[^a-zA-Z0-9_-]", "_", resource) or "Source"

        timestamp = datetime.now().strftime("%Y-%m-%d - %H-%M-%S")
        return log_dir / f"[{resource}] {timestamp}.log"

    def _build_mpv_command(self, url: str, log_path: Path | None = None) -> list:
        """Build mpv command with appropriate options"""
        cmd = [self.mpv_path]
        cfg = self.config

        cmd.append('--force-window=yes')
        cmd.append('--no-terminal')

        if log_path:
            cmd.append('--msg-level=all=trace')
            cmd.append(f'--log-file={log_path}')

        if cfg:
            tls_disabled = cfg.get("player", "disable_tls_verify")
            if tls_disabled is None or tls_disabled:
                cmd.append('--tls-verify=no')
            hwdec = cfg.get("player", "hwdec") or "auto"
            if hwdec and hwdec != "auto":
                cmd.append(f'--hwdec={hwdec}')
            volume = cfg.get("player", "volume")
            try:
                volume = int(volume) if volume is not None else 100
            except (TypeError, ValueError):
                volume = 100
            if volume != 100:
                cmd.append(f'--volume={max(0, min(100, volume))}')
            if cfg.get("player", "keep_open"):
                cmd.append('--keep-open=yes')
            if cfg.get("player", "ontop"):
                cmd.append('--ontop')
            ytdl_format = (cfg.get("player", "ytdl_format") or "").strip()
            if ytdl_format:
                cmd.append(f'--ytdl-format={ytdl_format}')
            extra = (cfg.get("player", "extra_args") or "").strip()
            if extra:
                cmd.extend(extra.split())

        if self.ytdlp_path:
            cmd.append(f'--script-opts=ytdl_hook-ytdl_path={self.ytdlp_path}')

        cmd.append(url)
        return cmd

    
    def _stop_loading(self):
        """Stop the loading spinner"""
        self.is_loading = False
        self.loading_spinner.stop()

    def cleanup(self):
        """Cleanup resources"""
        self.is_loading = False
        self.loading_spinner.stop()
        if self.loading_spinner:
            self.loading_spinner.deleteLater()
        self._close_previous_mpv()
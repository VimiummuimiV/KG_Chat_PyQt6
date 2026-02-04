"""Video player widget - launches mpvnet player for video URLs"""
import re
import subprocess
import platform
import shutil
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import QPoint, QTimer, Qt

from helpers.loading_spinner import LoadingSpinner


class VideoPlayer(QWidget):
    """Video player that launches mpvnet for playback"""
    
    VIDEO_PATTERNS = [
        re.compile(r'https?://[^\s<>"]+\.(?:mp4|webm|ogg|mov|avi|mkv|flv|wmv|m4v)(?:\?[^\s<>"]*)?', re.IGNORECASE),
        re.compile(r'https?://(?:www\.|m\.)?(?:youtube\.com/(?:shorts/|live/|watch\?v=|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})', re.IGNORECASE),
        re.compile(r'https?://(?:www\.)?rutube\.ru/video/[a-f0-9]{32}/?', re.IGNORECASE),
        re.compile(r'https?://(?:www\.)?(?:vkvideo\.ru|vk\.com)/video-?\d+_\d+', re.IGNORECASE),
    ]

    def __init__(self, parent=None, icons_path: Path = None, config=None):
        super().__init__(parent)
        # icons_path and config are ignored but kept for compatibility with message_delegate.py
        self.current_url = None
        self.mpv_path = self._find_mpv()
        
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
            # Search common Windows directories for mpvnet.exe
            search_dirs = [
                Path.home() / 'AppData/Local/Programs',
                Path('C:/Program Files'),
                Path('C:/Program Files (x86)'),
            ]
            
            for search_dir in search_dirs:
                if search_dir.exists():
                    # Look for mpvnet.exe in subdirectories (max 2 levels deep)
                    for path in search_dir.glob('*/mpvnet.exe'):
                        return str(path)
                    for path in search_dir.glob('*/*/mpvnet.exe'):
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
        copy_button = msg_box.addButton("Copy", QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton(QMessageBox.StandardButton.Ok)
        
        msg_box.exec()
        
        # If Copy button was clicked, copy the plain text to clipboard
        if msg_box.clickedButton() == copy_button:
            from PyQt6.QtWidgets import QApplication
            # Strip HTML tags for plain text copy
            import re
            plain_text = f"{text}\n\n{informative_text}"
            plain_text = re.sub(r'<br>', '\n', plain_text)
            plain_text = re.sub(r'<[^>]+>', '', plain_text)
            QApplication.clipboard().setText(plain_text)

    def _show_mpv_error(self):
        """Show a graphical error dialog when mpv is not found"""
        system = platform.system()
        
        # Base message with official site
        install_msg = 'Please install MPV from the official site:<br><a href="https://mpv.io/installation/">https://mpv.io/installation/</a>'
        
        # Add platform-specific additional options
        if system == 'Windows':
            install_msg += (
                '<br><br><b>Windows builds:</b><br>'
                '<a href="https://github.com/mpvnet-player/mpv.net/releases/">https://github.com/mpvnet-player/mpv.net/releases/</a><br>'
                'or<br>'
                '<a href="https://github.com/zhongfly/mpv-winbuild/releases/">https://github.com/zhongfly/mpv-winbuild/releases/</a>'
                '<br><br><b>.NET SDK</b> (required for mpv.net):<br>'
                '<a href="https://dotnet.microsoft.com/en-us/download/dotnet/">https://dotnet.microsoft.com/en-us/download/dotnet/</a>'
            )
        elif system == 'Darwin':
            install_msg += '<br><br><b>macOS:</b> brew install mpv'
        else:
            install_msg += '<br><br><b>Linux:</b> sudo apt install mpv<br>(or use your distro\'s package manager)'
        
        # Show graphical dialog
        self._show_error_dialog(
            "Video Player Not Found",
            "MPV video player is not installed.",
            install_msg
        )

    def show_video(self, url: str, cursor_pos: QPoint = None):
        """Launch mpv player with the video URL"""
        if self.current_url == url:
            return
        
        self.current_url = url
        
        # Check if mpv is available
        if not self.mpv_path or not shutil.which(self.mpv_path):
            # Show graphical error dialog (which also prints to console)
            self._show_mpv_error()
            return
        
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
            mpv_cmd = self._build_mpv_command(url)
            
            # Launch mpv as detached process
            if platform.system() == 'Windows':
                subprocess.Popen(
                    mpv_cmd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                # Unix-like: use start_new_session
                subprocess.Popen(
                    mpv_cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            # Stop spinner after brief delay (mpv is launching)
            QTimer.singleShot(1000, self._stop_loading)
            
        except Exception as e:
            print(f"Failed to launch mpv: {e}")
            self._stop_loading()
            
            # Show error dialog for launch failures
            self._show_error_dialog(
                "Video Player Error",
                "Failed to launch video player.",
                f"Error: {str(e)}",
                QMessageBox.Icon.Critical
            )
    
    def _build_mpv_command(self, url: str) -> list:
        """Build mpv command with appropriate options"""
        cmd = [self.mpv_path]
        
        # Basic options for good playback
        cmd.extend([
            '--force-window=yes',
            '--keep-open=yes',
            '--geometry=960x720',
            '--autofit-larger=90%x90%',
        ])
        
        # Add the URL
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
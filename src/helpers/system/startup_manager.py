"""
System startup manager for cross-platform auto-start functionality
Supports Windows, Linux (systemd/autostart), and macOS
"""

import platform
import sys
import textwrap
from pathlib import Path

from helpers.data import get_app_dir


class StartupManager:
    """Manages application auto-start on system boot"""

    def __init__(self, app_name: str = "KG_Chat", app_path: str = None):
        self._app_name = app_name
        self._app_path = app_path or sys.executable
        self.system = platform.system()
        self._script_dir = get_app_dir()
        self._main_script = self._script_dir / "main.py"

    def is_enabled(self) -> bool:
        """Check if auto-start is currently enabled"""
        try:
            if self.system == "Windows":
                import winreg  # Windows only
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, self._app_name)
                    winreg.CloseKey(key)
                    return True
                except FileNotFoundError:
                    winreg.CloseKey(key)
                    return False
            elif self.system == "Linux":
                autostart_dir = Path.home() / ".config" / "autostart"
                desktop_file = autostart_dir / f"{self._app_name.replace(' ', '-').lower()}.desktop"
                return desktop_file.exists()
            elif self.system == "Darwin":  # macOS
                launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
                plist_name = f"com.{self._app_name.replace(' ', '-').lower()}.plist"
                plist_path = launch_agents_dir / plist_name
                return plist_path.exists()
            return False
        except Exception as e:
            print(f"Error checking startup status: {e}")
            return False

    def enable(self) -> bool:
        """Enable auto-start on system boot"""
        try:
            if self.system == "Windows":
                import winreg  # Windows only
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
                python_exe = sys.executable
                if python_exe.endswith("python.exe"):
                    python_exe = python_exe.replace("python.exe", "pythonw.exe")
                command = f'"{python_exe}" "{self._main_script}"'
                winreg.SetValueEx(key, self._app_name, 0, winreg.REG_SZ, command)
                winreg.CloseKey(key)
                return True
            elif self.system == "Linux":
                autostart_dir = Path.home() / ".config" / "autostart"
                autostart_dir.mkdir(parents=True, exist_ok=True)
                desktop_file = autostart_dir / f"{self._app_name.replace(' ', '-').lower()}.desktop"
                content = textwrap.dedent(f"""\
                [Desktop Entry]
                Type=Application
                Name={self._app_name}
                Exec="{sys.executable}" "{self._main_script}"
                Hidden=false
                NoDisplay=false
                X-GNOME-Autostart-enabled=true
                Comment=Start {self._app_name} on login
                """)
                desktop_file.write_text(content)
                desktop_file.chmod(0o755)
                return True
            elif self.system == "Darwin":  # macOS
                launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
                launch_agents_dir.mkdir(parents=True, exist_ok=True)
                plist_name = f"com.{self._app_name.replace(' ', '-').lower()}.plist"
                plist_path = launch_agents_dir / plist_name
                content = textwrap.dedent(f"""\
                <?xml version="1.0" encoding="UTF-8"?>
                <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                <plist version="1.0">
                <dict>
                    <key>Label</key>
                    <string>com.{self._app_name.replace(' ', '-').lower()}</string>
                    <key>ProgramArguments</key>
                    <array>
                        <string>{sys.executable}</string>
                        <string>{self._main_script}</string>
                    </array>
                    <key>RunAtLoad</key>
                    <true/>
                    <key>KeepAlive</key>
                    <false/>
                </dict>
                </plist>
                """)
                plist_path.write_text(content)
                return True
            return False
        except Exception as e:
            print(f"Error enabling startup: {e}")
            return False

    def disable(self) -> bool:
        """Disable auto-start on system boot"""
        try:
            if self.system == "Windows":
                import winreg  # Windows only
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
                try:
                    winreg.DeleteValue(key, self._app_name)
                except FileNotFoundError:
                    pass  # Already disabled
                winreg.CloseKey(key)
                return True
            elif self.system == "Linux":
                autostart_dir = Path.home() / ".config" / "autostart"
                desktop_file = autostart_dir / f"{self._app_name.replace(' ', '-').lower()}.desktop"
                if desktop_file.exists():
                    desktop_file.unlink()
                return True
            elif self.system == "Darwin":  # macOS
                launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
                plist_name = f"com.{self._app_name.replace(' ', '-').lower()}.plist"
                plist_path = launch_agents_dir / plist_name
                if plist_path.exists():
                    plist_path.unlink()
                return True
            return False
        except Exception as e:
            print(f"Error disabling startup: {e}")
            return False

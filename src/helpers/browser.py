"""Detect installed browsers and open URLs with a chosen one."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# (display_name, key) — key is "system" or an executable path
BrowserEntry = Tuple[str, str]


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _exists(path: str) -> bool:
    return Path(path).is_file()


def _windows_browsers() -> List[BrowserEntry]:
    entries: List[BrowserEntry] = []
    try:
        import winreg
    except ImportError:
        return entries

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Clients\StartMenuInternet"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Clients\StartMenuInternet"),
    ]
    seen_paths: set[str] = set()

    for hive, subkey in roots:
        try:
            key = winreg.OpenKey(hive, subkey)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                try:
                    cmd_key = winreg.OpenKey(key, name + r"\shell\open\command")
                    cmd, _ = winreg.QueryValueEx(cmd_key, None)
                    winreg.CloseKey(cmd_key)
                except OSError:
                    continue
                # Command is usually '"C:\...\chrome.exe" %1' or similar
                exe = cmd.strip().strip('"').split('"')[0].strip()
                if not exe or not _exists(exe) or exe.lower() in seen_paths:
                    continue
                seen_paths.add(exe.lower())
                display = name
                try:
                    name_key = winreg.OpenKey(key, name)
                    display, _ = winreg.QueryValueEx(name_key, None)
                    winreg.CloseKey(name_key)
                except OSError:
                    pass
                if not display:
                    display = Path(exe).stem
                entries.append((display, exe))
        finally:
            winreg.CloseKey(key)

    return entries


def _macos_browsers() -> List[BrowserEntry]:
    apps = [
        ("Safari", "/Applications/Safari.app/Contents/MacOS/Safari"),
        ("Google Chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ("Firefox", "/Applications/Firefox.app/Contents/MacOS/firefox"),
        ("Microsoft Edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ("Brave Browser", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
        ("Opera", "/Applications/Opera.app/Contents/MacOS/Opera"),
        ("Vivaldi", "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi"),
        ("Chromium", "/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]
    return [(name, path) for name, path in apps if _exists(path)]


def _linux_browsers() -> List[BrowserEntry]:
    candidates = [
        ("Google Chrome", ["google-chrome-stable", "google-chrome", "chrome"]),
        ("Chromium", ["chromium-browser", "chromium"]),
        ("Firefox", ["firefox", "firefox-esr"]),
        ("Microsoft Edge", ["microsoft-edge", "microsoft-edge-stable"]),
        ("Brave", ["brave-browser", "brave"]),
        ("Opera", ["opera"]),
        ("Vivaldi", ["vivaldi", "vivaldi-stable"]),
        ("Epiphany", ["epiphany"]),
        ("Konqueror", ["konqueror"]),
        ("Falkon", ["falkon"]),
    ]
    entries: List[BrowserEntry] = []
    seen: set[str] = set()
    for display, names in candidates:
        for name in names:
            path = _which(name)
            if path and path not in seen:
                seen.add(path)
                entries.append((display, path))
                break
    return entries


def get_available_browsers() -> List[BrowserEntry]:
    """Return [(display_name, key), ...] with System default first."""
    system = platform.system()
    if system == "Windows":
        found = _windows_browsers()
    elif system == "Darwin":
        found = _macos_browsers()
    else:
        found = _linux_browsers()

    # Deduplicate by path, keep first occurrence
    seen: set[str] = set()
    unique: List[BrowserEntry] = []
    for name, key in found:
        if key not in seen:
            seen.add(key)
            unique.append((name, key))

    return [("System default", "system")] + unique


def open_url(url: str, browser_key: Optional[str] = None) -> None:
    """Open url with the given browser key (path or 'system')."""
    if not url:
        return
    key = (browser_key or "system").strip()
    if not key or key == "system":
        import webbrowser
        webbrowser.open(url)
        return

    if not _exists(key) and not _which(key):
        import webbrowser
        webbrowser.open(url)
        return

    try:
        if platform.system() == "Darwin" and ("/Contents/MacOS/" in key or key.endswith(".app")):
            app_path = key.split("/Contents/MacOS/")[0] if "/Contents/MacOS/" in key else key
            subprocess.Popen(
                ["open", "-a", app_path, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                [key, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception:
        import webbrowser
        webbrowser.open(url)

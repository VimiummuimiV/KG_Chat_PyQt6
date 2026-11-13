import os
import platform
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def get_app_dir() -> Path:
    """Return the application root (the folder holding main.py and the resource folders)."""
    return Path(__file__).resolve().parent.parent


def get_resource_dir(name: str) -> Path:
    """Return a bundled resource folder such as icons, sounds, fonts or emoticons."""
    return get_app_dir() / name


def get_data_dir(subdir: str = "") -> Path:
    """Return a user-accessible data directory based on OS."""
    system = platform.system()

    if system == "Windows":
        documents = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    elif system == "Darwin":
        documents = Path.home() / "Documents"
    else:
        # Linux/Termux: home is the safest always-present user-accessible location
        documents = Path.home()

    base_dir = documents / "KG_Chat_Data"

    if subdir:
        base_dir = base_dir / subdir

    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def get_state_dir() -> Path:
    """Return the folder of JSON state files (KG_Chat_Data/data)."""
    return get_data_dir("data")


def open_in_file_manager(path: Path | str | None = None) -> bool:
    """Open a folder in the OS file manager (Explorer / Finder / xdg-open).

    Defaults to the app data directory (KG_Chat_Data).
    Uses Qt QDesktopServices — works on Windows, macOS, and Linux.
    """
    if path is None or not isinstance(path, (str, os.PathLike)):
        target = get_data_dir()
    else:
        target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))

import os
import platform
from pathlib import Path

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
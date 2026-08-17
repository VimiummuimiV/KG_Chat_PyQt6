"""Cursor/keyboard activity detection, shared by notification popups and chat."""
import ctypes
import sys

from PyQt6.QtGui import QCursor


def any_key_pressed() -> bool:
    """True if any key is currently down (Windows only, silent fallback elsewhere)."""
    try:
        if sys.platform == "win32":
            return any(ctypes.windll.user32.GetAsyncKeyState(k) & 0x8000 for k in range(0x08, 0xFF))
    except Exception:
        pass
    return False


def cursor_moved_or_key_pressed(initial_pos, threshold: int = 50) -> bool:
    """True once the cursor has moved past threshold px from initial_pos, or a key is down."""
    return (QCursor.pos() - initial_pos).manhattanLength() > threshold or any_key_pressed()
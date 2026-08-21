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


def cursor_moved(initial_pos, threshold: int = 50) -> bool:
    """True once the cursor has moved past threshold px from initial_pos."""
    return (QCursor.pos() - initial_pos).manhattanLength() > threshold


def activity_detected(initial_pos, mode: str = "mouse_keyboard", threshold: int = 50) -> bool:
    """Whether user activity matching *mode* has occurred.

    mode:
      - "manual"          — never (caller handles close only)
      - "mouse"           — cursor movement only
      - "keyboard"        — any key down only
      - "mouse_keyboard"  — cursor movement or any key
    """
    if mode == "manual":
        return False
    if mode == "mouse":
        return cursor_moved(initial_pos, threshold)
    if mode == "keyboard":
        return any_key_pressed()
    # "mouse_keyboard" (default) and any unknown value
    return cursor_moved(initial_pos, threshold) or any_key_pressed()

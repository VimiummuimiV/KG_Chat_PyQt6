"""Global show/hide hotkey: registration, live status, capture-for-remap.

Windows uses RegisterHotKey (native, WM_HOTKEY) instead of a keyboard hook,
so a claimed combination (e.g. Win+C reserved by Copilot) fails registration
and shows as a conflict rather than working unpredictably. macOS/Linux fall
back to the 'keyboard' library's hook.

Key identity is layout-independent: on Windows, capture/fallback resolve the
physical key via MapVirtualKey (scan code → VK). A–Z / 0–9 VKs are ASCII, so
the Latin letter is recovered regardless of the active layout — same idea as
nativeVirtualKey in ui_chat.py. Stored combos stay as "win+c"; RegisterHotKey
uses those VKs directly.
"""
import sys
import time
import ctypes
if sys.platform == "win32":
    import ctypes.wintypes
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QAbstractNativeEventFilter
from PyQt6.QtWidgets import QApplication, QWidget

import keyboard

from helpers.translate import tr

DEFAULT_HOTKEY = "win+c"

STATUS_ACTIVE = "active"
STATUS_CONFLICT = "conflict"
STATUS_ERROR = "error"
STATUS_DISABLED = "disabled"

STATUS_COLORS = {
    STATUS_ACTIVE: "#2ecc71",
    STATUS_CONFLICT: "#e67e22",
    STATUS_ERROR: "#e74c3c",
    STATUS_DISABLED: "#888888",
}
def get_status_tooltip(status: str) -> str:
    return {
        STATUS_ACTIVE: tr("Hotkey is registered and active", "Хоткей зарегистрирован и активен"),
        STATUS_CONFLICT: tr(
            "Combination is already claimed by Windows or another app — pick a different one",
            "Комбинация уже занята Windows или другим приложением — выберите другую",
        ),
        STATUS_ERROR: tr("Hotkey registration failed", "Не удалось зарегистрировать хоткей"),
        STATUS_DISABLED: tr("Hotkey is not registered", "Хоткей не зарегистрирован"),
    }.get(status, "")

HOTKEY_ID = 1
WM_HOTKEY = 0x0312
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
MAPVK_VSC_TO_VK = 0x01

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

MODIFIER_ORDER = ["ctrl", "alt", "shift", "win"]
MODIFIER_FLAGS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
MODIFIER_DISPLAY = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}
FUNCTION_KEYS = {f"f{i}": 0x6F + i for i in range(1, 25)}
NAMED_KEYS = {
    "space": 0x20, "tab": 0x09, "esc": 0x1B, "enter": 0x0D,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}
NAMED_KEYS.update(FUNCTION_KEYS)
_VK_TO_NAME = {vk: name for name, vk in NAMED_KEYS.items()}

user32 = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None


def parse_hotkey(combo: str) -> tuple[list[str], str]:
    """'win+c' -> (['win'], 'c'), modifiers ordered consistently."""
    parts = [p.strip().lower() for p in (combo or "").split("+") if p.strip()]
    if not parts:
        return [], ""
    *mods, key = parts
    ordered_mods = [m for m in MODIFIER_ORDER if m in mods]
    return ordered_mods, key


def format_hotkey(mods: list[str], key: str) -> str:
    return "+".join([*mods, key.lower()]) if key else ""


def display_hotkey(combo: str) -> str:
    mods, key = parse_hotkey(combo)
    parts = [MODIFIER_DISPLAY.get(m, m.title()) for m in mods]
    if key:
        parts.append(key.upper() if len(key) == 1 else key.title())
    return " + ".join(parts) if parts else "—"


def _virtual_key_code(key: str) -> int | None:
    key = (key or "").lower()
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    return NAMED_KEYS.get(key)


def _normalize_key_name(name: str) -> str:
    name = (name or "").lower().strip()
    if name in ("page up", "page_up"):
        return "pageup"
    if name in ("page down", "page_down"):
        return "pagedown"
    return name


def _layout_independent_key(event) -> str | None:
    """Physical key → Latin/fixed name, independent of active keyboard layout.

    Windows: MapVirtualKey(scan → VK). A–Z / 0–9 VKs are ASCII, so "c" is always
    recovered for the physical C key. Named keys use the small VK→name table.
    Elsewhere: trust event.name when it is already Latin or a stable name
    (F-keys, arrows, space — same across layouts).
    """
    scan = getattr(event, "scan_code", None)
    if sys.platform == "win32" and user32 is not None and scan is not None:
        vk = user32.MapVirtualKeyW(int(scan) & 0xFF, MAPVK_VSC_TO_VK)
        if 0x41 <= vk <= 0x5A:  # A–Z
            return chr(vk).lower()
        if 0x30 <= vk <= 0x39:  # 0–9
            return chr(vk)
        named = _VK_TO_NAME.get(vk)
        if named:
            return named

    name = _normalize_key_name(getattr(event, "name", None) or "")
    if not name:
        return None
    if len(name) == 1 and name.isascii() and name.isalnum():
        return name
    if name in NAMED_KEYS:
        return name
    return None


def _native_modifiers_pressed() -> list[str]:
    """Modifiers currently held, checked natively on Windows for reliability."""
    mods = []
    if sys.platform == "win32":
        if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x5B, 0x5C)):
            mods.append("win")
        if user32.GetAsyncKeyState(0x11) & 0x8000:
            mods.append("ctrl")
        if user32.GetAsyncKeyState(0x12) & 0x8000:
            mods.append("alt")
        if user32.GetAsyncKeyState(0x10) & 0x8000:
            mods.append("shift")
    else:
        modifier_key = "command" if sys.platform == "darwin" else "super"
        if keyboard.is_pressed(modifier_key):
            mods.append("win")
        for name in ("ctrl", "alt", "shift"):
            if keyboard.is_pressed(name):
                mods.append(name)
    return [m for m in MODIFIER_ORDER if m in mods]


class _WindowsHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, manager: "GlobalHotkeyManager"):
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._manager._activate()
        return False, 0


class GlobalHotkeyManager(QObject):
    """Registers the show/hide hotkey and reports whether it's actually live."""

    activated = pyqtSignal()
    status_changed = pyqtSignal(str, str)

    DEBOUNCE_SECONDS = 0.15

    def __init__(self):
        super().__init__()
        self._combo = DEFAULT_HOTKEY
        self._status = STATUS_DISABLED
        self._message_window = None
        self._native_filter = None
        self._fallback_hooked = False
        self._fallback_mods: list[str] = []
        self._fallback_key = ""
        self._last_activation = 0.0

    @property
    def combo(self) -> str:
        return self._combo

    @property
    def status(self) -> str:
        return self._status

    def register(self, combo: str = None):
        """(Re)register the given combination, replacing any previous one."""
        self.unregister()
        self._combo = combo or DEFAULT_HOTKEY
        if sys.platform == "win32":
            self._register_windows()
        else:
            self._register_fallback()

    def unregister(self):
        if sys.platform == "win32":
            self._unregister_windows()
        else:
            self._unregister_fallback()
        self._status = STATUS_DISABLED

    def _set_status(self, status: str, detail: str = ""):
        self._status = status
        self.status_changed.emit(status, detail)

    def _activate(self):
        now = time.time()
        if now - self._last_activation < self.DEBOUNCE_SECONDS:
            return
        self._last_activation = now
        self.activated.emit()

    def _register_windows(self):
        mods, key = parse_hotkey(self._combo)
        vk = _virtual_key_code(key)
        if not mods or vk is None:
            self._set_status(STATUS_ERROR, tr(
                "Invalid key combination",
                "Недопустимая комбинация клавиш")
            )
            return

        if self._message_window is None:
            self._message_window = QWidget()
            self._message_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            self._message_window.winId()
            self._native_filter = _WindowsHotkeyFilter(self)
            QApplication.instance().installNativeEventFilter(self._native_filter)

        mod_flags = MOD_NOREPEAT
        for name in mods:
            mod_flags |= MODIFIER_FLAGS[name]

        hwnd = int(self._message_window.winId())
        ok = user32.RegisterHotKey(hwnd, HOTKEY_ID, mod_flags, vk)

        if ok:
            self._set_status(STATUS_ACTIVE)
        else:
            error_code = ctypes.get_last_error()
            if error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
                self._set_status(STATUS_CONFLICT, tr(
                    "Combination is already claimed by Windows or another app",
                    "Комбинация уже занята Windows или другим приложением")
                )
            else:
                self._set_status(STATUS_ERROR, tr(
                    f"Windows error code: {error_code}",
                    f"Код ошибки Windows: {error_code}")
                )

    def _unregister_windows(self):
        if self._message_window is not None:
            hwnd = int(self._message_window.winId())
            user32.UnregisterHotKey(hwnd, HOTKEY_ID)

    def _register_fallback(self):
        mods, key = parse_hotkey(self._combo)
        if not mods or not key:
            self._set_status(STATUS_ERROR, tr(
                "Invalid key combination",
                "Недопустимая комбинация клавиш")
            )
            return
        self._fallback_mods = mods
        self._fallback_key = key.lower()
        try:
            keyboard.on_press(self._on_fallback_key_press)
            self._fallback_hooked = True
            self._set_status(STATUS_ACTIVE)
        except Exception as error:
            self._set_status(STATUS_ERROR, str(error))

    def _unregister_fallback(self):
        if self._fallback_hooked:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
            self._fallback_hooked = False

    def _on_fallback_key_press(self, event):
        resolved = _layout_independent_key(event)
        if resolved is None or resolved != self._fallback_key:
            return
        pressed = _native_modifiers_pressed()
        if set(pressed) != set(self._fallback_mods):
            return
        self._activate()


class HotkeyCapture(QObject):
    """One-shot listener for the next key combination.

    Always stores a Latin / fixed name (via MapVirtualKey on Windows), so the
    combo is the same on EN, RU, or any other layout.
    """

    captured = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._active = False

    def start(self):
        try:
            keyboard.hook(self._on_event)
            self._active = True
        except Exception:
            self.cancelled.emit()

    def stop(self):
        if self._active:
            try:
                keyboard.unhook(self._on_event)
            except Exception:
                pass
            self._active = False

    def _on_event(self, event):
        if event.event_type != "down":
            return

        resolved = _layout_independent_key(event)
        raw_name = _normalize_key_name(getattr(event, "name", None) or "")
        if resolved == "esc" or raw_name == "esc":
            self.stop()
            self.cancelled.emit()
            return

        if any(token in raw_name for token in ("ctrl", "alt", "shift", "windows", "cmd", "command", "super")):
            return
        if resolved is None:
            return

        mods = _native_modifiers_pressed()
        if not mods:
            return

        self.stop()
        self.captured.emit(format_hotkey(mods, resolved))


hotkey_manager = GlobalHotkeyManager()
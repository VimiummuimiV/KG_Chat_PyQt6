"""Unified font manager for text and emoji rendering"""

import sys
from enum import Enum

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QToolTip

from helpers.config import Config
from helpers.data import get_resource_dir


class FontType(Enum):
    """Font type categories"""
    UI = "ui"           # Buttons, inputs, small UI elements
    TEXT = "text"       # Messages, content, body text
    HEADER = "header"   # Titles, section headers


class _FontManager:
    """Centralized font manager with unified API"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._fonts_dir = get_resource_dir("fonts")
        self.config = None
        self.loaded = False
        self.font_scaler = None
        self._font_cache: dict = {}
        self._available_families: list[str] = []
        self._available_emoji_families: list[str] = []
        self._loaded_dirs: set[str] = set()
        self._initialized = True

    def _invalidate_cache(self):
        self._font_cache.clear()

    def _set_config(self, config):
        self.config = config

    def _set_font_scaler(self, font_scaler):
        self.font_scaler = font_scaler
        font_scaler.font_size_changed.connect(self._invalidate_cache)

    def load_config(self):
        if self.config is None:
            try:
                self.config = Config()
            except ImportError:
                print("⚠️ Could not load config")
                self.config = type('SimpleConfig', (), {
                    'get': lambda self, *args: None
                })()

    def _get_family(self, kind: str) -> str:
        return self.config.get("font", kind, "family") or "Roboto"

    def _get_size(self, kind: str, default: int) -> int:
        size = self.config.get("font", kind, "size")
        return int(size) if size is not None else default

    def _is_emoji_dir(self, name: str) -> bool:
        return 'Emoji' in name or 'Color' in name

    def _load_dir(self, dir_name: str) -> list[str]:
        """Load all ttf from a font folder. Returns registered family names."""
        if dir_name in self._loaded_dirs:
            return []
        family_dir = self._fonts_dir / dir_name
        if not family_dir.exists():
            return []

        names: list[str] = []
        for font_file in sorted(family_dir.rglob("*.ttf")):
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            if font_id != -1:
                names.extend(QFontDatabase.applicationFontFamilies(font_id))

        self._loaded_dirs.add(dir_name)
        return names

    def _get_available_font_families(self) -> list[str]:
        """All unique Qt family names from fonts/ (weights included), excluding emoji."""
        if self._available_families:
            return list(self._available_families)

        if not self._fonts_dir.exists():
            return []

        found: set[str] = set()
        for d in sorted(self._fonts_dir.iterdir()):
            if not d.is_dir() or d.name.startswith('.') or self._is_emoji_dir(d.name):
                continue
            for name in self._load_dir(d.name):
                found.add(name)

        self._available_families = sorted(found, key=lambda s: s.lower())
        return list(self._available_families)

    def _get_available_emoji_families(self) -> list[str]:
        """Emoji families: real Qt names from fonts/*Emoji* dirs + common system ones."""
        if self._available_emoji_families:
            return list(self._available_emoji_families)

        found: set[str] = set()
        system_names = QFontDatabase.families()
        system_set = set(system_names)
        # The bundled COLRv1 emoji build does not render on Linux Qt, so a system emoji font wins there
        prefer_system = sys.platform.startswith("linux") and any("emoji" in name.lower() for name in system_names)

        # Bundled under fonts/ (folder name has Emoji/Color — e.g. Noto_Color_Emoji)
        if self._fonts_dir.exists() and not prefer_system:
            for d in sorted(self._fonts_dir.iterdir()):
                if not d.is_dir() or d.name.startswith('.') or not self._is_emoji_dir(d.name):
                    continue
                for name in self._load_dir(d.name):
                    found.add(name)

        # System color-emoji fonts already known to Qt
        for candidate in (
            "Noto Color Emoji",
            "Segoe UI Emoji",
            "Apple Color Emoji",
            "Twemoji Mozilla",
            "Emoji One",
            "JoyPixels",
        ):
            if candidate in system_set:
                found.add(candidate)
        for name in system_names:
            low = name.lower()
            if "emoji" in low and name not in found:
                found.add(name)

        self._available_emoji_families = sorted(found, key=lambda s: s.lower())
        return list(self._available_emoji_families)

    def _load_fonts(self):
        if self.loaded:
            return True

        self.load_config()

        if not self._fonts_dir.exists():
            print(f"⚠️ Fonts directory not found: {self._fonts_dir}")
            self.loaded = True
            return False

        families = self._get_available_font_families()
        if families:
            print(f"✅ Loaded fonts: {len(families)} faces from {len(self._loaded_dirs)} families")
        else:
            print("⚠️ No text fonts found")

        emoji_families = self._get_available_emoji_families()
        if emoji_families:
            print(f"✅ Emoji fonts: {', '.join(emoji_families)}")
        else:
            print("⚠️ No emoji fonts found")

        self.loaded = True
        return True

    def _ensure_family_loaded(self, family_name: str) -> bool:
        if not self._available_families:
            self._get_available_font_families()
        return family_name in self._available_families or any(
            family_name in n for n in self._available_families
        )

    def _get_font(self, font_type: FontType = FontType.TEXT,
                 size: int = None,
                 weight: QFont.Weight = QFont.Weight.Normal,
                 italic: bool = False) -> QFont:
        if not self.loaded:
            self.load_config()

        if font_type in (FontType.UI, FontType.HEADER):
            family = self._get_family("ui")
        else:
            family = self._get_family("text")

        emoji_family = self.config.get("font", "emoji_family") or "Noto Color Emoji"

        if size is None:
            if font_type == FontType.UI:
                size = self._get_size("ui", 12)
            elif font_type == FontType.TEXT:
                size = self.font_scaler.get_text_size() if self.font_scaler else self._get_size("text", 16)
            elif font_type == FontType.HEADER:
                size = self._get_size("header", 18)
                if weight == QFont.Weight.Normal:
                    weight = QFont.Weight.Bold
            else:
                size = 12

        # Weight is baked into family name for variable/static faces
        # (e.g. "Roboto Medium") — use Normal so Qt doesn't double-bold
        use_weight = QFont.Weight.Normal

        key = (font_type, family, size, int(use_weight), italic)
        cached = self._font_cache.get(key)
        if cached is not None:
            return cached

        font = QFont(family, size, use_weight)
        font.setItalic(italic)
        # Primary family + Emoji family fallback
        font.setFamilies([family, emoji_family])
        self._font_cache[key] = font
        return font

    def _set_application_font(self, app: QApplication):
        if not self.loaded:
            self.load_config()


        default_font = self._get_font(FontType.UI)
        app.setFont(default_font)
        QToolTip.setFont(default_font)

        ui_family = self._get_family("ui")
        ui_font_size = self._get_size("ui", 12)
        print(f"✅ Application font set: {ui_family} {ui_font_size}pt")


# Global instance
_font_manager = _FontManager()


# Public API
def load_fonts() -> bool:
    return _font_manager._load_fonts()


def get_font(font_type: FontType = FontType.TEXT,
             size: int = None,
             weight: QFont.Weight = QFont.Weight.Normal,
             italic: bool = False) -> QFont:
    return _font_manager._get_font(font_type, size, weight, italic)


def set_application_font(app: QApplication):
    _font_manager._set_application_font(app)


def set_font_scaler(font_scaler):
    _font_manager._set_font_scaler(font_scaler)


def set_config(config):
    _font_manager._set_config(config)


def get_available_font_families() -> list[str]:
    return _font_manager._get_available_font_families()


def get_available_emoji_families() -> list[str]:
    return _font_manager._get_available_emoji_families()


def ensure_family_loaded(family_name: str) -> bool:
    return _font_manager._ensure_family_loaded(family_name)


def invalidate_font_cache():
    _font_manager._invalidate_cache()


def _current_text_size(base_size: int = 16) -> int:
    if _font_manager.font_scaler:
        return _font_manager.font_scaler.get_text_size()
    if _font_manager.config:
        return _font_manager._get_size("text", base_size)
    return base_size


def get_userlist_width() -> int:
    base_size = 16
    base_width = 380
    scaled_width = int(base_width * (_current_text_size(base_size) / base_size))
    return max(200, min(500, scaled_width))


def get_scaled_width(base_width: int, base_size: int = 16, min_width: int = None, max_width: int = None) -> int:
    """Scale a pixel width proportionally to the current text font size (for fixed-width inputs/fields)."""
    scaled = int(base_width * (_current_text_size(base_size) / base_size))
    if min_width is not None:
        scaled = max(min_width, scaled)
    if max_width is not None:
        scaled = min(max_width, scaled)
    return scaled

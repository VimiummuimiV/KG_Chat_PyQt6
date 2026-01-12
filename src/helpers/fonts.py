"""Unified font manager for text and emoji rendering"""
from pathlib import Path
from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication
from enum import Enum


class FontType(Enum):
    """Font type categories"""
    UI = "ui"           # Buttons, inputs, small UI elements
    TEXT = "text"       # Messages, content, body text
    HEADER = "header"   # Titles, section headers


class FontManager:
    """Centralized font manager with unified API"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.fonts_dir = Path(__file__).parent.parent / "fonts"
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.config = None
        self.loaded = False
        self._initialized = True
    
    def _load_config(self):
        """Load config if not already loaded"""
        if self.config is None:
            try:
                from helpers.config import Config
                self.config = Config(str(self.config_path))
            except ImportError:
                print("⚠️ Could not load config")
                self.config = type('SimpleConfig', (), {
                    'get': lambda self, *args: args[-1] if args else None
                })()
    
    def load_fonts(self):
        """Load custom fonts from fonts directory"""
        if self.loaded:
            return True
        
        self._load_config()
        
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        
        if not self.fonts_dir.exists():
            print(f"⚠️ Fonts directory not found: {self.fonts_dir}")
            self.loaded = True
            return False
        
        # Load Montserrat variants
        montserrat_files = [
            self.fonts_dir / "Montserrat" / "Montserrat-VariableFont_wght.ttf",
            self.fonts_dir / "Montserrat" / "static" / "Montserrat-Regular.ttf",
            self.fonts_dir / "Montserrat" / "static" / "Montserrat-Medium.ttf",
            self.fonts_dir / "Montserrat" / "static" / "Montserrat-Bold.ttf",
        ]
        
        loaded_any = False
        for font_file in montserrat_files:
            if font_file.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_file))
                if font_id != -1:
                    loaded_any = True
        
        if loaded_any:
            print(f"✅ Loaded text font: {text_family}")
        
        # Load Noto Color Emoji
        emoji_file = self.fonts_dir / "Noto_Color_Emoji" / "NotoColorEmoji-Regular.ttf"
        if emoji_file.exists():
            font_id = QFontDatabase.addApplicationFont(str(emoji_file))
            if font_id != -1:
                print(f"✅ Loaded emoji font: {emoji_family}")
        
        self.loaded = True
        return True
    
    def get_font(self, font_type: FontType = FontType.TEXT, 
                  size: int = None, 
                  weight: QFont.Weight = QFont.Weight.Normal,
                  italic: bool = False) -> QFont:
        """
        Unified font getter with type-based defaults
        
        Args:
            font_type: FontType enum (UI, TEXT, or HEADER)
            size: Optional size override (uses config default if None)
            weight: Font weight
            italic: Italic style
            
        Returns:
            QFont with proper family fallback for emoji support
        """
        if not self.loaded:
            self._load_config()
        
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        
        # Get size from config based on type if not provided
        if size is None:
            if font_type == FontType.UI:
                size = self.config.get("ui", "ui_font_size") or 12
            elif font_type == FontType.TEXT:
                size = self.config.get("ui", "text_font_size") or 16
            elif font_type == FontType.HEADER:
                size = self.config.get("ui", "header_font_size") or 18
                if weight == QFont.Weight.Normal:
                    weight = QFont.Weight.Bold
            else:
                size = 12
        
        font = QFont(text_family, size, weight)
        font.setItalic(italic)
        font.setFamilies([text_family, emoji_family])
        
        return font
    
    def set_application_font(self, app: QApplication):
        """Set application-wide default font (uses UI size)"""
        if not self.loaded:
            self._load_config()
        
        default_font = self.get_font(FontType.UI)
        app.setFont(default_font)
        
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        ui_font_size = self.config.get("ui", "ui_font_size") or 12
        
        print(f"✅ Application font set: {text_family} {ui_font_size}pt with {emoji_family} for emoji")


# Global instance
_font_manager = FontManager()


# Public API
def load_fonts() -> bool:
    """Load custom fonts"""
    return _font_manager.load_fonts()


def get_font(font_type: FontType = FontType.TEXT, 
             size: int = None,
             weight: QFont.Weight = QFont.Weight.Normal,
             italic: bool = False) -> QFont:
    """
    Get a font with proper emoji support
    
    Args:
        font_type: FontType.UI, FontType.TEXT, or FontType.HEADER
        size: Optional size override
        weight: Font weight (Normal, Bold, etc.)
        italic: Italic style
    
    Examples:
        get_font(FontType.UI)  # 12pt UI font
        get_font(FontType.TEXT)  # 16pt text font
        get_font(FontType.HEADER)  # 18pt bold header
        get_font(FontType.TEXT, size=14)  # 14pt text font
        get_font(FontType.TEXT, weight=QFont.Weight.Bold)  # Bold text
    """
    return _font_manager.get_font(font_type, size, weight, italic)


def set_application_font(app: QApplication):
    """Set application-wide font"""
    _font_manager.set_application_font(app)
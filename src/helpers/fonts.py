"""Font manager for loading custom fonts"""
from pathlib import Path
from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication
import platform


class FontManager:
    """Centralized font manager for custom fonts"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Initialize paths
        self.fonts_dir = Path(__file__).parent.parent / "fonts"
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.config = None
        self.loaded = False
    
    def _load_config(self):
        """Load config if not already loaded"""
        if self.config is None:
            try:
                from helpers.config import Config
                self.config = Config(str(self.config_path))
            except ImportError:
                print("⚠️ Could not load config")
                # Create a default config
                self.config = type('SimpleConfig', (), {
                    'get': lambda self, *args: args[-1] if args else None
                })()
    
    def load_fonts(self):
        """Load custom fonts from fonts directory"""
        if self.loaded:
            return True
            
        self._load_config()
        
        # Get font families and sizes from config
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        ui_font_size = self.config.get("ui", "ui_font_size") or 12
        text_font_size = self.config.get("ui", "text_font_size") or 16
        header_font_size = self.config.get("ui", "header_font_size") or 18
        
        print(f"📝 Font settings:")
        print(f"   Text family: {text_family}, Emoji family: {emoji_family}")
        print(f"   UI size: {ui_font_size}, Text size: {text_font_size}, Header size: {header_font_size}")
        
        if not self.fonts_dir.exists():
            print(f"⚠️ Fonts directory not found: {self.fonts_dir}")
            self.loaded = True
            return False
        
        # Load Montserrat for text (including Medium and Bold for headers)
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
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        loaded_any = True
        
        if loaded_any:
            print(f"✅ Loaded text font: {text_family}")
        
        # Load Noto Color Emoji
        emoji_file = self.fonts_dir / "Noto_Color_Emoji" / "NotoColorEmoji-Regular.ttf"
        if emoji_file.exists():
            font_id = QFontDatabase.addApplicationFont(str(emoji_file))
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    print(f"✅ Loaded emoji font: {emoji_family}")
        
        self.loaded = True
        return True
    
    def get_ui_font(self, weight: QFont.Weight = QFont.Weight.Normal, 
                    italic: bool = False) -> QFont:
        """Get UI font (buttons, inputs, account window)"""
        if not self.loaded:
            self._load_config()
        
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        font_size = self.config.get("ui", "ui_font_size") or 12
        
        font = QFont(text_family, font_size, weight)
        font.setItalic(italic)
        font.setFamilies([text_family, emoji_family])
        
        return font
    
    def get_text_font(self, weight: QFont.Weight = QFont.Weight.Normal, 
                      italic: bool = False) -> QFont:
        """Get text font (messages, usernames, chat content)"""
        if not self.loaded:
            self._load_config()
        
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        font_size = self.config.get("ui", "text_font_size") or 16
        
        font = QFont(text_family, font_size, weight)
        font.setItalic(italic)
        font.setFamilies([text_family, emoji_family])
        
        return font
    
    def get_header_font(self, weight: QFont.Weight = QFont.Weight.Bold,
                        italic: bool = False) -> QFont:
        """Get header font (titles, section headers)"""
        if not self.loaded:
            self._load_config()
        
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        font_size = self.config.get("ui", "header_font_size") or 18
        
        font = QFont(text_family, font_size, weight)
        font.setItalic(italic)
        font.setFamilies([text_family, emoji_family])
        
        return font
    
    def get_custom_font(self, size: int, weight: QFont.Weight = QFont.Weight.Normal,
                        italic: bool = False) -> QFont:
        """Get custom font with specific size"""
        if not self.loaded:
            self._load_config()
        
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        
        font = QFont(text_family, size, weight)
        font.setItalic(italic)
        font.setFamilies([text_family, emoji_family])
        
        return font
    
    def set_application_font(self, app: QApplication):
        """Set application-wide default font (uses UI font size)"""
        if not self.loaded:
            self._load_config()
        
        default_font = self.get_ui_font()
        app.setFont(default_font)
        
        text_family = self.config.get("ui", "text_font_family") or "Montserrat"
        emoji_family = self.config.get("ui", "emoji_font_family") or "Noto Color Emoji"
        ui_font_size = self.config.get("ui", "ui_font_size") or 12
        
        print(f"✅ Application font set: {text_family} {ui_font_size}pt with {emoji_family} for emoji")


# Global instance
_font_manager = FontManager()


def load_fonts() -> bool:
    """Load custom fonts"""
    return _font_manager.load_fonts()


def get_ui_font(weight: QFont.Weight = QFont.Weight.Normal, italic: bool = False) -> QFont:
    """Get UI font (buttons, inputs, account window)"""
    return _font_manager.get_ui_font(weight, italic)


def get_text_font(weight: QFont.Weight = QFont.Weight.Normal, italic: bool = False) -> QFont:
    """Get text font (messages, usernames, chat content)"""
    return _font_manager.get_text_font(weight, italic)


def get_header_font(weight: QFont.Weight = QFont.Weight.Bold, italic: bool = False) -> QFont:
    """Get header font (titles, section headers)"""
    return _font_manager.get_header_font(weight, italic)


def get_custom_font(size: int, weight: QFont.Weight = QFont.Weight.Normal,
                    italic: bool = False) -> QFont:
    """Get custom font with specific size"""
    return _font_manager.get_custom_font(size, weight, italic)


def set_application_font(app: QApplication):
    """Set application-wide font"""
    _font_manager.set_application_font(app)
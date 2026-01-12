"""Font manager for loading custom fonts and setting up font families"""
from pathlib import Path
from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication


class FontManager:
    """Centralized font manager for custom fonts"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.fonts_dir = Path(__file__).parent.parent / "fonts"
        self.montserrat_loaded = False
        self.emoji_loaded = False
        self._initialized = True
    
    def load_fonts(self):
        """Load custom fonts from fonts directory"""
        if not self.fonts_dir.exists():
            print(f"⚠️ Fonts directory not found: {self.fonts_dir}")
            return False
        
        # Load Montserrat (variable font is preferred)
        montserrat_files = [
            self.fonts_dir / "Montserrat" / "Montserrat-VariableFont_wght.ttf",
            self.fonts_dir / "Montserrat" / "static" / "Montserrat-Regular.ttf",
            self.fonts_dir / "Montserrat" / "static" / "Montserrat-Bold.ttf",
            self.fonts_dir / "Montserrat" / "static" / "Montserrat-Medium.ttf",
        ]
        
        for font_file in montserrat_files:
            if font_file.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_file))
                if font_id != -1:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        self.montserrat_loaded = True
                        print(f"✅ Loaded font: {font_file.name} ({families[0]})")
        
        # Load Noto Color Emoji
        emoji_file = self.fonts_dir / "Noto_Color_Emoji" / "NotoColorEmoji-Regular.ttf"
        if emoji_file.exists():
            font_id = QFontDatabase.addApplicationFont(str(emoji_file))
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    self.emoji_loaded = True
                    print(f"✅ Loaded emoji font: {emoji_file.name} ({families[0]})")
        
        success = self.montserrat_loaded and self.emoji_loaded
        if success:
            print("✅ All fonts loaded successfully")
        else:
            if not self.montserrat_loaded:
                print("⚠️ Montserrat font not loaded - using system fallback")
            if not self.emoji_loaded:
                print("⚠️ Emoji font not loaded - using system fallback")
        
        return success
    
    def get_font(self, size: int = 12, weight: QFont.Weight = QFont.Weight.Normal, 
                 italic: bool = False) -> QFont:
        """Get a font with Montserrat for text and Noto Color Emoji for emojis
        
        Args:
            size: Font size in points
            weight: Font weight (Normal, Bold, etc.)
            italic: Whether font should be italic
        
        Returns:
            QFont configured with proper fallback chain
        """
        # Create font with Montserrat as primary
        font = QFont("Montserrat", size, weight)
        font.setItalic(italic)
        
        # Set fallback families for emoji support
        # Qt will use these in order if the primary font doesn't have a character
        fallback_families = ["Noto Color Emoji"]
        
        # Add system emoji fonts as additional fallbacks
        import platform
        system = platform.system()
        if system == "Windows":
            fallback_families.append("Segoe UI Emoji")
        elif system == "Darwin":  # macOS
            fallback_families.append("Apple Color Emoji")
        else:  # Linux
            fallback_families.extend(["Noto Emoji", "Symbola"])
        
        font.setFamilies(["Montserrat"] + fallback_families)
        
        return font
    
    def set_application_font(self, app: QApplication, size: int = 12):
        """Set application-wide default font
        
        Args:
            app: QApplication instance
            size: Default font size
        """
        default_font = self.get_font(size)
        app.setFont(default_font)
        print(f"✅ Application font set: Montserrat {size}pt with emoji fallback")
    
    def get_bold_font(self, size: int = 12) -> QFont:
        """Get bold font"""
        return self.get_font(size, QFont.Weight.Bold)
    
    def get_italic_font(self, size: int = 12) -> QFont:
        """Get italic font"""
        return self.get_font(size, italic=True)
    
    def is_loaded(self) -> bool:
        """Check if fonts are loaded"""
        return self.montserrat_loaded and self.emoji_loaded


# Global instance
_font_manager = FontManager()


def get_font_manager() -> FontManager:
    """Get global font manager instance"""
    return _font_manager


def load_fonts() -> bool:
    """Load custom fonts (convenience function)"""
    return get_font_manager().load_fonts()


def get_font(size: int = 12, weight: QFont.Weight = QFont.Weight.Normal, 
             italic: bool = False) -> QFont:
    """Get font with emoji support (convenience function)"""
    return get_font_manager().get_font(size, weight, italic)


def get_font_from_config(config, size_offset: int = 0, bold: bool = False, 
                        italic: bool = False) -> QFont:
    """Get font using config settings with emoji support
    
    Args:
        config: Config object with font settings
        size_offset: Offset to add to config font size (e.g., +2 for headers)
        bold: Whether font should be bold
        italic: Whether font should be italic
    
    Returns:
        QFont with proper emoji fallback
    """
    base_size = config.get("ui", "font_size") or 12
    size = base_size + size_offset
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    return get_font(size, weight, italic)


def set_application_font(app: QApplication, size: int = 12):
    """Set application-wide font (convenience function)"""
    get_font_manager().set_application_font(app, size)
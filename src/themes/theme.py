from PyQt6.QtWidgets import QApplication

from themes.stylesheet import build_stylesheet

_DEFAULT_INPUT_HEIGHT = 48


class ThemeManager:
    _DARK = "dark"
    _LIGHT = "light"

    def __init__(self, config):
        self.config = config
        self._current_theme = self.config.get("ui", "theme") or self._DARK

    def apply_theme(self, theme=None):
        if theme is None:
            theme = self._current_theme

        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_stylesheet(theme, self.config.get("ui", "input_height") or _DEFAULT_INPUT_HEIGHT))
            self._current_theme = theme
            self.config.set("ui", "theme", value=theme)

    def toggle_theme(self):
        """Toggle between dark and light theme"""
        new_theme = self._LIGHT if self._current_theme == self._DARK else self._DARK
        self.apply_theme(new_theme)
        return new_theme

    def is_dark(self):
        """Check if current theme is dark"""
        return self._current_theme == self._DARK

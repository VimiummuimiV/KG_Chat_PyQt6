import qdarktheme
from PyQt6.QtWidgets import QApplication


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
            stylesheet = qdarktheme.load_stylesheet(theme)

            # Custom overrides - make container borders transparent only
            stylesheet += """
                QListView,
                QScrollArea,
                QFrame,
                QTabWidget::pane {
                    border: 1px solid transparent !important;
                }
            """

            app.setStyleSheet(stylesheet)
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

    def _get_current_theme(self):
        """Get current theme name"""
        return self._current_theme

"""SettingsWidget: font families, sizes and preview."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTextEdit

from helpers.fonts.fonts import (
    ensure_family_loaded,
    FontType,
    get_available_emoji_families,
    get_available_font_families,
    get_font,
    invalidate_font_cache,
    set_application_font,
    set_config,
)
from helpers.translate import tr
from ui.settings.settings_widgets import (
    FONT_PREVIEW_BORDER,
    FONT_PREVIEW_PADDING,
    preview_box_stylesheet,
)


class SettingsFontsMixin:
    """SettingsWidget: font families, sizes and preview."""

    def build_fonts_section(self):
        section = self.create_section(tr("🅰️ Fonts", "🅰️ Шрифты"))
        # Combos start empty: refresh() fills them once after _setup_ui
        self._ui_font_combo = self.add_combo_row(
            section, tr("UI font", "Шрифт интерфейса"), [], self._on_ui_font_changed
        )
        self._ui_font_size_spin = self.add_slider_spin_row(
            section, tr("UI font size", "Размер шрифта интерфейса"), 10, 18, self._on_ui_font_size_changed,
            default=12
        )
        self._text_font_combo = self.add_combo_row(
            section, tr("Text font", "Шрифт текста"), [], self._on_text_font_changed
        )
        self._text_font_size_spin = self.add_slider_spin_row(
            section, tr("Text font size", "Размер шрифта текста"), 12, 24, self._on_text_font_size_changed,
            default=15
        )
        self._emoji_font_combo = self.add_combo_row(
            section, tr("Emoji font", "Шрифт эмодзи"), [], self._on_emoji_font_changed
        )
        self._ui_font_combo.setFixedWidth(240)
        self._text_font_combo.setFixedWidth(240)
        self._emoji_font_combo.setFixedWidth(240)

        preview_header, preview_content, preview_layout = self.add_subsection(section, tr("🔎 Preview", "🔎 Предпросмотр"))
        self._font_preview = QTextEdit()
        self._font_preview.setProperty("fontRole", "text")
        self._font_preview.setReadOnly(True)
        self._font_preview.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._font_preview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._font_preview.setPlainText(
            "Шла Маша по шоссе и сосала сушку\n"
            "The quick brown fox jumps over the lazy dog\n"
            "0 1 2 3 4 5 6 7 8 9\n"
            "😀 🎉 🚀 ❤️ 👍 🔥 ✨"
        )
        self.apply_font_preview_theme()
        preview_layout.addWidget(self._font_preview)
        self.update_font_preview()

        self.add_collapse_toggle(preview_header, preview_content, ("ui", "settings", "widgets", "font_preview"))

    def refresh_fonts(self):
        families = get_available_font_families() or ["Roboto"]
        for combo, kind in (
            (self._ui_font_combo, "ui"),
            (self._text_font_combo, "text"),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(families)
            current = self.config.get("font", kind, "family") or "Roboto"
            index = combo.findText(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

        emoji_families = get_available_emoji_families() or ["Noto Color Emoji"]
        self._emoji_font_combo.blockSignals(True)
        self._emoji_font_combo.clear()
        self._emoji_font_combo.addItems(emoji_families)
        current_emoji = self.config.get("font", "emoji_family") or "Noto Color Emoji"
        index = self._emoji_font_combo.findText(current_emoji)
        self._emoji_font_combo.setCurrentIndex(index if index >= 0 else 0)
        self._emoji_font_combo.blockSignals(False)

        ui_size = int(self.config.get("font", "ui", "size") or 12)
        text_size = (
            self.font_scaler.get_text_size()
            if self.font_scaler
            else int(self.config.get("font", "text", "size") or 15)
        )
        for spin, value in (
            (self._ui_font_size_spin, ui_size),
            (self._text_font_size_spin, text_size),
        ):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.linked_slider.blockSignals(True)
            spin.linked_slider.setValue(value)
            spin.linked_slider.blockSignals(False)
            spin.blockSignals(False)

        self.update_font_preview()

    def apply_font_preview_theme(self):
        if not hasattr(self, "_font_preview"):
            return
        self._font_preview.setStyleSheet(
            preview_box_stylesheet("QTextEdit", self.config.get("ui", "theme") or "dark")
        )

    def update_font_preview(self):
        if not hasattr(self, "_font_preview"):
            return
        self._font_preview.setFont(get_font(FontType.TEXT))
        self.apply_font_preview_theme()
        self._fit_font_preview_height()

    def _fit_font_preview_height(self):
        """Grow/shrink preview block to fit content without clipping, keeping the
        top and bottom gap identical (uses the same border/padding constants as
        the stylesheet instead of guessed frame/margin values)."""
        preview = self._font_preview
        doc = preview.document()
        width = preview.viewport().width()
        if width < 50:
            width = max(preview.width() - 20, 300)
        doc.setTextWidth(width)
        vertical_chrome = 2 * (FONT_PREVIEW_BORDER + FONT_PREVIEW_PADDING)
        height = int(doc.size().height()) + vertical_chrome
        preview.setFixedHeight(max(48, height))

    def _apply_font_family(self, kind: str, family: str):
        if not family:
            return
        self.config.set("font", kind, "family", value=family)
        set_config(self.config)
        ensure_family_loaded(family)
        invalidate_font_cache()
        app = QApplication.instance()
        if app:
            set_application_font(app)
        self.update_font_preview()
        self.font_family_changed.emit()

    def _on_ui_font_changed(self, _text: str = ""):
        self._apply_font_family("ui", self._ui_font_combo.currentText())

    def _on_text_font_changed(self, _text: str = ""):
        self._apply_font_family("text", self._text_font_combo.currentText())

    def _on_emoji_font_changed(self, _text: str = ""):
        family = self._emoji_font_combo.currentText()
        if not family:
            return
        self.config.set("font", "emoji_family", value=family)
        set_config(self.config)
        invalidate_font_cache()
        app = QApplication.instance()
        if app:
            set_application_font(app)
        self.update_font_preview()
        self.font_family_changed.emit()

    def _on_ui_font_size_changed(self, value: int):
        self.config.set("font", "ui", "size", value=value)
        set_config(self.config)
        invalidate_font_cache()
        app = QApplication.instance()
        if app:
            set_application_font(app)
        self.competitions_log.setFont(get_font(FontType.UI))
        if not self.competitions_log.isEnabled():
            self.competitions_log.setFixedHeight(self.collapsed_log_height())
        self.font_family_changed.emit()

    def _on_text_font_size_changed(self, value: int):
        if self.font_scaler:
            self.font_scaler.set_size(value)
        else:
            self.config.set("font", "text", "size", value=value)
            invalidate_font_cache()
            self.font_family_changed.emit()
        self.update_font_preview()

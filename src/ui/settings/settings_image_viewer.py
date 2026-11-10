"""SettingsWidget: image viewer gallery, slideshow and transition options."""

from components.image_viewer.options import (
    DEFAULT_SLIDESHOW_SECONDS,
    DEFAULT_TRANSITION_MS,
    show_thumbnails,
    show_zoom_slider,
    SLIDESHOW_SECONDS_RANGE,
    slideshow_interval_seconds,
    transition_duration_ms,
    TRANSITION_MS_RANGE,
)
from helpers.translate import tr
from ui.settings.settings_options import fill_image_reply_mode_combo, fill_image_transition_combo


class SettingsImageViewerMixin:
    """SettingsWidget: image viewer gallery, slideshow and transition options."""

    def build_image_viewer_section(self):
        section = self.create_section(tr("🖼️ Image viewer", "🖼️️️ Просмотр изображений"))

        gallery_header, gallery_content, gallery_layout = self.add_subsection(
            section, tr("Gallery", "Галерея")
        )
        self.image_viewer_thumbnails_checkbox = self.add_checkbox(
            gallery_layout,
            tr("Show thumbnails", "Показывать миниатюры"),
            self._on_image_viewer_thumbnails_toggled,
        )
        self.image_viewer_zoom_slider_checkbox = self.add_checkbox(
            gallery_layout,
            tr("Show zoom slider", "Показывать ползунок масштаба"),
            self._on_image_viewer_zoom_slider_toggled,
        )
        self.image_viewer_slideshow_spin = self.add_slider_spin_row(
            gallery_layout, tr("Slideshow interval (s)", "Интервал слайдшоу (с)"),
            *SLIDESHOW_SECONDS_RANGE, self._on_image_viewer_slideshow_changed,
            default=DEFAULT_SLIDESHOW_SECONDS,
        )
        self.add_collapse_toggle(gallery_header, gallery_content, ("ui", "settings", "widgets", "image_viewer_gallery"))

        reply_header, reply_content, reply_layout = self.add_subsection(section, tr("Reply", "Ответ"))
        self._image_viewer_reply_combo = self.add_combo_row(
            reply_layout, tr("Reply button", "Кнопка ответа"), [], self._on_image_viewer_reply_mode_changed
        )
        self._image_viewer_reply_combo.setFixedWidth(240)
        self.add_collapse_toggle(reply_header, reply_content, ("ui", "settings", "widgets", "image_viewer_reply"))

        transition_header, transition_content, transition_layout = self.add_subsection(
            section, tr("Transition", "Переход")
        )
        self.image_viewer_transition_combo = self.add_combo_row(
            transition_layout, tr("Animation", "Анимация"),
            [], self._on_image_viewer_transition_changed
        )
        self.image_viewer_transition_combo.setFixedWidth(240)
        self.image_viewer_transition_spin = self.add_slider_spin_row(
            transition_layout, tr("Duration (ms)", "Длительность (мс)"),
            *TRANSITION_MS_RANGE, self._on_image_viewer_transition_duration_changed,
            default=DEFAULT_TRANSITION_MS,
        )
        self.add_collapse_toggle(transition_header, transition_content, ("ui", "settings", "widgets", "image_viewer_transition"))

    def refresh_image_viewer(self):
        self.image_viewer_thumbnails_checkbox.setChecked(show_thumbnails(self.config))
        self.image_viewer_zoom_slider_checkbox.setChecked(show_zoom_slider(self.config))
        fill_image_reply_mode_combo(self._image_viewer_reply_combo, self.config.get("image_viewer", "reply_mode"))
        fill_image_transition_combo(self.image_viewer_transition_combo, self.config.get("image_viewer", "transition"))
        for spin, value in (
            (self.image_viewer_slideshow_spin, slideshow_interval_seconds(self.config)),
            (self.image_viewer_transition_spin, transition_duration_ms(self.config)),
        ):
            spin.setValue(value)
            spin.linked_slider.setValue(value)

    def _on_image_viewer_thumbnails_toggled(self, checked: bool):
        self.config.set("image_viewer", "show_thumbnails", value=checked)

    def _on_image_viewer_zoom_slider_toggled(self, checked: bool):
        self.config.set("image_viewer", "show_zoom_slider", value=checked)

    def _on_image_viewer_slideshow_changed(self, value: int):
        self.config.set("image_viewer", "slideshow_interval", value=int(value))

    def _on_image_viewer_reply_mode_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self._image_viewer_reply_combo)
        self.config.set("image_viewer", "reply_mode", value=self._image_viewer_reply_combo.currentData())

    def _on_image_viewer_transition_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.image_viewer_transition_combo)
        self.config.set("image_viewer", "transition", value=self.image_viewer_transition_combo.currentData())

    def _on_image_viewer_transition_duration_changed(self, value: int):
        self.config.set("image_viewer", "transition_ms", value=int(value))

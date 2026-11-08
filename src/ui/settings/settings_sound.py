"""SettingsWidget: alert sound selectors and playback options."""

from helpers.data import get_resource_dir
from helpers.translate import tr
from ui.settings.settings_options import DEFAULTS
from ui.settings.sound_selector import SoundSelectorWidget


class SettingsSoundMixin:
    """SettingsWidget: alert sound selectors and playback options."""

    def build_sound_section(self):
        section = self.create_section(tr("🔊 Sound", "🔊 Звук"))
        self.mention_always_checkbox = self.add_checkbox(
            section, tr("Play mention sound even when chat is focused", "Звук упоминания даже когда чат в фокусе"),
            self._on_mention_always_toggled
        )
        self.competition_always_checkbox = self.add_checkbox(
            section, tr("Play competition sound even when chat is focused", "Звук соревнования даже когда чат в фокусе"),
            self._on_competition_always_toggled
        )

        self.sound_selectors = {}
        self.sound_dir = get_resource_dir("sounds")
        sound_types = [
            ("mention", tr("Mention sound", "Звук упоминания")),
            ("ban", tr("Ban sound", "Звук бана")),
            ("competition", tr("Competition sound", "Звук соревнования")),
        ]
        for kind, label in sound_types:
            selector = SoundSelectorWidget(self.config, self.sound_dir, kind, label)
            selector.combo.currentIndexChanged.connect(self._on_sound_selection_changed)
            self.sound_selectors[kind] = selector
            section.addWidget(selector)

        self.competition_sound_repeat_checkbox = self.add_checkbox(
            section, tr("Repeat competition sound until you're back", "Повторять звук соревнования, пока вы не вернётесь"),
            self._on_competition_sound_repeat_toggled
        )
        self.competition_sound_repeat_interval_spin = self.add_slider_spin_row(
            section, tr("Repeat interval (sec)", "Интервал повтора (сек)"), 3, 120, self._on_competition_sound_repeat_interval_changed,
            default=DEFAULTS["competitions"]["sound_repeat_interval"],
        )

    def _on_sound_selection_changed(self, _index: int):
        self.sound_changed.emit()

    def refresh_sound(self):
        mention_always = self.config.get("sound", "play_mention_sound_always")
        self.mention_always_checkbox.setChecked(False if mention_always is None else bool(mention_always))

        competition_always = self.config.get("sound", "play_competition_sound_always")
        self.competition_always_checkbox.setChecked(True if competition_always is None else bool(competition_always))

        self.competition_sound_repeat_checkbox.setChecked(
            bool(self.config.get("sound", "competition_repeat_enabled"))
        )
        self.competition_sound_repeat_interval_spin.setValue(
            int(self.config.get("sound", "competition_repeat_interval") or DEFAULTS["competitions"]["sound_repeat_interval"])
        )
        self.competition_sound_repeat_interval_spin.linked_slider.setValue(self.competition_sound_repeat_interval_spin.value())
        self.set_spin_enabled(self.competition_sound_repeat_interval_spin, self.competition_sound_repeat_checkbox.isChecked())

    def _on_competition_sound_repeat_toggled(self, checked: bool):
        self.config.set("sound", "competition_repeat_enabled", value=checked)
        self.set_spin_enabled(self.competition_sound_repeat_interval_spin, checked)

    def _on_competition_sound_repeat_interval_changed(self, value: int):
        self.config.set("sound", "competition_repeat_interval", value=value)

    def _on_mention_always_toggled(self, checked: bool):
        self.config.set("sound", "play_mention_sound_always", value=checked)

    def _on_competition_always_toggled(self, checked: bool):
        self.config.set("sound", "play_competition_sound_always", value=checked)

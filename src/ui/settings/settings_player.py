"""SettingsWidget: media player options."""

from helpers.translate import tr
from ui.settings.settings_options import (
    DEFAULTS,
    fill_player_hwdec_combo,
    fill_player_ytdl_format_combo,
)


class SettingsPlayerMixin:
    """SettingsWidget: media player options."""

    def build_player_section(self):
        section = self.create_section(tr("🎬 Player", "🎬 Плеер"))

        mpv_header, mpv_content, mpv_layout = self.add_subsection(
            section, tr("MPV", "MPV")
        )
        self.player_tls_checkbox = self.add_checkbox(
            mpv_layout,
            tr("Disable TLS certificate verification", "Отключить проверку TLS-сертификатов"),
            self._on_player_tls_toggled,
        )
        self.player_hwdec_combo = self.add_combo_row(
            mpv_layout, tr("Hardware decoding", "Аппаратное декодирование"),
            [], self._on_player_hwdec_changed
        )
        self.player_hwdec_combo.setFixedWidth(240)
        self.player_volume_spin = self.add_slider_spin_row(
            mpv_layout, tr("Startup volume", "Начальная громкость"), 0, 100,
            self._on_player_volume_changed,
            default=DEFAULTS["player"]["volume"],
        )
        self.player_log_checkbox = self.add_checkbox(
            mpv_layout,
            tr("Save MPV log", "Сохранять лог MPV"),
            self._on_player_log_toggled,
        )
        self.player_keep_open_checkbox = self.add_checkbox(
            mpv_layout,
            tr("Keep window open", "Не закрывать окно"),
            self._on_player_keep_open_toggled,
        )
        self.player_ontop_checkbox = self.add_checkbox(
            mpv_layout,
            tr("Always on top", "Поверх всех окон"),
            self._on_player_ontop_toggled,
        )
        self.add_collapse_toggle(mpv_header, mpv_content, ("ui", "settings", "widgets", "player_mpv"))

        ytdl_header, ytdl_content, ytdl_layout = self.add_subsection(
            section, tr("YTDLP", "YTDLP")
        )
        self.player_ytdl_format_combo = self.add_combo_row(
            ytdl_layout, tr("Preferred format", "Предпочитаемый формат"),
            [], self._on_player_ytdl_format_changed
        )
        self.player_ytdl_format_combo.setFixedWidth(240)
        self.add_collapse_toggle(ytdl_header, ytdl_content, ("ui", "settings", "widgets", "player_ytdl"))

    def refresh_player(self):
        tls_disabled = self.config.get("player", "disable_tls_verify")
        self.player_tls_checkbox.setChecked(
            DEFAULTS["player"]["disable_tls_verify"] if tls_disabled is None else bool(tls_disabled)
        )
        fill_player_hwdec_combo(self.player_hwdec_combo, self.config.get("player", "hwdec"))

        volume = self.config.get("player", "volume")
        try:
            volume = int(volume) if volume is not None else DEFAULTS["player"]["volume"]
        except (TypeError, ValueError):
            volume = DEFAULTS["player"]["volume"]
        volume = max(0, min(100, volume))
        self.player_volume_spin.setValue(volume)
        self.player_volume_spin.linked_slider.setValue(volume)

        log = self.config.get("player", "log")
        self.player_log_checkbox.setChecked(
            DEFAULTS["player"]["log"] if log is None else bool(log)
        )
        keep_open = self.config.get("player", "keep_open")
        self.player_keep_open_checkbox.setChecked(
            DEFAULTS["player"]["keep_open"] if keep_open is None else bool(keep_open)
        )
        ontop = self.config.get("player", "ontop")
        self.player_ontop_checkbox.setChecked(
            DEFAULTS["player"]["ontop"] if ontop is None else bool(ontop)
        )
        fill_player_ytdl_format_combo(
            self.player_ytdl_format_combo, self.config.get("player", "ytdl_format") or ""
        )

    def _on_player_tls_toggled(self, checked: bool):
        self.config.set("player", "disable_tls_verify", value=checked)

    def _on_player_hwdec_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.player_hwdec_combo)
        value = self.player_hwdec_combo.currentData() or "auto"
        self.config.set("player", "hwdec", value=value)

    def _on_player_volume_changed(self, value: int):
        self.config.set("player", "volume", value=int(value))

    def _on_player_log_toggled(self, checked: bool):
        self.config.set("player", "log", value=checked)

    def _on_player_keep_open_toggled(self, checked: bool):
        self.config.set("player", "keep_open", value=checked)

    def _on_player_ontop_toggled(self, checked: bool):
        self.config.set("player", "ontop", value=checked)

    def _on_player_ytdl_format_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.player_ytdl_format_combo)
        value = self.player_ytdl_format_combo.currentData()
        self.config.set("player", "ytdl_format", value=value if value is not None else "")

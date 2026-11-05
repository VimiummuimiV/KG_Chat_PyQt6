"""SettingsWidget: startup, connection, language, YouTube, voice input and browser options."""

from PyQt6.QtWidgets import QMessageBox

from helpers.translate import get_language, set_language, tr
from ui.settings.settings_options import fill_own_message_mode_combo, fill_resource_combo


class SettingsGeneralMixin:
    """SettingsWidget: startup, connection, language, YouTube, voice input and browser options."""

    def _build_startup_section(self):
        section = self._create_section(tr("🚀 Startup", "🚀 Запуск"))
        self.auto_login_checkbox = self._add_checkbox(
            section, tr("Auto-login on startup", "Автовход при запуске"), self._on_auto_login_toggled
        )
        self.start_minimized_checkbox = self._add_checkbox(
            section, tr("Start minimized", "Запускать свёрнутым"), self._on_start_minimized_toggled
        )
        self.start_with_system_checkbox = self._add_checkbox(
            section, tr("Start with system", "Запускать вместе с системой"), self._on_start_with_system_toggled
        )

    def _refresh_general(self):
        self.settings_accordion_checkbox.setChecked(
            bool(self.config.get("ui", "settings", "accordion"))
        )
        self.auto_login_checkbox.setChecked(bool(self.config.get("startup", "auto_login")))
        self.start_minimized_checkbox.setChecked(bool(self.config.get("startup", "start_minimized")))
        self.start_with_system_checkbox.setChecked(self.startup_manager.is_enabled())

        fill_resource_combo(
            self.resource_combo,
            self.config.get("server", "resource") or "web",
        )
        fill_own_message_mode_combo(
            self.own_message_mode_combo,
            self.config.get("ui", "own_message_mode") or "local",
        )

        self.clear_private_checkbox.setChecked(bool(self.config.get("ui", "clear_private_messages_on_exit")))

        youtube_enabled = self.config.get("ui", "youtube", "enabled")
        self.youtube_checkbox.setChecked(True if youtube_enabled is None else bool(youtube_enabled))
        voice_input_enabled = self.config.get("voice_input", "enabled")
        self.voice_input_checkbox.setChecked(True if voice_input_enabled is None else bool(voice_input_enabled))

    def _on_settings_accordion_toggled(self, checked: bool):
        self.config.set("ui", "settings", "accordion", value=checked)

    def _on_auto_login_toggled(self, checked: bool):
        self.config.set("startup", "auto_login", value=checked)

    def _on_start_minimized_toggled(self, checked: bool):
        self.config.set("startup", "start_minimized", value=checked)

    def _on_start_with_system_toggled(self, checked: bool):
        success = self.startup_manager.enable() if checked else self.startup_manager.disable()
        if not success:
            QMessageBox.warning(
                self, tr("Error", "Ошибка"),
                tr(f"Failed to {'enable' if checked else 'disable'} start with system. Please check permissions.",
                   f"Не удалось {'включить' if checked else 'выключить'} запуск с системой. Проверьте права доступа.")
            )
            self.start_with_system_checkbox.blockSignals(True)
            self.start_with_system_checkbox.setChecked(not checked)
            self.start_with_system_checkbox.blockSignals(False)

    def _on_resource_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.resource_combo)
        value = self.resource_combo.currentData()
        if value is None:
            return
        previous = self.config.get("server", "resource") or "web"
        if value == previous:
            return
        self.config.set("server", "resource", value=value)
        print(f"📡 XMPP resource changed: {previous} → {value}")
        self.resource_changed.emit()

    def _on_own_message_mode_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.own_message_mode_combo)
        value = self.own_message_mode_combo.currentData()
        if value is None:
            return
        previous = self.config.get("ui", "own_message_mode") or "local"
        if value == previous:
            return
        self.config.set("ui", "own_message_mode", value=value)
        print(f"💬 Own message mode: {value}")

    def _on_language_changed(self, _text: str = ""):
        code = self.language_combo.currentData()
        if code and code != get_language():
            self.config.set("ui", "language", value=code)
            set_language(code)

    def _on_clear_private_toggled(self, checked: bool):
        self.config.set("ui", "clear_private_messages_on_exit", value=checked)

    def _on_youtube_toggled(self, checked: bool):
        self.config.set("ui", "youtube", "enabled", value=checked)

    def _on_voice_input_toggled(self, checked: bool):
        self.config.set("voice_input", "enabled", value=checked)

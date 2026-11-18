"""SettingsWidget: automatic update check, its interval and the manual check."""

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton

from core.web.updater import (
    check_interval_days,
    CHECK_INTERVAL_DAYS_RANGE,
    DEFAULT_CHECK_INTERVAL_DAYS,
    installed_commit,
    is_auto_check_enabled,
    is_development_checkout,
    last_checked_at,
    saved_update,
    short_commit,
)
from helpers.translate import tr
from ui.settings.settings_widgets import SettingsRow


_TIME_FORMAT = "%Y-%m-%d %H:%M"


class SettingsUpdatesMixin:
    """SettingsWidget: automatic update check, its interval and the manual check."""

    def build_updates_section(self):
        section = self.create_section(tr("🔄 Updates", "🔄 Обновления"))
        self.update_auto_check_checkbox = self.add_checkbox(
            section, tr("Check for updates automatically", "Проверять обновления автоматически"),
            self._on_update_auto_check_toggled,
        )
        self.update_interval_spin = self.add_slider_spin_row(
            section, tr("Check every (days)", "Проверять раз в (дней)"),
            *CHECK_INTERVAL_DAYS_RANGE, self._on_update_interval_changed,
            default=DEFAULT_CHECK_INTERVAL_DAYS,
        )

        row_widget = SettingsRow(spacing=self.element_spacing())
        row = row_widget.layout()
        self._update_status_label = QLabel()
        self._update_status_label.setObjectName("mutedHint")
        self._update_status_label.setWordWrap(True)
        row.addWidget(self._update_status_label, stretch=1)
        check_text = tr("Check now", "Проверить сейчас")
        self._update_check_button = QPushButton(check_text)
        self._update_check_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._update_check_button.clicked.connect(self._on_update_check_clicked)
        row.addWidget(self._update_check_button)
        self.register_tr(self._update_check_button.setText, check_text)
        section.addWidget(row_widget)

    def refresh_updates(self):
        enabled = is_auto_check_enabled(self.config)
        self.update_auto_check_checkbox.setChecked(enabled)
        days = check_interval_days(self.config)
        self.update_interval_spin.setValue(days)
        self.update_interval_spin.linked_slider.setValue(days)
        self.set_spin_enabled(self.update_interval_spin, enabled)
        self.refresh_update_status()

    def refresh_update_status(self):
        """Render the installed version, the last check and a waiting update; re-enable the manual check."""
        is_development = is_development_checkout()
        self._update_check_button.setEnabled(not is_development)
        if is_development:
            self._update_status_label.setText(
                tr("Development checkout: updates are disabled", "Рабочая копия git: обновления отключены")
            )
            return
        current = installed_commit()
        checked_at = last_checked_at()
        version = short_commit(current) if current else tr("unknown", "неизвестна")
        checked = datetime.fromtimestamp(checked_at).strftime(_TIME_FORMAT) if checked_at else tr("never", "никогда")
        text = tr(f"Version: {version} · Last check: {checked}", f"Версия: {version} · Последняя проверка: {checked}")
        update = saved_update()
        if update:
            commit = short_commit(update.latest_commit)
            text += tr(f" · Update available: {commit}", f" · Доступно обновление: {commit}")
        self._update_status_label.setText(text)

    def _on_update_auto_check_toggled(self, checked: bool):
        self.config.set("update", "auto_check", value=checked)
        self.set_spin_enabled(self.update_interval_spin, checked)

    def _on_update_interval_changed(self, value: int):
        self.config.set("update", "interval_days", value=int(value))

    def _on_update_check_clicked(self):
        self._update_check_button.setEnabled(False)
        self.update_check_requested.emit()

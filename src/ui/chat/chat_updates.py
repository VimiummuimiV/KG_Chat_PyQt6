"""ChatWindow: automatic and manual update checks, the update button and the install flow."""

import threading
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from components.button import animate_button_bounce
from components.toast import ToastKind
from core.web.updater import (
    check_for_update,
    check_interval_days,
    installed_commit,
    is_auto_check_enabled,
    is_development_checkout,
    last_checked_at,
    save_check_result,
    saved_update,
    short_commit,
    stage_update,
    upgrade_ytdlp,
)
from helpers.deferred import call_later
from helpers.translate import tr
from ui.dialogs.update_dialog import UpdateDialog


_STARTUP_CHECK_DELAY_MS = 5000
_UPDATE_HINT_INTERVAL_MS = 4000
_DUE_POLL_INTERVAL_MS = 60 * 60 * 1000
_DOWNLOAD_TOAST_MS = 60 * 1000
_SECONDS_PER_DAY = 24 * 60 * 60


class ChatUpdatesMixin:
    """ChatWindow: automatic and manual update checks, the update button and the install flow."""

    def setup_update_checks(self):
        """Show an update found earlier at once and schedule the automatic checks."""
        self._available_update = None
        self._update_check_running = False
        self._update_installing = False
        if is_development_checkout():
            return
        self._update_hint_timer = QTimer(self)
        self._update_hint_timer.timeout.connect(self._bounce_update_button)
        self._set_available_update(saved_update())
        due_timer = QTimer(self)
        due_timer.timeout.connect(self._check_for_update_when_due)
        due_timer.start(_DUE_POLL_INTERVAL_MS)
        call_later(self, _STARTUP_CHECK_DELAY_MS, self._check_for_update_when_due)

    def check_for_update_manually(self):
        """Check now, whatever the automatic check settings say, and report the result."""
        self._run_update_check(manual=True)

    def show_update_dialog(self):
        """Show the release notes and install the update when the user agrees."""
        if self._available_update is None or self._update_installing:
            return
        if UpdateDialog(self, self.config, self._available_update).exec() == QDialog.DialogCode.Accepted:
            self._install_update(self._available_update)

    def _check_for_update_when_due(self):
        if not is_auto_check_enabled(self.config):
            return
        checked_at = last_checked_at()
        is_recently_checked = (
            checked_at is not None and time.time() - checked_at < check_interval_days(self.config) * _SECONDS_PER_DAY
        )
        if installed_commit() is not None and is_recently_checked:  # without the installed commit the first check is due at once
            return
        self._run_update_check(manual=False)

    def _run_update_check(self, manual: bool):
        if self._update_check_running or is_development_checkout():
            return
        self._update_check_running = True

        def check():
            info, error = None, None
            try:
                info = check_for_update()
            except Exception as exception:
                error = str(exception)
            self.dispatch.emit(lambda: self._on_update_check_finished(info, error, manual))

        threading.Thread(target=check, daemon=True).start()

    def _on_update_check_finished(self, info, error: str | None, manual: bool):
        self._update_check_running = False
        if error:
            print(f"⚠️ Update check failed: {error}")
            if manual:
                self.toast.show_message(tr("Update check failed", "Не удалось проверить обновления"), ToastKind.ERROR)
            self._refresh_settings_update_status()
            return
        save_check_result(info, int(time.time()))
        is_new = info is not None and (
            self._available_update is None or self._available_update.latest_commit != info.latest_commit
        )
        self._set_available_update(info)
        if info and (is_new or manual):
            commit = short_commit(info.latest_commit)
            self.toast.show_message(tr(f"Update available: {commit}", f"Доступно обновление: {commit}"), ToastKind.INFO)
            self._bounce_update_button()
        elif manual:
            self.toast.show_message(tr("You have the latest version", "У вас последняя версия"), ToastKind.SUCCESS)
        self._refresh_settings_update_status()

    def _set_available_update(self, info):
        """Show the update button and bounce its icon periodically while an update waits."""
        self._available_update = info
        self.button_panel.set_update_available(short_commit(info.latest_commit) if info else None)
        if info:
            self._update_hint_timer.start(_UPDATE_HINT_INTERVAL_MS)
        else:
            self._update_hint_timer.stop()

    def _bounce_update_button(self):
        animate_button_bounce(self.button_panel.update_button)

    def _refresh_settings_update_status(self):
        settings = getattr(self, "settings_widget", None)
        if settings:
            settings.refresh_update_status()

    def _install_update(self, info):
        self._update_installing = True
        self.button_panel.update_button.setEnabled(False)
        self.toast.show_message(tr("Downloading update…", "Скачивание обновления…"), ToastKind.INFO, _DOWNLOAD_TOAST_MS)

        def download():
            error = None
            try:
                stage_update(info)
            except Exception as exception:
                error = str(exception)
            is_ytdlp_upgraded = upgrade_ytdlp() if error is None else True
            self.dispatch.emit(lambda: self._on_update_staged(error, is_ytdlp_upgraded))

        threading.Thread(target=download, daemon=True).start()

    def _on_update_staged(self, error: str | None, is_ytdlp_upgraded: bool):
        self._update_installing = False
        self.button_panel.update_button.setEnabled(True)
        if error:
            print(f"⚠️ Update download failed: {error}")
            self.toast.show_message(tr("Update download failed", "Не удалось скачать обновление"), ToastKind.ERROR)
            return
        if not is_ytdlp_upgraded:
            QMessageBox.warning(
                self, tr("Update", "Обновление"),
                tr("yt-dlp could not be upgraded. Run: pip install --upgrade yt-dlp",
                   "Не удалось обновить yt-dlp. Выполните: pip install --upgrade yt-dlp"),
            )
        if self.app_controller:
            self.app_controller.restart_application()
        else:
            QApplication.quit()

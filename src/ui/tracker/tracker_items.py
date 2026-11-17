"""Tracked user rows and history filter chips."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QSizePolicy

from components.button import create_icon_button, set_visual_active
from components.user_count_row import UserCountRow
from components.user_entry_row import UserEntryRow
from helpers.translate import on_language_changed, tr, TranslatableMixin


class TrackedUserItem(UserEntryRow):
    """Tracked user row: the shared user row with a freeze button."""

    freeze_toggled = pyqtSignal(str, bool)  # user_id, frozen

    def __init__(self, config, icons_path: Path, username="", user_id=""):
        super().__init__(config, icons_path, username, user_id)
        self.frozen = False

        self._freeze_button = create_icon_button(icons_path, "line/snowflake-line.svg", "", size_type="large", config=config)
        self._freeze_button.clicked.connect(self._toggle_freeze)
        self._show_freeze_tooltip()
        self.add_action(self._freeze_button)

    def set_frozen(self, frozen: bool):
        self.frozen = bool(frozen)
        set_visual_active(self.username_input, not self.frozen)
        set_visual_active(self.user_id_input, not self.frozen)
        set_visual_active(self._freeze_button, not self.frozen)
        self._show_freeze_tooltip()

    def _show_freeze_tooltip(self):
        self._freeze_button.setToolTip(
            tr("Unfreeze tracking", "Разморозить отслеживание") if self.frozen
            else tr("Freeze tracking", "Заморозить отслеживание")
        )

    def retranslate_all(self, _code=None):
        super().retranslate_all(_code)
        self._show_freeze_tooltip()

    def _toggle_freeze(self):
        if not self.user_id:
            return
        self.set_frozen(not self.frozen)
        self.freeze_toggled.emit(self.user_id, self.frozen)


class TrackerUserChip(TranslatableMixin, UserCountRow):
    """History filter chip: avatar + login + event count, orange highlight when filtered"""

    delete_requested = pyqtSignal(str)

    def __init__(self, config, icons_path: Path, login: str, count: int, user_id: str = None):
        super().__init__(
            login, count, config, icons_path, user_id,
        )
        self.init_translatable()
        self.login = login
        self._delete_button = create_icon_button(icons_path, "fill/delete-bin-fill.svg", "", size_type="small", config=config)
        self.tr_set(self._delete_button.setToolTip, "Remove history for this user", "Удалить историю этого пользователя")
        on_language_changed(self.retranslate_all)
        self._delete_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._delete_button.clicked.connect(lambda: self.delete_requested.emit(self.login))
        self.layout().addWidget(self._delete_button)

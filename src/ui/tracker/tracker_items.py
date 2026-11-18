"""History filter chips."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QSizePolicy

from components.button import create_icon_button
from components.user_count_row import UserCountRow
from helpers.translate import on_language_changed, TranslatableMixin


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
        self.tr_set(self._delete_button.setToolTip, "Clear history of this user", "Очистить историю этого пользователя")
        on_language_changed(self.retranslate_all)
        self._delete_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._delete_button.clicked.connect(lambda: self.delete_requested.emit(self.login))
        self.layout().addWidget(self._delete_button)

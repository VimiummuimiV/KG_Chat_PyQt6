"""UserTrackerWidget: tracked user list editing and persistence."""

from PyQt6.QtWidgets import QMessageBox

from components.user_row.model import COLUMN_TOGGLE, ExtraColumn, UserRow
from helpers.translate import tr
from ui.tracker.tracker_items import TrackerUserChip


FREEZE_COLUMN = ExtraColumn(
    "frozen", COLUMN_TOGGLE, icon="line/snowflake-line.svg", dims_row=True,
    tooltips=(("Freeze tracking", "Заморозить отслеживание"), ("Unfreeze tracking", "Разморозить отслеживание")),
)


class TrackerSelectionMixin:
    """UserTrackerWidget: tracked user list editing and persistence."""

    def make_chip(self, login: str, count: int, user_id: str = None) -> "TrackerUserChip":
        chip = TrackerUserChip(self.config, self.icons_path, login, count, user_id)
        if login in self.filtered_logins:
            chip.set_filtered(True)
        chip.clicked.connect(self.handle_filter_click)
        chip.delete_requested.connect(self.handle_chip_delete_requested)
        self.chip_widgets[login] = chip
        return chip

    def load_selected(self):
        self._are_rows_stale = False
        tracker = self.user_tracker
        self.users_view.set_rows([
            UserRow(username, user_id, {"frozen": tracker.is_frozen(user_id=user_id)})
            for user_id, username in tracker.get_selected().items()
        ])
        self.update_tracked_count()

    def add_new_item(self):
        if not self.users_view.edit_empty_row():
            self.users_view.add_row()

    def clear_users(self):
        """Stop tracking every user, after a confirmation."""
        if not self.users_view.rows:
            return
        reply = QMessageBox.question(
            self, tr("Remove all users", "Удалить всех пользователей"),
            tr("Stop tracking all users?", "Прекратить отслеживание всех пользователей?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.users_view.clear()
            self.save_selected()

    def update_tracked_count(self):
        count = self.users_view.filled_count()
        self.tracked_count_label.setText(tr(f"Total: {count}", f"Всего: {count}"))

    def handle_freeze_changed(self, row: UserRow, _key: str):
        self.user_tracker.set_frozen(row.user_id, row.extras["frozen"])

    def save_selected(self):
        self.user_tracker.replace_selected({row.user_id: row.username for row in self.users_view.rows if row.is_confirmed})
        self.update_tracked_count()
        self.tracked_users_changed.emit()

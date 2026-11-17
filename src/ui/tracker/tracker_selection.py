"""UserTrackerWidget: tracked user list editing and persistence."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from helpers.translate import tr
from ui.tracker.tracker_items import TrackedUserItem, TrackerUserChip


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

    def _discard_items(self):
        for item in self.user_items:
            self.users_grid.removeWidget(item)
            item.cleanup()
            item.deleteLater()
        self.user_items.clear()

    def load_selected(self):
        self._are_rows_stale = False
        self._discard_items()
        for user_id, username in self.user_tracker.get_selected().items():
            self._add_item(username, user_id, recalculate=False)
            item = self.user_items[-1]
            if self.user_tracker.is_frozen(user_id=user_id):
                item.set_frozen(True)

        if self.user_items:
            QTimer.singleShot(50, self.recalculate_layout)
        self.update_tracked_count()

    def _add_item(self, username="", user_id="", recalculate=True):
        item = TrackedUserItem(self.config, self.icons_path, username, user_id)
        item.remove_requested.connect(self._remove_item)
        item.changed.connect(self.save_selected)
        item.freeze_toggled.connect(self.user_tracker.set_frozen)
        self.user_items.append(item)
        if recalculate:
            self.recalculate_layout()

    def add_new_item(self):
        for item in self.user_items:
            if item.is_empty():
                item.update_input_style(highlight_empty=True)
                item.username_input.setFocus()
                return
        self._add_item()

    def _remove_item(self, item: TrackedUserItem):
        if item in self.user_items:
            self.user_items.remove(item)
            self.users_grid.removeWidget(item)
            item.cleanup()
            item.deleteLater()
            self.save_selected()
            self.recalculate_layout()

    def clear_users(self):
        """Stop tracking every user, after a confirmation."""
        if not self.user_items:
            return
        reply = QMessageBox.question(
            self, tr("Remove all users", "Удалить всех пользователей"),
            tr("Stop tracking all users?", "Прекратить отслеживание всех пользователей?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._discard_items()
            self.save_selected()

    def update_tracked_count(self):
        count = sum(1 for item in self.user_items if not item.is_empty())
        self.tracked_count_label.setText(tr(f"Total: {count}", f"Всего: {count}"))

    def save_selected(self):
        self.user_tracker.clear_selected()
        for item in self.user_items:
            username, user_id = item.get_data()
            if username and user_id and item.username_valid:
                self.user_tracker.add_selected(user_id, username)
        self.update_tracked_count()
        self.tracked_users_changed.emit()

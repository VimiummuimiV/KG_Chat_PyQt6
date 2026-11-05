"""UserTrackerWidget: tracked user list editing and persistence."""

from PyQt6.QtCore import QTimer

from ui.tracker.tracker_items import TrackedUserItem, TrackerUserChip


class TrackerSelectionMixin:
    """UserTrackerWidget: tracked user list editing and persistence."""

    def _make_chip(self, login: str, count: int, user_id: str = None) -> "TrackerUserChip":
        chip = TrackerUserChip(self.config, self.icons_path, login, count, user_id)
        chip.set_filtered(login in self.filtered_logins)
        chip.clicked.connect(self._handle_filter_click)
        chip.delete_requested.connect(self._handle_chip_delete_requested)
        self.chip_widgets[login] = chip
        return chip

    def _load_selected(self):
        for item in list(self.user_items):
            self.users_grid.removeWidget(item)
            item.cleanup()
            item.deleteLater()
        self.user_items.clear()

        for user_id, username in self.user_tracker.get_selected().items():
            self._add_item(username, user_id, recalculate=False)
            item = self.user_items[-1]
            if self.user_tracker.is_frozen(user_id=user_id):
                item.set_frozen(True)

        if self.user_items:
            QTimer.singleShot(50, self.recalculate_layout)

    def _add_item(self, username="", user_id="", recalculate=True):
        item = TrackedUserItem(self.config, self.icons_path, username, user_id)
        item.parent_widget = self
        item.remove_requested.connect(self._remove_item)
        self.user_items.append(item)
        if recalculate:
            self.recalculate_layout()

    def _add_new_item(self):
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

    def save_selected(self):
        self.user_tracker.clear_selected()
        for item in self.user_items:
            username, user_id = item.get_data()
            if username and user_id and item.username_valid:
                self.user_tracker.add_selected(user_id, username)
        self.tracked_users_changed.emit()

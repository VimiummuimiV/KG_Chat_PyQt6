"""UserTrackerWidget: history filters and filter chips."""

from collections import Counter

from PyQt6.QtWidgets import QMessageBox

from components.presence_badge import toggle_filter_value
from helpers.translate import tr


class TrackerFiltersMixin:
    """UserTrackerWidget: history filters and filter chips."""

    def _update_filter_panel_visibility(self):
        self.filter_panel.setVisible(self.userlist_visible and bool(self.chip_widgets))

    def _toggle_filter_set(self, attr: str, value: str, ctrl_pressed: bool, on_changed=None):
        if not value:
            return
        setattr(self, attr, toggle_filter_value(getattr(self, attr), value, ctrl_pressed))
        if on_changed:
            on_changed()
        self._update_filter_button()
        self._apply_event_filter()

    def _handle_filter_click(self, login: str, ctrl_pressed: bool):
        self._toggle_filter_set('filtered_logins', login, ctrl_pressed, self._update_chip_highlights)

    def _handle_type_filter_click(self, event_type: str, ctrl_pressed: bool):
        self._toggle_filter_set(
            'filtered_types', event_type, ctrl_pressed,
            lambda: self.type_filter_bar.set_active_types(self.filtered_types)
        )

    def _handle_date_filter_click(self, date_str: str, ctrl_pressed: bool):
        self._toggle_filter_set('filtered_dates', date_str, ctrl_pressed)

    def _on_type_filter_changed(self, types):
        self.filtered_types = set(types)
        self._update_filter_button()
        self._apply_event_filter()

    def _clear_filter(self):
        self.filtered_logins.clear()
        self.filtered_types.clear()
        self.filtered_dates.clear()
        self.type_filter_bar.set_active_types(())
        self._update_filter_button()
        self._apply_event_filter()
        self._update_chip_highlights()

    def _filter_description(self) -> str:
        parts = []
        if self.filtered_dates:
            parts.append(", ".join(sorted(self.filtered_dates)))
        if self.filtered_logins:
            parts.append(", ".join(sorted(self.filtered_logins)))
        if self.filtered_types:
            parts.append("/".join(t.upper() for t in sorted(self.filtered_types)))
        return " · ".join(parts)

    def _has_active_filters(self) -> bool:
        return bool(self.filtered_logins) or bool(self.filtered_types) or bool(self.filtered_dates)

    def _update_filter_button(self):
        active = self._has_active_filters()
        on_history = self.tabs.currentIndex() == 1
        self.clear_filter_button.setVisible(on_history and active)
        self.clear_filter_button.setToolTip(
            tr(f"Clear filter: {self._filter_description()}", f"Сбросить фильтр: {self._filter_description()}")
            if active else tr("Clear history filter", "Сбросить фильтр истории")
        )

    def _apply_event_filter(self):
        self.history_proxy.set_filters(self.filtered_logins, self.filtered_types, self.filtered_dates)
        self.history_delegate.clear_click_rects()
        self._update_history_empty_state()
        self._update_info_label()

    def _update_chip_highlights(self):
        for login, chip in self.chip_widgets.items():
            chip.set_filtered(login in self.filtered_logins)

    def _rebuild_filter_chips(self):
        while self.filter_chips_layout.count() > 1:
            item = self.filter_chips_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.chip_widgets = {}

        events = self.user_tracker.get_events()
        counts = Counter(e.get('login') for e in events if e.get('login'))
        user_ids = {}
        for e in events:
            login = e.get('login')
            if login and login not in user_ids and e.get('user_id'):
                user_ids[login] = e['user_id']

        for login, count in sorted(counts.items(), key=lambda x: (-x[1], x[0].lower())):
            chip = self._make_chip(login, count, user_ids.get(login))
            self.filter_chips_layout.insertWidget(self.filter_chips_layout.count() - 1, chip)
        self._update_filter_panel_visibility()

    def _handle_chip_delete_requested(self, login: str):
        reply = QMessageBox.question(
            self, tr("Remove History", "Удалить историю"),
            tr(f"Remove all history for {login}?", f"Удалить всю историю пользователя {login}?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.user_tracker.remove_user_events(login)
        self.filtered_logins.discard(login)
        self._update_filter_button()
        self._remove_login_from_view(login)

"""UserTrackerWidget: history list updates and info label."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QMessageBox

from helpers.scroll.scroll import scroll
from helpers.translate import tr


class TrackerHistoryMixin:
    """UserTrackerWidget: history list updates and info label."""

    def update_history_empty_state(self):
        self.history_stack.setCurrentIndex(1 if self.history_proxy.rowCount() == 0 else 0)

    def _scroll_history_to_bottom(self):
        scroll(self.history_list_view, mode="bottom", delay=10)

    def update_info_label(self):
        total = sum(
            1 for e in self.history_model.get_events() if not e.get('is_separator')
        )
        if total == 0:
            self.info_label.setText(tr("No events", "Нет событий"))
            return
        shown = 0
        for row in range(self.history_proxy.rowCount()):
            event = self.history_proxy.data(
                self.history_proxy.index(row, 0), Qt.ItemDataRole.DisplayRole
            )
            if event and not event.get('is_separator'):
                shown += 1
        desc = self.filter_description()
        if desc:
            self.info_label.setText(tr(
                f"Showing {shown}/{total} events ({desc})",
                f"Показано {shown}/{total} событий ({desc})"
            ))
        else:
            self.info_label.setText(tr(f"{total} events", f"{total} событий"))

    def rebuild_events(self):
        events = self.user_tracker.get_events()
        self.history_model.set_events(events)
        self.history_delegate.clear_click_rects()
        self.apply_event_filter()
        if events:
            QTimer.singleShot(0, self._scroll_history_to_bottom)
        self.rebuild_filter_chips()
        self.update_info_label()

    def remove_login_from_view(self, login: str):
        self.history_model.remove_login(login)
        self.history_delegate.clear_click_rects()
        self.update_history_empty_state()

        chip = self.chip_widgets.pop(login, None)
        if chip is not None:
            self.filter_chips_layout.removeWidget(chip)
            chip.deleteLater()
        self.update_filter_panel_visibility()
        self.update_info_label()

    def append_event(self, event: dict):
        sb = self.history_list_view.verticalScrollBar()
        at_bottom = (sb.maximum() - sb.value()) <= 100
        self.history_model.append_event(event)
        self.update_history_empty_state()
        if at_bottom:
            QTimer.singleShot(0, lambda: scroll(self.history_list_view, mode="bottom", delay=50))
        self._bump_chip_count(event)
        self.update_info_label()

    def _bump_chip_count(self, event: dict):
        login = event.get('login')
        if not login:
            return
        chip = self.chip_widgets.get(login)
        if chip is not None:
            chip.count_label.setText(str(int(chip.count_label.text()) + 1))
            return
        chip = self.make_chip(login, 1, event.get('user_id') or None)
        self.filter_chips_layout.insertWidget(0, chip)
        self.update_filter_panel_visibility()

    def clear_history(self):
        if not self.user_tracker.get_events():
            return
        reply = QMessageBox.question(
            self, tr("Clear History", "Очистить историю"),
                  tr("Clear all join/left history?", "Очистить всю историю входов/выходов?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.user_tracker.clear_events()
            self.rebuild_events()

    def reveal_event(self, login: str, event_ts: float = None):
        self.tabs.setCurrentIndex(1)
        if self.has_active_filters():
            self.clear_filter()

        source_row = self.history_model.find_row(login, event_ts)
        if source_row is None:
            return
        proxy_index = self.history_proxy.mapFromSource(self.history_model.index(source_row, 0))
        if not proxy_index.isValid():
            return
        row = proxy_index.row()

        scroll(self.history_list_view, mode="middle", target_row=row, delay=100)
        QTimer.singleShot(250, lambda: self.history_delegate.highlight_row(row))

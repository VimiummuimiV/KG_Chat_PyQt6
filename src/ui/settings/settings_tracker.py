"""SettingsWidget: user tracker options and retention."""

from PyQt6.QtWidgets import QHBoxLayout, QLabel

from components.badge import EVENT_TYPES, TypeFilterBar
from helpers.translate import tr
from ui.settings.settings_options import (
    DEFAULTS,
    fill_tracker_click_combo,
    fill_tracker_default_tab_combo,
)
from ui.settings.settings_widgets import NoWheelComboBox


class SettingsTrackerMixin:
    """SettingsWidget: user tracker options and retention."""

    def build_user_tracker_section(self):
        section = self.create_section(tr("🗿 User Tracker", "🗿 Трекер пользователей"))
        self.tracker_enabled_checkbox = self.add_checkbox(
            section, tr("Track users", "Отслеживать пользователей"),
            self._on_tracker_enabled_toggled
        )
        self.tracker_notifications_checkbox = self.add_checkbox(
            section, tr("Show events in notifications", "Показывать события в уведомлениях"),
            self._on_tracker_notifications_toggled
        )
        self.tracker_presence_log_checkbox = self.add_checkbox(
            section, tr("Show events in chat", "Показывать события в чате"),
            self._on_tracker_presence_log_toggled
        )
        self.tracker_presence_log_split_spin = self.add_slider_spin_row(
            section, tr("Presence pane height (%)", "Высота панели событий (%)"),
            DEFAULTS["user_tracker"]["presence_log_split_percent_min"],
            DEFAULTS["user_tracker"]["presence_log_split_percent_max"],
            self._on_tracker_presence_log_split_changed,
            default=DEFAULTS["user_tracker"]["presence_log_split_percent"],
        )
        self.tracker_badge_checkbox = self.add_checkbox(
            section, tr("Show count badge on tracker button", "Показывать счётчик на кнопке трекера"),
            self._on_tracker_badge_toggled
        )
        self.tracker_userlist_star_checkbox = self.add_checkbox(
            section, tr("Show star badge on tracked users in userlist", "Показывать звезду у отслеживаемых в списке пользователей"),
            self._on_tracker_userlist_star_toggled
        )
        # Tracked event types — same pills as tracker filter bar
        events_row = QHBoxLayout()
        events_row.setSpacing(8)
        events_label_text = tr("Track events:", "Отслеживаемые события:")
        events_label = QLabel(events_label_text)
        events_row.addWidget(events_label)
        self.register_tr(events_label.setText, events_label_text)
        theme = self.config.get("ui", "theme") or "dark"
        self.tracker_events_bar = TypeFilterBar(empty_means_all=False, is_dark=(theme == "dark"))
        self.tracker_events_bar.changed.connect(self._on_tracker_events_changed)
        events_row.addWidget(self.tracker_events_bar, stretch=1)
        section.addLayout(events_row)
        self._build_tracker_retention_row(section)
        self.tracker_default_tab_combo = self.add_combo_row(
            section, tr("Default tab on open", "Вкладка по умолчанию"), [], self._on_tracker_default_tab_changed
        )
        self.tracker_click_combo = self.add_combo_row(
            section, tr("On notification click", "При клике по уведомлению"), [], self._on_tracker_click_action_changed
        )

    def refresh_tracker(self):
        self.tracker_enabled_checkbox.setChecked(
            bool(self.config.get("user_tracker", "enabled")
                 if self.config.get("user_tracker", "enabled") is not None else True)
        )
        tracker_notify = self.config.get("user_tracker", "notifications")
        self.tracker_notifications_checkbox.setChecked(
            True if tracker_notify is None else bool(tracker_notify)
        )
        presence_log = self.config.get("user_tracker", "presence_log")
        self.tracker_presence_log_checkbox.setChecked(True if presence_log is None else bool(presence_log))
        split_percent = self.config.get("user_tracker", "presence_log_split_percent")
        split_value = (
            DEFAULTS["user_tracker"]["presence_log_split_percent"]
            if split_percent is None else int(split_percent)
        )
        self.tracker_presence_log_split_spin.blockSignals(True)
        self.tracker_presence_log_split_spin.setValue(split_value)
        self.tracker_presence_log_split_spin.blockSignals(False)
        self.tracker_presence_log_split_spin.linked_slider.blockSignals(True)
        self.tracker_presence_log_split_spin.linked_slider.setValue(split_value)
        self.tracker_presence_log_split_spin.linked_slider.blockSignals(False)
        update_reset = getattr(self.tracker_presence_log_split_spin, "update_reset_state", None)
        if update_reset is not None:
            update_reset(split_value)

        tracker_badge = self.config.get("user_tracker", "show_unread_badge")
        self.tracker_badge_checkbox.setChecked(
            True if tracker_badge is None else bool(tracker_badge)
        )
        star_badge = self.config.get("user_tracker", "show_star_badge")
        self.tracker_userlist_star_checkbox.setChecked(bool(star_badge))
        track_events = self.config.get("user_tracker", "track_events")
        if not track_events:
            track_events = list(EVENT_TYPES)
        self.tracker_events_bar.set_active_types(track_events)
        self._sync_tracker_retention_ui_from_config()
        fill_tracker_default_tab_combo(self.tracker_default_tab_combo, self.config.get("user_tracker", "default_tab"))

        fill_tracker_click_combo(self.tracker_click_combo, self.config.get("user_tracker", "click_action"))

    def _on_tracker_enabled_toggled(self, checked: bool):
        self.config.set("user_tracker", "enabled", value=checked)
        self.tracker_badge_style_changed.emit()
        self.tracker_enabled_changed.emit(checked)

    def _on_tracker_notifications_toggled(self, checked: bool):
        self.config.set("user_tracker", "notifications", value=checked)

    def _on_tracker_presence_log_toggled(self, checked: bool):
        self.config.set("user_tracker", "presence_log", value=checked)
        self.tracker_presence_log_changed.emit(checked)

    def _on_tracker_presence_log_split_changed(self, value: int):
        self.config.set("user_tracker", "presence_log_split_percent", value=int(value))
        self.tracker_presence_log_split_changed.emit(int(value))

    def _on_tracker_badge_toggled(self, checked: bool):
        self.config.set("user_tracker", "show_unread_badge", value=checked)
        self.tracker_badge_style_changed.emit()

    def _on_tracker_userlist_star_toggled(self, checked: bool):
        self.config.set("user_tracker", "show_star_badge", value=checked)
        self.tracker_userlist_star_changed.emit(checked)

    def _on_tracker_events_changed(self, types):
        # Keep at least one type enabled
        active = list(types) if types else list(EVENT_TYPES)
        if not types:
            self.tracker_events_bar.set_active_types(EVENT_TYPES)
            active = list(EVENT_TYPES)
        self.config.set("user_tracker", "track_events", value=active)

    def _build_tracker_retention_row(self, section_layout):
        self._tracker_retention_spin = self.add_slider_spin_row(
            section_layout, tr("History retention", "Хранить историю"), 1, 168,
            self._on_tracker_retention_value_changed,
            on_reset=self._on_tracker_retention_reset,
            default=24,
        )
        row = section_layout.itemAt(section_layout.count() - 1).widget().layout()
        self.tracker_retention_unit_combo = NoWheelComboBox()
        self.tracker_retention_unit_combo.addItem(tr("hours", "часов"), "hours")
        self.tracker_retention_unit_combo.addItem(tr("days", "дней"), "days")
        self.tracker_retention_unit_combo.setFixedWidth(90)
        self.tracker_retention_unit_combo.currentIndexChanged.connect(
            self._on_tracker_retention_unit_changed
        )
        # Insert unit selector before the reset button (last widget in the row)
        row.insertWidget(row.count() - 1, self.tracker_retention_unit_combo)

    def _tracker_retention_unit(self) -> str:
        return self.tracker_retention_unit_combo.currentData() or "hours"

    def _set_tracker_retention_range(self, unit: str):
        maximum = 30 if unit == "days" else 168
        self._set_retention_widgets_blocked(True)
        self._tracker_retention_spin.linked_slider.setRange(1, maximum)
        self._tracker_retention_spin.setRange(1, maximum)
        self._set_retention_widgets_blocked(False)

    def _set_tracker_retention_display(self, value: int):
        self._set_retention_widgets_blocked(True)
        self._tracker_retention_spin.linked_slider.setValue(value)
        self._tracker_retention_spin.setValue(value)
        self._set_retention_widgets_blocked(False)
        button = getattr(self._tracker_retention_spin, "_reset_button", None)
        if button is not None:
            button.setEnabled(self._tracker_retention_unit() != "hours" or value != 24)

    def _set_retention_widgets_blocked(self, blocked: bool):
        self._tracker_retention_spin.linked_slider.blockSignals(blocked)
        self._tracker_retention_spin.blockSignals(blocked)

    def _read_retention_hours(self) -> int:
        hours = self.config.get("user_tracker", "retention_hours")
        try:
            hours = int(hours) if hours is not None else 24
        except (TypeError, ValueError):
            hours = 24
        return max(1, min(720, hours))

    def _hours_to_display(self, hours: int, unit: str) -> int:
        if unit == "days":
            return max(1, min(30, round(hours / 24) or 1))
        return max(1, min(168, hours))

    def _sync_tracker_retention_ui_from_config(self):
        hours = self._read_retention_hours()
        unit = self.config.get("user_tracker", "retention_unit") or "hours"
        if unit not in ("hours", "days"):
            unit = "hours"

        self.tracker_retention_unit_combo.blockSignals(True)
        index = self.tracker_retention_unit_combo.findData(unit)
        self.tracker_retention_unit_combo.setCurrentIndex(index if index >= 0 else 0)
        self.tracker_retention_unit_combo.blockSignals(False)

        self._set_tracker_retention_range(unit)
        self._set_tracker_retention_display(self._hours_to_display(hours, unit))

    def _on_tracker_retention_value_changed(self, value: int):
        unit = self._tracker_retention_unit()
        hours = value * 24 if unit == "days" else value
        self.config.set("user_tracker", "retention_hours", value=max(1, min(720, hours)))
        self.config.set("user_tracker", "retention_unit", value=unit)

    def _on_tracker_retention_unit_changed(self, _index: int = 0):
        unit = self._tracker_retention_unit()
        hours = self._read_retention_hours()

        self._set_tracker_retention_range(unit)
        display = self._hours_to_display(hours, unit)
        self._set_tracker_retention_display(display)
        self._on_tracker_retention_value_changed(display)

    def _on_tracker_retention_reset(self):
        self.tracker_retention_unit_combo.blockSignals(True)
        self.tracker_retention_unit_combo.setCurrentIndex(
            self.tracker_retention_unit_combo.findData("hours")
        )
        self.tracker_retention_unit_combo.blockSignals(False)
        self._set_tracker_retention_range("hours")
        self._set_tracker_retention_display(24)
        self._on_tracker_retention_value_changed(24)

    def _on_tracker_default_tab_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.tracker_default_tab_combo)
        value = self.tracker_default_tab_combo.currentData() or "tracked"
        self.config.set("user_tracker", "default_tab", value=value)

    def _on_tracker_click_action_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.tracker_click_combo)
        value = self.tracker_click_combo.currentData() or "history"
        self.config.set("user_tracker", "click_action", value=value)

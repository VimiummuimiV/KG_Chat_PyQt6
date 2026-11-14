"""SettingsWidget: competition tracking options and status log."""

import re
from html import escape

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTextEdit

from components.button import create_icon_button
from components.toast import copy_text_with_toast
from helpers.colors.color_utils import blend_hex_colors
from helpers.translate import tr
from ui.settings.settings_options import (
    COMPETITIONS_LOG_COLORS,
    CONNECTION_STATES,
    DEFAULTS,
    fill_alert_chat_action_combo,
    fill_competition_notification_style_combo,
)


class SettingsCompetitionsMixin:
    """SettingsWidget: competition tracking options and status log."""

    def build_competitions_section(self):
        section = self.create_section(tr("🏆 Competitions", "🏆 Соревнования"))

        self.track_competitions_checkbox = self.add_checkbox(
            section, tr("Track rating competitions", "Отслеживать рейтинговые соревнования"), self._on_track_competitions_toggled
        )

        self._remove_on_enter_checkbox = self.add_checkbox(
            section,
            tr("Remove message and notification on entering competition", "Удалять сообщение и уведомление при входе в соревнование"),
            self._on_remove_on_enter_toggled,
        )

        log_header, log_content, log_layout = self.add_subsection(section, tr("📜 WebSocket Log", "📜 Лог WebSocket"))

        copy_log_tooltip = tr("Copy log", "Скопировать лог")
        self._copy_log_button = create_icon_button(
            self.icons_path, "fill/file-copy-fill.svg", copy_log_tooltip, size_type="small", config=self.config
        )
        self._copy_log_button.clicked.connect(self._on_copy_log_clicked)
        log_header.addWidget(self._copy_log_button)
        self.register_tr(self._copy_log_button.setToolTip, copy_log_tooltip)

        clear_log_tooltip = tr("Clear log", "Очистить лог")
        self._clear_log_button = create_icon_button(
            self.icons_path, "fill/delete-bin-fill.svg", clear_log_tooltip, size_type="small", config=self.config
        )
        self._clear_log_button.clicked.connect(self._on_clear_log_clicked)
        log_header.addWidget(self._clear_log_button)
        self.register_tr(self._clear_log_button.setToolTip, clear_log_tooltip)

        self.competitions_log = QTextEdit()
        self.competitions_log.setReadOnly(True)
        self.competitions_log.setFixedHeight(DEFAULTS["competitions"]["log_height"])
        log_placeholder = tr("Competition log", "Лог соревнований")
        self.competitions_log.setPlaceholderText(log_placeholder)
        self.register_tr(self.competitions_log.setPlaceholderText, log_placeholder)
        self.competitions_log.setAcceptRichText(True)
        self.apply_competitions_log_theme()
        log_layout.addWidget(self.competitions_log)

        self.add_collapse_toggle(log_header, log_content, ("ui", "settings", "widgets", "ws_log"))

        self.min_multiplier_combo = self.add_combo_row(
            section, tr("Minimum multiplier", "Минимальный множитель"), ["x1+", "x2+", "x3+", "x5+"],
            self._on_min_multiplier_changed
        )

        self.show_cost_checkbox = self.add_checkbox(
            section, tr("Show competition cost", "Показывать стоимость соревнования"), self._on_show_cost_toggled
        )

        self.show_scores_checkbox = self.add_checkbox(
            section, tr("Show scores balance", "Показывать остаток очков"), self._on_show_scores_toggled
        )

        self.show_bonuses_checkbox = self.add_checkbox(
            section, tr("Show bonuses balance", "Показывать остаток бонусов"), self._on_show_bonuses_toggled
        )

        self.show_players_checkbox = self.add_checkbox(
            section, tr("Show player usernames", "Показывать имена игроков"), self._on_show_players_toggled
        )
        self.max_player_chips_spin = self.add_slider_spin_row(
            section, tr("Max player usernames", "Макс. число имён"), 1, 100,
            self._on_max_player_chips_changed,
            default=DEFAULTS["competitions"]["max_player_chips"],
        )
        self.sort_players_by_level_checkbox = self.add_checkbox(
            section, tr("Sort player usernames by rank", "Сортировать имена игроков по рангу"), self._on_sort_players_by_level_toggled
        )

        self.competitions_alert_lead_spin = self.add_slider_spin_row(
            section, tr("Alert lead time before start (sec)", "Время оповещения до старта (сек)"), 0, 300,
            self._on_competitions_alert_lead_changed,
            default=DEFAULTS["competitions"]["alert_lead"],
        )

        self.alert_chat_action_combo = self.add_combo_row(
            section, tr("On alert in chat", "При оповещении в чате"), [], self._on_alert_chat_action_changed
        )

        self.competition_notification_style_combo = self.add_combo_row(
            section, tr("Competition notification style", "Стиль уведомления о соревновании"), [],
            self._on_competition_notification_style_changed
        )

        self.competitions_notify_window_checkbox = self.add_checkbox(
            section, tr("Only alert during allowed hours", "Оповещать только в разрешённые часы"), self._on_competitions_notify_window_toggled
        )
        self.competitions_notify_start_spin = self.add_slider_spin_row(
            section, tr("From", "С"), 0, 24, self._on_competitions_notify_start_changed,
            default=DEFAULTS["competitions"]["notify_start"],
        )
        self.competitions_notify_end_spin = self.add_slider_spin_row(
            section, tr("To", "До"), 0, 24, self._on_competitions_notify_end_changed,
            default=DEFAULTS["competitions"]["notify_end"],
        )

    def refresh_competitions_enabled(self):
        track = self.config.get("competitions", "enabled")
        enabled = True if track is None else bool(track)
        self.track_competitions_checkbox.setChecked(enabled)
        self.update_competitions_status(enabled, None if not enabled else "connecting")

    def refresh_competitions(self):
        min_m = self.config.get("competitions", "min_multiplier") or "x1+"
        index = self.min_multiplier_combo.findText(min_m)
        self.min_multiplier_combo.setCurrentIndex(index if index >= 0 else 0)

        self._remove_on_enter_checkbox.setChecked(bool(self.config.get("competitions", "remove_message_on_enter")))

        show_cost = self.config.get("competitions", "show_cost")
        self.show_cost_checkbox.setChecked(True if show_cost is None else bool(show_cost))

        show_scores = self.config.get("competitions", "show_scores")
        self.show_scores_checkbox.setChecked(True if show_scores is None else bool(show_scores))

        show_bonuses = self.config.get("competitions", "show_bonuses")
        self.show_bonuses_checkbox.setChecked(True if show_bonuses is None else bool(show_bonuses))

        show_players = self.config.get("competitions", "show_players")
        self.show_players_checkbox.setChecked(True if show_players is None else bool(show_players))
        self.max_player_chips_spin.setValue(int(self.config.get("competitions", "max_player_chips") or DEFAULTS["competitions"]["max_player_chips"]))
        self.max_player_chips_spin.linked_slider.setValue(self.max_player_chips_spin.value())
        self.sort_players_by_level_checkbox.setChecked(bool(self.config.get("competitions", "sort_players_by_level")))
        self._set_players_controls_enabled(self.show_players_checkbox.isChecked())

        self.competitions_alert_lead_spin.setValue(int(self.config.get("competitions", "alert_lead_seconds") or DEFAULTS["competitions"]["alert_lead"]))
        self.competitions_alert_lead_spin.linked_slider.setValue(self.competitions_alert_lead_spin.value())

        fill_alert_chat_action_combo(self.alert_chat_action_combo, self.config.get("competitions", "alert_chat_action"))

        fill_competition_notification_style_combo(
            self.competition_notification_style_combo, self.config.get("competitions", "notification_style")
        )

        self.competitions_notify_window_checkbox.setChecked(
            bool(self.config.get("competitions", "notify_window_enabled"))
        )
        self.competitions_notify_start_spin.setValue(int(self.config.get("competitions", "notify_window_start") or DEFAULTS["competitions"]["notify_start"]))
        self.competitions_notify_start_spin.linked_slider.setValue(self.competitions_notify_start_spin.value())
        self.competitions_notify_end_spin.setValue(int(self.config.get("competitions", "notify_window_end") or DEFAULTS["competitions"]["notify_end"]))
        self.competitions_notify_end_spin.linked_slider.setValue(self.competitions_notify_end_spin.value())
        self._set_notify_window_controls_enabled(self.competitions_notify_window_checkbox.isChecked())

    def _on_track_competitions_toggled(self, checked: bool):
        self.config.set("competitions", "enabled", value=checked)
        self.update_competitions_status(checked)

    def tracking_disabled_text(self) -> str:
        return tr("Tracking disabled", "Отслеживание выключено")

    def _tracking_enabled_text(self) -> str:
        return tr("Tracking enabled", "Отслеживание включено")

    def _status_log_html(self, text: str, kind: str) -> str:
        c = self._competitions_log_colors()
        color = {
            "disabled": c["error"],
            "enabled": c["finished"],
        }.get(kind, c["default"])
        return f'<span style="color:{color}"><b>{text}</b></span>'

    def collapsed_log_height(self) -> int:
        return max(DEFAULTS["competitions"]["log_height_collapsed"], self.competitions_log.fontMetrics().height() + 16)

    def update_competitions_status(self, enabled: bool, connection: str | None = None):
        """connection: connecting | connected | disconnected (optional).
        Log text is owned by ChatWindow buffer — do not clear it here when enabled.
        """
        if not enabled:
            self.competitions_accent_color = self._competitions_log_colors()["error"]
            self.apply_competitions_log_theme()
            self.competitions_log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.competitions_log.setEnabled(False)
            self.competitions_log.setFixedHeight(self.collapsed_log_height())
            self.competitions_log.setHtml(self._status_log_html(self.tracking_disabled_text(), "disabled"))
            return

        self.competitions_log.setEnabled(True)
        self.competitions_log.setFixedHeight(DEFAULTS["competitions"]["log_height"])
        plain = self.competitions_log.toPlainText().strip()
        if plain in ("", self.tracking_disabled_text()):
            self.competitions_log.setHtml(self._status_log_html(self._tracking_enabled_text(), "enabled"))

        state = connection or "connecting"
        self.competitions_accent_color = CONNECTION_STATES.get(
            state, CONNECTION_STATES["reconnecting"]
        )
        self.apply_competitions_log_theme()
        self.competitions_log.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if state == "disconnected"
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

    def _competitions_log_colors(self) -> dict:
        theme = self.config.get("ui", "theme") or "dark"
        return COMPETITIONS_LOG_COLORS["dark" if theme == "dark" else "light"]

    def apply_competitions_log_theme(self):
        c = self._competitions_log_colors()
        accent = self.competitions_accent_color or c["default"]
        is_dark = (self.config.get("ui", "theme") or "dark") == "dark"
        container_background = "#000000" if is_dark else "#FFFFFF"
        mix_ratio = 0.10 if is_dark else 0.30
        mixed_background = blend_hex_colors(container_background, accent, mix_ratio)
        self.competitions_log.setStyleSheet(
            f"QTextEdit {{ background-color: {mixed_background}; color: {c['fg']}; border: none; padding: 6px 8px; }}"
        )

    def _colorize_log_line(self, line: str) -> str:
        c = self._competitions_log_colors()
        low = line.lower()
        if "[ws]" in low or "  ws " in f"  {low}":
            color = c["ws"]
        elif "waiting" in low:
            color = c["waiting"]
        elif "paused" in low:
            color = c["paused"]
        elif "racing" in low:
            color = c["racing"]
        elif "finished" in low:
            color = c["finished"]
        elif "error" in low or "disconnect" in low:
            color = c["error"]
        else:
            color = c["default"]

        def _bold_tag(m):
            return f"{m.group(1)}<b>{escape(m.group(2))}</b>{m.group(3)}"

        html_line = escape(line)
        html_line = re.sub(
            r"^(\d{2}:\d{2}:\d{2}\s+)(\[?\w+\+?]?)(\s+)",
            _bold_tag,
            html_line,
            count=1,
        )
        return f'<span style="color:{color}">{html_line}</span>'

    def set_competition_log_lines(self, lines: list):
        """Replace log content from chat session buffer (HTML colored)."""
        self.apply_competitions_log_theme()
        if not lines:
            self.competitions_log.clear()
            return
        html = "<br>".join(self._colorize_log_line(x) for x in lines)
        self.competitions_log.setHtml(html)
        cursor = self.competitions_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.competitions_log.setTextCursor(cursor)

    def append_competition_log(self, line: str):
        """Called from chat when a competition event is logged."""
        if not self.track_competitions_checkbox.isChecked():
            return
        cursor = self.competitions_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if self.competitions_log.toPlainText():
            cursor.insertHtml("<br>" + self._colorize_log_line(line))
        else:
            cursor.insertHtml(self._colorize_log_line(line))
        self.competitions_log.setTextCursor(cursor)
        if self.competitions_log.document().blockCount() > 200:
            lines = self.competitions_log.toPlainText().splitlines()[-200:]
            self.set_competition_log_lines(lines)

    def _on_copy_log_clicked(self):
        copy_text_with_toast(self, self.competitions_log.toPlainText(), tr("Log copied", "Лог скопирован"))

    def _on_clear_log_clicked(self):
        self.competitions_log.clear()
        self.competition_log_clear_requested.emit()

    def _on_min_multiplier_changed(self, text: str):
        self.config.set("competitions", "min_multiplier", value=text)

    def _on_remove_on_enter_toggled(self, checked: bool):
        self.config.set("competitions", "remove_message_on_enter", value=checked)

    def _set_players_controls_enabled(self, enabled: bool):
        self.set_spin_enabled(self.max_player_chips_spin, enabled)
        self.sort_players_by_level_checkbox.setEnabled(enabled)

    def _set_notify_window_controls_enabled(self, enabled: bool):
        self.set_spin_enabled(self.competitions_notify_start_spin, enabled)
        self.set_spin_enabled(self.competitions_notify_end_spin, enabled)

    def _on_show_cost_toggled(self, checked: bool):
        self.config.set("competitions", "show_cost", value=checked)

    def _on_show_scores_toggled(self, checked: bool):
        self.config.set("competitions", "show_scores", value=checked)

    def _on_show_bonuses_toggled(self, checked: bool):
        self.config.set("competitions", "show_bonuses", value=checked)

    def _on_show_players_toggled(self, checked: bool):
        self.config.set("competitions", "show_players", value=checked)
        self._set_players_controls_enabled(checked)

    def _on_max_player_chips_changed(self, value: int):
        self.config.set("competitions", "max_player_chips", value=value)

    def _on_sort_players_by_level_toggled(self, checked: bool):
        self.config.set("competitions", "sort_players_by_level", value=checked)

    def _on_competitions_alert_lead_changed(self, value: int):
        self.config.set("competitions", "alert_lead_seconds", value=value)

    def _on_alert_chat_action_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.alert_chat_action_combo)
        value = self.alert_chat_action_combo.currentData() or "scroll"
        self.config.set("competitions", "alert_chat_action", value=value)

    def _on_competition_notification_style_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.competition_notification_style_combo)
        value = self.competition_notification_style_combo.currentData() or "inline"
        self.config.set("competitions", "notification_style", value=value)
        self.update_center_offset_enabled()

    def _on_competitions_notify_window_toggled(self, checked: bool):
        self.config.set("competitions", "notify_window_enabled", value=checked)
        self._set_notify_window_controls_enabled(checked)

    def _on_competitions_notify_start_changed(self, value: int):
        self.config.set("competitions", "notify_window_start", value=value)

    def _on_competitions_notify_end_changed(self, value: int):
        self.config.set("competitions", "notify_window_end", value=value)

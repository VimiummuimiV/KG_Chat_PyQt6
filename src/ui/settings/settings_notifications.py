"""SettingsWidget: popup notification options and live preview."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit

from components.button import create_icon_button
from components.tag_button import SavedValuesBar
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import tr
from ui.notification.notification_settings import expanded_reply_width, resolve_notification_width
from ui.notification.popup_manager import popup_manager, show_notification
from ui.settings.settings_options import (
    DEFAULTS,
    fill_notification_hide_on_combo,
    fill_notification_mode_combo,
    fill_notification_mute_bypass_combo,
    fill_notification_position_combo,
    fill_reply_style_combo,
)


class SettingsNotificationsMixin:
    """SettingsWidget: popup notification options and live preview."""

    def build_notifications_section(self):
        section = self.create_section(tr("🔔 Notifications", "🔔 Уведомления"))
        self.notification_mode_combo = self.add_combo_row(
            section, tr("Notification mode", "Режим уведомлений"), [], self._on_notification_mode_changed
        )
        self.notification_position_combo = self.add_combo_row(
            section, tr("Notification position", "Расположение уведомлений"), [],
            self._on_notification_position_changed
        )
        self.reply_style_combo = self.add_combo_row(
            section, tr("Reply style", "Стиль ответа"), [], self._on_reply_style_changed
        )
        self.notification_margin_x_spin = self.add_slider_spin_row(
            section,
            tr("Notification side margin (X)", "Отступ уведомлений по X"),
            0, 300,
            self._on_notification_margin_x_changed,
            default=DEFAULTS["notification"]["margin_x"],
        )
        self.notification_margin_top_spin = self.add_slider_spin_row(
            section,
            tr("Notification top margin (Y)", "Отступ уведомлений сверху (Y)"),
            0, 300,
            self._on_notification_margin_top_changed,
            default=DEFAULTS["notification"]["margin_top"],
        )
        self.reply_center_offset_spin = self.add_slider_spin_row(
            section,
            tr("Reply vertical offset", "Смещение ответа по Y"),
            -400, 400,
            self._on_reply_center_offset_changed,
            default=DEFAULTS["notification"]["reply_center_offset_y"],
        )
        self.notification_width_spin = self.add_slider_spin_row(
            section, tr("Notification width", "Ширина уведомления"), DEFAULTS["notification"]["width"], 1000, self._on_notification_width_changed,
            default=DEFAULTS["notification"]["width"],
        )
        self.reply_focus_expand_spin = self.add_slider_spin_row(
            section,
            tr("Reply field expand width", "Расширение поля ответа"),
            0, 600,
            self._on_reply_focus_expand_changed,
            default=DEFAULTS["notification"]["reply_focus_expand_width"],
        )
        self.notification_hide_on_combo = self.add_combo_row(
            section, tr("Hide notifications on", "Скрывать уведомления по"), [], self._on_notification_hide_on_changed
        )
        self.notification_duration_spin = self.add_slider_spin_row(
            section,
            tr("Auto-hide delay (sec)", "Задержка автоскрытия (сек)"),
            1, 60,
            self._on_notification_duration_changed,
            default=DEFAULTS["notification"]["duration"],
        )
        self.notification_fade_spin = self.add_slider_spin_row(
            section,
            tr("Fade duration (ms)", "Длительность затухания (мс)"),
            50, 2000,
            self._on_notification_fade_changed,
            default=DEFAULTS["notification"]["fade_ms"],
        )

        bypass_header, bypass_content, bypass_layout = self.add_subsection(section, tr("🚧 Bypass When Muted", "🚧 Показ при отключении уведомлений"))
        self.competitions_bypass_combo = self.add_combo_row(
            bypass_layout, tr("Competitions", "Соревнования"), [],
            lambda _t: self._on_mute_bypass_changed(self.competitions_bypass_combo, "competitions_bypass_mute"),
        )
        self.mentions_bypass_combo = self.add_combo_row(
            bypass_layout, tr("Mentions & private messages", "Упоминания и приватные сообщения"), [],
            lambda _t: self._on_mute_bypass_changed(self.mentions_bypass_combo, "mentions_bypass_mute"),
        )
        self.bans_bypass_combo = self.add_combo_row(
            bypass_layout, tr("Bans", "Баны"), [],
            lambda _t: self._on_mute_bypass_changed(self.bans_bypass_combo, "bans_bypass_mute"),
        )
        self.tracker_bypass_combo = self.add_combo_row(
            bypass_layout, tr("Tracked users", "Отслеживаемые пользователи"), [],
            lambda _t: self._on_mute_bypass_changed(self.tracker_bypass_combo, "tracked_bypass_mute"),
        )
        self.messages_bypass_combo = self.add_combo_row(
            bypass_layout, tr("Regular messages", "Обычные сообщения"), [],
            lambda _t: self._on_mute_bypass_changed(self.messages_bypass_combo, "messages_bypass_mute"),
        )
        self.add_collapse_toggle(bypass_header, bypass_content, ("ui", "settings", "widgets", "notifications_bypass"))

        if self.my_username:
            local_header, local_content, local_layout = self.add_subsection(
                section, tr("🏷️ Local aliases (this account)", "🏷️ Локальные алиасы (этот аккаунт)")
            )
            self.add_alias_block(
                local_layout,
                lambda: self.mention_aliases.local_aliases(self.my_username),
                lambda values: self.mention_aliases.set_local_aliases(self.my_username, values),
            )
            self.add_collapse_toggle(local_header, local_content, ("ui", "settings", "widgets", "aliases_local"))

        global_header, global_content, global_layout = self.add_subsection(
            section, tr("🌐 Global aliases (all accounts)", "🌐 Глобальные алиасы (все аккаунты)")
        )
        self.add_alias_block(global_layout, self.mention_aliases.global_aliases, self.mention_aliases.set_global_aliases)
        self.add_collapse_toggle(global_header, global_content, ("ui", "settings", "widgets", "aliases_global"))

    def add_alias_block(self, layout, load_values, save_values):
        """Input row plus draggable chips of extra words that trigger mention sound and popup."""
        hint_text = tr(
            "Words that notify like your nickname, comma-separated",
            "Слова, которые оповещают как ваш ник, через запятую",
        )
        hint = QLabel(hint_text)
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        self.register_tr(hint.setText, hint_text)
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(self.element_spacing())
        alias_input = QLineEdit()
        alias_input.setFont(get_font(FontType.UI))
        row.addWidget(alias_input, stretch=1)
        add_tooltip = tr("Add alias", "Добавить алиас")
        add_button = create_icon_button(self.icons_path, "line/add-large-line.svg", add_tooltip, size_type="small", config=self.config)
        add_button.setEnabled(False)
        self.register_tr(add_button.setToolTip, add_tooltip)
        row.addWidget(add_button)
        layout.addLayout(row)

        bar = SavedValuesBar(self.icons_path, load_values, save_values)
        layout.addWidget(bar)

        def add_aliases():
            bar.add_values([alias.strip() for alias in alias_input.text().split(",") if alias.strip()])
            alias_input.clear()

        alias_input.textChanged.connect(lambda text: add_button.setEnabled(bool(text.strip())))
        alias_input.returnPressed.connect(add_aliases)
        add_button.clicked.connect(add_aliases)

    def refresh_notification_bypass(self):
        fill_notification_mute_bypass_combo(
            self.competitions_bypass_combo, self.config.get("notification", "competitions_bypass_mute")
        )
        fill_notification_mute_bypass_combo(
            self.mentions_bypass_combo, self.config.get("notification", "mentions_bypass_mute")
        )
        fill_notification_mute_bypass_combo(
            self.bans_bypass_combo, self.config.get("notification", "bans_bypass_mute")
        )
        fill_notification_mute_bypass_combo(
            self.tracker_bypass_combo, self.config.get("notification", "tracked_bypass_mute")
        )
        fill_notification_mute_bypass_combo(
            self.messages_bypass_combo, self.config.get("notification", "messages_bypass_mute")
        )

    def refresh_notifications(self):
        fill_notification_mode_combo(self.notification_mode_combo, self.config.get("notification", "mode"))

        fill_notification_position_combo(self.notification_position_combo, self.config.get("ui", "notification_position"))
        fill_reply_style_combo(self.reply_style_combo, self.config.get("notification", "reply_style"))
        offset_y = self.config.get("notification", "reply_center_offset_y")
        try:
            offset_y = int(offset_y) if offset_y is not None else DEFAULTS["notification"]["reply_center_offset_y"]
        except (TypeError, ValueError):
            offset_y = DEFAULTS["notification"]["reply_center_offset_y"]
        self.reply_center_offset_spin.setValue(offset_y)
        self.reply_center_offset_spin.linked_slider.setValue(offset_y)
        self.update_center_offset_enabled()
        self.notification_width_spin.setValue(int(self.config.get("ui", "notification_width") or DEFAULTS["notification"]["width"]))
        self.notification_width_spin.linked_slider.setValue(self.notification_width_spin.value())
        self.reply_focus_expand_spin.setValue(int(self.config.get("notification", "reply_focus_expand_width") or DEFAULTS["notification"]["reply_focus_expand_width"]))
        self.reply_focus_expand_spin.linked_slider.setValue(self.reply_focus_expand_spin.value())
        self.notification_margin_x_spin.setValue(int(self.config.get("notification", "margin_x") or DEFAULTS["notification"]["margin_x"]))
        self.notification_margin_x_spin.linked_slider.setValue(self.notification_margin_x_spin.value())
        self.notification_margin_top_spin.setValue(int(self.config.get("notification", "margin_top") or DEFAULTS["notification"]["margin_top"]))
        self.notification_margin_top_spin.linked_slider.setValue(self.notification_margin_top_spin.value())

        fill_notification_hide_on_combo(self.notification_hide_on_combo, self.config.get("notification", "hide_on"))

        duration_ms = self.config.get("notification", "duration_ms")
        try:
            duration_ms = int(duration_ms) if duration_ms is not None else DEFAULTS["notification"]["duration"] * 1000
        except (TypeError, ValueError):
            duration_ms = DEFAULTS["notification"]["duration"] * 1000
        duration = max(1, round(duration_ms / 1000))
        self.notification_duration_spin.setValue(duration)
        self.notification_duration_spin.linked_slider.setValue(duration)
        fade_ms = self.config.get("notification", "fade_ms")
        try:
            fade_ms = int(fade_ms) if fade_ms is not None else DEFAULTS["notification"]["fade_ms"]
        except (TypeError, ValueError):
            fade_ms = DEFAULTS["notification"]["fade_ms"]
        fade_ms = max(50, min(2000, fade_ms))
        self.notification_fade_spin.setValue(fade_ms)
        self.notification_fade_spin.linked_slider.setValue(fade_ms)

    def _on_mute_bypass_changed(self, combo, config_key: str):
        self.sync_combo_tooltip(combo)
        value = combo.currentData() or "off"
        self.config.set("notification", config_key, value=value)

    def _on_notification_mode_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.notification_mode_combo)
        mode = self.notification_mode_combo.currentData() or "stack"
        self.config.set("notification", "mode", value=mode)
        popup_manager.set_notification_mode(mode)

    def _on_notification_position_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.notification_position_combo)
        value = self.notification_position_combo.currentData()
        if value is not None:
            self.config.set("ui", "notification_position", value=value)
        self.update_center_offset_enabled()
        self._refresh_notification_preview()

    def update_center_offset_enabled(self):
        """Offset only does anything when something is actually centered
        (reply or competition) and notifications aren't already centered
        (see _resolve_centered_style() in notification.py)."""
        reply_style = self.reply_style_combo.currentData() or "inline"
        competition_style = self.competition_notification_style_combo.currentData() or "inline"
        position = self.notification_position_combo.currentData() or "right"
        centered = reply_style == "center" or competition_style == "center"
        self.set_spin_enabled(self.reply_center_offset_spin, centered and position != "center")
        self.set_spin_enabled(self.notification_margin_x_spin, position != "center")

    def _on_reply_style_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.reply_style_combo)
        value = self.reply_style_combo.currentData() or "inline"
        self.config.set("notification", "reply_style", value=value)
        self.update_center_offset_enabled()
        self._refresh_notification_preview()

    def _on_reply_center_offset_changed(self, value: int):
        self.config.set("notification", "reply_center_offset_y", value=value)
        self._refresh_notification_preview()

    def _on_notification_width_changed(self, value: int):
        self.config.set("ui", "notification_width", value=value)
        self._refresh_notification_preview()

    def _on_reply_focus_expand_changed(self, value: int):
        self.config.set("notification", "reply_focus_expand_width", value=value)
        self._refresh_notification_preview(show_expand=True)

    def _on_notification_margin_x_changed(self, value: int):
        self.config.set("notification", "margin_x", value=value)
        self._refresh_notification_preview()

    def _on_notification_margin_top_changed(self, value: int):
        self.config.set("notification", "margin_top", value=value)
        self._refresh_notification_preview()

    def _on_notification_hide_on_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.notification_hide_on_combo)
        value = self.notification_hide_on_combo.currentData() or "mouse_keyboard"
        self.config.set("notification", "hide_on", value=value)
        self._refresh_notification_preview()

    def _on_notification_duration_changed(self, value: int):
        self.config.set("notification", "duration_ms", value=int(value) * 1000)
        self._refresh_notification_preview()

    def _on_notification_fade_changed(self, value: int):
        self.config.set("notification", "fade_ms", value=int(value))
        self._refresh_notification_preview()

    def _refresh_notification_preview(self, show_expand: bool = False):
        """Create a real test notification once; later setting changes update it in place.
        show_expand=True temporarily widens by reply_focus_expand_width, then restores base width."""

        preview_tag = "settings_notification_preview"
        duration_ms = int(self.config.get("notification", "duration_ms") or 5000)
        base_width = resolve_notification_width(self.config)
        screen_width = QApplication.primaryScreen().availableGeometry().width()
        width = expanded_reply_width(self.config, base_width, screen_width) if show_expand else base_width

        popup = popup_manager.find_by_tag(preview_tag)
        if popup is not None and popup.isVisible():
            popup.config = self.config
            popup.data.config = self.config
            popup.manager.config = self.config
            popup.duration = duration_ms
            if popup.hide_timer is not None and popup.hide_timer.isActive():
                popup.hide_timer.stop()
            if popup.self_hides_after_duration():
                popup.start_hide_timer()
        else:
            show_notification(
                title=tr("Preview", "Пример"),
                message=tr("Preview notification", "Пример уведомления"),
                config=self.config,
                emoticon_manager=self.emoticon_manager,
                is_system=True,
                tag=preview_tag,
                duration=duration_ms,
                auto_hide_after_duration=True,
                force=True,
            )
            popup = popup_manager.find_by_tag(preview_tag)
            if popup is None:
                return

        popup.base_width = base_width
        popup.animate_width(width)
        popup.manager.position_and_cleanup()
        if show_expand:
            self._schedule_preview_width_restore(base_width)

    def _schedule_preview_width_restore(self, base_width: int):
        """After briefly showing expand width, restore notification width."""

        timer = getattr(self, "_preview_expand_timer", None)
        if timer is not None:
            timer.stop()
        timer = QTimer(self)
        timer.setSingleShot(True)

        def _restore():
            popup = popup_manager.find_by_tag("settings_notification_preview")
            if popup is not None and popup.isVisible():
                popup.base_width = base_width
                popup.animate_width(base_width)

        timer.timeout.connect(_restore)
        timer.start(1200)
        self._preview_expand_timer = timer

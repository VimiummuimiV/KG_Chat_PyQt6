"""Application Settings widget"""

import re
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from components.button import create_icon_button
from helpers.fonts.fonts import FontType, get_font
from helpers.system import hotkey_manager as hotkey
from helpers.system.startup_manager import StartupManager
from helpers.translate import on_language_changed, tr, TranslatableMixin, TrStr
from ui.settings.settings_chat import SettingsChatMixin
from ui.settings.settings_competitions import SettingsCompetitionsMixin
from ui.settings.settings_fonts import SettingsFontsMixin
from ui.settings.settings_general import SettingsGeneralMixin
from ui.settings.settings_hotkey import SettingsHotkeyMixin
from ui.settings.settings_image_viewer import SettingsImageViewerMixin
from ui.settings.settings_notifications import SettingsNotificationsMixin
from ui.settings.settings_pets import SettingsPetsMixin
from ui.settings.settings_options import (
    fill_alert_chat_action_combo,
    fill_chatlog_filtered_click_combo,
    fill_competition_notification_style_combo,
    fill_flash_easing_combo,
    fill_image_transition_combo,
    fill_mentions_digest_mode_combo,
    fill_notification_hide_on_combo,
    fill_notification_mode_combo,
    fill_notification_mute_bypass_combo,
    fill_notification_position_combo,
    fill_own_message_mode_combo,
    fill_player_hwdec_combo,
    fill_player_ytdl_format_combo,
    fill_reply_style_combo,
    fill_resource_combo,
    fill_tracker_click_combo,
    fill_tracker_default_tab_combo,
)
from ui.settings.settings_player import SettingsPlayerMixin
from ui.settings.settings_sound import SettingsSoundMixin
from ui.settings.settings_tracker import SettingsTrackerMixin
from ui.settings.settings_widgets import (
    NoWheelComboBox,
    NoWheelSlider,
    SettingsRow,
    SLIDER_DEBOUNCE_MS,
    SpinCommitSignal,
)


class SettingsWidget(
    TranslatableMixin,
    SettingsChatMixin,
    SettingsCompetitionsMixin,
    SettingsFontsMixin,
    SettingsGeneralMixin,
    SettingsHotkeyMixin,
    SettingsImageViewerMixin,
    SettingsNotificationsMixin,
    SettingsPetsMixin,
    SettingsPlayerMixin,
    SettingsSoundMixin,
    SettingsTrackerMixin,
    QWidget,
):
    """Settings page organized into collapsible sections"""

    back_requested = pyqtSignal()
    sound_changed = pyqtSignal()
    competition_log_clear_requested = pyqtSignal()
    font_family_changed = pyqtSignal()
    tracker_badge_style_changed = pyqtSignal()
    input_style_changed = pyqtSignal()
    tracker_enabled_changed = pyqtSignal(bool)
    tracker_presence_log_changed = pyqtSignal(bool)
    tracker_userlist_star_changed = pyqtSignal(bool)
    tracker_presence_log_split_changed = pyqtSignal(int)
    resource_changed = pyqtSignal()
    pets_changed = pyqtSignal()

    def __init__(self, config, icons_path: Path, font_scaler=None, emoticon_manager=None):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.font_scaler = font_scaler
        self.emoticon_manager = emoticon_manager
        self.startup_manager = StartupManager()
        self.competitions_accent_color = None
        self.hotkey_capture = None

        self._setup_ui()
        self.refresh()
        hotkey.hotkey_manager.status_changed.connect(self.on_hotkey_status_changed)
        on_language_changed(self._retranslate)

    def element_spacing(self) -> int:
        return self.config.get("ui", "spacing", "widget_elements") or 6

    def create_section(self, title: str) -> QVBoxLayout:
        """Create a titled, collapsible section and append it to the scroll content."""
        section = QWidget()
        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(4, 4, 4, 4)
        section_layout.setSpacing(self.element_spacing())
        section.setLayout(section_layout)

        header_row = QHBoxLayout()
        header_row.setSpacing(self.element_spacing())
        label = QLabel(title)
        label.setProperty("fontRole", "header")
        label.setFont(get_font(FontType.HEADER))
        header_row.addWidget(label)
        header_row.addStretch(1)
        section_layout.addLayout(header_row)
        self.register_tr(label.setText, title)

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(self.element_spacing())
        content.setLayout(content_layout)
        section_layout.addWidget(content)

        # Slug is the config-path key for this section's collapsed state, so it
        # must stay stable regardless of the active UI language.
        slug_source = title.en if isinstance(title, TrStr) else title
        slug = re.sub(r"[^a-z0-9]+", "_", slug_source.lower()).strip("_")
        self.add_collapse_toggle(header_row, content, ("ui", "settings", "sections", slug), section=True)

        self._sections_layout.addWidget(section)
        return content_layout

    def add_collapse_toggle(self, header_layout: QHBoxLayout, content: QWidget, config_path: tuple,
                               default_collapsed: bool = False, *, section: bool = False) -> QToolButton:
        stored = self.config.get(*config_path)
        collapsed = default_collapsed if stored is None else bool(stored)

        button = QToolButton()
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setArrowType(Qt.ArrowType.RightArrow if collapsed else Qt.ArrowType.DownArrow)
        button.setChecked(collapsed)
        content.setVisible(not collapsed)

        button._section_content = content
        button._section_config_path = config_path

        def _on_toggled(checked):
            content.setVisible(not checked)
            button.setArrowType(Qt.ArrowType.RightArrow if checked else Qt.ArrowType.DownArrow)
            self.config.set(*config_path, value=checked)
            if section and not checked and self._accordion_enabled():
                for other in self._section_toggles:
                    if other is not button and not other.isChecked():
                        other.blockSignals(True)
                        other.setChecked(True)
                        other.setArrowType(Qt.ArrowType.RightArrow)
                        other._section_content.setVisible(False)
                        self.config.set(*other._section_config_path, value=True)
                        other.blockSignals(False)

        button.toggled.connect(_on_toggled)
        header_layout.insertWidget(0, button)
        if section:
            self._section_toggles.append(button)
        return button

    def _accordion_enabled(self) -> bool:
        return bool(self.config.get("ui", "settings", "accordion"))

    def add_subsection(self, section_layout: QVBoxLayout, title: str) -> tuple[QHBoxLayout, QWidget, QVBoxLayout]:
        """Create a titled sub-block (header row + content widget) inside a section
        and append it to section_layout. Caller adds rows to the returned content
        layout, then finishes with _add_collapse_toggle(header_row, content, config_path)."""
        header_row = QHBoxLayout()
        header_row.setSpacing(self.element_spacing())
        label = QLabel(title)
        label.setFont(get_font(FontType.UI))
        header_row.addWidget(label)
        header_row.addStretch(1)
        section_layout.addLayout(header_row)
        self.register_tr(label.setText, title)

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(self.element_spacing())
        content.setLayout(content_layout)
        section_layout.addWidget(content)

        return header_row, content, content_layout

    def add_checkbox(self, section_layout: QVBoxLayout, text: str, on_toggled) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setFont(get_font(FontType.UI))
        checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        checkbox.toggled.connect(on_toggled)
        section_layout.addWidget(checkbox)
        self.register_tr(checkbox.setText, text)
        return checkbox

    def add_combo_row(self, section_layout: QVBoxLayout, label_text: str, items: list, on_changed) -> QComboBox:
        row_widget = SettingsRow(spacing=self.element_spacing())
        row = row_widget.layout()
        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label, stretch=1)
        self.register_tr(label.setText, label_text)

        combo = NoWheelComboBox()
        combo.setFont(get_font(FontType.UI))
        combo.blockSignals(True)
        combo.addItems(items)
        combo.blockSignals(False)
        combo.setFixedWidth(240)
        combo.currentTextChanged.connect(on_changed)
        row.addWidget(combo)
        section_layout.addWidget(row_widget)
        return combo

    def add_slider_spin_row(self, section_layout: QVBoxLayout, label_text: str, minimum: int, maximum: int, on_changed, on_reset=None, default=None) -> QSpinBox:
        row_widget = SettingsRow(spacing=self.element_spacing())
        row = row_widget.layout()

        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label)
        self.register_tr(label.setText, label_text)

        slider = NoWheelSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        row.addWidget(slider, stretch=1)

        spin = QSpinBox()
        spin.setFont(get_font(FontType.UI))
        spin.setRange(minimum, maximum)
        spin.setFixedWidth(100)
        row.addWidget(spin)

        reset_button = None

        def update_reset_state(value):
            if reset_button is not None and default is not None:
                reset_button.setEnabled(value != default)

        # Debounce: slider/spin fire on every step; only commit on_changed after idle,
        # so dragging doesn't write to config.json on every intermediate value.
        commit_timer = QTimer(self)
        commit_timer.setSingleShot(True)
        pending_value = []
        commit_signal = SpinCommitSignal(spin)

        def commit():
            if pending_value:
                value = pending_value.pop()
                on_changed(value)
                commit_signal.committed.emit(value)

        commit_timer.timeout.connect(commit)

        def request_commit(value):
            pending_value[:] = [value]
            commit_timer.start(SLIDER_DEBOUNCE_MS)

        def sync_from_slider(value):
            # signalsBlocked() on the spin doubles as the "bulk-loading config, do not commit" flag
            if spin.signalsBlocked():
                return
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
            request_commit(value)
            update_reset_state(value)

        def sync_from_spin(value):
            if spin.signalsBlocked():
                return
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
            request_commit(value)
            update_reset_state(value)

        slider.valueChanged.connect(sync_from_slider)
        spin.valueChanged.connect(sync_from_spin)
        spin.linked_slider = slider
        spin.committed = commit_signal.committed

        # Default reset restores the default in the spin; sync_from_spin propagates it, so on_reset is only for extra work
        if on_reset is None and default is not None:
            on_reset = lambda: spin.setValue(default)

        if on_reset:
            reset_tooltip = tr("Reset to default", "Сбросить по умолчанию")
            reset_button = create_icon_button(self.icons_path, "line/refresh-line.svg", reset_tooltip, size_type="small", config=self.config)
            reset_button.clicked.connect(on_reset)
            row.addWidget(reset_button)
            update_reset_state(spin.value())
            spin._reset_button = reset_button
            spin.update_reset_state = update_reset_state
            self.register_tr(reset_button.setToolTip, reset_tooltip)

        section_layout.addWidget(row_widget)
        return spin

    def _setup_ui(self):
        window_margin = self.config.get("ui", "margins", "window") or 10
        window_spacing = self.config.get("ui", "spacing", "window_content") or 10

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(window_margin, window_margin, window_margin, window_margin)
        main_layout.setSpacing(window_spacing)
        self.setLayout(main_layout)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(self.element_spacing())
        main_layout.addLayout(header_layout)

        back_tooltip = tr("Back to Messages", "Назад к сообщениям")
        self._back_button = create_icon_button(
            self.icons_path, "line/arrow-go-back-line.svg", back_tooltip, config=self.config
        )
        self._back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self._back_button)
        self.register_tr(self._back_button.setToolTip, back_tooltip)

        title_text = tr("Settings", "Настройки")
        title_label = QLabel(title_text)
        title_label.setProperty("fontRole", "header")
        title_label.setFont(get_font(FontType.HEADER))
        header_layout.addWidget(title_label, stretch=1)
        self.register_tr(title_label.setText, title_text)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(self.scroll, stretch=1)

        content = QWidget()
        self._sections_layout = QVBoxLayout()
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(self.config.get("ui", "spacing", "section_gap") or 12)
        self._sections_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        content.setLayout(self._sections_layout)
        self._section_toggles = []
        self.scroll.setWidget(content)

        self.build_startup_section()
        self.build_chat_section()
        self.build_player_section()
        self.build_image_viewer_section()
        self.build_pets_section()
        self.build_fonts_section()
        self.build_notifications_section()
        self.build_competitions_section()
        self.build_user_tracker_section()
        self.build_sound_section()

        self._sections_layout.addStretch(1)

    def refresh(self):
        """Reload every control from the current config state."""
        widgets = (
            self.settings_accordion_checkbox, self.auto_login_checkbox,
            self.start_minimized_checkbox, self.start_with_system_checkbox,
            self.resource_combo, self.own_message_mode_combo,
            self.clear_private_checkbox, self.youtube_checkbox, self.voice_input_checkbox,
            self.player_tls_checkbox, self.player_hwdec_combo, self.player_volume_spin,
            self.player_log_checkbox, self.player_keep_open_checkbox, self.player_ontop_checkbox,
            self.player_ytdl_format_combo,
            self.image_viewer_thumbnails_checkbox, self.image_viewer_zoom_slider_checkbox,
            self.image_viewer_slideshow_spin, self.image_viewer_transition_combo, self.image_viewer_transition_spin,
            self.pets_checkbox, self.pets_stepped_checkbox, *self.pet_size_spins.values(), self.pet_visit_spin,
            self.chatlog_max_messages_spin, self.chatlog_live_search_spin,
            self.chatlog_filtered_click_combo,
            self.parser_validate_usernames_checkbox,
            self.badge_size_spin, self.input_hue_spin, self.input_saturation_spin,
            self.input_opacity_spin, self.input_idle_opacity_spin,
            self.mentions_digest_mode_combo,
            self.mentions_digest_interval_spin,
            self.flash_easing_combo, self.flash_row_duration_spin, self.flash_copy_duration_spin,
            self.browser_combo,
            self.track_competitions_checkbox,
            self.competitions_bypass_combo, self.mentions_bypass_combo, self.bans_bypass_combo,
            self.tracker_bypass_combo, self.messages_bypass_combo,
            self.tracker_enabled_checkbox,
            self.tracker_notifications_checkbox,
            self.tracker_presence_log_checkbox, self.tracker_presence_log_split_spin,
            self.tracker_badge_checkbox, self.tracker_userlist_star_checkbox,
            self.min_multiplier_combo,
            self.show_cost_checkbox, self.show_scores_checkbox, self.show_bonuses_checkbox,
            self.show_players_checkbox, self.max_player_chips_spin, self.sort_players_by_level_checkbox,
            self.competitions_alert_lead_spin, self.alert_chat_action_combo,
            self.competition_notification_style_combo,
            self.competitions_notify_window_checkbox,
            self.competitions_notify_start_spin, self.competitions_notify_end_spin,
            self.notification_mode_combo, self.notification_position_combo, self.reply_style_combo,
            self.reply_center_offset_spin, self.notification_width_spin, self.reply_focus_expand_spin,
            self.notification_margin_x_spin, self.notification_margin_top_spin,
            self.notification_hide_on_combo, self.notification_duration_spin, self.notification_fade_spin,
            self.mention_always_checkbox, self.competition_always_checkbox,
            self.competition_sound_repeat_checkbox, self.competition_sound_repeat_interval_spin,
        )
        if hasattr(self, "sound_selectors"):
            for selector in self.sound_selectors.values():
                selector.refresh()
        for widget in widgets:
            widget.blockSignals(True)

        self.refresh_general()
        self.refresh_player()
        self.refresh_image_viewer()
        self.refresh_pets()
        self.refresh_chat()
        self.refresh_hotkey_row()
        self.refresh_fonts()
        self.refresh_competitions_enabled()
        self.refresh_notification_bypass()
        self.refresh_tracker()
        self.refresh_competitions()
        self.refresh_notifications()
        self.refresh_sound()

        for widget in widgets:
            widget.blockSignals(False)

    def _refill_option_combos(self):
        """Re-populate combos whose *options* (not just their row label) are
        produced by tr(), preserving the current selection. Combos with
        static content (language, fonts, browser, multiplier) don't need this."""
        for combo, fill in (
            (self.resource_combo, fill_resource_combo),
            (self.own_message_mode_combo, fill_own_message_mode_combo),
            (self.mentions_digest_mode_combo, fill_mentions_digest_mode_combo),
            (self.flash_easing_combo, fill_flash_easing_combo),
            (self.notification_mode_combo, fill_notification_mode_combo),
            (self.notification_position_combo, fill_notification_position_combo),
            (self.reply_style_combo, fill_reply_style_combo),
            (self.notification_hide_on_combo, fill_notification_hide_on_combo),
            (self.competitions_bypass_combo, fill_notification_mute_bypass_combo),
            (self.mentions_bypass_combo, fill_notification_mute_bypass_combo),
            (self.bans_bypass_combo, fill_notification_mute_bypass_combo),
            (self.tracker_bypass_combo, fill_notification_mute_bypass_combo),
            (self.messages_bypass_combo, fill_notification_mute_bypass_combo),
            (self.alert_chat_action_combo, fill_alert_chat_action_combo),
            (self.competition_notification_style_combo, fill_competition_notification_style_combo),
            (self.tracker_default_tab_combo, fill_tracker_default_tab_combo),
            (self.tracker_click_combo, fill_tracker_click_combo),
            (self.chatlog_filtered_click_combo, fill_chatlog_filtered_click_combo),
            (self.player_hwdec_combo, fill_player_hwdec_combo),
            (self.player_ytdl_format_combo, fill_player_ytdl_format_combo),
            (self.image_viewer_transition_combo, fill_image_transition_combo),
        ):
            fill(combo, combo.currentData())

        # Not backed by a fill_*_combo helper (only two static items).
        current_unit = self.tracker_retention_unit_combo.currentData()
        self.tracker_retention_unit_combo.blockSignals(True)
        self.tracker_retention_unit_combo.clear()
        self.tracker_retention_unit_combo.addItem(tr("hours", "часов"), "hours")
        self.tracker_retention_unit_combo.addItem(tr("days", "дней"), "days")
        index = self.tracker_retention_unit_combo.findData(current_unit)
        self.tracker_retention_unit_combo.setCurrentIndex(index if index >= 0 else 0)
        self.tracker_retention_unit_combo.blockSignals(False)

    def _retranslate(self, _code=None):
        self.retranslate_all()
        self._refill_option_combos()
        self.refresh_hotkey_row()

    def sync_combo_tooltip(self, combo):
        tip = combo.itemData(combo.currentIndex(), Qt.ItemDataRole.ToolTipRole)
        combo.setToolTip(tip or "")

    def update_theme(self):
        """Re-apply theme-dependent colors after a theme toggle (competitions log + previews)."""
        theme = self.config.get("ui", "theme") or "dark"
        if hasattr(self, "tracker_events_bar"):
            self.tracker_events_bar.update_theme(theme == "dark")
        self.apply_font_preview_theme()
        self.apply_flash_preview_theme()
        self.apply_input_preview()
        if not hasattr(self, "competitions_log"):
            return
        lines = self.competitions_log.toPlainText().splitlines()
        if lines and lines != [self.tracking_disabled_text()]:
            self.set_competition_log_lines(lines)
        else:
            self.apply_competitions_log_theme()

    def set_spin_enabled(self, spin, enabled: bool):
        spin.setEnabled(enabled)
        if hasattr(spin, "linked_slider"):
            spin.linked_slider.setEnabled(enabled)

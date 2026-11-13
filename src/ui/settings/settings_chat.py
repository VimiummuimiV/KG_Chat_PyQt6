"""SettingsWidget: chat, chatlog, mentions digest and flash highlight options."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QSizePolicy, QWidget

from components.flash_highlight import DURATION_KEYS, FlashLabel
from helpers.browser import get_available_browsers
from helpers.colors.color_utils import (
    get_input_colors,
    get_input_stylesheet,
    hsl_to_hex,
    INPUT_HUE_DEFAULT,
    INPUT_HUE_MAX,
    INPUT_IDLE_OPACITY_DEFAULT,
    INPUT_OPACITY_DEFAULT,
    INPUT_OPACITY_MAX,
    INPUT_SATURATION_DEFAULT,
    INPUT_SATURATION_MAX,
)
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import tr
from ui.settings.settings_options import (
    DEFAULTS,
    fill_chatlog_filtered_click_combo,
    fill_flash_easing_combo,
    fill_mentions_digest_mode_combo,
    fill_tooltip_combo,
    LANGUAGE_OPTIONS,
)
from ui.settings.settings_widgets import gradient_slider_stylesheet, preview_box_stylesheet

_HUE_GRADIENT_STEP = 60
_GRADIENT_LIGHTNESS = 50
_HUE_GRADIENT_STOPS = [hsl_to_hex(hue, 100, _GRADIENT_LIGHTNESS) for hue in range(0, 361, _HUE_GRADIENT_STEP)]


class SettingsChatMixin:
    """SettingsWidget: chat, chatlog, mentions digest and flash highlight options."""

    def build_chat_section(self):
        section = self.create_section(tr("🗯️ Chat", "🗯️ Чат"))
        self.language_combo = self.add_combo_row(
            section, tr("Language", "Язык"), [], self.on_language_changed
        )
        self.language_combo.setFixedWidth(240)
        fill_tooltip_combo(
            self.language_combo, LANGUAGE_OPTIONS,
            self.config.get("ui", "language"), "en"
        )
        self.clear_private_checkbox = self.add_checkbox(
            section, tr("Clear private messages on exit", "Очищать приватные сообщения при выходе"),
            self.on_clear_private_toggled
        )
        self.youtube_checkbox = self.add_checkbox(
            section, tr("YouTube link previews", "Превью ссылок YouTube"),
            self.on_youtube_toggled
        )
        self.voice_input_checkbox = self.add_checkbox(
            section, tr("Voice input button", "Кнопка голосового ввода"),
            self.on_voice_input_toggled
        )
        self.settings_accordion_checkbox = self.add_checkbox(
            section, tr("Accordion settings sections (opening one collapses others)",
                        "Аккордеон секций настроек (открытие одной сворачивает остальные)"),
            self.on_settings_accordion_toggled
        )
        self.browser_combo = self.add_combo_row(
            section, tr("Open links in", "Открывать ссылки в"), [], self._on_browser_changed
        )
        self.browser_combo.setFixedWidth(240)
        self.badge_size_spin = self.add_slider_spin_row(
            section, tr("Badge font size", "Размер шрифта бейджа"), 8, 18,
            self._on_badge_size_changed, default=DEFAULTS["chat"]["badge_font_size"],
        )
        self.mentions_digest_mode_combo = self.add_combo_row(
            section, tr("Personal mentions check", "Проверка личных упоминаний"), [],
            self._on_mentions_digest_mode_changed
        )
        self.mentions_digest_mode_combo.setFixedWidth(240)
        self.mentions_digest_interval_spin = self.add_slider_spin_row(
            section, tr("Custom interval (hours)", "Свой интервал (часы)"), 1, 168,
            self._on_mentions_digest_interval_changed,
            default=DEFAULTS["chat"]["mentions_digest_interval_hours"],
        )
        self.add_hotkey_row(section, tr("Toggle chat window", "Показать/скрыть окно чата"))

        limits_header, limits_content, limits_layout = self.add_subsection(
            section, tr("📏 Message Limits", "📏 Лимиты сообщений")
        )
        self.chatlog_max_messages_spin = self.add_slider_spin_row(
            limits_layout, tr("Chatlog messages display limit", "Лимит отображения сообщений чатлога"),
            DEFAULTS["chatlog"]["max_messages_min"], DEFAULTS["chatlog"]["max_messages_max"],
            self._on_chatlog_max_messages_changed,
            default=DEFAULTS["chatlog"]["max_messages"],
        )
        self.chatlog_max_messages_spin.setSingleStep(1000)
        self.chatlog_max_messages_spin.linked_slider.setSingleStep(1000)
        self.chatlog_max_messages_spin.linked_slider.setPageStep(5000)

        self.chatlog_live_search_spin = self.add_slider_spin_row(
            limits_layout, tr("Chatlog live search up to (messages)", "Живой поиск чатлога до (сообщений)"),
            DEFAULTS["chatlog"]["live_search_max_messages_min"],
            DEFAULTS["chatlog"]["live_search_max_messages_max"],
            self._on_chatlog_live_search_max_changed,
            default=DEFAULTS["chatlog"]["live_search_max_messages"],
        )
        self.chatlog_live_search_spin.setSingleStep(500)
        self.chatlog_live_search_spin.linked_slider.setSingleStep(500)
        self.chatlog_live_search_spin.linked_slider.setPageStep(2000)

        self.chat_max_messages_spin = self.add_slider_spin_row(
            limits_layout, tr("Chat messages display limit", "Лимит отображения сообщений чата"),
            DEFAULTS["chat"]["max_messages_min"], DEFAULTS["chat"]["max_messages_max"],
            self._on_chat_max_messages_changed,
            default=DEFAULTS["chat"]["max_messages"],
        )
        self.chat_max_messages_spin.setSingleStep(100)
        self.chat_max_messages_spin.linked_slider.setSingleStep(100)
        self.chat_max_messages_spin.linked_slider.setPageStep(500)
        self.add_collapse_toggle(limits_header, limits_content, ("ui", "settings", "widgets", "chat_limits"))

        input_header, input_content, input_layout = self.add_subsection(
            section, tr("⌨️ Input Field", "⌨️ Строка ввода")
        )
        self.input_hue_spin = self.add_slider_spin_row(
            input_layout, tr("Hue", "Оттенок"), 0, INPUT_HUE_MAX,
            self._on_input_hue_changed, default=INPUT_HUE_DEFAULT,
        )
        self.input_saturation_spin = self.add_slider_spin_row(
            input_layout, tr("Saturation", "Насыщенность"), 0, INPUT_SATURATION_MAX,
            self._on_input_saturation_changed, default=INPUT_SATURATION_DEFAULT,
        )
        self.input_opacity_spin = self.add_slider_spin_row(
            input_layout, tr("Opacity when focused", "Прозрачность в фокусе"), 0, INPUT_OPACITY_MAX,
            self._on_input_opacity_changed, default=INPUT_OPACITY_DEFAULT,
        )
        self.input_idle_opacity_spin = self.add_slider_spin_row(
            input_layout, tr("Opacity when unfocused", "Прозрачность без фокуса"), 0, INPUT_OPACITY_MAX,
            self._on_input_idle_opacity_changed, default=INPUT_IDLE_OPACITY_DEFAULT,
        )
        for spin in (self.input_opacity_spin, self.input_idle_opacity_spin):
            spin.valueChanged.connect(self._clamp_input_idle_opacity)
            spin.linked_slider.valueChanged.connect(self._clamp_input_idle_opacity)
        self._input_preview = {}
        preview_row = QHBoxLayout()
        for state, placeholder in (("idle", tr("Unfocused", "Без фокуса")), ("focus", tr("Focused", "В фокусе"))):
            preview = QLineEdit()
            preview.setReadOnly(True)
            preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            preview.setPlaceholderText(placeholder)
            self.register_tr(preview.setPlaceholderText, placeholder)
            preview_row.addWidget(preview, stretch=1)
            self._input_preview[state] = preview
        input_layout.addLayout(preview_row)

        self.input_hue_spin.linked_slider.setStyleSheet(gradient_slider_stylesheet(_HUE_GRADIENT_STOPS))
        self.input_hue_spin.linked_slider.valueChanged.connect(self._update_input_saturation_gradient)
        self._update_input_saturation_gradient()
        self.apply_input_preview()
        self.add_collapse_toggle(input_header, input_content, ("ui", "settings", "widgets", "chat_input"))

        xmpp_header, xmpp_content, xmpp_layout = self.add_subsection(section, "🔌 XMPP")
        self.resource_combo = self.add_combo_row(
            xmpp_layout, tr("XMPP resource", "XMPP ресурс"), [], self.on_resource_changed
        )
        self.resource_combo.setFixedWidth(240)
        self.own_message_mode_combo = self.add_combo_row(
            xmpp_layout, tr("Own messages", "Свои сообщения"), [], self.on_own_message_mode_changed
        )
        self.own_message_mode_combo.setFixedWidth(240)
        self.delivery_marker_checkbox = self.add_checkbox(
            xmpp_layout, tr("Delivery marker after own messages", "Маркер доставки после своих сообщений"),
            self.on_delivery_marker_toggled,
        )
        self.tr_set(
            self.delivery_marker_checkbox.setToolTip,
            "Orange dot: sending. Green dot: the server has the message. Red dot: not delivered.",
            "Оранжевая точка: отправляется. Зелёная: сервер получил сообщение. Красная: не доставлено.",
        )
        self.add_collapse_toggle(xmpp_header, xmpp_content, ("ui", "settings", "widgets", "chat_xmpp"))

        chatlog_header, chatlog_content, chatlog_layout = self.add_subsection(
            section, tr("📜 Chatlog", "📜 Чатлог")
        )
        self.chatlog_filtered_click_combo = self.add_combo_row(
            chatlog_layout, tr("Click on filtered message", "Клик по отфильтрованному сообщению"), [],
            self._on_chatlog_filtered_click_changed
        )
        self.chatlog_filtered_click_combo.setFixedWidth(240)
        self.add_collapse_toggle(chatlog_header, chatlog_content, ("ui", "settings", "widgets", "chat_chatlog"))

        parser_header, parser_content, parser_layout = self.add_subsection(
            section, tr("🔍 Chatlog Parser", "🔍 Парсер чатлога")
        )
        self.parser_validate_usernames_checkbox = self.add_checkbox(
            parser_layout,
            tr("Validate usernames in chatlog parser (API check)",
               "Проверять имена в парсере чатлога (через API)"),
            self._on_parser_validate_usernames_toggled,
        )
        self.add_collapse_toggle(parser_header, parser_content, ("ui", "settings", "widgets", "chat_parser"))

        copy_header, copy_content, copy_layout = self.add_subsection(
            section, tr("📋 Copying Messages", "📋 Копирование сообщений")
        )
        self.copy_username_checkbox = self.add_checkbox(
            copy_layout, tr("Include username", "Добавлять имя пользователя"), self._on_copy_username_toggled
        )
        self.copy_timestamp_checkbox = self.add_checkbox(
            copy_layout, tr("Include timestamp", "Добавлять время"), self._on_copy_timestamp_toggled
        )
        self.add_collapse_toggle(copy_header, copy_content, ("ui", "settings", "widgets", "chat_copy"))

        flash_header, flash_content, flash_layout = self.add_subsection(
            section, tr("🪄 Highlight Animation", "🪄 Анимация подсветки")
        )
        self.flash_easing_combo = self.add_combo_row(
            flash_layout, tr("Timing function", "Функция плавности"), [], self._on_flash_easing_changed
        )
        self.flash_easing_combo.setFixedWidth(240)
        dmin = DEFAULTS["chat"]["flash_duration_ms_min"]
        dmax = DEFAULTS["chat"]["flash_duration_ms_max"]
        self.flash_row_duration_spin = self.add_slider_spin_row(
            flash_layout, tr("Row highlight (ms)", "Подсветка строки (мс)"),
            dmin, dmax, lambda v: self._on_flash_duration_changed("row", v),
            default=DEFAULTS["chat"]["flash_row_duration_ms"],
        )
        self.flash_copy_duration_spin = self.add_slider_spin_row(
            flash_layout, tr("Copy (ms)", "Копирование (мс)"),
            dmin, dmax, lambda v: self._on_flash_duration_changed("copy", v),
            default=DEFAULTS["chat"]["flash_copy_duration_ms"],
        )
        for spin in (self.flash_row_duration_spin, self.flash_copy_duration_spin):
            spin.setSingleStep(50)
            spin.linked_slider.setSingleStep(50)

        self._flash_preview = {}
        preview_widget = QWidget()
        preview_widget.setObjectName("flashPreview")
        preview_layout = QHBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)
        for kind, label_text in (
            ("row", tr("ROW", "СТРОКА")),
            ("copy", tr("COPY", "КОПИРОВАНИЕ")),
        ):
            label = FlashLabel(
                label_text,
                is_dark_fn=lambda: (self.config.get("ui", "theme") or "dark") == "dark",
                config=self.config,
                duration_kind=kind,
            )
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFont(get_font(FontType.UI))
            label.setMargin(0)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            preview_layout.addWidget(label, stretch=1)
            self._flash_preview[kind] = label

        self.apply_flash_preview_theme()
        flash_layout.addWidget(preview_widget)
        self.add_collapse_toggle(flash_header, flash_content, ("ui", "settings", "widgets", "chat_flash"))

    def refresh_chat(self):
        max_messages = self.config.get("ui", "chatlog", "max_messages")
        max_messages = DEFAULTS["chatlog"]["max_messages"] if max_messages is None else int(max_messages)
        max_messages = max(
            DEFAULTS["chatlog"]["max_messages_min"],
            min(DEFAULTS["chatlog"]["max_messages_max"], max_messages),
        )
        self.chatlog_max_messages_spin.setValue(max_messages)
        self.chatlog_max_messages_spin.linked_slider.setValue(max_messages)

        live_search_max = self.config.get("ui", "chatlog", "live_search_max_messages")
        live_search_max = DEFAULTS["chatlog"]["live_search_max_messages"] if live_search_max is None else int(live_search_max)
        live_search_max = max(
            DEFAULTS["chatlog"]["live_search_max_messages_min"],
            min(DEFAULTS["chatlog"]["live_search_max_messages_max"], live_search_max),
        )
        self.chatlog_live_search_spin.setValue(live_search_max)
        self.chatlog_live_search_spin.linked_slider.setValue(live_search_max)
        fill_chatlog_filtered_click_combo(
            self.chatlog_filtered_click_combo, self.config.get("ui", "chatlog", "filtered_click_action")
        )

        validate_usernames = self.config.get("chatlog_parser", "validate_usernames")
        self.parser_validate_usernames_checkbox.setChecked(
            True if validate_usernames is None else bool(validate_usernames)
        )

        self.copy_username_checkbox.setChecked(bool(self.config.get("ui", "chat", "copy_include_username")))
        self.copy_timestamp_checkbox.setChecked(bool(self.config.get("ui", "chat", "copy_include_timestamp")))

        chat_max_messages = self.config.get("ui", "chat", "max_messages")
        chat_max_messages = DEFAULTS["chat"]["max_messages"] if chat_max_messages is None else int(chat_max_messages)
        chat_max_messages = max(
            DEFAULTS["chat"]["max_messages_min"],
            min(DEFAULTS["chat"]["max_messages_max"], chat_max_messages),
        )
        self.chat_max_messages_spin.setValue(chat_max_messages)
        self.chat_max_messages_spin.linked_slider.setValue(chat_max_messages)

        badge_size = self.config.get("ui", "chat", "badge_font_size")
        try:
            badge_size = int(badge_size) if badge_size is not None else DEFAULTS["chat"]["badge_font_size"]
        except (TypeError, ValueError):
            badge_size = DEFAULTS["chat"]["badge_font_size"]
        badge_size = max(8, min(18, badge_size))
        self.badge_size_spin.setValue(badge_size)
        self.badge_size_spin.linked_slider.setValue(badge_size)

        input_hue = self.config.get("ui", "input_color", "hue")
        input_hue = INPUT_HUE_DEFAULT if input_hue is None else max(0, min(INPUT_HUE_MAX, int(input_hue)))
        self.input_hue_spin.setValue(input_hue)
        self.input_hue_spin.linked_slider.setValue(input_hue)

        input_saturation = self.config.get("ui", "input_color", "saturation")
        input_saturation = (
            INPUT_SATURATION_DEFAULT if input_saturation is None
            else max(0, min(INPUT_SATURATION_MAX, int(input_saturation)))
        )
        self.input_saturation_spin.setValue(input_saturation)
        self.input_saturation_spin.linked_slider.setValue(input_saturation)

        input_opacity = self.config.get("ui", "input_color", "background_opacity")
        input_opacity = (
            INPUT_OPACITY_DEFAULT if input_opacity is None
            else max(0, min(INPUT_OPACITY_MAX, int(input_opacity)))
        )
        self.input_opacity_spin.setValue(input_opacity)
        self.input_opacity_spin.linked_slider.setValue(input_opacity)

        input_idle_opacity = self.config.get("ui", "input_color", "background_opacity_idle")
        input_idle_opacity = (
            INPUT_IDLE_OPACITY_DEFAULT if input_idle_opacity is None else max(0, int(input_idle_opacity))
        )
        input_idle_opacity = min(input_idle_opacity, input_opacity)
        self.input_idle_opacity_spin.setValue(input_idle_opacity)
        self.input_idle_opacity_spin.linked_slider.setValue(input_idle_opacity)
        self.apply_input_preview()

        fill_mentions_digest_mode_combo(
            self.mentions_digest_mode_combo,
            self.config.get("ui", "chat", "mentions_digest_mode"),
        )
        digest_hours = self.config.get("ui", "chat", "mentions_digest_interval_hours")
        try:
            digest_hours = int(digest_hours) if digest_hours is not None else DEFAULTS["chat"]["mentions_digest_interval_hours"]
        except (TypeError, ValueError):
            digest_hours = DEFAULTS["chat"]["mentions_digest_interval_hours"]
        digest_hours = max(1, min(168, digest_hours))
        self.mentions_digest_interval_spin.setValue(digest_hours)
        self.mentions_digest_interval_spin.linked_slider.setValue(digest_hours)
        self._sync_mentions_digest_interval_visibility()

        fill_flash_easing_combo(self.flash_easing_combo, self.config.get("ui", "chat", "flash_easing"))
        self._load_flash_duration_spins()

        browsers = get_available_browsers()
        self.browser_combo.blockSignals(True)
        self.browser_combo.clear()
        for display_name, key in browsers:
            self.browser_combo.addItem(display_name, key)
        current_browser = self.config.get("browser") or "system"
        index = self.browser_combo.findData(current_browser)
        self.browser_combo.setCurrentIndex(index if index >= 0 else 0)
        self.browser_combo.blockSignals(False)

    def _on_chatlog_max_messages_changed(self, value: int):
        self.config.set("ui", "chatlog", "max_messages", value=int(value))

    def _on_chatlog_live_search_max_changed(self, value: int):
        self.config.set("ui", "chatlog", "live_search_max_messages", value=int(value))

    def _on_chatlog_filtered_click_changed(self, _text: str = ""):
        self.sync_combo_tooltip(self.chatlog_filtered_click_combo)
        value = self.chatlog_filtered_click_combo.currentData() or DEFAULTS["chatlog"]["filtered_click_action"]
        self.config.set("ui", "chatlog", "filtered_click_action", value=value)

    def _on_parser_validate_usernames_toggled(self, checked: bool):
        self.config.set("chatlog_parser", "validate_usernames", value=checked)

    def _on_copy_username_toggled(self, checked: bool):
        self.config.set("ui", "chat", "copy_include_username", value=checked)

    def _on_copy_timestamp_toggled(self, checked: bool):
        self.config.set("ui", "chat", "copy_include_timestamp", value=checked)

    def _on_chat_max_messages_changed(self, value: int):
        self.config.set("ui", "chat", "max_messages", value=int(value))

    def _on_browser_changed(self, _text: str = ""):
        key = self.browser_combo.currentData()
        if key is not None:
            self.config.set("browser", value=key)

    def apply_flash_preview_theme(self):
        if not hasattr(self, "_flash_preview"):
            return
        preview_style = preview_box_stylesheet("QLabel", self.config.get("ui", "theme") or "dark")
        for preview in self._flash_preview.values():
            preview.setStyleSheet(preview_style)

    def _load_flash_duration_spins(self):
        dmin = DEFAULTS["chat"]["flash_duration_ms_min"]
        dmax = DEFAULTS["chat"]["flash_duration_ms_max"]
        legacy = self.config.get("ui", "chat", "flash_duration_ms")
        try:
            legacy = int(legacy) if legacy is not None else DEFAULTS["chat"]["flash_duration_ms"]
        except (TypeError, ValueError):
            legacy = DEFAULTS["chat"]["flash_duration_ms"]
        for kind, spin in (
            ("row", self.flash_row_duration_spin),
            ("copy", self.flash_copy_duration_spin),
        ):
            value = self.config.get("ui", "chat", DURATION_KEYS[kind])
            try:
                value = int(value) if value is not None else legacy
            except (TypeError, ValueError):
                value = legacy
            value = max(dmin, min(dmax, value))
            spin.setValue(value)
            spin.linked_slider.setValue(value)

    def _on_badge_size_changed(self, value: int):
        self.config.set("ui", "chat", "badge_font_size", value=int(value))
        self.tracker_badge_style_changed.emit()

    def _update_input_saturation_gradient(self, _value: int = 0):
        hue = self.input_hue_spin.linked_slider.value()
        self.input_saturation_spin.linked_slider.setStyleSheet(gradient_slider_stylesheet([
            hsl_to_hex(hue, 0, _GRADIENT_LIGHTNESS),
            hsl_to_hex(hue, INPUT_SATURATION_MAX, _GRADIENT_LIGHTNESS),
        ]))

    def apply_input_preview(self):
        """Show the unfocused and focused look of the regular input with the current settings."""
        if not hasattr(self, "_input_preview"):
            return
        colors = get_input_colors(self.config, (self.config.get("ui", "theme") or "dark") == "dark")
        focused_colors = {**colors, "input_bg_idle": colors["input_bg"], "input_border_idle": colors["input_border"]}
        self._input_preview["idle"].setStyleSheet(get_input_stylesheet(colors))
        self._input_preview["focus"].setStyleSheet(get_input_stylesheet(focused_colors))

    def _on_input_style_changed(self):
        self.apply_input_preview()
        self.input_style_changed.emit()

    def _on_input_hue_changed(self, value: int):
        self.config.set("ui", "input_color", "hue", value=int(value))
        self._on_input_style_changed()

    def _on_input_saturation_changed(self, value: int):
        self.config.set("ui", "input_color", "saturation", value=int(value))
        self._on_input_style_changed()

    def _on_input_opacity_changed(self, value: int):
        self.config.set("ui", "input_color", "background_opacity", value=int(value))
        self._on_input_style_changed()

    def _on_input_idle_opacity_changed(self, value: int):
        self.config.set("ui", "input_color", "background_opacity_idle", value=int(value))
        self._on_input_style_changed()

    def _clamp_input_idle_opacity(self, _value: int = 0):
        """The unfocused opacity can never exceed the focused one."""
        if self.input_idle_opacity_spin.value() > self.input_opacity_spin.value():
            self.input_idle_opacity_spin.setValue(self.input_opacity_spin.value())

    def _on_mentions_digest_mode_changed(self, _text: str = ""):
        mode = self.mentions_digest_mode_combo.currentData()
        if mode is not None:
            self.config.set("ui", "chat", "mentions_digest_mode", value=mode)
        self._sync_mentions_digest_interval_visibility()
        tip = self.mentions_digest_mode_combo.itemData(
            self.mentions_digest_mode_combo.currentIndex(), Qt.ItemDataRole.ToolTipRole
        )
        self.mentions_digest_mode_combo.setToolTip(tip or "")

    def _sync_mentions_digest_interval_visibility(self):
        is_custom = self.mentions_digest_mode_combo.currentData() == "custom"
        spin = self.mentions_digest_interval_spin
        spin.setEnabled(is_custom)
        if hasattr(spin, "linked_slider"):
            spin.linked_slider.setEnabled(is_custom)

    def _on_mentions_digest_interval_changed(self, value: int):
        self.config.set("ui", "chat", "mentions_digest_interval_hours", value=int(value))

    def _on_flash_easing_changed(self, _text: str = ""):
        value = self.flash_easing_combo.currentData()
        if value is not None:
            self.config.set("ui", "chat", "flash_easing", value=value)
        for kind, preview in self._flash_preview.items():
            preview.flash(kind)

    def _on_flash_duration_changed(self, kind: str, value: int):
        self.config.set("ui", "chat", DURATION_KEYS[kind], value=int(value))
        self._flash_preview[kind].flash(kind)

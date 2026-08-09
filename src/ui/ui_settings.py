"""Application Settings widget"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QCheckBox, QComboBox, QSpinBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from helpers.create import create_icon_button
from helpers.fonts import get_font, FontType
from helpers.startup_manager import StartupManager


class SettingsWidget(QWidget):
    """Settings page organized into collapsible sections"""

    back_requested = pyqtSignal()

    def __init__(self, config, icons_path: Path):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.startup_manager = StartupManager()

        self._setup_ui()
        self.refresh()

    # ------------------------------------------------------------------ #
    # Layout helpers
    # ------------------------------------------------------------------ #
    def _create_section(self, title: str) -> QVBoxLayout:
        """Create a titled section and append it to the scroll content."""
        section = QWidget()
        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(4, 4, 4, 4)
        section_layout.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        section.setLayout(section_layout)

        label = QLabel(title)
        label.setFont(get_font(FontType.HEADER))
        section_layout.addWidget(label)

        self._sections_layout.addWidget(section)
        return section_layout

    def _add_checkbox(self, section_layout: QVBoxLayout, text: str, on_toggled) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setFont(get_font(FontType.UI))
        checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        checkbox.toggled.connect(on_toggled)
        section_layout.addWidget(checkbox)
        return checkbox

    def _add_combo_row(self, section_layout: QVBoxLayout, label_text: str, items: list, on_changed) -> QComboBox:
        row = QHBoxLayout()
        row.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label, stretch=1)

        combo = QComboBox()
        combo.setFont(get_font(FontType.UI))
        combo.addItems(items)
        combo.setFixedWidth(160)
        combo.currentTextChanged.connect(on_changed)
        row.addWidget(combo)
        section_layout.addLayout(row)
        return combo

    def _add_spin_row(self, section_layout: QVBoxLayout, label_text: str, minimum: int, maximum: int, on_changed) -> QSpinBox:
        row = QHBoxLayout()
        row.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label, stretch=1)

        spin = QSpinBox()
        spin.setFont(get_font(FontType.UI))
        spin.setRange(minimum, maximum)
        spin.setFixedWidth(100)
        spin.valueChanged.connect(on_changed)
        row.addWidget(spin)
        section_layout.addLayout(row)
        return spin

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        window_margin = self.config.get("ui", "margins", "window") or 10
        window_spacing = self.config.get("ui", "spacing", "window_content") or 10

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(window_margin, window_margin, window_margin, window_margin)
        main_layout.setSpacing(window_spacing)
        self.setLayout(main_layout)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        main_layout.addLayout(header_layout)

        self.back_button = create_icon_button(
            self.icons_path, "go-back.svg", "Back to Messages", config=self.config
        )
        self.back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.back_button)

        title_label = QLabel("Settings")
        title_label.setFont(get_font(FontType.HEADER))
        header_layout.addWidget(title_label, stretch=1)

        # Scroll area
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
        self.scroll.setWidget(content)

        self._build_startup_section()
        self._build_chat_section()
        self._build_notifications_section()
        self._build_sound_section()

        self._sections_layout.addStretch(1)

    def _build_startup_section(self):
        section = self._create_section("Startup")
        self.auto_login_checkbox = self._add_checkbox(
            section, "Auto-login on startup", self._on_auto_login_toggled
        )
        self.start_minimized_checkbox = self._add_checkbox(
            section, "Start minimized", self._on_start_minimized_toggled
        )
        self.start_with_system_checkbox = self._add_checkbox(
            section, "Start with system", self._on_start_with_system_toggled
        )

    def _build_chat_section(self):
        section = self._create_section("Chat")
        self.clear_private_checkbox = self._add_checkbox(
            section, "Clear private messages on exit", self._on_clear_private_toggled
        )
        self.youtube_checkbox = self._add_checkbox(
            section, "Enable YouTube link previews", self._on_youtube_toggled
        )

    def _build_notifications_section(self):
        section = self._create_section("Notifications")
        self.notification_position_combo = self._add_combo_row(
            section, "Notification position", ["Right", "Left", "Center"],
            self._on_notification_position_changed
        )
        self.notification_width_spin = self._add_spin_row(
            section, "Notification width", 250, 1000, self._on_notification_width_changed
        )

    def _build_sound_section(self):
        section = self._create_section("Sound")
        self.mention_always_checkbox = self._add_checkbox(
            section, "Always play mention sound", self._on_mention_always_toggled
        )

    # ------------------------------------------------------------------ #
    # Config <-> UI sync
    # ------------------------------------------------------------------ #
    def refresh(self):
        """Reload every control from the current config state."""
        widgets = (
            self.auto_login_checkbox, self.start_minimized_checkbox, self.start_with_system_checkbox,
            self.clear_private_checkbox, self.youtube_checkbox,
            self.notification_position_combo, self.notification_width_spin,
            self.mention_always_checkbox,
        )
        for widget in widgets:
            widget.blockSignals(True)

        self.auto_login_checkbox.setChecked(bool(self.config.get("startup", "auto_login")))
        self.start_minimized_checkbox.setChecked(bool(self.config.get("startup", "start_minimized")))
        self.start_with_system_checkbox.setChecked(self.startup_manager.is_enabled())

        self.clear_private_checkbox.setChecked(bool(self.config.get("ui", "clear_private_messages_on_exit")))
        youtube_enabled = self.config.get("ui", "youtube", "enabled")
        self.youtube_checkbox.setChecked(True if youtube_enabled is None else bool(youtube_enabled))

        position = (self.config.get("ui", "notification_position") or "right").capitalize()
        idx = self.notification_position_combo.findText(position)
        self.notification_position_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.notification_width_spin.setValue(int(self.config.get("ui", "notification_width") or 550))

        self.mention_always_checkbox.setChecked(bool(self.config.get("sound", "play_mention_sound_always")))

        for widget in widgets:
            widget.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #
    def _on_auto_login_toggled(self, checked: bool):
        self.config.set("startup", "auto_login", value=checked)

    def _on_start_minimized_toggled(self, checked: bool):
        self.config.set("startup", "start_minimized", value=checked)

    def _on_start_with_system_toggled(self, checked: bool):
        success = self.startup_manager.enable() if checked else self.startup_manager.disable()
        if not success:
            QMessageBox.warning(
                self, "Error",
                f"Failed to {'enable' if checked else 'disable'} start with system. "
                "Please check permissions."
            )
            self.start_with_system_checkbox.blockSignals(True)
            self.start_with_system_checkbox.setChecked(not checked)
            self.start_with_system_checkbox.blockSignals(False)

    def _on_clear_private_toggled(self, checked: bool):
        self.config.set("ui", "clear_private_messages_on_exit", value=checked)

    def _on_youtube_toggled(self, checked: bool):
        self.config.set("ui", "youtube", "enabled", value=checked)

    def _on_notification_position_changed(self, text: str):
        self.config.set("ui", "notification_position", value=text.lower())

    def _on_notification_width_changed(self, value: int):
        self.config.set("ui", "notification_width", value=value)

    def _on_mention_always_toggled(self, checked: bool):
        self.config.set("sound", "play_mention_sound_always", value=checked)
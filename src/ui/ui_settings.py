"""Application Settings widget"""
from pathlib import Path
import shutil

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QCheckBox, QComboBox, QSpinBox, QSlider, QMessageBox, QTextEdit,
    QApplication, QInputDialog, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from helpers.create import create_icon_button
from helpers.fonts import get_font, FontType
from helpers.startup_manager import StartupManager
from helpers.voice_engine import play_sound
from helpers.data import get_data_dir
from helpers.color_utils import blend_hex_colors

NOTIFICATION_WIDTH_DEFAULT = 565
COMPETITIONS_ALERT_LEAD_DEFAULT = 0
COMPETITIONS_NOTIFY_START_DEFAULT = 0
COMPETITIONS_NOTIFY_END_DEFAULT = 24
COMPETITION_SOUND_REPEAT_INTERVAL_DEFAULT = 15
COMPETITIONS_MAX_PLAYER_CHIPS_DEFAULT = 20
COMPETITIONS_LOG_HEIGHT = 300
COMPETITIONS_LOG_HEIGHT_COLLAPSED = 32

CONNECTION_STATES = {
    "connected": "#2ecc71",
    "connecting": "#f1c40f",
    "reconnecting": "#e67e22",
}

COMPETITIONS_LOG_COLORS = {
    "dark": {
        "bg": "#1E1E1E",
        "fg": "#D4D4D4",
        "ws": "#888888",
        "waiting": "#4EC9B0",
        "paused": "#DCDCAA",
        "racing": "#569CD6",
        "finished": "#6A9955",
        "error": "#F44747",
        "default": "#D4D4D4",
    },
    "light": {
        "bg": "#FFFFFF",
        "fg": "#333333",
        "ws": "#6A6A6A",
        "waiting": "#0E8A6A",
        "paused": "#8A7A00",
        "racing": "#1A6FB5",
        "finished": "#2E7D32",
        "error": "#C62828",
        "default": "#333333",
    },
}


# kind == folder name == config key: "mention" | "ban" | "competition"

def get_system_sound_dir(sound_root: Path, kind: str) -> Path:
    """Project-bundled sounds (read-only for the user)."""
    if not sound_root:
        return Path()
    return sound_root / (kind or "").strip().lower()


def get_user_sound_dir(kind: str) -> Path:
    """User-writable sounds under KG_Chat_Data/sounds/<kind>/."""
    return get_data_dir("sounds") / (kind or "").strip().lower()


def get_sound_files(sound_dir: Path) -> list[str]:
    """Return sorted MP3 names from one directory."""
    if not sound_dir or not sound_dir.exists():
        return []
    return sorted(
        [p.name for p in sound_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp3"],
        key=lambda name: name.lower(),
    )


def get_merged_sound_files(system_dir: Path, user_dir: Path) -> list[str]:
    """Unique filenames from system + user dirs (user overrides on name clash)."""
    names = set(get_sound_files(system_dir)) | set(get_sound_files(user_dir))
    return sorted(names, key=lambda n: n.lower())


def resolve_sound_file(name: str, system_dir: Path, user_dir: Path) -> Path | None:
    """Prefer user copy, then system."""
    if not name:
        return None
    user_path = user_dir / name
    if user_path.is_file():
        return user_path
    system_path = system_dir / name
    if system_path.is_file():
        return system_path
    return None


def _read_selected_name(config, kind: str) -> str | None:
    """Read sound.selected.<kind>."""
    if isinstance(config, dict):
        selected = (config.get("sound") or {}).get("selected") or {}
    else:
        selected = config.get("sound", "selected") or {}
    if not isinstance(selected, dict):
        return None
    return selected.get(kind)


def get_sound_name(sound_root: Path, kind: str, config) -> str | None:
    """Filename currently chosen for this kind, or a sensible default."""
    system_dir = get_system_sound_dir(sound_root, kind)
    user_dir = get_user_sound_dir(kind)
    files = get_merged_sound_files(system_dir, user_dir)
    if not files:
        return None

    name = _read_selected_name(config, kind)
    if name and name in files:
        return name

    # Prefer <kind>.mp3 if present, else first file
    preferred = f"{(kind or '').strip().lower()}.mp3"
    if preferred in files:
        return preferred
    return files[0]


def get_sound_path(sound_root: Path, kind: str, config) -> Path | None:
    """Full path to the active sound for this kind (user dir wins over system)."""
    name = get_sound_name(sound_root, kind, config)
    if not name:
        return None
    return resolve_sound_file(
        name,
        get_system_sound_dir(sound_root, kind),
        get_user_sound_dir(kind),
    )


class NoWheelSlider(QSlider):
    """QSlider that ignores mouse wheel events, letting the parent scroll area handle scrolling instead."""

    def wheelEvent(self, event):
        event.ignore()


class SoundSelectorWidget(QWidget):
    """Selector for one notification sound type.

    System sounds (project/sounds/...) are listed but cannot be deleted or renamed.
    User sounds live in KG_Chat_Data/sounds/<kind>/ and can be added, renamed, deleted.
    """

    def __init__(self, config, sound_root: Path, kind: str, label_text: str):
        super().__init__()
        self.config = config
        self.sound_root = sound_root
        self.kind = kind
        self.config_key = (kind or '').strip().lower()
        self.system_dir = get_system_sound_dir(sound_root, kind)
        self.user_dir = get_user_sound_dir(kind)
        self.icons_path = Path(__file__).parent.parent / "icons"

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.setLayout(layout)

        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        layout.addWidget(label)

        self.prev_button = create_icon_button(
            self.icons_path, "arrow-left.svg", "Previous sound", size_type="small", config=self.config
        )
        self.prev_button.clicked.connect(self._on_prev)
        layout.addWidget(self.prev_button)

        self.combo = QComboBox()
        self.combo.setFont(get_font(FontType.UI))
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        self.combo.setMinimumWidth(180)
        layout.addWidget(self.combo, stretch=1)

        self.next_button = create_icon_button(
            self.icons_path, "arrow-right.svg", "Next sound", size_type="small", config=self.config
        )
        self.next_button.clicked.connect(self._on_next)
        layout.addWidget(self.next_button)

        self.play_button = create_icon_button(
            self.icons_path, "play.svg", "Play sound", size_type="small", config=self.config
        )
        self.play_button.clicked.connect(self._on_play)
        layout.addWidget(self.play_button)

        self.add_button = create_icon_button(
            self.icons_path, "add.svg", "Add sound from file", size_type="small", config=self.config
        )
        self.add_button.clicked.connect(self._on_add)
        layout.addWidget(self.add_button)

        self.delete_button = create_icon_button(
            self.icons_path, "trash.svg", "Delete sound", size_type="small", config=self.config
        )
        self.delete_button.clicked.connect(self._on_delete)
        layout.addWidget(self.delete_button)

        self.rename_button = create_icon_button(
            self.icons_path, "pencil.svg", "Rename sound", size_type="small", config=self.config
        )
        self.rename_button.clicked.connect(self._on_rename)
        layout.addWidget(self.rename_button)

        self.refresh()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _safe_name(self) -> str | None:
        return self.combo.currentData()

    def _is_user_owned(self, file_name: str | None) -> bool:
        if not file_name:
            return False
        return (self.user_dir / file_name).is_file()

    def _resolve_path(self, file_name: str | None) -> Path | None:
        if not file_name:
            return None
        return resolve_sound_file(file_name, self.system_dir, self.user_dir)

    def _update_edit_buttons(self):
        """Delete/Rename only for user-owned files."""
        user_owned = self._is_user_owned(self._safe_name())
        self.delete_button.setEnabled(user_owned)
        self.rename_button.setEnabled(user_owned)

    def _persist_selection(self, name: str | None):
        if not self.config:
            return
        selected = self.config.get("sound", "selected") or {}
        if not isinstance(selected, dict):
            selected = {}
        selected = dict(selected)

        if name:
            selected[self.config_key] = name
        else:
            selected.pop(self.config_key, None)

        self.config.set(
            "sound",
            "selected",
            value={k: v for k, v in selected.items() if v is not None},
        )

    def _play_file(self, file_name: str | None):
        """Stop any current effect and play the chosen file (preview ignores mute)."""
        path = self._resolve_path(file_name)
        if not path:
            return
        # force=True so preview works even when effects are muted;
        # play_sound already cancels the previous sound.
        play_sound(str(path), config=self.config, force=True)

    @staticmethod
    def _display_name(file_name: str) -> str:
        """Combo label without the extension - only .mp3 is supported, so it's just noise."""
        return file_name[:-4] if file_name.lower().endswith(".mp3") else file_name

    # ------------------------------------------------------------------ #
    # Refresh / selection
    # ------------------------------------------------------------------ #
    def refresh(self, select_name: str | None = None):
        files = get_merged_sound_files(self.system_dir, self.user_dir)
        self.combo.blockSignals(True)
        self.combo.clear()

        if not files:
            self.combo.addItem("No sound", None)
            self.combo.setEnabled(False)
            self._persist_selection(None)
            self.combo.blockSignals(False)
            self._update_edit_buttons()
            return

        self.combo.setEnabled(True)
        for file_name in files:
            self.combo.addItem(self._display_name(file_name), file_name)

        preferred = select_name or get_sound_name(self.sound_root, self.kind, self.config)
        index = self.combo.findData(preferred) if preferred else -1
        self.combo.setCurrentIndex(index if index >= 0 else 0)

        self._persist_selection(self.combo.currentData())
        self.combo.blockSignals(False)
        self._update_edit_buttons()

    def _on_combo_changed(self, _index: int):
        name = self.combo.currentData()
        if name is None:
            self._persist_selection(None)
            self._update_edit_buttons()
            return
        self._persist_selection(name)
        self._update_edit_buttons()
        self._play_file(name)

    def _on_prev(self):
        if self.combo.count() <= 1:
            return
        self.combo.setCurrentIndex((self.combo.currentIndex() - 1) % self.combo.count())

    def _on_next(self):
        if self.combo.count() <= 1:
            return
        self.combo.setCurrentIndex((self.combo.currentIndex() + 1) % self.combo.count())

    def _on_play(self):
        self._play_file(self._safe_name())

    # ------------------------------------------------------------------ #
    # User file operations (only touch user_dir)
    # ------------------------------------------------------------------ #
    def _on_add(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select sound file",
            "",
            "Audio (*.mp3);;All files (*)",
        )
        if not path:
            return

        src = Path(path)
        if not src.is_file():
            return

        self.user_dir.mkdir(parents=True, exist_ok=True)

        stem = src.stem
        dest_name = f"{stem}.mp3"
        dest = self.user_dir / dest_name

        if dest.exists():
            reply = QMessageBox.question(
                self,
                "File exists",
                f"'{dest_name}' already exists in your sounds. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            QMessageBox.warning(self, "Add sound", f"Failed to copy file: {exc}")
            return

        self.refresh(select_name=dest_name)
        self._play_file(dest_name)

    def _on_delete(self):
        file_name = self._safe_name()
        if not file_name or not self._is_user_owned(file_name):
            QMessageBox.information(
                self,
                "Delete sound",
                "System sounds cannot be deleted. Only sounds you added can be removed.",
            )
            return

        path = self.user_dir / file_name
        reply = QMessageBox.question(
            self,
            "Delete sound",
            f"Delete '{file_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            path.unlink()
        except OSError as exc:
            QMessageBox.warning(self, "Delete sound", f"Failed to delete sound: {exc}")
            return

        self.refresh()

    def _on_rename(self):
        file_name = self._safe_name()
        if not file_name or not self._is_user_owned(file_name):
            QMessageBox.information(
                self,
                "Rename sound",
                "System sounds cannot be renamed. Only sounds you added can be renamed.",
            )
            return

        current_path = self.user_dir / file_name
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Rename sound")
        dialog.setLabelText("New file name:")
        dialog.setTextValue(self._display_name(file_name))
        dialog.resize(400, dialog.sizeHint().height())
        if not dialog.exec():
            return
        new_stem = dialog.textValue()
        if not new_stem.strip():
            return

        clean_name = new_stem.strip().strip("\\/")
        if clean_name.lower().endswith(".mp3"):
            clean_name = clean_name[:-4]  # in case the user typed it anyway
        clean_name = f"{clean_name}.mp3"

        if any(ch in clean_name for ch in ("/", "\\")):
            QMessageBox.warning(self, "Rename sound", "The name cannot contain path separators.")
            return

        target_path = self.user_dir / clean_name
        if target_path.exists() and target_path.name.lower() != current_path.name.lower():
            QMessageBox.warning(self, "Rename sound", "A sound with that name already exists.")
            return

        try:
            current_path.rename(target_path)
        except OSError as exc:
            QMessageBox.warning(self, "Rename sound", f"Failed to rename sound: {exc}")
            return

        self.refresh(select_name=clean_name)


class SettingsWidget(QWidget):
    """Settings page organized into collapsible sections"""

    back_requested = pyqtSignal()
    sound_changed = pyqtSignal()
    competition_log_clear_requested = pyqtSignal()

    def __init__(self, config, icons_path: Path):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.startup_manager = StartupManager()
        self._competitions_accent_color = None

        self._setup_ui()
        self.refresh()

    # ------------------------------------------------------------------ #
    # Layout helpers
    # ------------------------------------------------------------------ #
    def _spacing(self) -> int:
        return self.config.get("ui", "spacing", "widget_elements") or 6

    def _create_section(self, title: str) -> QVBoxLayout:
        """Create a titled section and append it to the scroll content."""
        section = QWidget()
        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(4, 4, 4, 4)
        section_layout.setSpacing(self._spacing())
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
        row.setSpacing(self._spacing())
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

    def _add_slider_spin_row(self, section_layout: QVBoxLayout, label_text: str, minimum: int, maximum: int, on_changed, on_reset=None, default=None) -> QSpinBox:
        row = QHBoxLayout()
        row.setSpacing(self._spacing())

        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label)

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

        def sync_from_slider(value):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
            on_changed(value)
            update_reset_state(value)

        def sync_from_spin(value):
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
            on_changed(value)
            update_reset_state(value)

        slider.valueChanged.connect(sync_from_slider)
        spin.valueChanged.connect(sync_from_spin)
        spin._slider = slider

        if on_reset:
            reset_button = create_icon_button(self.icons_path, "reload.svg", "Reset to default", size_type="small", config=self.config)
            reset_button.clicked.connect(on_reset)
            row.addWidget(reset_button)
            update_reset_state(spin.value())

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

        header_layout = QHBoxLayout()
        header_layout.setSpacing(self._spacing())
        main_layout.addLayout(header_layout)

        self.back_button = create_icon_button(
            self.icons_path, "go-back.svg", "Back to Messages", config=self.config
        )
        self.back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.back_button)

        title_label = QLabel("Settings")
        title_label.setFont(get_font(FontType.HEADER))
        header_layout.addWidget(title_label, stretch=1)

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
        self._build_competitions_section()
        self._build_sound_section()

        self._sections_layout.addStretch(1)

    def _build_startup_section(self):
        section = self._create_section("🚀 Startup")
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
        section = self._create_section("💬 Chat")
        self.clear_private_checkbox = self._add_checkbox(
            section, "Clear private messages on exit", self._on_clear_private_toggled
        )
        self.youtube_checkbox = self._add_checkbox(
            section, "Enable YouTube link previews", self._on_youtube_toggled
        )

    def _build_notifications_section(self):
        section = self._create_section("⚠️ Notifications")
        self.notification_position_combo = self._add_combo_row(
            section, "Notification position", ["Right", "Left", "Center"],
            self._on_notification_position_changed
        )
        self.notification_width_spin = self._add_slider_spin_row(
            section, "Notification width", NOTIFICATION_WIDTH_DEFAULT, 1000, self._on_notification_width_changed,
            on_reset=self._on_notification_width_reset, default=NOTIFICATION_WIDTH_DEFAULT
        )

        self.competitions_bypass_mute_checkbox = self._add_checkbox(
            section, "Notify about competitions even when muted", self._on_competitions_bypass_mute_toggled
        )

    def _build_competitions_section(self):
        section = self._create_section("🏆 Competitions")

        self.track_competitions_checkbox = self._add_checkbox(
            section, "Track rating competitions", self._on_track_competitions_toggled
        )

        log_header_row = QHBoxLayout()
        log_header_row.setSpacing(self._spacing())
        log_label = QLabel("📜 WebSocket Log")
        log_label.setFont(get_font(FontType.UI))
        log_header_row.addWidget(log_label)
        log_header_row.addStretch(1)

        self.copy_log_button = create_icon_button(
            self.icons_path, "copy.svg", "Copy log", size_type="small", config=self.config
        )
        self.copy_log_button.clicked.connect(self._on_copy_log_clicked)
        log_header_row.addWidget(self.copy_log_button)

        self.clear_log_button = create_icon_button(
            self.icons_path, "trash.svg", "Clear log", size_type="small", config=self.config
        )
        self.clear_log_button.clicked.connect(self._on_clear_log_clicked)
        log_header_row.addWidget(self.clear_log_button)

        section.addLayout(log_header_row)

        self.competitions_log = QTextEdit()
        self.competitions_log.setReadOnly(True)
        self.competitions_log.setFixedHeight(COMPETITIONS_LOG_HEIGHT)
        self.competitions_log.setFont(get_font(FontType.UI))
        self.competitions_log.setPlaceholderText("Competition log")
        self.competitions_log.setAcceptRichText(True)
        self._apply_competitions_log_theme()
        section.addWidget(self.competitions_log)

        self.min_multiplier_combo = self._add_combo_row(
            section, "Minimum multiplier", ["x1+", "x2+", "x3+", "x5+"],
            self._on_min_multiplier_changed
        )

        self.show_players_checkbox = self._add_checkbox(
            section, "Show player chips", self._on_show_players_toggled
        )
        self.max_player_chips_spin = self._add_slider_spin_row(
            section, "Max player chips", 1, 100,
            self._on_max_player_chips_changed,
            on_reset=self._on_max_player_chips_reset, default=COMPETITIONS_MAX_PLAYER_CHIPS_DEFAULT
        )
        self.sort_players_by_level_checkbox = self._add_checkbox(
            section, "Sort player chips by rank", self._on_sort_players_by_level_toggled
        )

        self.competitions_alert_lead_spin = self._add_slider_spin_row(
            section, "Alert lead time before start (sec)", 0, 300,
            self._on_competitions_alert_lead_changed,
            on_reset=self._on_competitions_alert_lead_reset, default=COMPETITIONS_ALERT_LEAD_DEFAULT
        )

        self.competitions_notify_window_checkbox = self._add_checkbox(
            section, "Only alert during allowed hours", self._on_competitions_notify_window_toggled
        )
        self.competitions_notify_start_spin = self._add_slider_spin_row(
            section, "From", 0, 24, self._on_competitions_notify_start_changed,
            on_reset=self._on_competitions_notify_start_reset, default=COMPETITIONS_NOTIFY_START_DEFAULT
        )
        self.competitions_notify_end_spin = self._add_slider_spin_row(
            section, "To", 0, 24, self._on_competitions_notify_end_changed,
            on_reset=self._on_competitions_notify_end_reset, default=COMPETITIONS_NOTIFY_END_DEFAULT
        )

    def _build_sound_section(self):
        section = self._create_section("🔊 Sound")
        self.mention_always_checkbox = self._add_checkbox(
            section, "Always play mention sound", self._on_mention_always_toggled
        )

        self.sound_selectors = {}
        self.sound_dir = Path(__file__).parent.parent / "sounds"
        sound_types = [
            ("mention", "Mention sound"),
            ("ban", "Ban sound"),
            ("competition", "Competition sound"),
        ]
        for kind, label in sound_types:
            selector = SoundSelectorWidget(self.config, self.sound_dir, kind, label)
            selector.combo.currentIndexChanged.connect(self._on_sound_selection_changed)
            self.sound_selectors[kind] = selector
            section.addWidget(selector)

        # Competition-sound-specific behavior, grouped together after the selectors
        self.competitions_force_sound_checkbox = self._add_checkbox(
            section, "Always play competition sound",
            self._on_competitions_force_sound_toggled
        )
        self.competition_sound_repeat_checkbox = self._add_checkbox(
            section, "Repeat competition sound until you're back",
            self._on_competition_sound_repeat_toggled
        )
        self.competition_sound_repeat_interval_spin = self._add_slider_spin_row(
            section, "Repeat interval (sec)", 3, 120, self._on_competition_sound_repeat_interval_changed,
            on_reset=self._on_competition_sound_repeat_interval_reset, default=COMPETITION_SOUND_REPEAT_INTERVAL_DEFAULT
        )

    def _on_sound_selection_changed(self, _index: int):
        self.sound_changed.emit()

    # ------------------------------------------------------------------ #
    # Config <-> UI sync
    # ------------------------------------------------------------------ #
    def refresh(self):
        """Reload every control from the current config state."""
        widgets = (
            self.auto_login_checkbox, self.start_minimized_checkbox, self.start_with_system_checkbox,
            self.clear_private_checkbox, self.youtube_checkbox,
            self.track_competitions_checkbox, self.competitions_bypass_mute_checkbox,
            self.competitions_force_sound_checkbox, self.min_multiplier_combo,
            self.show_players_checkbox, self.max_player_chips_spin, self.sort_players_by_level_checkbox,
            self.competitions_alert_lead_spin, self.competitions_notify_window_checkbox,
            self.competitions_notify_start_spin, self.competitions_notify_end_spin,
            self.notification_position_combo, self.notification_width_spin,
            self.mention_always_checkbox,
            self.competition_sound_repeat_checkbox, self.competition_sound_repeat_interval_spin,
        )
        if hasattr(self, "sound_selectors"):
            for selector in self.sound_selectors.values():
                selector.refresh()
        for widget in widgets:
            widget.blockSignals(True)

        self.auto_login_checkbox.setChecked(bool(self.config.get("startup", "auto_login")))
        self.start_minimized_checkbox.setChecked(bool(self.config.get("startup", "start_minimized")))
        self.start_with_system_checkbox.setChecked(self.startup_manager.is_enabled())

        self.clear_private_checkbox.setChecked(bool(self.config.get("ui", "clear_private_messages_on_exit")))
        youtube_enabled = self.config.get("ui", "youtube", "enabled")
        self.youtube_checkbox.setChecked(True if youtube_enabled is None else bool(youtube_enabled))

        track = self.config.get("competitions", "enabled")
        enabled = True if track is None else bool(track)
        self.track_competitions_checkbox.setChecked(enabled)
        self._update_competitions_status(enabled, None if not enabled else "connecting")
        self.competitions_bypass_mute_checkbox.setChecked(
            bool(self.config.get("notification", "competitions_bypass_mute"))
        )
        self.competitions_force_sound_checkbox.setChecked(
            bool(self.config.get("sound", "competition_sound_force"))
        )
        min_m = self.config.get("competitions", "min_multiplier") or "x1+"
        idx = self.min_multiplier_combo.findText(min_m)
        self.min_multiplier_combo.setCurrentIndex(idx if idx >= 0 else 0)

        show_players = self.config.get("competitions", "show_players")
        self.show_players_checkbox.setChecked(True if show_players is None else bool(show_players))
        self.max_player_chips_spin.setValue(int(self.config.get("competitions", "max_player_chips") or COMPETITIONS_MAX_PLAYER_CHIPS_DEFAULT))
        self.max_player_chips_spin._slider.setValue(self.max_player_chips_spin.value())
        self.sort_players_by_level_checkbox.setChecked(bool(self.config.get("competitions", "sort_players_by_level")))
        self._set_players_controls_enabled(self.show_players_checkbox.isChecked())

        self.competitions_alert_lead_spin.setValue(int(self.config.get("competitions", "alert_lead_seconds") or COMPETITIONS_ALERT_LEAD_DEFAULT))
        self.competitions_alert_lead_spin._slider.setValue(self.competitions_alert_lead_spin.value())

        self.competitions_notify_window_checkbox.setChecked(
            bool(self.config.get("competitions", "notify_window_enabled"))
        )
        self.competitions_notify_start_spin.setValue(int(self.config.get("competitions", "notify_window_start") or COMPETITIONS_NOTIFY_START_DEFAULT))
        self.competitions_notify_start_spin._slider.setValue(self.competitions_notify_start_spin.value())
        self.competitions_notify_end_spin.setValue(int(self.config.get("competitions", "notify_window_end") or COMPETITIONS_NOTIFY_END_DEFAULT))
        self.competitions_notify_end_spin._slider.setValue(self.competitions_notify_end_spin.value())
        self._set_notify_window_controls_enabled(self.competitions_notify_window_checkbox.isChecked())

        position = (self.config.get("ui", "notification_position") or "right").capitalize()
        idx = self.notification_position_combo.findText(position)
        self.notification_position_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.notification_width_spin.setValue(int(self.config.get("ui", "notification_width") or NOTIFICATION_WIDTH_DEFAULT))
        self.notification_width_spin._slider.setValue(self.notification_width_spin.value())

        self.mention_always_checkbox.setChecked(bool(self.config.get("sound", "play_mention_sound_always")))

        self.competition_sound_repeat_checkbox.setChecked(
            bool(self.config.get("sound", "competition_repeat_enabled"))
        )
        self.competition_sound_repeat_interval_spin.setValue(
            int(self.config.get("sound", "competition_repeat_interval") or COMPETITION_SOUND_REPEAT_INTERVAL_DEFAULT)
        )
        self.competition_sound_repeat_interval_spin._slider.setValue(self.competition_sound_repeat_interval_spin.value())
        self._set_spin_enabled(self.competition_sound_repeat_interval_spin, self.competition_sound_repeat_checkbox.isChecked())

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

    def _on_track_competitions_toggled(self, checked: bool):
        self.config.set("competitions", "enabled", value=checked)
        self._update_competitions_status(checked)

    def _on_competitions_bypass_mute_toggled(self, checked: bool):
        self.config.set("notification", "competitions_bypass_mute", value=checked)

    def _on_competitions_force_sound_toggled(self, checked: bool):
        self.config.set("sound", "competition_sound_force", value=checked)

    def _status_log_html(self, text: str, kind: str) -> str:
        c = self._competitions_log_colors()
        color = {
            "disabled": c["error"],
            "enabled": c["finished"],
        }.get(kind, c["default"])
        return f'<span style="color:{color}"><b>{text}</b></span>'

    def _update_competitions_status(self, enabled: bool, connection: str | None = None):
        """connection: connecting | connected | disconnected (optional).
        Log text is owned by ChatWindow buffer — do not clear it here when enabled.
        """
        if not enabled:
            self._competitions_accent_color = self._competitions_log_colors()["error"]
            self._apply_competitions_log_theme()
            self.competitions_log.setEnabled(False)
            self.competitions_log.setFixedHeight(COMPETITIONS_LOG_HEIGHT_COLLAPSED)
            self.competitions_log.setHtml(self._status_log_html("Tracking disabled", "disabled"))
            return

        self.competitions_log.setEnabled(True)
        self.competitions_log.setFixedHeight(COMPETITIONS_LOG_HEIGHT)
        plain = self.competitions_log.toPlainText().strip()
        if plain in ("", "Tracking disabled"):
            self.competitions_log.setHtml(self._status_log_html("Tracking enabled", "enabled"))

        state = connection or "connecting"
        self._competitions_accent_color = CONNECTION_STATES.get(
            state, CONNECTION_STATES["reconnecting"]
        )
        self._apply_competitions_log_theme()

    def _competitions_log_colors(self) -> dict:
        theme = self.config.get("ui", "theme") or "dark"
        return COMPETITIONS_LOG_COLORS["dark" if theme == "dark" else "light"]

    def _apply_competitions_log_theme(self):
        c = self._competitions_log_colors()
        accent = self._competitions_accent_color or c["default"]
        is_dark = (self.config.get("ui", "theme") or "dark") == "dark"
        container_bg = "#000000" if is_dark else "#FFFFFF"
        mix_ratio = 0.10 if is_dark else 0.30
        mixed_bg = blend_hex_colors(container_bg, accent, mix_ratio)
        self.competitions_log.setStyleSheet(
            f"QTextEdit {{ background-color: {mixed_bg}; color: {c['fg']}; border: none; }}"
        )

    def _colorize_log_line(self, line: str) -> str:
        from html import escape
        import re as _re
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
        html_line = _re.sub(
            r"^(\d{2}:\d{2}:\d{2}\s+)(\[?\w+\+?]?)(\s+)",
            _bold_tag,
            html_line,
            count=1,
        )
        return f'<span style="color:{color}">{html_line}</span>'

    def set_competition_log_lines(self, lines: list):
        """Replace log content from chat session buffer (HTML colored)."""
        self._apply_competitions_log_theme()
        if not lines:
            self.competitions_log.clear()
            return
        html = "<br>".join(self._colorize_log_line(x) for x in lines)
        self.competitions_log.setHtml(html)
        cursor = self.competitions_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.competitions_log.setTextCursor(cursor)

    def update_theme(self):
        """Re-apply competitions log colors after theme toggle."""
        if not hasattr(self, "competitions_log"):
            return
        lines = self.competitions_log.toPlainText().splitlines()
        if lines and lines != ["Tracking disabled"]:
            self.set_competition_log_lines(lines)
        else:
            self._apply_competitions_log_theme()

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
        QApplication.clipboard().setText(self.competitions_log.toPlainText())

    def _on_clear_log_clicked(self):
        self.competitions_log.clear()
        self.competition_log_clear_requested.emit()

    def _on_min_multiplier_changed(self, text: str):
        self.config.set("competitions", "min_multiplier", value=text)

    def _set_spin_enabled(self, spin, enabled: bool):
        spin.setEnabled(enabled)
        if hasattr(spin, "_slider"):
            spin._slider.setEnabled(enabled)

    def _set_players_controls_enabled(self, enabled: bool):
        self._set_spin_enabled(self.max_player_chips_spin, enabled)
        self.sort_players_by_level_checkbox.setEnabled(enabled)

    def _set_notify_window_controls_enabled(self, enabled: bool):
        self._set_spin_enabled(self.competitions_notify_start_spin, enabled)
        self._set_spin_enabled(self.competitions_notify_end_spin, enabled)

    def _on_show_players_toggled(self, checked: bool):
        self.config.set("competitions", "show_players", value=checked)
        self._set_players_controls_enabled(checked)

    def _on_max_player_chips_changed(self, value: int):
        self.config.set("competitions", "max_player_chips", value=value)

    def _on_max_player_chips_reset(self):
        self.max_player_chips_spin.setValue(COMPETITIONS_MAX_PLAYER_CHIPS_DEFAULT)

    def _on_sort_players_by_level_toggled(self, checked: bool):
        self.config.set("competitions", "sort_players_by_level", value=checked)

    def _on_competitions_alert_lead_changed(self, value: int):
        self.config.set("competitions", "alert_lead_seconds", value=value)

    def _on_competitions_alert_lead_reset(self):
        self.competitions_alert_lead_spin.setValue(COMPETITIONS_ALERT_LEAD_DEFAULT)

    def _on_competitions_notify_window_toggled(self, checked: bool):
        self.config.set("competitions", "notify_window_enabled", value=checked)
        self._set_notify_window_controls_enabled(checked)

    def _on_competitions_notify_start_changed(self, value: int):
        self.config.set("competitions", "notify_window_start", value=value)

    def _on_competitions_notify_start_reset(self):
        self.competitions_notify_start_spin.setValue(COMPETITIONS_NOTIFY_START_DEFAULT)

    def _on_competitions_notify_end_changed(self, value: int):
        self.config.set("competitions", "notify_window_end", value=value)

    def _on_competitions_notify_end_reset(self):
        self.competitions_notify_end_spin.setValue(COMPETITIONS_NOTIFY_END_DEFAULT)

    def _on_competition_sound_repeat_toggled(self, checked: bool):
        self.config.set("sound", "competition_repeat_enabled", value=checked)
        self._set_spin_enabled(self.competition_sound_repeat_interval_spin, checked)

    def _on_competition_sound_repeat_interval_changed(self, value: int):
        self.config.set("sound", "competition_repeat_interval", value=value)

    def _on_competition_sound_repeat_interval_reset(self):
        self.competition_sound_repeat_interval_spin.setValue(COMPETITION_SOUND_REPEAT_INTERVAL_DEFAULT)

    def _on_notification_position_changed(self, text: str):
        self.config.set("ui", "notification_position", value=text.lower())

    def _on_notification_width_changed(self, value: int):
        self.config.set("ui", "notification_width", value=value)

    def _on_notification_width_reset(self):
        self.notification_width_spin.setValue(NOTIFICATION_WIDTH_DEFAULT)

    def _on_mention_always_toggled(self, checked: bool):
        self.config.set("sound", "play_mention_sound_always", value=checked)
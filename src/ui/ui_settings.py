"""Application Settings widget"""
import re
import shutil
from html import escape
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QCheckBox, QComboBox, QSpinBox, QSlider, QMessageBox, QTextEdit,
    QApplication, QInputDialog, QFileDialog, QToolButton, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from helpers.create import create_icon_button
from components.presence_badge import TypeFilterBar, EVENT_TYPES
from helpers import hotkey_manager as hotkey
from helpers.fonts import (
    get_font,
    FontType,
    get_available_font_families,
    get_available_emoji_families,
    ensure_family_loaded,
    invalidate_font_cache,
    set_application_font,
    set_config,
)
from helpers.startup_manager import StartupManager
from helpers.voice_engine import play_sound
from helpers.data import get_data_dir
from helpers.color_utils import blend_hex_colors, tinted_chip_colors
from helpers.browser import get_available_browsers

DEFAULTS = {
    "notification": {
        "width": 550,
        "duration": 5,
        "fade_ms": 300,
    },
    "competitions": {
        "alert_lead": 0,
        "notify_start": 0,
        "notify_end": 24,
        "sound_repeat_interval": 15,
        "max_player_chips": 20,
        "log_height": 300,
        "log_height_collapsed": 32,
    },
    "chatlog": {
        "max_messages": 50000,
        "max_messages_min": 1000,
        "max_messages_max": 100000,
        "live_search_max_messages": 5000,
        "live_search_max_messages_min": 500,
        "live_search_max_messages_max": 50000,
    },
    "chat": {
        "max_messages": 1000,
        "max_messages_min": 20,
        "max_messages_max": 5000,
    }
}

FONT_PREVIEW_BORDER = 1
FONT_PREVIEW_PADDING = 6

XMPP_RESOURCE_OPTIONS = (
    ("web", "Same resource as the website. Receives private messages from the site client."),
    ("client", "Works alongside the website. May not receive private messages from the web resource."),
)

OWN_MESSAGE_MODE_OPTIONS = (
    ("local", "Show own messages immediately. Server echoes are ignored."),
    ("server", "Show own messages only when the server echoes them back."),
)

NOTIFICATION_MODE_OPTIONS = (
    ("stack",   "Stack",   "Stack notifications vertically; oldest is dropped once they no longer fit."),
    ("replace", "Replace", "Close the previous notification when a new one arrives."),
    ("scroll",  "Scroll",  "Keep every notification; scroll with the mouse wheel to see more."),
)

NOTIFICATION_HIDE_ON_OPTIONS = (
    ("manual",         "Manual",            "Auto-hide off — closes only by clicking it or the close button."),
    ("mouse",          "Mouse",             "Auto-hide countdown starts once the mouse moves."),
    ("keyboard",       "Keyboard",          "Auto-hide countdown starts once you press a key."),
    ("mouse_keyboard", "Mouse or Keyboard", "Auto-hide countdown starts on mouse or keyboard activity."),
)

ALERT_CHAT_ACTION_OPTIONS = (
    ("scroll", "Scroll to message", "Scrolls the chat to the competition message."),
    ("move",   "Move to bottom",    "Removes the competition message and reposts it at the bottom of the chat."),
)

TRACKER_CLICK_OPTIONS = (
    ("history", "Open history", "Open the User Tracker's History tab."),
    ("chat",    "Show chat",    "Open the regular chat window — messages and user list, no tracker."),
)

TRACKER_DEFAULT_TAB_OPTIONS = (
    ("tracked", "Tracked", "Open on the list of currently tracked users."),
    ("history", "History", "Open on the log of past tracker events."),
)

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


def fill_tooltip_combo(combo, options, current=None, default=None):
    """options entries are (value, tip) or (value, label, tip); label defaults to value."""
    combo.blockSignals(True)
    combo.clear()
    for entry in options:
        value, label, tip = entry if len(entry) == 3 else (entry[0], entry[0], entry[1])
        combo.addItem(label, value)
        combo.setItemData(combo.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
    selected = current or default
    index = combo.findData(selected)
    combo.setCurrentIndex(index if index >= 0 else 0)
    tip = combo.itemData(combo.currentIndex(), Qt.ItemDataRole.ToolTipRole)
    combo.setToolTip(tip or "")
    combo.blockSignals(False)


def fill_resource_combo(combo, current=None):
    fill_tooltip_combo(combo, XMPP_RESOURCE_OPTIONS, current, "web")


def fill_own_message_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, OWN_MESSAGE_MODE_OPTIONS, current, "local")


def fill_notification_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, NOTIFICATION_MODE_OPTIONS, current, "stack")


def fill_notification_hide_on_combo(combo, current=None):
    fill_tooltip_combo(combo, NOTIFICATION_HIDE_ON_OPTIONS, current, "mouse_keyboard")


def fill_alert_chat_action_combo(combo, current=None):
    fill_tooltip_combo(combo, ALERT_CHAT_ACTION_OPTIONS, current, "scroll")


def fill_tracker_click_combo(combo, current=None):
    fill_tooltip_combo(combo, TRACKER_CLICK_OPTIONS, current, "history")


def fill_tracker_default_tab_combo(combo, current=None):
    fill_tooltip_combo(combo, TRACKER_DEFAULT_TAB_OPTIONS, current, "tracked")


class NoWheelSlider(QSlider):
    """QSlider that ignores mouse wheel events, letting the parent scroll area handle scrolling instead."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events, letting the parent scroll area handle scrolling instead."""

    def wheelEvent(self, event):
        event.ignore()


class ClickableLabel(QLabel):
    """QLabel that emits clicked() on left-click."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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

        self.combo = NoWheelComboBox()
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

    def _confirm(self, title: str, text: str) -> bool:
        reply = QMessageBox.question(
            self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _require_user_owned(self, title: str, verb: str) -> str | None:
        """Return the selected file name if it's user-owned, else show why not and return None."""
        file_name = self._safe_name()
        if file_name and self._is_user_owned(file_name):
            return file_name
        QMessageBox.information(
            self, title,
            f"System sounds cannot be {verb}. Only sounds you added can be {verb}.",
        )
        return None

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

        if dest.exists() and not self._confirm(
            "File exists", f"'{dest_name}' already exists in your sounds. Overwrite?"
        ):
            return

        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            QMessageBox.warning(self, "Add sound", f"Failed to copy file: {exc}")
            return

        self.refresh(select_name=dest_name)
        self._play_file(dest_name)

    def _on_delete(self):
        file_name = self._require_user_owned("Delete sound", "deleted")
        if not file_name:
            return

        path = self.user_dir / file_name
        if not self._confirm("Delete sound", f"Delete '{file_name}'?"):
            return

        try:
            path.unlink()
        except OSError as exc:
            QMessageBox.warning(self, "Delete sound", f"Failed to delete sound: {exc}")
            return

        self.refresh()

    def _on_rename(self):
        file_name = self._require_user_owned("Rename sound", "renamed")
        if not file_name:
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
    font_family_changed = pyqtSignal()
    tracker_badge_style_changed = pyqtSignal()
    tracker_chat_log_changed = pyqtSignal(bool)
    resource_changed = pyqtSignal()

    def __init__(self, config, icons_path: Path, font_scaler=None):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.font_scaler = font_scaler
        self.startup_manager = StartupManager()
        self._competitions_accent_color = None
        self._hotkey_capture = None

        self._setup_ui()
        self.refresh()
        hotkey.hotkey_manager.status_changed.connect(self._on_hotkey_status_changed)

    # ------------------------------------------------------------------ #
    # Layout helpers
    # ------------------------------------------------------------------ #
    def _spacing(self) -> int:
        return self.config.get("ui", "spacing", "widget_elements") or 6

    def _create_section(self, title: str) -> QVBoxLayout:
        """Create a titled, collapsible section and append it to the scroll content."""
        section = QWidget()
        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(4, 4, 4, 4)
        section_layout.setSpacing(self._spacing())
        section.setLayout(section_layout)

        header_row = QHBoxLayout()
        header_row.setSpacing(self._spacing())
        label = QLabel(title)
        label.setProperty("fontRole", "header")
        label.setFont(get_font(FontType.HEADER))
        header_row.addWidget(label)
        header_row.addStretch(1)
        section_layout.addLayout(header_row)

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(self._spacing())
        content.setLayout(content_layout)
        section_layout.addWidget(content)

        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
        self._add_collapse_toggle(header_row, content, ("ui", "settings", "sections", slug), section=True)

        self._sections_layout.addWidget(section)
        return content_layout

    def _add_collapse_toggle(self, header_layout: QHBoxLayout, content: QWidget, config_path: tuple,
                               default_collapsed: bool = False, *, section: bool = False) -> QToolButton:
        stored = self.config.get(*config_path)
        collapsed = default_collapsed if stored is None else bool(stored)

        btn = QToolButton()
        btn.setCheckable(True)
        btn.setAutoRaise(True)
        btn.setArrowType(Qt.ArrowType.RightArrow if collapsed else Qt.ArrowType.DownArrow)
        btn.setChecked(collapsed)
        content.setVisible(not collapsed)

        btn._section_content = content
        btn._section_config_path = config_path

        def _on_toggled(checked):
            content.setVisible(not checked)
            btn.setArrowType(Qt.ArrowType.RightArrow if checked else Qt.ArrowType.DownArrow)
            self.config.set(*config_path, value=checked)
            if section and not checked and self._accordion_enabled():
                for other in self._section_toggles:
                    if other is not btn and not other.isChecked():
                        other.blockSignals(True)
                        other.setChecked(True)
                        other.setArrowType(Qt.ArrowType.RightArrow)
                        other._section_content.setVisible(False)
                        self.config.set(*other._section_config_path, value=True)
                        other.blockSignals(False)

        btn.toggled.connect(_on_toggled)
        header_layout.insertWidget(0, btn)
        if section:
            self._section_toggles.append(btn)
        return btn

    def _accordion_enabled(self) -> bool:
        return bool(self.config.get("ui", "settings", "accordion"))

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

        combo = NoWheelComboBox()
        combo.setFont(get_font(FontType.UI))
        combo.blockSignals(True)
        combo.addItems(items)
        combo.blockSignals(False)
        combo.setFixedWidth(240)
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

        # Default reset behavior is just "put the default back in the spin box" -
        # sync_from_spin (above) already propagates that to the slider and fires
        # on_changed, so callers only need to pass a custom on_reset when a reset
        # has to do more than restore the default value.
        if on_reset is None and default is not None:
            on_reset = lambda: spin.setValue(default)

        if on_reset:
            reset_button = create_icon_button(self.icons_path, "reload.svg", "Reset to default", size_type="small", config=self.config)
            reset_button.clicked.connect(on_reset)
            row.addWidget(reset_button)
            update_reset_state(spin.value())
            spin._reset_button = reset_button
            spin._update_reset_state = update_reset_state

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
        title_label.setProperty("fontRole", "header")
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
        self._section_toggles = []
        self.scroll.setWidget(content)

        self._build_startup_section()
        self._build_chat_section()
        self._build_fonts_section()
        self._build_notifications_section()
        self._build_competitions_section()
        self._build_user_tracker_section()
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
        section = self._create_section("🗯️ Chat")
        self.clear_private_checkbox = self._add_checkbox(
            section, "Clear private messages on exit", self._on_clear_private_toggled
        )
        self.youtube_checkbox = self._add_checkbox(
            section, "Enable YouTube link previews", self._on_youtube_toggled
        )
        self.chatlog_max_messages_spin = self._add_slider_spin_row(
            section, "Chatlog display limit",
            DEFAULTS["chatlog"]["max_messages_min"], DEFAULTS["chatlog"]["max_messages_max"],
            self._on_chatlog_max_messages_changed,
            default=DEFAULTS["chatlog"]["max_messages"],
        )
        self.chatlog_max_messages_spin.setSingleStep(1000)
        self.chatlog_max_messages_spin._slider.setSingleStep(1000)
        self.chatlog_max_messages_spin._slider.setPageStep(5000)

        self.chatlog_live_search_spin = self._add_slider_spin_row(
            section, "Chatlog live search up to (messages)",
            DEFAULTS["chatlog"]["live_search_max_messages_min"],
            DEFAULTS["chatlog"]["live_search_max_messages_max"],
            self._on_chatlog_live_search_max_changed,
            default=DEFAULTS["chatlog"]["live_search_max_messages"],
        )
        self.chatlog_live_search_spin.setSingleStep(500)
        self.chatlog_live_search_spin._slider.setSingleStep(500)
        self.chatlog_live_search_spin._slider.setPageStep(2000)

        self.parser_validate_usernames_checkbox = self._add_checkbox(
            section,
            "Validate usernames in chatlog parser (API check)",
            self._on_parser_validate_usernames_toggled,
        )

        self.chat_max_messages_spin = self._add_slider_spin_row(
            section, "Chat display limit",
            DEFAULTS["chat"]["max_messages_min"], DEFAULTS["chat"]["max_messages_max"],
            self._on_chat_max_messages_changed,
            default=DEFAULTS["chat"]["max_messages"],
        )
        self.chat_max_messages_spin.setSingleStep(100)
        self.chat_max_messages_spin._slider.setSingleStep(100)
        self.chat_max_messages_spin._slider.setPageStep(500)
        self.browser_combo = self._add_combo_row(
            section, "Open links in", [], self._on_browser_changed
        )
        self.browser_combo.setFixedWidth(240)
        self.resource_combo = self._add_combo_row(
            section, "XMPP resource", [], self._on_resource_changed
        )
        self.resource_combo.setFixedWidth(240)
        self.own_message_mode_combo = self._add_combo_row(
            section, "Own messages", [], self._on_own_message_mode_changed
        )
        self.own_message_mode_combo.setFixedWidth(240)
        self._add_hotkey_row(section, "Toggle chat window")
        self.settings_accordion_checkbox = self._add_checkbox(
            section, "Accordion settings sections (opening one collapses others)",
            self._on_settings_accordion_toggled
        )

    def _add_hotkey_row(self, section_layout: QVBoxLayout, label_text: str):
        row = QHBoxLayout()
        row.setSpacing(self._spacing())

        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label, stretch=1)

        self.hotkey_status_dot = ClickableLabel()
        self.hotkey_status_dot.setObjectName("hotkeyStatusDot")
        self.hotkey_status_dot.setFixedSize(10, 10)
        self.hotkey_status_dot.clicked.connect(self._on_hotkey_status_clicked)
        row.addWidget(self.hotkey_status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(4)

        self.hotkey_button = QPushButton()
        self.hotkey_button.setFont(get_font(FontType.UI))
        self.hotkey_button.setFixedWidth(180)
        self.hotkey_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hotkey_button.clicked.connect(self._on_hotkey_record_clicked)
        row.addWidget(self.hotkey_button)

        self.hotkey_reset_button = create_icon_button(
            self.icons_path, "reload.svg", "Reset to default", size_type="small", config=self.config
        )
        self.hotkey_reset_button.clicked.connect(self._on_hotkey_reset_clicked)
        row.addWidget(self.hotkey_reset_button)

        section_layout.addLayout(row)

    def _current_hotkey(self) -> str:
        return self.config.get("hotkey", "combo") or hotkey.DEFAULT_HOTKEY

    def _refresh_hotkey_row(self):
        combo = self._current_hotkey()
        self.hotkey_button.setText(hotkey.display_hotkey(combo))
        self.hotkey_reset_button.setEnabled(combo != hotkey.DEFAULT_HOTKEY)
        self._on_hotkey_status_changed(hotkey.hotkey_manager.status, "")

    def _on_hotkey_record_clicked(self):
        if self._hotkey_capture is not None:
            return
        self.hotkey_button.setText("Press keys…")
        self.hotkey_button.setEnabled(False)
        self.hotkey_reset_button.setEnabled(False)
        self._hotkey_capture = hotkey.HotkeyCapture()
        self._hotkey_capture.captured.connect(self._on_hotkey_captured)
        self._hotkey_capture.cancelled.connect(self._on_hotkey_capture_cancelled)
        self._hotkey_capture.start()

    def _on_hotkey_captured(self, combo: str):
        self._hotkey_capture = None
        self.hotkey_button.setEnabled(True)
        self.config.set("hotkey", "combo", value=combo)
        hotkey.hotkey_manager.register(combo)
        self._refresh_hotkey_row()

    def _on_hotkey_capture_cancelled(self):
        self._hotkey_capture = None
        self.hotkey_button.setEnabled(True)
        self._refresh_hotkey_row()

    def _on_hotkey_reset_clicked(self):
        self.config.set("hotkey", "combo", value=hotkey.DEFAULT_HOTKEY)
        hotkey.hotkey_manager.register(hotkey.DEFAULT_HOTKEY)
        self._refresh_hotkey_row()

    def _on_hotkey_status_changed(self, status: str, detail: str):
        color = hotkey.STATUS_COLORS.get(status, hotkey.STATUS_COLORS[hotkey.STATUS_DISABLED])
        tooltip = detail or hotkey.STATUS_TOOLTIPS.get(status, "")
        can_retry = status != hotkey.STATUS_ACTIVE
        is_dark = (self.config.get("ui", "theme") or "dark") == "dark"
        tooltip_bg, tooltip_fg, tooltip_border = tinted_chip_colors(color, is_dark)
        self.hotkey_status_dot.setStyleSheet(
            f"#hotkeyStatusDot {{ background-color: {color}; border-radius: 5px; }}"
            f"QToolTip {{ background-color: {tooltip_bg}; color: {tooltip_fg}; border: 1px solid {tooltip_border}; }}"
        )
        self.hotkey_status_dot.setToolTip(tooltip + " (click to retry)" if can_retry else tooltip)
        self.hotkey_status_dot.setCursor(
            Qt.CursorShape.PointingHandCursor if can_retry else Qt.CursorShape.ArrowCursor
        )

    def _on_hotkey_status_clicked(self):
        if hotkey.hotkey_manager.status == hotkey.STATUS_ACTIVE:
            return
        hotkey.hotkey_manager.register(self._current_hotkey())

    def _build_fonts_section(self):
        section = self._create_section("🅰️ Fonts")
        # Combos start empty - refresh() (called right after _setup_ui in
        # __init__) is the single place that queries available families and
        # fills them, so there's no point doing it twice on every construction.
        self.ui_font_combo = self._add_combo_row(
            section, "UI font", [], self._on_ui_font_changed
        )
        self.ui_font_size_spin = self._add_slider_spin_row(
            section, "UI size", 10, 18, self._on_ui_font_size_changed,
            default=12
        )
        self.text_font_combo = self._add_combo_row(
            section, "Text font", [], self._on_text_font_changed
        )
        self.text_font_size_spin = self._add_slider_spin_row(
            section, "Text size", 12, 24, self._on_text_font_size_changed,
            default=15
        )
        self.emoji_font_combo = self._add_combo_row(
            section, "Emoji font", [], self._on_emoji_font_changed
        )
        self.ui_font_combo.setFixedWidth(240)
        self.text_font_combo.setFixedWidth(240)
        self.emoji_font_combo.setFixedWidth(240)

        preview_header_row = QHBoxLayout()
        preview_header_row.setSpacing(self._spacing())
        preview_label = QLabel("🔎 Preview")
        preview_label.setFont(get_font(FontType.UI))
        preview_header_row.addWidget(preview_label)
        preview_header_row.addStretch(1)
        section.addLayout(preview_header_row)

        self.font_preview = QTextEdit()
        self.font_preview.setProperty("fontRole", "text")
        self.font_preview.setReadOnly(True)
        self.font_preview.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.font_preview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.font_preview.setPlainText(
            "Шла Маша по шоссе и сосала сушку\n"
            "The quick brown fox jumps over the lazy dog\n"
            "0 1 2 3 4 5 6 7 8 9\n"
            "😀 🎉 🚀 ❤️ 👍 🔥 ✨"
        )
        self._apply_font_preview_theme()
        section.addWidget(self.font_preview)
        self._update_font_preview()

        self._add_collapse_toggle(preview_header_row, self.font_preview, ("ui", "settings", "widgets", "font_preview"))

    def _build_notifications_section(self):
        section = self._create_section("⚠️ Notifications")
        self.notification_mode_combo = self._add_combo_row(
            section, "Notification mode", [], self._on_notification_mode_changed
        )
        self.notification_position_combo = self._add_combo_row(
            section, "Notification position", ["Right", "Left", "Center"],
            self._on_notification_position_changed
        )
        self.notification_width_spin = self._add_slider_spin_row(
            section, "Notification width", DEFAULTS["notification"]["width"], 1000, self._on_notification_width_changed,
            default=DEFAULTS["notification"]["width"],
        )
        self.notification_hide_on_combo = self._add_combo_row(
            section, "Hide notifications on", [], self._on_notification_hide_on_changed
        )
        self.notification_duration_spin = self._add_slider_spin_row(
            section,
            "Auto-hide delay (seconds)",
            1, 60,
            self._on_notification_duration_changed,
            default=DEFAULTS["notification"]["duration"],
        )
        self.notification_fade_spin = self._add_slider_spin_row(
            section,
            "Fade duration (ms)",
            50, 2000,
            self._on_notification_fade_changed,
            default=DEFAULTS["notification"]["fade_ms"],
        )

        self.competitions_bypass_mute_checkbox = self._add_checkbox(
            section, "Notify about competitions even when notifications are disabled",
            self._on_competitions_bypass_mute_toggled
        )
        self.mentions_bypass_mute_checkbox = self._add_checkbox(
            section, "Notify about mentions and private messages even when notifications are disabled",
            self._on_mentions_bypass_mute_toggled
        )
        self.bans_bypass_mute_checkbox = self._add_checkbox(
            section, "Notify about bans even when notifications are disabled",
            self._on_bans_bypass_mute_toggled
        )
        self.tracker_notify_checkbox = self._add_checkbox(
            section, "Notify about tracked user even when notifications are disabled",
            self._on_tracker_notify_toggled
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
        self.competitions_log.setFixedHeight(DEFAULTS["competitions"]["log_height"])
        self.competitions_log.setFont(get_font(FontType.UI))
        self.competitions_log.setPlaceholderText("Competition log")
        self.competitions_log.setAcceptRichText(True)
        self._apply_competitions_log_theme()
        section.addWidget(self.competitions_log)

        self._add_collapse_toggle(log_header_row, self.competitions_log, ("ui", "settings", "widgets", "ws_log"))

        self.min_multiplier_combo = self._add_combo_row(
            section, "Minimum multiplier", ["x1+", "x2+", "x3+", "x5+"],
            self._on_min_multiplier_changed
        )

        self.show_cost_checkbox = self._add_checkbox(
            section, "Show competition cost", self._on_show_cost_toggled
        )

        self.show_players_checkbox = self._add_checkbox(
            section, "Show player chips", self._on_show_players_toggled
        )
        self.max_player_chips_spin = self._add_slider_spin_row(
            section, "Max player chips", 1, 100,
            self._on_max_player_chips_changed,
            default=DEFAULTS["competitions"]["max_player_chips"],
        )
        self.sort_players_by_level_checkbox = self._add_checkbox(
            section, "Sort player chips by rank", self._on_sort_players_by_level_toggled
        )

        self.competitions_alert_lead_spin = self._add_slider_spin_row(
            section, "Alert lead time before start (seconds)", 0, 300,
            self._on_competitions_alert_lead_changed,
            default=DEFAULTS["competitions"]["alert_lead"],
        )

        self.alert_chat_action_combo = self._add_combo_row(
            section, "On alert in chat", [], self._on_alert_chat_action_changed
        )

        self.competitions_notify_window_checkbox = self._add_checkbox(
            section, "Only alert during allowed hours", self._on_competitions_notify_window_toggled
        )
        self.competitions_notify_start_spin = self._add_slider_spin_row(
            section, "From", 0, 24, self._on_competitions_notify_start_changed,
            default=DEFAULTS["competitions"]["notify_start"],
        )
        self.competitions_notify_end_spin = self._add_slider_spin_row(
            section, "To", 0, 24, self._on_competitions_notify_end_changed,
            default=DEFAULTS["competitions"]["notify_end"],
        )


    def _build_user_tracker_section(self):
        section = self._create_section("🗿 User Tracker")
        self.tracker_enabled_checkbox = self._add_checkbox(
            section, "Track users",
            self._on_tracker_enabled_toggled
        )
        self.tracker_notifications_checkbox = self._add_checkbox(
            section, "Show events in notifications",
            self._on_tracker_notifications_toggled
        )
        self.tracker_notifications_auto_hide_checkbox = self._add_checkbox(
            section, "Auto-hide notifications after duration (ignore mouse/keyboard rules)",
            self._on_tracker_notifications_auto_hide_toggled
        )
        self.tracker_chat_log_checkbox = self._add_checkbox(
            section, "Show events in chat",
            self._on_tracker_chat_log_toggled
        )
        self.tracker_badge_checkbox = self._add_checkbox(
            section, "Show unread badge on tracker button",
            self._on_tracker_badge_toggled
        )
        self.tracker_badge_size_spin = self._add_slider_spin_row(
            section, "Badge font size", 8, 18,
            self._on_tracker_badge_size_changed, default=9
        )
        # Tracked event types — same pills as tracker filter bar
        events_row = QHBoxLayout()
        events_row.setSpacing(8)
        events_label = QLabel("Track events:")
        events_label.setFont(get_font(FontType.UI))
        events_row.addWidget(events_label)
        theme = self.config.get("ui", "theme") or "dark"
        self.tracker_events_bar = TypeFilterBar(empty_means_all=False, is_dark=(theme == "dark"))
        self.tracker_events_bar.changed.connect(self._on_tracker_events_changed)
        events_row.addWidget(self.tracker_events_bar, stretch=1)
        section.addLayout(events_row)
        self._build_tracker_retention_row(section)
        self.tracker_default_tab_combo = self._add_combo_row(
            section, "Default tab on open", [], self._on_tracker_default_tab_changed
        )
        self.tracker_click_combo = self._add_combo_row(
            section, "On notification click", [], self._on_tracker_click_action_changed
        )

    def _build_sound_section(self):
        section = self._create_section("🔊 Sound")
        self.mention_always_checkbox = self._add_checkbox(
            section, "Play mention sound even when chat is focused",
            self._on_mention_always_toggled
        )
        self.competition_always_checkbox = self._add_checkbox(
            section, "Play competition sound even when chat is focused",
            self._on_competition_always_toggled
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

        self.competition_sound_repeat_checkbox = self._add_checkbox(
            section, "Repeat competition sound until you're back",
            self._on_competition_sound_repeat_toggled
        )
        self.competition_sound_repeat_interval_spin = self._add_slider_spin_row(
            section, "Repeat interval (seconds)", 3, 120, self._on_competition_sound_repeat_interval_changed,
            default=DEFAULTS["competitions"]["sound_repeat_interval"],
        )

    def _on_sound_selection_changed(self, _index: int):
        self.sound_changed.emit()

    # ------------------------------------------------------------------ #
    # Config <-> UI sync
    # ------------------------------------------------------------------ #
    def refresh(self):
        """Reload every control from the current config state."""
        widgets = (
            self.settings_accordion_checkbox, self.auto_login_checkbox,
            self.start_minimized_checkbox, self.start_with_system_checkbox,
            self.resource_combo, self.own_message_mode_combo,
            self.clear_private_checkbox, self.youtube_checkbox,
            self.chatlog_max_messages_spin, self.chatlog_live_search_spin,
            self.parser_validate_usernames_checkbox, self.browser_combo,
            self.track_competitions_checkbox, self.competitions_bypass_mute_checkbox,
            self.mentions_bypass_mute_checkbox, self.bans_bypass_mute_checkbox,
            self.tracker_notify_checkbox, self.tracker_enabled_checkbox,
            self.tracker_notifications_checkbox, self.tracker_notifications_auto_hide_checkbox,
            self.tracker_chat_log_checkbox, self.tracker_badge_checkbox,
            self.min_multiplier_combo,
            self.show_cost_checkbox,
            self.show_players_checkbox, self.max_player_chips_spin, self.sort_players_by_level_checkbox,
            self.competitions_alert_lead_spin, self.alert_chat_action_combo,
            self.competitions_notify_window_checkbox,
            self.competitions_notify_start_spin, self.competitions_notify_end_spin,
            self.notification_mode_combo, self.notification_position_combo, self.notification_width_spin,
            self.notification_hide_on_combo, self.notification_duration_spin, self.notification_fade_spin,
            self.mention_always_checkbox, self.competition_always_checkbox,
            self.competition_sound_repeat_checkbox, self.competition_sound_repeat_interval_spin,
        )
        if hasattr(self, "sound_selectors"):
            for selector in self.sound_selectors.values():
                selector.refresh()
        for widget in widgets:
            widget.blockSignals(True)

        self.settings_accordion_checkbox.setChecked(
            bool(self.config.get("ui", "settings", "accordion"))
        )
        self.auto_login_checkbox.setChecked(bool(self.config.get("startup", "auto_login")))
        self.start_minimized_checkbox.setChecked(bool(self.config.get("startup", "start_minimized")))
        self.start_with_system_checkbox.setChecked(self.startup_manager.is_enabled())

        fill_resource_combo(
            self.resource_combo,
            self.config.get("server", "resource") or "web",
        )
        fill_own_message_mode_combo(
            self.own_message_mode_combo,
            self.config.get("ui", "own_message_mode") or "local",
        )

        self.clear_private_checkbox.setChecked(bool(self.config.get("ui", "clear_private_messages_on_exit")))

        youtube_enabled = self.config.get("ui", "youtube", "enabled")
        self.youtube_checkbox.setChecked(True if youtube_enabled is None else bool(youtube_enabled))

        max_messages = self.config.get("ui", "chatlog", "max_messages")
        max_messages = DEFAULTS["chatlog"]["max_messages"] if max_messages is None else int(max_messages)
        max_messages = max(
            DEFAULTS["chatlog"]["max_messages_min"],
            min(DEFAULTS["chatlog"]["max_messages_max"], max_messages),
        )
        self.chatlog_max_messages_spin.setValue(max_messages)
        self.chatlog_max_messages_spin._slider.setValue(max_messages)

        live_search_max = self.config.get("ui", "chatlog", "live_search_max_messages")
        live_search_max = DEFAULTS["chatlog"]["live_search_max_messages"] if live_search_max is None else int(live_search_max)
        live_search_max = max(
            DEFAULTS["chatlog"]["live_search_max_messages_min"],
            min(DEFAULTS["chatlog"]["live_search_max_messages_max"], live_search_max),
        )
        self.chatlog_live_search_spin.setValue(live_search_max)
        self.chatlog_live_search_spin._slider.setValue(live_search_max)

        validate_usernames = self.config.get("chatlog_parser", "validate_usernames")
        self.parser_validate_usernames_checkbox.setChecked(
            True if validate_usernames is None else bool(validate_usernames)
        )

        chat_max_messages = self.config.get("ui", "chat", "max_messages")
        chat_max_messages = DEFAULTS["chat"]["max_messages"] if chat_max_messages is None else int(chat_max_messages)
        chat_max_messages = max(
            DEFAULTS["chat"]["max_messages_min"],
            min(DEFAULTS["chat"]["max_messages_max"], chat_max_messages),
        )
        self.chat_max_messages_spin.setValue(chat_max_messages)
        self.chat_max_messages_spin._slider.setValue(chat_max_messages)

        browsers = get_available_browsers()
        self.browser_combo.blockSignals(True)
        self.browser_combo.clear()
        for display_name, key in browsers:
            self.browser_combo.addItem(display_name, key)
        current_browser = self.config.get("browser") or "system"
        idx = self.browser_combo.findData(current_browser)
        self.browser_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.browser_combo.blockSignals(False)

        self._refresh_hotkey_row()

        families = get_available_font_families() or ["Roboto"]
        for combo, kind in (
            (self.ui_font_combo, "ui"),
            (self.text_font_combo, "text"),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(families)
            current = self.config.get("font", kind, "family") or "Roboto"
            idx = combo.findText(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

        emoji_families = get_available_emoji_families() or ["Noto Color Emoji"]
        self.emoji_font_combo.blockSignals(True)
        self.emoji_font_combo.clear()
        self.emoji_font_combo.addItems(emoji_families)
        current_emoji = self.config.get("font", "emoji_family") or "Noto Color Emoji"
        idx = self.emoji_font_combo.findText(current_emoji)
        self.emoji_font_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.emoji_font_combo.blockSignals(False)

        ui_size = int(self.config.get("font", "ui", "size") or 12)
        text_size = (
            self.font_scaler.get_text_size()
            if self.font_scaler
            else int(self.config.get("font", "text", "size") or 15)
        )
        for spin, val in (
            (self.ui_font_size_spin, ui_size),
            (self.text_font_size_spin, text_size),
        ):
            spin.blockSignals(True)
            spin.setValue(val)
            spin._slider.blockSignals(True)
            spin._slider.setValue(val)
            spin._slider.blockSignals(False)
            spin.blockSignals(False)

        self._update_font_preview()

        track = self.config.get("competitions", "enabled")
        enabled = True if track is None else bool(track)
        self.track_competitions_checkbox.setChecked(enabled)
        self._update_competitions_status(enabled, None if not enabled else "connecting")
        self.competitions_bypass_mute_checkbox.setChecked(
            bool(self.config.get("notification", "competitions_bypass_mute"))
        )
        self.mentions_bypass_mute_checkbox.setChecked(
            bool(self.config.get("notification", "mentions_bypass_mute"))
        )
        self.bans_bypass_mute_checkbox.setChecked(
            bool(self.config.get("notification", "bans_bypass_mute"))
        )
        self.tracker_notify_checkbox.setChecked(
            bool(self.config.get("notification", "tracked_bypass_mute"))
        )
        self.tracker_enabled_checkbox.setChecked(
            bool(self.config.get("user_tracker", "enabled")
                 if self.config.get("user_tracker", "enabled") is not None else True)
        )
        tracker_notify = self.config.get("user_tracker", "notifications")
        self.tracker_notifications_checkbox.setChecked(
            True if tracker_notify is None else bool(tracker_notify)
        )
        self.tracker_notifications_auto_hide_checkbox.setChecked(
            bool(self.config.get("user_tracker", "notifications_auto_hide"))
        )
        self.tracker_notifications_auto_hide_checkbox.setEnabled(
            self.tracker_notifications_checkbox.isChecked()
        )
        chat_log = self.config.get("user_tracker", "chat_log")
        self.tracker_chat_log_checkbox.setChecked(True if chat_log is None else bool(chat_log))

        tracker_badge = self.config.get("user_tracker", "show_badge")
        self.tracker_badge_checkbox.setChecked(
            True if tracker_badge is None else bool(tracker_badge)
        )
        badge_size = self.config.get("user_tracker", "badge_font_size")
        try:
            badge_size = int(badge_size) if badge_size is not None else 9
        except (TypeError, ValueError):
            badge_size = 9
        self.tracker_badge_size_spin.setValue(max(8, min(18, badge_size)))
        track_events = self.config.get("user_tracker", "track_events")
        if not track_events:
            track_events = list(EVENT_TYPES)
        self.tracker_events_bar.set_active_types(track_events)
        self._sync_tracker_retention_ui_from_config()
        fill_tracker_default_tab_combo(self.tracker_default_tab_combo, self.config.get("user_tracker", "default_tab"))

        fill_tracker_click_combo(self.tracker_click_combo, self.config.get("user_tracker", "click_action"))

        min_m = self.config.get("competitions", "min_multiplier") or "x1+"
        idx = self.min_multiplier_combo.findText(min_m)
        self.min_multiplier_combo.setCurrentIndex(idx if idx >= 0 else 0)

        show_cost = self.config.get("competitions", "show_cost")
        self.show_cost_checkbox.setChecked(True if show_cost is None else bool(show_cost))

        show_players = self.config.get("competitions", "show_players")
        self.show_players_checkbox.setChecked(True if show_players is None else bool(show_players))
        self.max_player_chips_spin.setValue(int(self.config.get("competitions", "max_player_chips") or DEFAULTS["competitions"]["max_player_chips"]))
        self.max_player_chips_spin._slider.setValue(self.max_player_chips_spin.value())
        self.sort_players_by_level_checkbox.setChecked(bool(self.config.get("competitions", "sort_players_by_level")))
        self._set_players_controls_enabled(self.show_players_checkbox.isChecked())

        self.competitions_alert_lead_spin.setValue(int(self.config.get("competitions", "alert_lead_seconds") or DEFAULTS["competitions"]["alert_lead"]))
        self.competitions_alert_lead_spin._slider.setValue(self.competitions_alert_lead_spin.value())

        fill_alert_chat_action_combo(self.alert_chat_action_combo, self.config.get("competitions", "alert_chat_action"))

        self.competitions_notify_window_checkbox.setChecked(
            bool(self.config.get("competitions", "notify_window_enabled"))
        )
        self.competitions_notify_start_spin.setValue(int(self.config.get("competitions", "notify_window_start") or DEFAULTS["competitions"]["notify_start"]))
        self.competitions_notify_start_spin._slider.setValue(self.competitions_notify_start_spin.value())
        self.competitions_notify_end_spin.setValue(int(self.config.get("competitions", "notify_window_end") or DEFAULTS["competitions"]["notify_end"]))
        self.competitions_notify_end_spin._slider.setValue(self.competitions_notify_end_spin.value())
        self._set_notify_window_controls_enabled(self.competitions_notify_window_checkbox.isChecked())

        fill_notification_mode_combo(self.notification_mode_combo, self.config.get("notification", "mode"))

        position = (self.config.get("ui", "notification_position") or "right").capitalize()
        idx = self.notification_position_combo.findText(position)
        self.notification_position_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.notification_width_spin.setValue(int(self.config.get("ui", "notification_width") or DEFAULTS["notification"]["width"]))
        self.notification_width_spin._slider.setValue(self.notification_width_spin.value())

        fill_notification_hide_on_combo(self.notification_hide_on_combo, self.config.get("notification", "hide_on"))

        duration_ms = self.config.get("notification", "duration_ms")
        try:
            duration_ms = int(duration_ms) if duration_ms is not None else DEFAULTS["notification"]["duration"] * 1000
        except (TypeError, ValueError):
            duration_ms = DEFAULTS["notification"]["duration"] * 1000
        duration = max(1, round(duration_ms / 1000))
        self.notification_duration_spin.setValue(duration)
        self.notification_duration_spin._slider.setValue(duration)
        fade_ms = self.config.get("notification", "fade_ms")
        try:
            fade_ms = int(fade_ms) if fade_ms is not None else DEFAULTS["notification"]["fade_ms"]
        except (TypeError, ValueError):
            fade_ms = DEFAULTS["notification"]["fade_ms"]
        fade_ms = max(50, min(2000, fade_ms))
        self.notification_fade_spin.setValue(fade_ms)
        self.notification_fade_spin._slider.setValue(fade_ms)

        mention_always = self.config.get("sound", "play_mention_sound_always")
        self.mention_always_checkbox.setChecked(False if mention_always is None else bool(mention_always))

        competition_always = self.config.get("sound", "play_competition_sound_always")
        self.competition_always_checkbox.setChecked(True if competition_always is None else bool(competition_always))

        self.competition_sound_repeat_checkbox.setChecked(
            bool(self.config.get("sound", "competition_repeat_enabled"))
        )
        self.competition_sound_repeat_interval_spin.setValue(
            int(self.config.get("sound", "competition_repeat_interval") or DEFAULTS["competitions"]["sound_repeat_interval"])
        )
        self.competition_sound_repeat_interval_spin._slider.setValue(self.competition_sound_repeat_interval_spin.value())
        self._set_spin_enabled(self.competition_sound_repeat_interval_spin, self.competition_sound_repeat_checkbox.isChecked())

        for widget in widgets:
            widget.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #
    def _on_settings_accordion_toggled(self, checked: bool):
        self.config.set("ui", "settings", "accordion", value=checked)

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

    def _sync_combo_tooltip(self, combo):
        tip = combo.itemData(combo.currentIndex(), Qt.ItemDataRole.ToolTipRole)
        combo.setToolTip(tip or "")

    def _on_resource_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.resource_combo)
        value = self.resource_combo.currentData()
        if value is None:
            return
        previous = self.config.get("server", "resource") or "web"
        if value == previous:
            return
        self.config.set("server", "resource", value=value)
        print(f"📡 XMPP resource changed: {previous} → {value}")
        self.resource_changed.emit()

    def _on_own_message_mode_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.own_message_mode_combo)
        value = self.own_message_mode_combo.currentData()
        if value is None:
            return
        previous = self.config.get("ui", "own_message_mode") or "local"
        if value == previous:
            return
        self.config.set("ui", "own_message_mode", value=value)
        print(f"💬 Own message mode: {value}")

    def _on_clear_private_toggled(self, checked: bool):
        self.config.set("ui", "clear_private_messages_on_exit", value=checked)

    def _on_youtube_toggled(self, checked: bool):
        self.config.set("ui", "youtube", "enabled", value=checked)

    def _on_chatlog_max_messages_changed(self, value: int):
        self.config.set("ui", "chatlog", "max_messages", value=int(value))

    def _on_chatlog_live_search_max_changed(self, value: int):
        self.config.set("ui", "chatlog", "live_search_max_messages", value=int(value))

    def _on_parser_validate_usernames_toggled(self, checked: bool):
        self.config.set("chatlog_parser", "validate_usernames", value=checked)

    def _on_chat_max_messages_changed(self, value: int):
        self.config.set("ui", "chat", "max_messages", value=int(value))

    def _on_browser_changed(self, _text: str = ""):
        key = self.browser_combo.currentData()
        if key is not None:
            self.config.set("browser", value=key)

    def _apply_font_preview_theme(self):
        if not hasattr(self, "font_preview"):
            return
        theme = self.config.get("ui", "theme") or "dark"
        if theme == "dark":
            bg, fg, border = "#1E1E1E", "#D4D4D4", "#3C3C3C"
        else:
            bg, fg, border = "#F5F5F5", "#333333", "#CCCCCC"
        self.font_preview.setStyleSheet(
            f"QTextEdit {{ background-color: {bg}; color: {fg}; "
            f"border: {FONT_PREVIEW_BORDER}px solid {border}; border-radius: 4px; "
            f"padding: {FONT_PREVIEW_PADDING}px; }}"
        )

    def _update_font_preview(self):
        if not hasattr(self, "font_preview"):
            return
        self.font_preview.setFont(get_font(FontType.TEXT))
        self._apply_font_preview_theme()
        self._fit_font_preview_height()

    def _fit_font_preview_height(self):
        """Grow/shrink preview block to fit content without clipping, keeping the
        top and bottom gap identical (uses the same border/padding constants as
        the stylesheet instead of guessed frame/margin values)."""
        preview = self.font_preview
        doc = preview.document()
        width = preview.viewport().width()
        if width < 50:
            width = max(preview.width() - 20, 300)
        doc.setTextWidth(width)
        vertical_chrome = 2 * (FONT_PREVIEW_BORDER + FONT_PREVIEW_PADDING)
        height = int(doc.size().height()) + vertical_chrome
        preview.setFixedHeight(max(48, height))

    def _apply_font_family(self, kind: str, family: str):
        if not family:
            return
        self.config.set("font", kind, "family", value=family)
        set_config(self.config)
        ensure_family_loaded(family)
        invalidate_font_cache()
        app = QApplication.instance()
        if app:
            set_application_font(app)
        self._update_font_preview()
        self.font_family_changed.emit()

    def _on_ui_font_changed(self, _text: str = ""):
        self._apply_font_family("ui", self.ui_font_combo.currentText())

    def _on_text_font_changed(self, _text: str = ""):
        self._apply_font_family("text", self.text_font_combo.currentText())

    def _on_emoji_font_changed(self, _text: str = ""):
        family = self.emoji_font_combo.currentText()
        if not family:
            return
        self.config.set("font", "emoji_family", value=family)
        set_config(self.config)
        invalidate_font_cache()
        app = QApplication.instance()
        if app:
            set_application_font(app)
        self._update_font_preview()
        self.font_family_changed.emit()

    def _on_ui_font_size_changed(self, value: int):
        # Debounce: slider fires every step; only persist/apply after idle.
        if not hasattr(self, "_ui_font_size_timer"):
            self._ui_font_size_timer = QTimer(self)
            self._ui_font_size_timer.setSingleShot(True)
            self._ui_font_size_timer.timeout.connect(self._commit_ui_font_size)
        self._pending_ui_font_size = value
        self._ui_font_size_timer.start(80)

    def _commit_ui_font_size(self):
        value = getattr(self, "_pending_ui_font_size", None)
        if value is None:
            return
        self.config.set("font", "ui", "size", value=value)
        set_config(self.config)
        invalidate_font_cache()
        app = QApplication.instance()
        if app:
            set_application_font(app)
        self.competitions_log.setFont(get_font(FontType.UI))
        if not self.competitions_log.isEnabled():
            self.competitions_log.setFixedHeight(self._collapsed_log_height())
        self.font_family_changed.emit()

    def _on_text_font_size_changed(self, value: int):
        if self.font_scaler:
            self.font_scaler.set_size(value)
        else:
            self.config.set("font", "text", "size", value=value)
            invalidate_font_cache()
            self.font_family_changed.emit()
        self._update_font_preview()

    def _on_track_competitions_toggled(self, checked: bool):
        self.config.set("competitions", "enabled", value=checked)
        self._update_competitions_status(checked)

    def _on_competitions_bypass_mute_toggled(self, checked: bool):
        self.config.set("notification", "competitions_bypass_mute", value=checked)

    def _on_mentions_bypass_mute_toggled(self, checked: bool):
        self.config.set("notification", "mentions_bypass_mute", value=checked)

    def _on_bans_bypass_mute_toggled(self, checked: bool):
        self.config.set("notification", "bans_bypass_mute", value=checked)

    def _on_tracker_notify_toggled(self, checked: bool):
        self.config.set("notification", "tracked_bypass_mute", value=checked)

    def _on_tracker_enabled_toggled(self, checked: bool):
        self.config.set("user_tracker", "enabled", value=checked)
        self.tracker_badge_style_changed.emit()

    def _on_tracker_notifications_toggled(self, checked: bool):
        self.config.set("user_tracker", "notifications", value=checked)
        self.tracker_notifications_auto_hide_checkbox.setEnabled(checked)

    def _on_tracker_notifications_auto_hide_toggled(self, checked: bool):
        self.config.set("user_tracker", "notifications_auto_hide", value=checked)

    def _on_tracker_chat_log_toggled(self, checked: bool):
        self.config.set("user_tracker", "chat_log", value=checked)
        self.tracker_chat_log_changed.emit(checked)

    def _on_tracker_badge_toggled(self, checked: bool):
        self.config.set("user_tracker", "show_badge", value=checked)
        self.tracker_badge_style_changed.emit()

    def _on_tracker_badge_size_changed(self, value: int):
        self.config.set("user_tracker", "badge_font_size", value=int(value))
        self.tracker_badge_style_changed.emit()

    def _on_tracker_events_changed(self, types):
        # Keep at least one type enabled
        active = list(types) if types else list(EVENT_TYPES)
        if not types:
            self.tracker_events_bar.set_active_types(EVENT_TYPES)
            active = list(EVENT_TYPES)
        self.config.set("user_tracker", "track_events", value=active)


    def _build_tracker_retention_row(self, section_layout):
        self.tracker_retention_spin = self._add_slider_spin_row(
            section_layout, "History retention", 1, 168,
            self._on_tracker_retention_value_changed,
            on_reset=self._on_tracker_retention_reset,
            default=24,
        )
        row = section_layout.itemAt(section_layout.count() - 1).layout()
        self.tracker_retention_unit_combo = NoWheelComboBox()
        self.tracker_retention_unit_combo.setFont(get_font(FontType.UI))
        self.tracker_retention_unit_combo.addItem("hours", "hours")
        self.tracker_retention_unit_combo.addItem("days", "days")
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
        self.tracker_retention_spin._slider.setRange(1, maximum)
        self.tracker_retention_spin.setRange(1, maximum)
        self._set_retention_widgets_blocked(False)

    def _set_tracker_retention_display(self, value: int):
        self._set_retention_widgets_blocked(True)
        self.tracker_retention_spin._slider.setValue(value)
        self.tracker_retention_spin.setValue(value)
        self._set_retention_widgets_blocked(False)
        btn = getattr(self.tracker_retention_spin, "_reset_button", None)
        if btn is not None:
            btn.setEnabled(self._tracker_retention_unit() != "hours" or value != 24)

    def _set_retention_widgets_blocked(self, blocked: bool):
        self.tracker_retention_spin._slider.blockSignals(blocked)
        self.tracker_retention_spin.blockSignals(blocked)

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
        self._sync_combo_tooltip(self.tracker_default_tab_combo)
        value = self.tracker_default_tab_combo.currentData() or "tracked"
        self.config.set("user_tracker", "default_tab", value=value)

    def _on_tracker_click_action_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.tracker_click_combo)
        value = self.tracker_click_combo.currentData() or "history"
        self.config.set("user_tracker", "click_action", value=value)

    def _status_log_html(self, text: str, kind: str) -> str:
        c = self._competitions_log_colors()
        color = {
            "disabled": c["error"],
            "enabled": c["finished"],
        }.get(kind, c["default"])
        return f'<span style="color:{color}"><b>{text}</b></span>'

    def _collapsed_log_height(self) -> int:
        return max(DEFAULTS["competitions"]["log_height_collapsed"], self.competitions_log.fontMetrics().height() + 16)

    def _update_competitions_status(self, enabled: bool, connection: str | None = None):
        """connection: connecting | connected | disconnected (optional).
        Log text is owned by ChatWindow buffer — do not clear it here when enabled.
        """
        if not enabled:
            self._competitions_accent_color = self._competitions_log_colors()["error"]
            self._apply_competitions_log_theme()
            self.competitions_log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.competitions_log.setEnabled(False)
            self.competitions_log.setFixedHeight(self._collapsed_log_height())
            self.competitions_log.setHtml(self._status_log_html("Tracking disabled", "disabled"))
            return

        self.competitions_log.setEnabled(True)
        self.competitions_log.setFixedHeight(DEFAULTS["competitions"]["log_height"])
        plain = self.competitions_log.toPlainText().strip()
        if plain in ("", "Tracking disabled"):
            self.competitions_log.setHtml(self._status_log_html("Tracking enabled", "enabled"))

        state = connection or "connecting"
        self._competitions_accent_color = CONNECTION_STATES.get(
            state, CONNECTION_STATES["reconnecting"]
        )
        self._apply_competitions_log_theme()
        self.competitions_log.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if state == "disconnected"
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

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
            f"QTextEdit {{ background-color: {mixed_bg}; color: {c['fg']}; border: none; padding: 6px 8px; }}"
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
        """Re-apply theme-dependent colors after a theme toggle (competitions log + font preview)."""
        theme = self.config.get("ui", "theme") or "dark"
        if hasattr(self, "tracker_events_bar"):
            self.tracker_events_bar.update_theme(theme == "dark")
        self._apply_font_preview_theme()
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

    def _on_show_cost_toggled(self, checked: bool):
        self.config.set("competitions", "show_cost", value=checked)

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
        self._sync_combo_tooltip(self.alert_chat_action_combo)
        value = self.alert_chat_action_combo.currentData() or "scroll"
        self.config.set("competitions", "alert_chat_action", value=value)

    def _on_competitions_notify_window_toggled(self, checked: bool):
        self.config.set("competitions", "notify_window_enabled", value=checked)
        self._set_notify_window_controls_enabled(checked)

    def _on_competitions_notify_start_changed(self, value: int):
        self.config.set("competitions", "notify_window_start", value=value)

    def _on_competitions_notify_end_changed(self, value: int):
        self.config.set("competitions", "notify_window_end", value=value)

    def _on_competition_sound_repeat_toggled(self, checked: bool):
        self.config.set("sound", "competition_repeat_enabled", value=checked)
        self._set_spin_enabled(self.competition_sound_repeat_interval_spin, checked)

    def _on_competition_sound_repeat_interval_changed(self, value: int):
        self.config.set("sound", "competition_repeat_interval", value=value)

    def _on_notification_mode_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.notification_mode_combo)
        mode = self.notification_mode_combo.currentData() or "stack"
        self.config.set("notification", "mode", value=mode)
        from components.notification import popup_manager
        popup_manager.set_notification_mode(mode)

    def _on_notification_position_changed(self, text: str):
        self.config.set("ui", "notification_position", value=text.lower())

    def _on_notification_width_changed(self, value: int):
        self.config.set("ui", "notification_width", value=value)

    def _on_notification_hide_on_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.notification_hide_on_combo)
        value = self.notification_hide_on_combo.currentData() or "mouse_keyboard"
        self.config.set("notification", "hide_on", value=value)

    def _on_notification_duration_changed(self, value: int):
        self.config.set("notification", "duration_ms", value=int(value) * 1000)

    def _on_notification_fade_changed(self, value: int):
        self.config.set("notification", "fade_ms", value=int(value))

    def _on_mention_always_toggled(self, checked: bool):
        self.config.set("sound", "play_mention_sound_always", value=checked)

    def _on_competition_always_toggled(self, checked: bool):
        self.config.set("sound", "play_competition_sound_always", value=checked)
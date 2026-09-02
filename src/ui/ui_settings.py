"""Application Settings widget"""
import re
import shutil
from html import escape
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QCheckBox, QComboBox, QSpinBox, QSlider, QMessageBox, QTextEdit,
    QApplication, QInputDialog, QFileDialog, QToolButton, QPushButton,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer

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
from helpers.translate import tr, set_language, get_language, on_language_changed, TrStr, TranslatableMixin
from helpers.flash_highlight import TIMING_FUNCTIONS, FlashLabel, DURATION_KEYS

DEFAULTS = {
    "notification": {
        "width": 550,
        "duration": 5,
        "fade_ms": 300,
        "reply_center_offset_y": 0,
        "reply_focus_expand_width": 200,
        "margin_x": 20,
        "margin_top": 20,
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
        "badge_font_size": 9,
        "mentions_digest_mode": "daily",
        "mentions_digest_interval_hours": 24,
        "flash_easing": "linear",
        "flash_duration_ms": 1000,  # legacy fallback
        "flash_row_duration_ms": 1000,
        "flash_copy_duration_ms": 1000,
        "flash_duration_ms_min": 200,
        "flash_duration_ms_max": 3000,
    },
    "user_tracker": {
        "presence_log_split_percent": 20,
        "presence_log_split_percent_min": 5,
        "presence_log_split_percent_max": 70,
    },
    "player": {
        # MPV
        "hwdec": "auto",
        "log": False,
        "keep_open": False,
        "ontop": False,
        "volume": 100,
        # YT-DLP
        "disable_tls_verify": True,
        "ytdl_format": "",

        "extra_args": "",
    },
}

FONT_PREVIEW_BORDER = 1
FONT_PREVIEW_PADDING = 6
SLIDER_DEBOUNCE_MS = 150


def preview_box_colors(theme: str) -> tuple[str, str, str]:
    """(bg, fg, border) for a themed preview box; shared by font and flash previews."""
    if theme == "dark":
        return "#1E1E1E", "#D4D4D4", "#3C3C3C"
    return "#F5F5F5", "#333333", "#CCCCCC"


def preview_box_stylesheet(widget_selector: str, theme: str) -> str:
    bg, fg, border = preview_box_colors(theme)
    return (
        f"{widget_selector} {{ background-color: {bg}; color: {fg}; "
        f"border: {FONT_PREVIEW_BORDER}px solid {border}; border-radius: 4px; "
        f"padding: {FONT_PREVIEW_PADDING}px; }}"
    )


class _SpinCommitSignal(QObject):
    """Fires once a slider/spin row's debounced value has been committed, for
    external listeners that need the settled value rather than every step."""
    committed = pyqtSignal(int)

# Option tuples are built by functions (not module constants) so tr() picks up
# the current language each time a combo is (re)filled.

def xmpp_resource_options():
    return (
        ("web", tr("Same resource as the website. Receives private messages from the site client.",
                   "Тот же ресурс, что у сайта. Получает приватные сообщения от веб-клиента.")),
        ("client", tr("Works alongside the website. May not receive private messages from the web resource.",
                      "Работает параллельно с сайтом. Может не получать приватные сообщения от веб-ресурса.")),
    )

def own_message_mode_options():
    return (
        ("local", tr("Show own messages immediately. Server echoes are ignored.",
                     "Показывать свои сообщения сразу. Эхо сервера игнорируется.")),
        ("server", tr("Show own messages only when the server echoes them back.",
                      "Показывать свои сообщения только после эха сервера.")),
    )

def notification_mode_options():
    return (
        ("stack", tr("Stack", "Стопка"),
         tr("Stack notifications vertically; oldest is dropped once they no longer fit.",
            "Складывать уведомления вертикально; старые убираются, когда не помещаются.")),
        ("replace", tr("Replace", "Замена"),
         tr("Close the previous notification when a new one arrives.",
            "Закрывать предыдущее уведомление при появлении нового.")),
        ("scroll", tr("Scroll", "Прокрутка"),
         tr("Keep every notification; scroll with the mouse wheel to see more.",
            "Сохранять все уведомления; прокрутка колесом мыши для просмотра.")),
    )

def notification_hide_on_options():
    return (
        ("manual", tr("Manual", "Вручную"),
         tr("Auto-hide off — closes only by clicking it or the close button.",
            "Автоскрытие выключено — закрытие только кликом или кнопкой закрытия.")),
        ("mouse", tr("Mouse", "Мышь"),
         tr("Auto-hide countdown starts once the mouse moves.",
            "Отсчёт автоскрытия начинается при движении мыши.")),
        ("keyboard", tr("Keyboard", "Клавиатура"),
         tr("Auto-hide countdown starts once you press a key.",
            "Отсчёт автоскрытия начинается при нажатии клавиши.")),
        ("mouse_keyboard", tr("Mouse or Keyboard", "Мышь или клавиатура"),
         tr("Auto-hide countdown starts on mouse or keyboard activity.",
            "Отсчёт автоскрытия начинается при активности мыши или клавиатуры.")),
    )

# When notifications are muted: off | default (follow Hide notifications on) | duration (ignore activity).
def notification_mute_bypass_options():
    return (
        ("off", tr("Off", "Выкл"),
         tr("Do not show when notifications are disabled.",
            "Не показывать, когда уведомления отключены.")),
        ("default", tr("Default", "По умолчанию"),
         tr("Show when muted; auto-hide follows the Hide notifications on setting.",
            "Показывать при отключении уведомлений; автоскрытие по настройке «Скрывать уведомления по».")),
        ("duration", tr("Duration", "По таймеру"),
         tr("Show when muted; auto-hide after delay, ignore mouse/keyboard.",
            "Показывать при отключении уведомлений; автоскрытие по таймеру, без учёта мыши/клавиатуры.")),
    )

def alert_chat_action_options():
    return (
        ("scroll", tr("Scroll to message", "Прокрутить к сообщению"),
         tr("Scrolls the chat to the competition message.",
            "Прокручивает чат к сообщению о соревновании.")),
        ("move", tr("Move to bottom", "Переместить вниз"),
         tr("Removes the competition message and reposts it at the bottom of the chat.",
            "Удаляет сообщение о соревновании и публикует его заново внизу чата.")),
    )

def tracker_click_options():
    return (
        ("history", tr("Open history", "Открыть историю"),
         tr("Open the User Tracker's History tab.",
            "Открыть вкладку истории трекера пользователей.")),
        ("chat", tr("Show chat", "Показать чат"),
         tr("Open the chat window — messages and user list, no tracker.",
            "Открыть окно чата — сообщения и список пользователей, без трекера.")),
    )

def tracker_default_tab_options():
    return (
        ("tracked", tr("Tracked", "Отслеживаемые"),
         tr("Open on the list of currently tracked users.",
            "Открывать список отслеживаемых пользователей.")),
        ("history", tr("History", "История"),
         tr("Open on the log of past tracker events.",
            "Открывать журнал прошлых событий трекера.")),
    )

def mentions_digest_mode_options():
    return (
        ("off", tr("Off", "Выкл"),
         tr("Never check personal mentions automatically.",
            "Никогда не проверять личные упоминания автоматически.")),
        ("daily", tr("Once per day", "Раз в день"),
         tr("Check personal mentions at most once every 24 hours per account.",
            "Проверять личные упоминания не чаще раза в 24 часа на аккаунт.")),
        ("custom", tr("Custom interval", "Свой интервал"),
         tr("Check only after the chosen number of hours since last session end.",
            "Проверять только через заданное число часов после конца последней сессии.")),
        ("start", tr("Every chat start", "При каждом запуске чата"),
         tr("Check on every chat start (ignore the interval).",
            "Проверять при каждом запуске чата (игнорируя интервал).")),
    )

def flash_easing_options():
    labels = {
        "linear": tr("Linear", "Линейно"),
        "ease_out": tr("Ease out", "С замедлением"),
        "ease_in_out": tr("Ease in-out", "Плавный переход"),
        "ease_out_cubic": tr("Ease out (pronounced)", "С сильным замедлением"),
        "ease_in_out_cubic": tr("Ease in-out (pronounced)", "Выраженный плавный переход"),
        "ease_elastic_in_out": tr("Elastic in-out", "Пружина"),
        "ease_elastic_out_in": tr("Elastic out-in", "Пружина (наоборот)"),
        "ease_back_in": tr("Overshoot in", "С замахом"),
        "ease_back_out": tr("Overshoot out", "С отскоком назад"),
        "ease_back_in_out": tr("Overshoot in-out", "С замахом и отскоком"),
        "ease_back_out_in": tr("Overshoot out-in", "С отскоком и замахом"),
        "ease_bounce_in": tr("Bounce in", "Отскок (в начале)"),
        "ease_bounce_out": tr("Bounce out", "Отскок (в конце)"),
    }
    return tuple((key, labels[key], labels[key]) for key in TIMING_FUNCTIONS)


def notification_position_options():
    return (
        ("right", tr("Right", "Справа"),
         tr("Show notifications along the right edge of the screen.",
            "Показывать уведомления у правого края экрана.")),
        ("left", tr("Left", "Слева"),
         tr("Show notifications along the left edge of the screen.",
            "Показывать уведомления у левого края экрана.")),
        ("center", tr("Center", "По центру"),
         tr("Show notifications centered on the screen.",
            "Показывать уведомления по центру экрана.")),
    )

def centered_style_options(inline_tip, center_tip):
    """Shared (value, label, tip) pairs for 'inline' vs 'center' placement
    settings; callers supply context-specific tooltip text."""
    return (
        ("inline", tr("In place", "На месте"), inline_tip),
        ("center", tr("Centered", "По центру"), center_tip),
    )


def reply_style_options():
    return centered_style_options(
        tr("Reply field opens inside the notification, at its current position.",
           "Поле ответа открывается прямо в уведомлении, на его текущем месте."),
        tr("Notification detaches and centers on screen while you reply. "
           "No effect if Notification position is already Center.",
           "Уведомление отделяется от стека и центрируется на экране на время ответа. "
           "Не действует, если «Расположение уведомлений» уже установлено на «По центру»."),
    )


def competition_notification_style_options():
    return centered_style_options(
        tr("Competition notification stays in the regular notification stack.",
           "Уведомление о соревновании остаётся в обычном стеке уведомлений."),
        tr("Competition notification detaches and centers on screen for more visibility. "
           "No effect if Notification position is already Center.",
           "Уведомление о соревновании отделяется от стека и центрируется на экране для большей заметности. "
           "Не действует, если «Расположение уведомлений» уже установлено на «По центру»."),
    )

def player_hwdec_options():
    return (
        ("auto", "auto", tr(
            "MPV picks the best available method. Low CPU, GPU does the work.",
            "MVP выбирает лучший доступный способ. Низкая нагрузка на CPU, работает GPU.")),
        ("no", "no", tr(
            "Software only. Most compatible, higher CPU load.",
            "Только программное. Совместимее всего, выше нагрузка на CPU.")),
        ("d3d11va", "d3d11va", tr(
            "Direct3D 11 (Windows). Low CPU, recommended on Windows.",
            "Direct3D 11 (Windows). Низкая нагрузка на CPU, рекомендуется на Windows.")),
        ("nvdec", "nvdec", tr(
            "NVIDIA NVDEC (CUDA). Low CPU on NVIDIA GPUs.",
            "NVIDIA NVDEC (CUDA). Низкая нагрузка на CPU на NVIDIA.")),
        ("vulkan", "vulkan", tr(
            "Vulkan Video. Low CPU where supported (needs --vo=gpu-next).",
            "Vulkan Video. Низкая нагрузка на CPU там, где поддерживается (нужен --vo=gpu-next).")),
    )


def player_ytdl_format_options():
    # Official yt-dlp selectors (see FORMAT SELECTION in yt-dlp README).
    return (
        ("", tr("Default", "По умолчанию"),
         tr("yt-dlp default (usually bv*+ba/b).",
            "Формат по умолчанию yt-dlp (обычно bv*+ba/b).")),
        ("bv*+ba/b", "bv*+ba/b",
         tr("Best separate video+audio, else best combined.",
            "Лучшие отдельные видео+аудио, иначе лучший совмещённый.")),
        ("bv*[height<=1080]+ba/b", "≤1080p",
         tr("Best video up to 1080p + best audio.",
            "Лучшее видео до 1080p + лучшее аудио.")),
        ("bv*[height<=720]+ba/b", "≤720p",
         tr("Best video up to 720p + best audio.",
            "Лучшее видео до 720p + лучшее аудио.")),
        ("bv*[height<=480]+ba/b", "≤480p",
         tr("Best video up to 480p + best audio.",
            "Лучшее видео до 480p + лучшее аудио.")),
        ("bestaudio/best", tr("Audio only", "Только аудио"),
         tr("Best audio stream only.", "Только лучший аудиопоток.")),
    )



LANGUAGE_OPTIONS = (
    ("en", "English", "English interface language"),
    ("ru", "Русский", "Русский язык интерфейса"),
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
    fill_tooltip_combo(combo, xmpp_resource_options(), current, "web")


def fill_own_message_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, own_message_mode_options(), current, "local")


def fill_notification_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, notification_mode_options(), current, "stack")


def fill_notification_hide_on_combo(combo, current=None):
    fill_tooltip_combo(combo, notification_hide_on_options(), current, "mouse_keyboard")


def fill_notification_mute_bypass_combo(combo, current=None):
    fill_tooltip_combo(combo, notification_mute_bypass_options(), current, "off")


def fill_alert_chat_action_combo(combo, current=None):
    fill_tooltip_combo(combo, alert_chat_action_options(), current, "scroll")


def fill_tracker_click_combo(combo, current=None):
    fill_tooltip_combo(combo, tracker_click_options(), current, "history")


def fill_tracker_default_tab_combo(combo, current=None):
    fill_tooltip_combo(combo, tracker_default_tab_options(), current, "tracked")


def fill_mentions_digest_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, mentions_digest_mode_options(), current, "daily")


def fill_flash_easing_combo(combo, current=None):
    fill_tooltip_combo(combo, flash_easing_options(), current, DEFAULTS["chat"]["flash_easing"])


def fill_notification_position_combo(combo, current=None):
    fill_tooltip_combo(combo, notification_position_options(), current, "right")


def fill_reply_style_combo(combo, current=None):
    fill_tooltip_combo(combo, reply_style_options(), current, "inline")


def fill_competition_notification_style_combo(combo, current=None):
    fill_tooltip_combo(combo, competition_notification_style_options(), current, "inline")

def fill_player_hwdec_combo(combo, current=None):
    fill_tooltip_combo(combo, player_hwdec_options(), current, "auto")

def fill_player_ytdl_format_combo(combo, current=None):
    fill_tooltip_combo(combo, player_ytdl_format_options(), current, "")


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


class SettingsRow(QWidget):
    """Label + control line with a soft hover fill so the pair stays readable when wide."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self.setObjectName("settingsRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(spacing)
        # Soft row fill; label/slider transparent so it shows through (combo/spin keep chrome).
        self.setStyleSheet(
            "#settingsRow { background: transparent; border-radius: 6px; }"
            "#settingsRow:hover { background: rgba(128, 128, 128, 0.10); }"
            "#settingsRow QLabel, #settingsRow QSlider { background: transparent; }"
        )


class SoundSelectorWidget(TranslatableMixin, QWidget):
    """Selector for one notification sound type.

    System sounds (project/sounds/...) are listed but cannot be deleted or renamed.
    User sounds live in KG_Chat_Data/sounds/<kind>/ and can be added, renamed, deleted.
    """

    def __init__(self, config, sound_root: Path, kind: str, label_text: str):
        super().__init__()
        self._init_translatable()
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
        self._register_tr(label.setText, label_text)

        def _nav_button(icon_name, tooltip, on_click):
            button = create_icon_button(self.icons_path, icon_name, tooltip, size_type="small", config=self.config)
            button.clicked.connect(on_click)
            layout.addWidget(button)
            self._register_tr(button.setToolTip, tooltip)
            return button

        self.prev_button = _nav_button("arrow-left.svg", tr("Previous sound", "Предыдущий звук"), self._on_prev)

        self.combo = NoWheelComboBox()
        self.combo.setFont(get_font(FontType.UI))
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        self.combo.setMinimumWidth(180)
        layout.addWidget(self.combo, stretch=1)

        self.next_button = _nav_button("arrow-right.svg", tr("Next sound", "Следующий звук"), self._on_next)
        self.play_button = _nav_button("play.svg", tr("Play sound", "Воспроизвести звук"), self._on_play)
        self.add_button = _nav_button("add.svg", tr("Add sound from file", "Добавить звук из файла"), self._on_add)
        self.delete_button = _nav_button("trash.svg", tr("Delete sound", "Удалить звук"), self._on_delete)
        self.rename_button = _nav_button("pencil.svg", tr("Rename sound", "Переименовать звук"), self._on_rename)

        self.refresh()
        on_language_changed(self._retranslate_all)

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

    def _require_user_owned(self, title: str, message: str) -> str | None:
        """Return the selected file name if it's user-owned, else show why not and return None."""
        file_name = self._safe_name()
        if file_name and self._is_user_owned(file_name):
            return file_name
        QMessageBox.information(self, title, message)
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
            self.combo.addItem(tr("No sound", "Нет звука"), None)
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
            tr("Select sound file", "Выберите файл со звуком"),
            "",
            tr("Audio (*.mp3);;All files (*)", "Аудио (*.mp3);;Все файлы (*)"),
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
            tr("File exists", "Файл уже существует"),
            tr(f"'{dest_name}' already exists in your sounds. Overwrite?",
               f"«{dest_name}» уже есть в ваших звуках. Перезаписать?"),
        ):
            return

        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            QMessageBox.warning(self, tr("Add sound", "Добавить звук"),
                                 tr(f"Failed to copy file: {exc}", f"Не удалось скопировать файл: {exc}"))
            return

        self.refresh(select_name=dest_name)
        self._play_file(dest_name)

    def _on_delete(self):
        title = tr("Delete sound", "Удалить звук")
        file_name = self._require_user_owned(
            title, tr("System sounds cannot be deleted. Only sounds you added can be deleted.",
                      "Системные звуки нельзя удалить. Можно удалять только добавленные вами звуки.")
        )
        if not file_name:
            return

        path = self.user_dir / file_name
        if not self._confirm(title, tr(f"Delete '{file_name}'?", f"Удалить «{file_name}»?")):
            return

        try:
            path.unlink()
        except OSError as exc:
            QMessageBox.warning(self, title, tr(f"Failed to delete sound: {exc}", f"Не удалось удалить звук: {exc}"))
            return

        self.refresh()

    def _on_rename(self):
        title = tr("Rename sound", "Переименовать звук")
        file_name = self._require_user_owned(
            title, tr("System sounds cannot be renamed. Only sounds you added can be renamed.",
                      "Системные звуки нельзя переименовать. Можно переименовывать только добавленные вами звуки.")
        )
        if not file_name:
            return

        current_path = self.user_dir / file_name
        dialog = QInputDialog(self)
        dialog.setWindowTitle(title)
        dialog.setLabelText(tr("New file name:", "Новое имя файла:"))
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
            QMessageBox.warning(self, title, tr("The name cannot contain path separators.",
                                                 "Имя не может содержать разделители пути."))
            return

        target_path = self.user_dir / clean_name
        if target_path.exists() and target_path.name.lower() != current_path.name.lower():
            QMessageBox.warning(self, title, tr("A sound with that name already exists.",
                                                 "Звук с таким именем уже существует."))
            return

        try:
            current_path.rename(target_path)
        except OSError as exc:
            QMessageBox.warning(self, title, tr(f"Failed to rename sound: {exc}", f"Не удалось переименовать звук: {exc}"))
            return

        self.refresh(select_name=clean_name)


class SettingsWidget(TranslatableMixin, QWidget):
    """Settings page organized into collapsible sections"""

    back_requested = pyqtSignal()
    sound_changed = pyqtSignal()
    competition_log_clear_requested = pyqtSignal()
    font_family_changed = pyqtSignal()
    tracker_badge_style_changed = pyqtSignal()
    tracker_enabled_changed = pyqtSignal(bool)
    tracker_presence_log_changed = pyqtSignal(bool)
    tracker_userlist_star_changed = pyqtSignal(bool)
    tracker_presence_log_split_changed = pyqtSignal(int)
    resource_changed = pyqtSignal()

    def __init__(self, config, icons_path: Path, font_scaler=None):
        super().__init__()
        self._init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.font_scaler = font_scaler
        self.startup_manager = StartupManager()
        self._competitions_accent_color = None
        self._hotkey_capture = None

        self._setup_ui()
        self.refresh()
        hotkey.hotkey_manager.status_changed.connect(self._on_hotkey_status_changed)
        on_language_changed(self._retranslate)

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
        self._register_tr(label.setText, title)

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(self._spacing())
        content.setLayout(content_layout)
        section_layout.addWidget(content)

        # Slug is the config-path key for this section's collapsed state, so it
        # must stay stable regardless of the active UI language.
        slug_source = title.en if isinstance(title, TrStr) else title
        slug = re.sub(r"[^a-z0-9]+", "_", slug_source.lower()).strip("_")
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

    def _add_subsection(self, section_layout: QVBoxLayout, title: str) -> tuple[QHBoxLayout, QWidget, QVBoxLayout]:
        """Create a titled sub-block (header row + content widget) inside a section
        and append it to section_layout. Caller adds rows to the returned content
        layout, then finishes with _add_collapse_toggle(header_row, content, config_path)."""
        header_row = QHBoxLayout()
        header_row.setSpacing(self._spacing())
        label = QLabel(title)
        label.setFont(get_font(FontType.UI))
        header_row.addWidget(label)
        header_row.addStretch(1)
        section_layout.addLayout(header_row)
        self._register_tr(label.setText, title)

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(self._spacing())
        content.setLayout(content_layout)
        section_layout.addWidget(content)

        return header_row, content, content_layout

    def _add_checkbox(self, section_layout: QVBoxLayout, text: str, on_toggled) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setFont(get_font(FontType.UI))
        checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        checkbox.toggled.connect(on_toggled)
        section_layout.addWidget(checkbox)
        self._register_tr(checkbox.setText, text)
        return checkbox

    def _add_combo_row(self, section_layout: QVBoxLayout, label_text: str, items: list, on_changed) -> QComboBox:
        row_widget = SettingsRow(spacing=self._spacing())
        row = row_widget.layout()
        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label, stretch=1)
        self._register_tr(label.setText, label_text)

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

    def _add_slider_spin_row(self, section_layout: QVBoxLayout, label_text: str, minimum: int, maximum: int, on_changed, on_reset=None, default=None) -> QSpinBox:
        row_widget = SettingsRow(spacing=self._spacing())
        row = row_widget.layout()

        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label)
        self._register_tr(label.setText, label_text)

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
        commit_signal = _SpinCommitSignal(spin)

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
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
            request_commit(value)
            update_reset_state(value)

        def sync_from_spin(value):
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
            request_commit(value)
            update_reset_state(value)

        slider.valueChanged.connect(sync_from_slider)
        spin.valueChanged.connect(sync_from_spin)
        spin._slider = slider
        spin.committed = commit_signal.committed

        # Default reset behavior is just "put the default back in the spin box" -
        # sync_from_spin (above) already propagates that to the slider and fires
        # on_changed, so callers only need to pass a custom on_reset when a reset
        # has to do more than restore the default value.
        if on_reset is None and default is not None:
            on_reset = lambda: spin.setValue(default)

        if on_reset:
            reset_tooltip = tr("Reset to default", "Сбросить по умолчанию")
            reset_button = create_icon_button(self.icons_path, "reload.svg", reset_tooltip, size_type="small", config=self.config)
            reset_button.clicked.connect(on_reset)
            row.addWidget(reset_button)
            update_reset_state(spin.value())
            spin._reset_button = reset_button
            spin._update_reset_state = update_reset_state
            self._register_tr(reset_button.setToolTip, reset_tooltip)

        section_layout.addWidget(row_widget)
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

        back_tooltip = tr("Back to Messages", "Назад к сообщениям")
        self.back_button = create_icon_button(
            self.icons_path, "go-back.svg", back_tooltip, config=self.config
        )
        self.back_button.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.back_button)
        self._register_tr(self.back_button.setToolTip, back_tooltip)

        title_text = tr("Settings", "Настройки")
        title_label = QLabel(title_text)
        title_label.setProperty("fontRole", "header")
        title_label.setFont(get_font(FontType.HEADER))
        header_layout.addWidget(title_label, stretch=1)
        self._register_tr(title_label.setText, title_text)

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
        self._build_player_section()
        self._build_fonts_section()
        self._build_notifications_section()
        self._build_competitions_section()
        self._build_user_tracker_section()
        self._build_sound_section()

        self._sections_layout.addStretch(1)

    def _build_startup_section(self):
        section = self._create_section(tr("🚀 Startup", "🚀 Запуск"))
        self.auto_login_checkbox = self._add_checkbox(
            section, tr("Auto-login on startup", "Автовход при запуске"), self._on_auto_login_toggled
        )
        self.start_minimized_checkbox = self._add_checkbox(
            section, tr("Start minimized", "Запускать свёрнутым"), self._on_start_minimized_toggled
        )
        self.start_with_system_checkbox = self._add_checkbox(
            section, tr("Start with system", "Запускать вместе с системой"), self._on_start_with_system_toggled
        )

    def _build_chat_section(self):
        section = self._create_section(tr("🗯️ Chat", "🗯️ Чат"))
        self.language_combo = self._add_combo_row(
            section, tr("Language", "Язык"), [], self._on_language_changed
        )
        self.language_combo.setFixedWidth(240)
        fill_tooltip_combo(
            self.language_combo, LANGUAGE_OPTIONS,
            self.config.get("ui", "language"), "en"
        )
        self.clear_private_checkbox = self._add_checkbox(
            section, tr("Clear private messages on exit", "Очищать приватные сообщения при выходе"),
            self._on_clear_private_toggled
        )
        self.youtube_checkbox = self._add_checkbox(
            section, tr("YouTube link previews", "Превью ссылок YouTube"),
            self._on_youtube_toggled
        )
        self.settings_accordion_checkbox = self._add_checkbox(
            section, tr("Accordion settings sections (opening one collapses others)",
                        "Аккордеон секций настроек (открытие одной сворачивает остальные)"),
            self._on_settings_accordion_toggled
        )
        self.browser_combo = self._add_combo_row(
            section, tr("Open links in", "Открывать ссылки в"), [], self._on_browser_changed
        )
        self.browser_combo.setFixedWidth(240)
        self.badge_size_spin = self._add_slider_spin_row(
            section, tr("Badge font size", "Размер шрифта бейджа"), 8, 18,
            self._on_badge_size_changed, default=DEFAULTS["chat"]["badge_font_size"],
        )
        self.mentions_digest_mode_combo = self._add_combo_row(
            section, tr("Personal mentions check", "Проверка личных упоминаний"), [],
            self._on_mentions_digest_mode_changed
        )
        self.mentions_digest_mode_combo.setFixedWidth(240)
        self.mentions_digest_interval_spin = self._add_slider_spin_row(
            section, tr("Custom interval (hours)", "Свой интервал (часы)"), 1, 168,
            self._on_mentions_digest_interval_changed,
            default=DEFAULTS["chat"]["mentions_digest_interval_hours"],
        )
        self._add_hotkey_row(section, tr("Toggle chat window", "Показать/скрыть окно чата"))

        limits_header, limits_content, limits_layout = self._add_subsection(
            section, tr("📏 Message Limits", "📏 Лимиты сообщений")
        )
        self.chatlog_max_messages_spin = self._add_slider_spin_row(
            limits_layout, tr("Chatlog messages display limit", "Лимит отображения сообщений чатлога"),
            DEFAULTS["chatlog"]["max_messages_min"], DEFAULTS["chatlog"]["max_messages_max"],
            self._on_chatlog_max_messages_changed,
            default=DEFAULTS["chatlog"]["max_messages"],
        )
        self.chatlog_max_messages_spin.setSingleStep(1000)
        self.chatlog_max_messages_spin._slider.setSingleStep(1000)
        self.chatlog_max_messages_spin._slider.setPageStep(5000)

        self.chatlog_live_search_spin = self._add_slider_spin_row(
            limits_layout, tr("Chatlog live search up to (messages)", "Живой поиск чатлога до (сообщений)"),
            DEFAULTS["chatlog"]["live_search_max_messages_min"],
            DEFAULTS["chatlog"]["live_search_max_messages_max"],
            self._on_chatlog_live_search_max_changed,
            default=DEFAULTS["chatlog"]["live_search_max_messages"],
        )
        self.chatlog_live_search_spin.setSingleStep(500)
        self.chatlog_live_search_spin._slider.setSingleStep(500)
        self.chatlog_live_search_spin._slider.setPageStep(2000)

        self.chat_max_messages_spin = self._add_slider_spin_row(
            limits_layout, tr("Chat messages display limit", "Лимит отображения сообщений чата"),
            DEFAULTS["chat"]["max_messages_min"], DEFAULTS["chat"]["max_messages_max"],
            self._on_chat_max_messages_changed,
            default=DEFAULTS["chat"]["max_messages"],
        )
        self.chat_max_messages_spin.setSingleStep(100)
        self.chat_max_messages_spin._slider.setSingleStep(100)
        self.chat_max_messages_spin._slider.setPageStep(500)
        self._add_collapse_toggle(limits_header, limits_content, ("ui", "settings", "widgets", "chat_limits"))

        xmpp_header, xmpp_content, xmpp_layout = self._add_subsection(section, "🔌 XMPP")
        self.resource_combo = self._add_combo_row(
            xmpp_layout, tr("XMPP resource", "XMPP ресурс"), [], self._on_resource_changed
        )
        self.resource_combo.setFixedWidth(240)
        self.own_message_mode_combo = self._add_combo_row(
            xmpp_layout, tr("Own messages", "Свои сообщения"), [], self._on_own_message_mode_changed
        )
        self.own_message_mode_combo.setFixedWidth(240)
        self._add_collapse_toggle(xmpp_header, xmpp_content, ("ui", "settings", "widgets", "chat_xmpp"))

        parser_header, parser_content, parser_layout = self._add_subsection(
            section, tr("🔍 Chatlog Parser", "🔍 Парсер чатлога")
        )
        self.parser_validate_usernames_checkbox = self._add_checkbox(
            parser_layout,
            tr("Validate usernames in chatlog parser (API check)",
               "Проверять имена в парсере чатлога (через API)"),
            self._on_parser_validate_usernames_toggled,
        )
        self._add_collapse_toggle(parser_header, parser_content, ("ui", "settings", "widgets", "chat_parser"))

        flash_header, flash_content, flash_layout = self._add_subsection(
            section, tr("🪄 Highlight Animation", "🪄 Анимация подсветки")
        )
        self.flash_easing_combo = self._add_combo_row(
            flash_layout, tr("Timing function", "Функция плавности"), [], self._on_flash_easing_changed
        )
        self.flash_easing_combo.setFixedWidth(240)
        dmin = DEFAULTS["chat"]["flash_duration_ms_min"]
        dmax = DEFAULTS["chat"]["flash_duration_ms_max"]
        self.flash_row_duration_spin = self._add_slider_spin_row(
            flash_layout, tr("Row highlight (ms)", "Подсветка строки (мс)"),
            dmin, dmax, lambda v: self._on_flash_duration_changed("row", v),
            default=DEFAULTS["chat"]["flash_row_duration_ms"],
        )
        self.flash_copy_duration_spin = self._add_slider_spin_row(
            flash_layout, tr("Copy (ms)", "Копирование (мс)"),
            dmin, dmax, lambda v: self._on_flash_duration_changed("copy", v),
            default=DEFAULTS["chat"]["flash_copy_duration_ms"],
        )
        for spin in (self.flash_row_duration_spin, self.flash_copy_duration_spin):
            spin.setSingleStep(50)
            spin._slider.setSingleStep(50)

        self.flash_preview = {}
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
            label.setMinimumHeight(26)
            label.setFont(get_font(FontType.UI))
            label.setMargin(0)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            preview_layout.addWidget(label, stretch=1)
            self.flash_preview[kind] = label

        self._apply_flash_preview_theme()
        flash_layout.addWidget(preview_widget)
        self._add_collapse_toggle(flash_header, flash_content, ("ui", "settings", "widgets", "chat_flash"))

    def _add_hotkey_row(self, section_layout: QVBoxLayout, label_text: str):
        row_widget = SettingsRow(spacing=self._spacing())
        row = row_widget.layout()

        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label, stretch=1)
        self._register_tr(label.setText, label_text)

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

        hotkey_reset_tooltip = tr("Reset to default", "Сбросить по умолчанию")
        self.hotkey_reset_button = create_icon_button(
            self.icons_path, "reload.svg", hotkey_reset_tooltip, size_type="small", config=self.config
        )
        self.hotkey_reset_button.clicked.connect(self._on_hotkey_reset_clicked)
        row.addWidget(self.hotkey_reset_button)
        self._register_tr(self.hotkey_reset_button.setToolTip, hotkey_reset_tooltip)

        section_layout.addWidget(row_widget)

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
        self.hotkey_button.setText(tr("Press keys…", "Нажмите клавиши…"))
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
        tooltip = detail or hotkey.get_status_tooltip(status)
        can_retry = status != hotkey.STATUS_ACTIVE
        is_dark = (self.config.get("ui", "theme") or "dark") == "dark"
        tooltip_bg, tooltip_fg, tooltip_border = tinted_chip_colors(color, is_dark)
        self.hotkey_status_dot.setStyleSheet(
            f"#hotkeyStatusDot {{ background-color: {color}; border-radius: 5px; }}"
            f"QToolTip {{ background-color: {tooltip_bg}; color: {tooltip_fg}; border: 1px solid {tooltip_border}; }}"
        )
        self.hotkey_status_dot.setToolTip(tooltip + tr(" (click to retry)", " (нажмите для повтора)") if can_retry else tooltip)
        self.hotkey_status_dot.setCursor(
            Qt.CursorShape.PointingHandCursor if can_retry else Qt.CursorShape.ArrowCursor
        )

    def _on_hotkey_status_clicked(self):
        if hotkey.hotkey_manager.status == hotkey.STATUS_ACTIVE:
            return
        hotkey.hotkey_manager.register(self._current_hotkey())

    def _build_player_section(self):
        section = self._create_section(tr("🎬 Player", "🎬 Плеер"))

        mpv_header, mpv_content, mpv_layout = self._add_subsection(
            section, tr("MPV", "MPV")
        )
        self.player_tls_checkbox = self._add_checkbox(
            mpv_layout,
            tr("Disable TLS certificate verification", "Отключить проверку TLS-сертификатов"),
            self._on_player_tls_toggled,
        )
        self.player_hwdec_combo = self._add_combo_row(
            mpv_layout, tr("Hardware decoding", "Аппаратное декодирование"),
            [], self._on_player_hwdec_changed
        )
        self.player_hwdec_combo.setFixedWidth(240)
        self.player_volume_spin = self._add_slider_spin_row(
            mpv_layout, tr("Startup volume", "Начальная громкость"), 0, 100,
            self._on_player_volume_changed,
            default=DEFAULTS["player"]["volume"],
        )
        self.player_log_checkbox = self._add_checkbox(
            mpv_layout,
            tr("Save MPV log", "Сохранять лог MPV"),
            self._on_player_log_toggled,
        )
        self.player_keep_open_checkbox = self._add_checkbox(
            mpv_layout,
            tr("Keep window open", "Не закрывать окно"),
            self._on_player_keep_open_toggled,
        )
        self.player_ontop_checkbox = self._add_checkbox(
            mpv_layout,
            tr("Always on top", "Поверх всех окон"),
            self._on_player_ontop_toggled,
        )
        self._add_collapse_toggle(mpv_header, mpv_content, ("ui", "settings", "widgets", "player_mpv"))

        ytdl_header, ytdl_content, ytdl_layout = self._add_subsection(
            section, tr("YTDLP", "YTDLP")
        )
        self.player_ytdl_format_combo = self._add_combo_row(
            ytdl_layout, tr("Preferred format", "Предпочитаемый формат"),
            [], self._on_player_ytdl_format_changed
        )
        self.player_ytdl_format_combo.setFixedWidth(240)
        self._add_collapse_toggle(ytdl_header, ytdl_content, ("ui", "settings", "widgets", "player_ytdl"))

    def _build_fonts_section(self):
        section = self._create_section(tr("🅰️ Fonts", "🅰️ Шрифты"))
        # Combos start empty - refresh() (called right after _setup_ui in
        # __init__) is the single place that queries available families and
        # fills them, so there's no point doing it twice on every construction.
        self.ui_font_combo = self._add_combo_row(
            section, tr("UI font", "Шрифт интерфейса"), [], self._on_ui_font_changed
        )
        self.ui_font_size_spin = self._add_slider_spin_row(
            section, tr("UI font size", "Размер шрифта интерфейса"), 10, 18, self._on_ui_font_size_changed,
            default=12
        )
        self.text_font_combo = self._add_combo_row(
            section, tr("Text font", "Шрифт текста"), [], self._on_text_font_changed
        )
        self.text_font_size_spin = self._add_slider_spin_row(
            section, tr("Text font size", "Размер шрифта текста"), 12, 24, self._on_text_font_size_changed,
            default=15
        )
        self.emoji_font_combo = self._add_combo_row(
            section, tr("Emoji font", "Шрифт эмодзи"), [], self._on_emoji_font_changed
        )
        self.ui_font_combo.setFixedWidth(240)
        self.text_font_combo.setFixedWidth(240)
        self.emoji_font_combo.setFixedWidth(240)

        preview_header, preview_content, preview_layout = self._add_subsection(section, tr("🔎 Preview", "🔎 Предпросмотр"))
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
        preview_layout.addWidget(self.font_preview)
        self._update_font_preview()

        self._add_collapse_toggle(preview_header, preview_content, ("ui", "settings", "widgets", "font_preview"))

    def _build_notifications_section(self):
        section = self._create_section(tr("🔔 Notifications", "🔔 Уведомления"))
        self.notification_mode_combo = self._add_combo_row(
            section, tr("Notification mode", "Режим уведомлений"), [], self._on_notification_mode_changed
        )
        self.notification_position_combo = self._add_combo_row(
            section, tr("Notification position", "Расположение уведомлений"), [],
            self._on_notification_position_changed
        )
        self.reply_style_combo = self._add_combo_row(
            section, tr("Reply style", "Стиль ответа"), [], self._on_reply_style_changed
        )
        self.notification_margin_x_spin = self._add_slider_spin_row(
            section,
            tr("Notification side margin (X)", "Отступ уведомлений по X"),
            0, 300,
            self._on_notification_margin_x_changed,
            default=DEFAULTS["notification"]["margin_x"],
        )
        self.notification_margin_top_spin = self._add_slider_spin_row(
            section,
            tr("Notification top margin (Y)", "Отступ уведомлений сверху (Y)"),
            0, 300,
            self._on_notification_margin_top_changed,
            default=DEFAULTS["notification"]["margin_top"],
        )
        self.reply_center_offset_spin = self._add_slider_spin_row(
            section,
            tr("Reply vertical offset", "Смещение ответа по Y"),
            -400, 400,
            self._on_reply_center_offset_changed,
            default=DEFAULTS["notification"]["reply_center_offset_y"],
        )
        self.notification_width_spin = self._add_slider_spin_row(
            section, tr("Notification width", "Ширина уведомления"), DEFAULTS["notification"]["width"], 1000, self._on_notification_width_changed,
            default=DEFAULTS["notification"]["width"],
        )
        self.reply_focus_expand_spin = self._add_slider_spin_row(
            section,
            tr("Reply field expand width", "Расширение поля ответа"),
            0, 600,
            self._on_reply_focus_expand_changed,
            default=DEFAULTS["notification"]["reply_focus_expand_width"],
        )
        self.notification_hide_on_combo = self._add_combo_row(
            section, tr("Hide notifications on", "Скрывать уведомления по"), [], self._on_notification_hide_on_changed
        )
        self.notification_duration_spin = self._add_slider_spin_row(
            section,
            tr("Auto-hide delay (sec)", "Задержка автоскрытия (сек)"),
            1, 60,
            self._on_notification_duration_changed,
            default=DEFAULTS["notification"]["duration"],
        )
        self.notification_fade_spin = self._add_slider_spin_row(
            section,
            tr("Fade duration (ms)", "Длительность затухания (мс)"),
            50, 2000,
            self._on_notification_fade_changed,
            default=DEFAULTS["notification"]["fade_ms"],
        )

        bypass_header, bypass_content, bypass_layout = self._add_subsection(section, tr("🚧 Bypass When Muted", "🚧 Показ при отключении уведомлений"))
        self.competitions_bypass_combo = self._add_combo_row(
            bypass_layout, tr("Competitions", "Соревнования"), [],
            lambda _t: self._on_mute_bypass_changed(self.competitions_bypass_combo, "competitions_bypass_mute"),
        )
        self.mentions_bypass_combo = self._add_combo_row(
            bypass_layout, tr("Mentions & private messages", "Упоминания и приватные сообщения"), [],
            lambda _t: self._on_mute_bypass_changed(self.mentions_bypass_combo, "mentions_bypass_mute"),
        )
        self.bans_bypass_combo = self._add_combo_row(
            bypass_layout, tr("Bans", "Баны"), [],
            lambda _t: self._on_mute_bypass_changed(self.bans_bypass_combo, "bans_bypass_mute"),
        )
        self.tracker_bypass_combo = self._add_combo_row(
            bypass_layout, tr("Tracked users", "Отслеживаемые пользователи"), [],
            lambda _t: self._on_mute_bypass_changed(self.tracker_bypass_combo, "tracked_bypass_mute"),
        )
        self.messages_bypass_combo = self._add_combo_row(
            bypass_layout, tr("Regular messages", "Обычные сообщения"), [],
            lambda _t: self._on_mute_bypass_changed(self.messages_bypass_combo, "messages_bypass_mute"),
        )
        self._add_collapse_toggle(bypass_header, bypass_content, ("ui", "settings", "widgets", "notifications_bypass"))

    def _build_competitions_section(self):
        section = self._create_section(tr("🏆 Competitions", "🏆 Соревнования"))

        self.track_competitions_checkbox = self._add_checkbox(
            section, tr("Track rating competitions", "Отслеживать рейтинговые соревнования"), self._on_track_competitions_toggled
        )

        self.remove_on_enter_checkbox = self._add_checkbox(
            section,
            tr("Remove message and notification on entering competition", "Удалять сообщение и уведомление при входе в соревнование"),
            self._on_remove_on_enter_toggled,
        )

        log_header, log_content, log_layout = self._add_subsection(section, tr("📜 WebSocket Log", "📜 Лог WebSocket"))

        copy_log_tooltip = tr("Copy log", "Скопировать лог")
        self.copy_log_button = create_icon_button(
            self.icons_path, "copy.svg", copy_log_tooltip, size_type="small", config=self.config
        )
        self.copy_log_button.clicked.connect(self._on_copy_log_clicked)
        log_header.addWidget(self.copy_log_button)
        self._register_tr(self.copy_log_button.setToolTip, copy_log_tooltip)

        clear_log_tooltip = tr("Clear log", "Очистить лог")
        self.clear_log_button = create_icon_button(
            self.icons_path, "trash.svg", clear_log_tooltip, size_type="small", config=self.config
        )
        self.clear_log_button.clicked.connect(self._on_clear_log_clicked)
        log_header.addWidget(self.clear_log_button)
        self._register_tr(self.clear_log_button.setToolTip, clear_log_tooltip)

        self.competitions_log = QTextEdit()
        self.competitions_log.setReadOnly(True)
        self.competitions_log.setFixedHeight(DEFAULTS["competitions"]["log_height"])
        self.competitions_log.setFont(get_font(FontType.UI))
        log_placeholder = tr("Competition log", "Лог соревнований")
        self.competitions_log.setPlaceholderText(log_placeholder)
        self._register_tr(self.competitions_log.setPlaceholderText, log_placeholder)
        self.competitions_log.setAcceptRichText(True)
        self._apply_competitions_log_theme()
        log_layout.addWidget(self.competitions_log)

        self._add_collapse_toggle(log_header, log_content, ("ui", "settings", "widgets", "ws_log"))

        self.min_multiplier_combo = self._add_combo_row(
            section, tr("Minimum multiplier", "Минимальный множитель"), ["x1+", "x2+", "x3+", "x5+"],
            self._on_min_multiplier_changed
        )

        self.show_cost_checkbox = self._add_checkbox(
            section, tr("Show competition cost", "Показывать стоимость соревнования"), self._on_show_cost_toggled
        )

        self.show_scores_checkbox = self._add_checkbox(
            section, tr("Show scores balance", "Показывать остаток очков"), self._on_show_scores_toggled
        )

        self.show_bonuses_checkbox = self._add_checkbox(
            section, tr("Show bonuses balance", "Показывать остаток бонусов"), self._on_show_bonuses_toggled
        )

        self.show_players_checkbox = self._add_checkbox(
            section, tr("Show player usernames", "Показывать имена игроков"), self._on_show_players_toggled
        )
        self.max_player_chips_spin = self._add_slider_spin_row(
            section, tr("Max player usernames", "Макс. число имён"), 1, 100,
            self._on_max_player_chips_changed,
            default=DEFAULTS["competitions"]["max_player_chips"],
        )
        self.sort_players_by_level_checkbox = self._add_checkbox(
            section, tr("Sort player usernames by rank", "Сортировать имена игроков по рангу"), self._on_sort_players_by_level_toggled
        )

        self.competitions_alert_lead_spin = self._add_slider_spin_row(
            section, tr("Alert lead time before start (sec)", "Время оповещения до старта (сек)"), 0, 300,
            self._on_competitions_alert_lead_changed,
            default=DEFAULTS["competitions"]["alert_lead"],
        )

        self.alert_chat_action_combo = self._add_combo_row(
            section, tr("On alert in chat", "При оповещении в чате"), [], self._on_alert_chat_action_changed
        )

        self.competition_notification_style_combo = self._add_combo_row(
            section, tr("Competition notification style", "Стиль уведомления о соревновании"), [],
            self._on_competition_notification_style_changed
        )

        self.competitions_notify_window_checkbox = self._add_checkbox(
            section, tr("Only alert during allowed hours", "Оповещать только в разрешённые часы"), self._on_competitions_notify_window_toggled
        )
        self.competitions_notify_start_spin = self._add_slider_spin_row(
            section, tr("From", "С"), 0, 24, self._on_competitions_notify_start_changed,
            default=DEFAULTS["competitions"]["notify_start"],
        )
        self.competitions_notify_end_spin = self._add_slider_spin_row(
            section, tr("To", "До"), 0, 24, self._on_competitions_notify_end_changed,
            default=DEFAULTS["competitions"]["notify_end"],
        )


    def _build_user_tracker_section(self):
        section = self._create_section(tr("🗿 User Tracker", "🗿 Трекер пользователей"))
        self.tracker_enabled_checkbox = self._add_checkbox(
            section, tr("Track users", "Отслеживать пользователей"),
            self._on_tracker_enabled_toggled
        )
        self.tracker_notifications_checkbox = self._add_checkbox(
            section, tr("Show events in notifications", "Показывать события в уведомлениях"),
            self._on_tracker_notifications_toggled
        )
        self.tracker_presence_log_checkbox = self._add_checkbox(
            section, tr("Show events in chat", "Показывать события в чате"),
            self._on_tracker_presence_log_toggled
        )
        self.tracker_presence_log_split_spin = self._add_slider_spin_row(
            section, tr("Presence pane height (%)", "Высота панели событий (%)"),
            DEFAULTS["user_tracker"]["presence_log_split_percent_min"],
            DEFAULTS["user_tracker"]["presence_log_split_percent_max"],
            self._on_tracker_presence_log_split_changed,
            default=DEFAULTS["user_tracker"]["presence_log_split_percent"],
        )
        self.tracker_badge_checkbox = self._add_checkbox(
            section, tr("Show count badge on tracker button", "Показывать счётчик на кнопке трекера"),
            self._on_tracker_badge_toggled
        )
        self.tracker_userlist_star_checkbox = self._add_checkbox(
            section, tr("Show star badge on tracked users in userlist", "Показывать звезду у отслеживаемых в списке пользователей"),
            self._on_tracker_userlist_star_toggled
        )
        # Tracked event types — same pills as tracker filter bar
        events_row = QHBoxLayout()
        events_row.setSpacing(8)
        events_label_text = tr("Track events:", "Отслеживаемые события:")
        events_label = QLabel(events_label_text)
        events_label.setFont(get_font(FontType.UI))
        events_row.addWidget(events_label)
        self._register_tr(events_label.setText, events_label_text)
        theme = self.config.get("ui", "theme") or "dark"
        self.tracker_events_bar = TypeFilterBar(empty_means_all=False, is_dark=(theme == "dark"))
        self.tracker_events_bar.changed.connect(self._on_tracker_events_changed)
        events_row.addWidget(self.tracker_events_bar, stretch=1)
        section.addLayout(events_row)
        self._build_tracker_retention_row(section)
        self.tracker_default_tab_combo = self._add_combo_row(
            section, tr("Default tab on open", "Вкладка по умолчанию"), [], self._on_tracker_default_tab_changed
        )
        self.tracker_click_combo = self._add_combo_row(
            section, tr("On notification click", "При клике по уведомлению"), [], self._on_tracker_click_action_changed
        )

    def _build_sound_section(self):
        section = self._create_section(tr("🔊 Sound", "🔊 Звук"))
        self.mention_always_checkbox = self._add_checkbox(
            section, tr("Play mention sound even when chat is focused", "Звук упоминания даже когда чат в фокусе"),
            self._on_mention_always_toggled
        )
        self.competition_always_checkbox = self._add_checkbox(
            section, tr("Play competition sound even when chat is focused", "Звук соревнования даже когда чат в фокусе"),
            self._on_competition_always_toggled
        )

        self.sound_selectors = {}
        self.sound_dir = Path(__file__).parent.parent / "sounds"
        sound_types = [
            ("mention", tr("Mention sound", "Звук упоминания")),
            ("ban", tr("Ban sound", "Звук бана")),
            ("competition", tr("Competition sound", "Звук соревнования")),
        ]
        for kind, label in sound_types:
            selector = SoundSelectorWidget(self.config, self.sound_dir, kind, label)
            selector.combo.currentIndexChanged.connect(self._on_sound_selection_changed)
            self.sound_selectors[kind] = selector
            section.addWidget(selector)

        self.competition_sound_repeat_checkbox = self._add_checkbox(
            section, tr("Repeat competition sound until you're back", "Повторять звук соревнования, пока вы не вернётесь"),
            self._on_competition_sound_repeat_toggled
        )
        self.competition_sound_repeat_interval_spin = self._add_slider_spin_row(
            section, tr("Repeat interval (sec)", "Интервал повтора (сек)"), 3, 120, self._on_competition_sound_repeat_interval_changed,
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
            self.player_tls_checkbox, self.player_hwdec_combo, self.player_volume_spin,
            self.player_log_checkbox, self.player_keep_open_checkbox, self.player_ontop_checkbox,
            self.player_ytdl_format_combo,
            self.chatlog_max_messages_spin, self.chatlog_live_search_spin,
            self.parser_validate_usernames_checkbox,
            self.badge_size_spin, self.mentions_digest_mode_combo,
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

        tls_disabled = self.config.get("player", "disable_tls_verify")
        self.player_tls_checkbox.setChecked(
            DEFAULTS["player"]["disable_tls_verify"] if tls_disabled is None else bool(tls_disabled)
        )
        fill_player_hwdec_combo(self.player_hwdec_combo, self.config.get("player", "hwdec"))

        volume = self.config.get("player", "volume")
        try:
            volume = int(volume) if volume is not None else DEFAULTS["player"]["volume"]
        except (TypeError, ValueError):
            volume = DEFAULTS["player"]["volume"]
        volume = max(0, min(100, volume))
        self.player_volume_spin.setValue(volume)
        self.player_volume_spin._slider.setValue(volume)

        log = self.config.get("player", "log")
        self.player_log_checkbox.setChecked(
            DEFAULTS["player"]["log"] if log is None else bool(log)
        )
        keep_open = self.config.get("player", "keep_open")
        self.player_keep_open_checkbox.setChecked(
            DEFAULTS["player"]["keep_open"] if keep_open is None else bool(keep_open)
        )
        ontop = self.config.get("player", "ontop")
        self.player_ontop_checkbox.setChecked(
            DEFAULTS["player"]["ontop"] if ontop is None else bool(ontop)
        )
        fill_player_ytdl_format_combo(
            self.player_ytdl_format_combo, self.config.get("player", "ytdl_format") or ""
        )

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

        badge_size = self.config.get("ui", "chat", "badge_font_size")
        try:
            badge_size = int(badge_size) if badge_size is not None else DEFAULTS["chat"]["badge_font_size"]
        except (TypeError, ValueError):
            badge_size = DEFAULTS["chat"]["badge_font_size"]
        badge_size = max(8, min(18, badge_size))
        self.badge_size_spin.setValue(badge_size)
        self.badge_size_spin._slider.setValue(badge_size)

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
        self.mentions_digest_interval_spin._slider.setValue(digest_hours)
        self._sync_mentions_digest_interval_visibility()

        fill_flash_easing_combo(self.flash_easing_combo, self.config.get("ui", "chat", "flash_easing"))
        self._load_flash_duration_spins()

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
        self.tracker_presence_log_split_spin._slider.blockSignals(True)
        self.tracker_presence_log_split_spin._slider.setValue(split_value)
        self.tracker_presence_log_split_spin._slider.blockSignals(False)
        update_reset = getattr(self.tracker_presence_log_split_spin, "_update_reset_state", None)
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

        min_m = self.config.get("competitions", "min_multiplier") or "x1+"
        idx = self.min_multiplier_combo.findText(min_m)
        self.min_multiplier_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.remove_on_enter_checkbox.setChecked(bool(self.config.get("competitions", "remove_message_on_enter")))

        show_cost = self.config.get("competitions", "show_cost")
        self.show_cost_checkbox.setChecked(True if show_cost is None else bool(show_cost))

        show_scores = self.config.get("competitions", "show_scores")
        self.show_scores_checkbox.setChecked(True if show_scores is None else bool(show_scores))

        show_bonuses = self.config.get("competitions", "show_bonuses")
        self.show_bonuses_checkbox.setChecked(True if show_bonuses is None else bool(show_bonuses))

        show_players = self.config.get("competitions", "show_players")
        self.show_players_checkbox.setChecked(True if show_players is None else bool(show_players))
        self.max_player_chips_spin.setValue(int(self.config.get("competitions", "max_player_chips") or DEFAULTS["competitions"]["max_player_chips"]))
        self.max_player_chips_spin._slider.setValue(self.max_player_chips_spin.value())
        self.sort_players_by_level_checkbox.setChecked(bool(self.config.get("competitions", "sort_players_by_level")))
        self._set_players_controls_enabled(self.show_players_checkbox.isChecked())

        self.competitions_alert_lead_spin.setValue(int(self.config.get("competitions", "alert_lead_seconds") or DEFAULTS["competitions"]["alert_lead"]))
        self.competitions_alert_lead_spin._slider.setValue(self.competitions_alert_lead_spin.value())

        fill_alert_chat_action_combo(self.alert_chat_action_combo, self.config.get("competitions", "alert_chat_action"))

        fill_competition_notification_style_combo(
            self.competition_notification_style_combo, self.config.get("competitions", "notification_style")
        )

        self.competitions_notify_window_checkbox.setChecked(
            bool(self.config.get("competitions", "notify_window_enabled"))
        )
        self.competitions_notify_start_spin.setValue(int(self.config.get("competitions", "notify_window_start") or DEFAULTS["competitions"]["notify_start"]))
        self.competitions_notify_start_spin._slider.setValue(self.competitions_notify_start_spin.value())
        self.competitions_notify_end_spin.setValue(int(self.config.get("competitions", "notify_window_end") or DEFAULTS["competitions"]["notify_end"]))
        self.competitions_notify_end_spin._slider.setValue(self.competitions_notify_end_spin.value())
        self._set_notify_window_controls_enabled(self.competitions_notify_window_checkbox.isChecked())

        fill_notification_mode_combo(self.notification_mode_combo, self.config.get("notification", "mode"))

        fill_notification_position_combo(self.notification_position_combo, self.config.get("ui", "notification_position"))
        fill_reply_style_combo(self.reply_style_combo, self.config.get("notification", "reply_style"))
        offset_y = self.config.get("notification", "reply_center_offset_y")
        try:
            offset_y = int(offset_y) if offset_y is not None else DEFAULTS["notification"]["reply_center_offset_y"]
        except (TypeError, ValueError):
            offset_y = DEFAULTS["notification"]["reply_center_offset_y"]
        self.reply_center_offset_spin.setValue(offset_y)
        self.reply_center_offset_spin._slider.setValue(offset_y)
        self._update_center_offset_enabled()
        self.notification_width_spin.setValue(int(self.config.get("ui", "notification_width") or DEFAULTS["notification"]["width"]))
        self.notification_width_spin._slider.setValue(self.notification_width_spin.value())
        self.reply_focus_expand_spin.setValue(int(self.config.get("notification", "reply_focus_expand_width") or DEFAULTS["notification"]["reply_focus_expand_width"]))
        self.reply_focus_expand_spin._slider.setValue(self.reply_focus_expand_spin.value())
        self.notification_margin_x_spin.setValue(int(self.config.get("notification", "margin_x") or DEFAULTS["notification"]["margin_x"]))
        self.notification_margin_x_spin._slider.setValue(self.notification_margin_x_spin.value())
        self.notification_margin_top_spin.setValue(int(self.config.get("notification", "margin_top") or DEFAULTS["notification"]["margin_top"]))
        self.notification_margin_top_spin._slider.setValue(self.notification_margin_top_spin.value())

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
    # Live retranslation
    # ------------------------------------------------------------------ #
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
            (self.player_hwdec_combo, fill_player_hwdec_combo),
            (self.player_ytdl_format_combo, fill_player_ytdl_format_combo),
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
        self._retranslate_all()
        self._refill_option_combos()
        self._refresh_hotkey_row()

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
                self, tr("Error", "Ошибка"),
                tr(f"Failed to {'enable' if checked else 'disable'} start with system. Please check permissions.",
                   f"Не удалось {'включить' if checked else 'выключить'} запуск с системой. Проверьте права доступа.")
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

    def _on_language_changed(self, _text: str = ""):
        code = self.language_combo.currentData()
        if code and code != get_language():
            self.config.set("ui", "language", value=code)
            set_language(code)

    def _on_clear_private_toggled(self, checked: bool):
        self.config.set("ui", "clear_private_messages_on_exit", value=checked)

    def _on_youtube_toggled(self, checked: bool):
        self.config.set("ui", "youtube", "enabled", value=checked)

    def _on_player_tls_toggled(self, checked: bool):
        self.config.set("player", "disable_tls_verify", value=checked)

    def _on_player_hwdec_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.player_hwdec_combo)
        value = self.player_hwdec_combo.currentData() or "auto"
        self.config.set("player", "hwdec", value=value)

    def _on_player_volume_changed(self, value: int):
        self.config.set("player", "volume", value=int(value))

    def _on_player_log_toggled(self, checked: bool):
        self.config.set("player", "log", value=checked)

    def _on_player_keep_open_toggled(self, checked: bool):
        self.config.set("player", "keep_open", value=checked)

    def _on_player_ontop_toggled(self, checked: bool):
        self.config.set("player", "ontop", value=checked)

    def _on_player_ytdl_format_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.player_ytdl_format_combo)
        value = self.player_ytdl_format_combo.currentData()
        self.config.set("player", "ytdl_format", value=value if value is not None else "")

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
        self.font_preview.setStyleSheet(
            preview_box_stylesheet("QTextEdit", self.config.get("ui", "theme") or "dark")
        )

    def _apply_flash_preview_theme(self):
        if not hasattr(self, "flash_preview"):
            return
        preview_style = preview_box_stylesheet("QLabel", self.config.get("ui", "theme") or "dark")
        for preview in self.flash_preview.values():
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
            spin._slider.setValue(value)

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

    def _on_mute_bypass_changed(self, combo, config_key: str):
        self._sync_combo_tooltip(combo)
        value = combo.currentData() or "off"
        self.config.set("notification", config_key, value=value)

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

    def _on_badge_size_changed(self, value: int):
        self.config.set("ui", "chat", "badge_font_size", value=int(value))
        self.tracker_badge_style_changed.emit()

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
        if hasattr(spin, "_slider"):
            spin._slider.setEnabled(is_custom)

    def _on_mentions_digest_interval_changed(self, value: int):
        self.config.set("ui", "chat", "mentions_digest_interval_hours", value=int(value))

    def _on_flash_easing_changed(self, _text: str = ""):
        value = self.flash_easing_combo.currentData()
        if value is not None:
            self.config.set("ui", "chat", "flash_easing", value=value)
        for kind, preview in self.flash_preview.items():
            preview.flash(kind)

    def _on_flash_duration_changed(self, kind: str, value: int):
        self.config.set("ui", "chat", DURATION_KEYS[kind], value=int(value))
        self.flash_preview[kind].flash(kind)

    def _on_tracker_events_changed(self, types):
        # Keep at least one type enabled
        active = list(types) if types else list(EVENT_TYPES)
        if not types:
            self.tracker_events_bar.set_active_types(EVENT_TYPES)
            active = list(EVENT_TYPES)
        self.config.set("user_tracker", "track_events", value=active)


    def _build_tracker_retention_row(self, section_layout):
        self.tracker_retention_spin = self._add_slider_spin_row(
            section_layout, tr("History retention", "Хранить историю"), 1, 168,
            self._on_tracker_retention_value_changed,
            on_reset=self._on_tracker_retention_reset,
            default=24,
        )
        row = section_layout.itemAt(section_layout.count() - 1).widget().layout()
        self.tracker_retention_unit_combo = NoWheelComboBox()
        self.tracker_retention_unit_combo.setFont(get_font(FontType.UI))
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

    def _tracking_disabled_text(self) -> str:
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
            self.competitions_log.setHtml(self._status_log_html(self._tracking_disabled_text(), "disabled"))
            return

        self.competitions_log.setEnabled(True)
        self.competitions_log.setFixedHeight(DEFAULTS["competitions"]["log_height"])
        plain = self.competitions_log.toPlainText().strip()
        if plain in ("", self._tracking_disabled_text()):
            self.competitions_log.setHtml(self._status_log_html(self._tracking_enabled_text(), "enabled"))

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
        """Re-apply theme-dependent colors after a theme toggle (competitions log + previews)."""
        theme = self.config.get("ui", "theme") or "dark"
        if hasattr(self, "tracker_events_bar"):
            self.tracker_events_bar.update_theme(theme == "dark")
        self._apply_font_preview_theme()
        self._apply_flash_preview_theme()
        if not hasattr(self, "competitions_log"):
            return
        lines = self.competitions_log.toPlainText().splitlines()
        if lines and lines != [self._tracking_disabled_text()]:
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

    def _on_remove_on_enter_toggled(self, checked: bool):
        self.config.set("competitions", "remove_message_on_enter", value=checked)

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
        self._sync_combo_tooltip(self.alert_chat_action_combo)
        value = self.alert_chat_action_combo.currentData() or "scroll"
        self.config.set("competitions", "alert_chat_action", value=value)

    def _on_competition_notification_style_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.competition_notification_style_combo)
        value = self.competition_notification_style_combo.currentData() or "inline"
        self.config.set("competitions", "notification_style", value=value)
        self._update_center_offset_enabled()

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

    def _on_notification_position_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.notification_position_combo)
        value = self.notification_position_combo.currentData()
        if value is not None:
            self.config.set("ui", "notification_position", value=value)
        self._update_center_offset_enabled()

    def _update_center_offset_enabled(self):
        """Offset only does anything when something is actually centered
        (reply or competition) and notifications aren't already centered
        (see _resolve_centered_style() in notification.py)."""
        reply_style = self.reply_style_combo.currentData() or "inline"
        competition_style = self.competition_notification_style_combo.currentData() or "inline"
        position = self.notification_position_combo.currentData() or "right"
        centered = reply_style == "center" or competition_style == "center"
        self._set_spin_enabled(self.reply_center_offset_spin, centered and position != "center")
        self._set_spin_enabled(self.notification_margin_x_spin, position != "center")

    def _on_reply_style_changed(self, _text: str = ""):
        self._sync_combo_tooltip(self.reply_style_combo)
        value = self.reply_style_combo.currentData() or "inline"
        self.config.set("notification", "reply_style", value=value)
        self._update_center_offset_enabled()

    def _on_reply_center_offset_changed(self, value: int):
        self.config.set("notification", "reply_center_offset_y", value=value)

    def _on_notification_width_changed(self, value: int):
        self.config.set("ui", "notification_width", value=value)

    def _on_reply_focus_expand_changed(self, value: int):
        self.config.set("notification", "reply_focus_expand_width", value=value)

    def _on_notification_margin_x_changed(self, value: int):
        self.config.set("notification", "margin_x", value=value)

    def _on_notification_margin_top_changed(self, value: int):
        self.config.set("notification", "margin_top", value=value)

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
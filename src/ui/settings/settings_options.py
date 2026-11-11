"""Settings defaults, option lists and combo fillers."""

from PyQt6.QtCore import Qt

from components.flash_highlight import TIMING_FUNCTIONS
from components.image_viewer.layer import TRANSITION_MODES
from components.image_viewer.options import DEFAULT_REPLY_MODE, DEFAULT_TRANSITION_MODE, REPLY_MODE_CLOSE, REPLY_MODE_INLINE
from helpers.pets.catalog import HIDE_BOUNCE, HIDE_FLIGHT, HIDE_OFF
from helpers.translate import tr


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
        "filtered_click_action": "reveal",
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


# Option tuples are built by functions (not constants) so tr() follows the current language.
def _xmpp_resource_options():
    return (
        ("web", tr("Same resource as the website. Receives private messages from the site client.",
                   "Тот же ресурс, что у сайта. Получает приватные сообщения от веб-клиента.")),
        ("client", tr("Works alongside the website. May not receive private messages from the web resource.",
                      "Работает параллельно с сайтом. Может не получать приватные сообщения от веб-ресурса.")),
    )


def _own_message_mode_options():
    return (
        ("local", tr("Show own messages immediately. Server echoes are ignored.",
                     "Показывать свои сообщения сразу. Эхо сервера игнорируется.")),
        ("server", tr("Show own messages only when the server echoes them back.",
                      "Показывать свои сообщения только после эха сервера.")),
    )


def _notification_mode_options():
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


def _notification_hide_on_options():
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
def _notification_mute_bypass_options():
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


def _alert_chat_action_options():
    return (
        ("scroll", tr("Scroll to message", "Прокрутить к сообщению"),
         tr("Scrolls the chat to the competition message.",
            "Прокручивает чат к сообщению о соревновании.")),
        ("move", tr("Move to bottom", "Переместить вниз"),
         tr("Removes the competition message and reposts it at the bottom of the chat.",
            "Удаляет сообщение о соревновании и публикует его заново внизу чата.")),
    )


def _chatlog_filtered_click_options():
    return (
        ("reveal", tr("Reveal all messages", "Показать все сообщения"),
         tr("Clears the filter, shows all messages again and scrolls to the clicked one.",
            "Сбрасывает фильтр, снова показывает все сообщения и прокручивает к выбранному.")),
        ("split", tr("Open split view", "Открыть разделённый вид"),
         tr("Keeps the filtered list and shows the clicked message in the full chatlog in a split below.",
            "Оставляет отфильтрованный список и показывает выбранное сообщение в полном чатлоге в нижнем сплите.")),
    )


def _tracker_click_options():
    return (
        ("history", tr("Open history", "Открыть историю"),
         tr("Open the User Tracker's History tab.",
            "Открыть вкладку истории трекера пользователей.")),
        ("chat", tr("Show chat", "Показать чат"),
         tr("Open the chat window — messages and user list, no tracker.",
            "Открыть окно чата — сообщения и список пользователей, без трекера.")),
    )


def _tracker_default_tab_options():
    return (
        ("tracked", tr("Tracked", "Отслеживаемые"),
         tr("Open on the list of currently tracked users.",
            "Открывать список отслеживаемых пользователей.")),
        ("history", tr("History", "История"),
         tr("Open on the log of past tracker events.",
            "Открывать журнал прошлых событий трекера.")),
    )


def _mentions_digest_mode_options():
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


def _pets_hide_options():
    return (
        (HIDE_OFF, tr("Off", "Выкл"),
         tr("The chat stays visible during throws.",
            "Чат остаётся на виду во время бросков.")),
        (HIDE_BOUNCE, tr("Bounce", "Отскок"),
         tr("The chat fades out at the first bounce off the cursor and returns when every "
            "thrown pet has landed.",
            "Чат скрывается при первом отскоке от курсора и возвращается, когда все "
            "брошенные питомцы приземлились.")),
        (HIDE_FLIGHT, tr("Flight", "Полёт"),
         tr("The chat fades out as soon as a pet is thrown and returns when every thrown "
            "pet has landed.",
            "Чат скрывается сразу при броске питомца и возвращается, когда все "
            "брошенные питомцы приземлились.")),
    )


def _flash_easing_options():
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


def _image_reply_mode_options():
    return [
        (REPLY_MODE_INLINE, tr("Field in the viewer", "Поле в просмотрщике"),
         tr("Write the reply in an input field over the viewer; the viewer stays open.",
            "Писать ответ в поле ввода поверх просмотрщика; просмотрщик остаётся открытым.")),
        (REPLY_MODE_CLOSE, tr("Close the viewer", "Закрыть просмотрщик"),
         tr("Close the viewer and write the reply in the chat input.",
            "Закрыть просмотрщик и писать ответ в строке ввода чата.")),
    ]


def _image_transition_options():
    labels = {
        "instant": (tr("Instant", "Мгновенно"),
                    tr("Switch images with no animation.", "Переключать изображения без анимации.")),
        "fade": (tr("Fade", "Затухание"),
                 tr("Cross-fade between images.", "Плавное перетекание одного изображения в другое.")),
        "slide": (tr("Slide", "Сдвиг"),
                  tr("Images slide sideways in the direction of navigation.",
                     "Изображения сдвигаются в сторону навигации.")),
        "drift": (tr("Drift", "Дрейф"),
                  tr("A short slide combined with a fade.", "Короткий сдвиг вместе с затуханием.")),
        "zoom": (tr("Zoom", "Масштаб"),
                 tr("The old image grows and fades while the new one scales in.",
                    "Старое изображение увеличивается и тает, новое появляется с масштабированием.")),
        "flip": (tr("Flip", "Переворот"),
                 tr("The image turns around its vertical axis.", "Изображение поворачивается вокруг вертикальной оси.")),
    }
    return tuple((key, *labels[key]) for key in TRANSITION_MODES)


def _notification_position_options():
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


def _centered_style_options(inline_tip, center_tip):
    """Shared (value, label, tip) pairs for 'inline' vs 'center' placement
    settings; callers supply context-specific tooltip text."""
    return (
        ("inline", tr("In place", "На месте"), inline_tip),
        ("center", tr("Centered", "По центру"), center_tip),
    )


def _reply_style_options():
    return _centered_style_options(
        tr("Reply field opens inside the notification, at its current position.",
           "Поле ответа открывается прямо в уведомлении, на его текущем месте."),
        tr("Notification detaches and centers on screen while you reply. "
           "No effect if Notification position is already Center.",
           "Уведомление отделяется от стека и центрируется на экране на время ответа. "
           "Не действует, если «Расположение уведомлений» уже установлено на «По центру»."),
    )


def _competition_notification_style_options():
    return _centered_style_options(
        tr("Competition notification stays in the regular notification stack.",
           "Уведомление о соревновании остаётся в обычном стеке уведомлений."),
        tr("Competition notification detaches and centers on screen for more visibility. "
           "No effect if Notification position is already Center.",
           "Уведомление о соревновании отделяется от стека и центрируется на экране для большей заметности. "
           "Не действует, если «Расположение уведомлений» уже установлено на «По центру»."),
    )


def _player_hwdec_options():
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


def _player_ytdl_format_options():
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
    fill_tooltip_combo(combo, _xmpp_resource_options(), current, "web")


def fill_own_message_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, _own_message_mode_options(), current, "local")


def fill_notification_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, _notification_mode_options(), current, "stack")


def fill_notification_hide_on_combo(combo, current=None):
    fill_tooltip_combo(combo, _notification_hide_on_options(), current, "mouse_keyboard")


def fill_notification_mute_bypass_combo(combo, current=None):
    fill_tooltip_combo(combo, _notification_mute_bypass_options(), current, "off")


def fill_alert_chat_action_combo(combo, current=None):
    fill_tooltip_combo(combo, _alert_chat_action_options(), current, "scroll")


def fill_chatlog_filtered_click_combo(combo, current=None):
    fill_tooltip_combo(combo, _chatlog_filtered_click_options(), current, DEFAULTS["chatlog"]["filtered_click_action"])


def fill_tracker_click_combo(combo, current=None):
    fill_tooltip_combo(combo, _tracker_click_options(), current, "history")


def fill_tracker_default_tab_combo(combo, current=None):
    fill_tooltip_combo(combo, _tracker_default_tab_options(), current, "tracked")


def fill_mentions_digest_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, _mentions_digest_mode_options(), current, "daily")


def fill_pets_hide_combo(combo, current=None):
    fill_tooltip_combo(combo, _pets_hide_options(), current, HIDE_OFF)


def fill_flash_easing_combo(combo, current=None):
    fill_tooltip_combo(combo, _flash_easing_options(), current, DEFAULTS["chat"]["flash_easing"])


def fill_image_reply_mode_combo(combo, current=None):
    fill_tooltip_combo(combo, _image_reply_mode_options(), current, DEFAULT_REPLY_MODE)


def fill_image_transition_combo(combo, current=None):
    fill_tooltip_combo(combo, _image_transition_options(), current, DEFAULT_TRANSITION_MODE)


def fill_notification_position_combo(combo, current=None):
    fill_tooltip_combo(combo, _notification_position_options(), current, "right")


def fill_reply_style_combo(combo, current=None):
    fill_tooltip_combo(combo, _reply_style_options(), current, "inline")


def fill_competition_notification_style_combo(combo, current=None):
    fill_tooltip_combo(combo, _competition_notification_style_options(), current, "inline")


def fill_player_hwdec_combo(combo, current=None):
    fill_tooltip_combo(combo, _player_hwdec_options(), current, "auto")


def fill_player_ytdl_format_combo(combo, current=None):
    fill_tooltip_combo(combo, _player_ytdl_format_options(), current, "")

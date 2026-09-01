"""Context-aware help panel - displays keyboard shortcuts for the currently active component"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QApplication
from PyQt6.QtCore import Qt
from pathlib import Path
import json

from helpers.translate import tr, on_language_changed
from helpers.config import get_config_path


# ─────────────────────────────────────────────────────────────────────────────
# Hotkey data tables
# ─────────────────────────────────────────────────────────────────────────────

CHAT_GENERAL_KB = [
    ("F",           "Focus input field", "Фокус на поле ввода"),
    ("Tab",         "Switch Messages / Chatlog", "Переключить Сообщения / Чатлог"),
    ("U",           "Toggle user list", "Список пользователей"),
    ("B",           "Toggle ban list", "Список банов"),
    ("V",           "Toggle voice / TTS", "Голос / TTS"),
    ("M",           "Toggle effects sound", "Звуки эффектов"),
    ("N",           "Toggle notifications", "Уведомления"),
    ("T",           "Toggle always on top", "Поверх всех окон"),
    ("R",           "Reset window size", "Сбросить размер окна"),
    ("C",           "Change username color", "Цвет имени"),
    ("S",           "Toggle search bar", "Строка поиска"),
    ("E",           "Open latest competition race in browser", "Открыть последний соревновательный заезд в браузере"),
    ("X",           "Exit private chat / Clear markers, presence", "Выйти из ЛС / Очистить маркеры, присутствие"),
    ("Esc",         "Clear input focus / Close search", "Снять фокус с ввода / Закрыть поиск"),
]

CHAT_CTRL_KB = [
    ("Ctrl+;",         "Toggle emoticon selector", "Селектор эмотиконов"),
    ("Ctrl+F",         "Toggle search bar", "Строка поиска"),
    ("Ctrl+T",         "Toggle theme", "Тема"),
    ("Ctrl+U",         "Switch account", "Сменить аккаунт"),
    ("Ctrl+Shift+U",   "Toggle user tracker", "Трекер пользователей"),
    ("Ctrl+,",         "Toggle settings", "Настройки"),
    ("Ctrl+J",         "Join / Create room", "Войти / создать комнату"),
    ("Ctrl+P",         "Open chatlog parser", "Парсер чатлогов"),
    ("Ctrl+C",         "Reset username color", "Сбросить цвет имени"),
    ("Ctrl + / -",     "Font size up / down", "Размер шрифта + / −"),
    ("Ctrl+Scroll",    "Font size up / down", "Размер шрифта + / −"),
]

CHAT_SCROLL_KB = [
    ("J / ↓",       "Scroll down", "Прокрутка вниз"),
    ("K / ↑",       "Scroll up", "Прокрутка вверх"),
    ("G G",         "Scroll to top", "В начало"),
    ("Shift+G",     "Scroll to bottom", "В конец"),
    ("Space",       "Page down", "Страница вниз"),
    ("Shift+Space", "Page up", "Страница вверх"),
]

USERLIST_MOUSE = [
    ("Left click",   "Левый клик",   "View user profile", "Профиль пользователя"),
    ("Ctrl+Click",   "Ctrl+клик",    "Start private chat", "Приватный чат"),
    ("Middle click", "Средний клик", "Open game chat (if in a race)", "Чат заезда (если в гонке)"),
    ("Right click",  "Правый клик",  "Context menu", "Контекстное меню"),
]

MSG_USERNAME_MOUSE = [
    ("Left click",   "Левый клик",   "Add username to input", "Добавить ник во ввод"),
    ("Double click", "Двойной клик", "Replace input / clear if solo", "Заменить ввод / очистить если один"),
    ("Ctrl+Click",   "Ctrl+клик",    "Start private chat", "Приватный чат"),
    ("Shift+Click",  "Shift+клик",   "View user profile", "Профиль пользователя"),
    ("Right click",  "Правый клик",  "Context menu", "Контекстное меню"),
]

MSG_TIMESTAMP_MOUSE = [
    ("Left click",    "Левый клик",    "Open chatlog for that day", "Чатлог за этот день"),
    ("Left click 🏆", "Левый клик 🏆", "Open competition room chat", "Чат соревновательной комнаты"),
    ("Right click",   "Правый клик",   "Open chatlog for that day in split view", "Чатлог за день в разделённом виде"),
]

MSG_BODY_MOUSE = [
    ("Right click", "Правый клик", "Open selectable text (reply / copy / paste)", "Выделяемый текст (ответ / копировать / вставить)"),
]

MSG_COMPETITION_CHIP_MOUSE = [
    ("Left click", "Левый клик", "View profile", "Открыть профиль"),
]

MSG_URL_MOUSE = [
    ("Right click on URL", "Правый клик по ссылке", "Copy link", "Копировать ссылку"),
]

NOTIFICATION_MOUSE = [
    ("Middle click", "Средний клик", "Quick reply from message notification popup", "Быстрый ответ из попапа уведомления о сообщении"),
]

CHATLOG_TIMESTAMP_MOUSE = [
    ("Left click", "Левый клик", "Copy chatlog link for that message", "Ссылка на чатлог для сообщения"),
]

CHATLOG_KB = [
    ("H / ←",           "Previous day (hold to fast-seek)", "Предыдущий день (удерживать для быстрой перемотки)"),
    ("L / →",           "Next day (hold to fast-seek)", "Следующий день (удерживать для быстрой перемотки)"),
    ("D",               "Open calendar date picker", "Календарь выбора даты"),
    ("S / Ctrl+F",      "Toggle search bar", "Панель поиска"),
    ("P",               "Toggle chatlog parser", "Парсер чатлогов"),
    ("M",               "Toggle mention filter", "Фильтр упоминаний"),
    ("Esc",             "Close search", "Закрыть поиск"),
]

CHATLOG_USERLIST_MOUSE = [
    ("Left click",  "Левый клик",  "Filter messages by user (click again to clear)", "Фильтр сообщений по пользователю (ещё раз — сброс)"),
    ("Ctrl+Click",  "Ctrl+клик",   "Add / remove user from filter", "Добавить / убрать пользователя из фильтра"),
    ("Right click", "Правый клик", "Context menu", "Контекстное меню"),
]

CHATLOG_MOUSE = [
    ("Back button",    "Кнопка «Назад»",  "Navigate to previous day", "К предыдущему дню"),
    ("Forward button", "Кнопка «Вперёд»", "Navigate to next day", "К следующему дню"),
]

EMOTICON_KB = [
    ("H / ←",           "Move cursor left", "Курсор влево"),
    ("L / →",           "Move cursor right", "Курсор вправо"),
    ("J / ↓",           "Move cursor down", "Курсор вниз"),
    ("K / ↑",           "Move cursor up", "Курсор вверх"),
    ("Tab",             "Next emoticon group", "Следующая группа эмотиконов"),
    ("Shift+Tab",       "Previous emoticon group", "Предыдущая группа эмотиконов"),
    ("Enter / ;",       "Insert emoticon & close", "Вставить эмотикон и закрыть"),
    ("Shift+Enter",     "Insert emoticon & stay open", "Вставить эмотикон и оставить открытым"),
    ("Esc",             "Close selector", "Закрыть селектор"),
]

EMOTICON_MOUSE = [
    ("Scroll on group tabs", "Прокрутка по вкладкам групп", "Navigate groups prev / next", "Группы назад / вперёд"),
]

CHATLOG_PARSER_ACTIVE_KB = [
    ("P",               "Toggle chatlog parser", "Парсер чатлогов"),
    ("S",               "Start parsing", "Начать парсинг"),
    ("C",               "Cancel parsing", "Отменить парсинг"),
    ("Ctrl+C",          "Copy results", "Копировать результаты"),
    ("Ctrl+S",          "Save results to file", "Сохранить результаты в файл"),
    ("Ctrl+F",          "Toggle search bar", "Строка поиска"),
]

PARSER_TAG_MOUSE = [
    ("Left click",   "Левый клик",     "Add username to field", "Добавить ник в поле"),
    ("Double click", "Двойной клик",   "Replace field / clear if solo", "Заменить поле / очистить если один"),
    ("Drag",         "Перетаскивание", "Reorder saved usernames", "Изменить порядок сохранённых имён"),
]

ACCOUNTS_CONNECT_KB = [
    ("Enter / E",   "Connect to chat", "Подключиться к чату"),
    ("Tab",         "Cycle account selection", "Переключение аккаунта"),
    ("C",           "Change username color", "Цвет ника"),
    ("Ctrl+C",      "Reset username color", "Сбросить цвет ника"),
    ("D",           "Remove selected account", "Удалить выбранный аккаунт"),
    ("W",           "Add account via browser login", "Добавить аккаунт через браузер"),
    ("1",           "Toggle Auto-login", "Авто-вход"),
    ("2",           "Toggle Start minimized", "Запуск свёрнутым"),
    ("3",           "Toggle Start with system", "Запуск с системой"),
]

ACCOUNTS_CONNECT_MOUSE = [
    ("Left click", "Левый клик", "Change username color", "Цвет ника"),
    ("Ctrl+Click", "Ctrl+клик",  "Reset username color", "Сбросить цвет ника"),
]

IMAGE_KB = [
    ("Esc / Space / Q", "Close image viewer", "Закрыть просмотр изображения"),
]

IMAGE_MOUSE = [
    ("Left drag",        "Перетаскивание (ЛКМ)",        "Pan / move image", "Переместить изображение"),
    ("Ctrl + Left drag", "Ctrl + перетаскивание (ЛКМ)", "Scale image (up / down)", "Масштаб изображения (+ / −)"),
    ("Wheel",            "Колесо мыши",                 "Zoom in / out", "Приблизить / отдалить"),
    ("Right click",      "Правый клик",                 "Close image viewer", "Закрыть просмотр изображения"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Context definitions
# Each context lists one or more sections to render.
# ─────────────────────────────────────────────────────────────────────────────

CONTEXTS = {
    "chat": {
        "title": ("Chat — Controls", "Чат — управление"),
        "sections": [
            (("General", "Общее"),                                        CHAT_GENERAL_KB, None),
            (("Ctrl Shortcuts", "Ctrl-сочетания"),                        CHAT_CTRL_KB,    None),
            (("Scrolling", "Прокрутка"),                                  CHAT_SCROLL_KB,  None),
            (("User List Clicks", "Клики по списку пользователей"),       None, USERLIST_MOUSE),
            (("Message Timestamp Clicks", "Клики по времени сообщения"),  None, MSG_TIMESTAMP_MOUSE),
            (("Message Username Clicks", "Клики по нику в сообщении"),    None, MSG_USERNAME_MOUSE),
            (("Competition Player Names", "Имена игроков соревнования"),  None, MSG_COMPETITION_CHIP_MOUSE),
            (("Message Body Clicks", "Клики по телу сообщения"),          None, MSG_BODY_MOUSE),
            (("URL Interactions", "Взаимодействие с URL"),                None, MSG_URL_MOUSE),
            (("Notification Popup", "Всплывающее уведомление"),           None, NOTIFICATION_MOUSE),
        ],
    },
    "chatlog": {
        "title": ("Chatlog — Controls", "Чатлог — управление"),
        "sections": [
            (("Navigation", "Навигация"),                                CHATLOG_KB,      CHATLOG_MOUSE),
            (("Scrolling", "Прокрутка"),                                 CHAT_SCROLL_KB,  None),
            (("User List", "Список пользователей"),                      None, CHATLOG_USERLIST_MOUSE),
            (("Message Username Clicks", "Клики по нику в сообщении"),   None, MSG_USERNAME_MOUSE),
            (("Message Timestamp Clicks", "Клики по времени сообщения"), None, CHATLOG_TIMESTAMP_MOUSE),
            (("Message Body Clicks", "Клики по телу сообщения"),         None, MSG_BODY_MOUSE),
            (("URL Interactions", "Взаимодействие с URL"),               None, MSG_URL_MOUSE),
        ],
    },
    "parser": {
        "title": ("Chatlog Parser — Keyboard Shortcuts", "Парсер чатлогов — горячие клавиши"),
        "sections": [
            (("Parser Controls", "Управление парсером"),   CHATLOG_PARSER_ACTIVE_KB, None),
            (("Saved Username Tags", "Сохранённые имена"), None, PARSER_TAG_MOUSE),
        ],
    },
    "accounts_connect": {
        "title": ("Accounts — Connect Page", "Аккаунты — страница подключения"),
        "sections": [
            (("Keyboard Shortcuts", "Горячие клавиши"),        ACCOUNTS_CONNECT_KB, None),
            (("Color Button Clicks", "Клики по кнопке цвета"), None, ACCOUNTS_CONNECT_MOUSE),
        ],
    },
    "emoticon": {
        "title": ("Emoticon Selector — Controls", "Селектор эмотиконов — управление"),
        "sections": [
            (("Keyboard", "Клавиатура"), EMOTICON_KB, None),
            (("Mouse", "Мышь"),          None, EMOTICON_MOUSE),
        ],
    },
    "image": {
        "title": ("Image Viewer — Controls", "Просмотр изображений — управление"),
        "sections": [
            (("Keyboard Shortcuts", "Горячие клавиши"), IMAGE_KB, None),
            (("Mouse Controls", "Управление мышью"),    None, IMAGE_MOUSE),
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Theme colors
# ─────────────────────────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        "bg": "#1e1e1e",
        "title_color": "#6bb6d6",
        "section_color": "#6ba885",
        "text_color": "#c8c8c8",
        "sep_color": "#404040",
        "kb_bg": "#5a8fb4",
        "kb_text": "#1a1a1a",
        "mouse_bg": "#c9954d",
        "mouse_text": "#1a1a1a",
    },
    "light": {
        "bg": "#f0f0f0",
        "title_color": "#3a8fb0",
        "section_color": "#4a9570",
        "text_color": "#4a4a4a",
        "sep_color": "#d0d0d0",
        "kb_bg": "#7ba8c7",
        "kb_text": "#1a1a1a",
        "mouse_bg": "#d9a866",
        "mouse_text": "#1a1a1a",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# HelpPanel widget
# ─────────────────────────────────────────────────────────────────────────────

class HelpPanel(QWidget):
    """
    Context-aware help panel. Call show_for_context(context_key) to display
    shortcuts relevant to the currently active component.

    Valid context keys: 'chat', 'chatlog', 'emoticon', 'image'
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._config_path = get_config_path()
        self._current_context = None

        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle(tr("Help", "Справка"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        on_language_changed(self._on_language_changed)

    def _on_language_changed(self, _code=None):
        self.setWindowTitle(tr("Help", "Справка"))
        if self.isVisible() and self._current_context:
            try:
                theme = json.loads(self._config_path.read_text(encoding="utf-8")).get("ui", {}).get("theme", "dark")
            except Exception:
                theme = "dark"
            self._build(self._current_context, theme)

    # ── Public API ─────────────────────────────────────────────────────────

    def show_for_context(self, context_key: str):
        """
        Rebuild the panel for the given context and show it centered on screen.
        Calling with the same context while visible toggles the panel off.
        """
        if self.isVisible() and self._current_context == context_key:
            self.hide()
            return

        self._current_context = context_key
        try:
            theme = json.loads(self._config_path.read_text(encoding="utf-8")).get("ui", {}).get("theme", "dark")
        except Exception:
            theme = "dark"
        geo = QApplication.primaryScreen().availableGeometry()
        self._build(context_key, theme)
        self.show()
        self.raise_()
        # Measure the real content height + chrome (title + footer + margins + spacing)
        content_h = self._scroll_content.sizeHint().height()
        chrome_h = self.height() - (self.findChild(QScrollArea).height())
        desired_h = content_h + chrome_h + 48  # buffer for layout spacing + window frame
        h = min(desired_h, geo.height())
        self.resize(self.width(), h)
        self._center_on_screen()
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        super().hideEvent(event)
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.MouseButtonPress:
            try:
                gp = event.globalPosition().toPoint()
            except AttributeError:
                gp = event.globalPos()
            if not self.geometry().contains(gp):
                self.hide()
        return super().eventFilter(obj, event)

    # ── Internal ───────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)

    def _center_on_screen(self):
        geo = QApplication.primaryScreen().availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    def _build(self, context_key: str, theme: str = "dark"):
        """Rebuild UI for the given context with current theme."""
        # ── Clear existing layout ─────────────────────────────────────────
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                child = old_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    _clear_layout(child.layout())
            QWidget().setLayout(old_layout)

        # ── Theme colors ──────────────────────────────────────────────────
        colors = THEMES.get(theme, THEMES["dark"])

        self.setStyleSheet(f"QWidget {{ background-color: {colors['bg']}; }}")

        # ── Context definition ────────────────────────────────────────────
        ctx = CONTEXTS.get(context_key, CONTEXTS["chat"])

        # ── Outer layout: title (pinned) + scroll area + footer (pinned) ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(6)

        # Title — always visible, outside scroll
        title_lbl = QLabel(tr(*ctx["title"]))
        title_lbl.setStyleSheet(
            f"color: {colors['title_color']}; font-size: 14px; font-weight: bold; padding-bottom: 6px;"
        )
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title_lbl)

        # ── Scroll area wrapping all sections ─────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background-color: {colors['bg']}; border: none; }}")

        content = QWidget()
        content.setStyleSheet(f"background-color: {colors['bg']};")
        sections_layout = QVBoxLayout(content)
        sections_layout.setContentsMargins(0, 0, 8, 0)
        sections_layout.setSpacing(6)

        for section_title, kb_rows, mouse_rows in ctx["sections"]:
            if not kb_rows and not mouse_rows:
                continue

            sec_lbl = QLabel(tr(*section_title))
            sec_lbl.setStyleSheet(
                f"color: {colors['section_color']}; font-size: 12px; font-weight: bold; "
                f"padding: 6px 0 2px 0;"
            )
            sections_layout.addWidget(sec_lbl)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {colors['sep_color']}; margin: 2px 0;")
            sections_layout.addWidget(sep)

            if kb_rows:
                for key_text, desc_en, desc_ru in kb_rows:
                    sections_layout.addLayout(
                        _badge_row(key_text, tr(desc_en, desc_ru),
                                   colors['kb_bg'], colors['kb_text'], 130, colors['text_color'])
                    )

            if mouse_rows:
                for action_en, action_ru, desc_en, desc_ru in mouse_rows:
                    sections_layout.addLayout(
                        _badge_row(tr(action_en, action_ru), tr(desc_en, desc_ru),
                                   colors['mouse_bg'], colors['mouse_text'], 130, colors['text_color'])
                    )

        sections_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        self._scroll_content = content  # store ref to measure after show

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_F1, Qt.Key.Key_Escape):
            self.hide()
        else:
            super().keyPressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _badge_row(key_text, desc_text, badge_bg, badge_text, min_width, desc_color):
    row = QHBoxLayout()
    row.setSpacing(10)

    key = QLabel(key_text)
    key.setStyleSheet(
        f"background-color: {badge_bg}; color: {badge_text}; "
        f"border-radius: 4px; padding: 3px 8px; font-weight: bold;"
    )
    key.setMinimumWidth(min_width)
    key.setAlignment(Qt.AlignmentFlag.AlignCenter)

    desc = QLabel(desc_text)
    desc.setStyleSheet(f"color: {desc_color}; font-size: 12px; padding: 3px 8px;")

    row.addWidget(key)
    row.addWidget(desc, 1)
    return row


def _clear_layout(layout):
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()
        elif child.layout():
            _clear_layout(child.layout())
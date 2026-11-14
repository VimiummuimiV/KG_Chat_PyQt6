"""Profile display widget for user information"""

import threading

from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from components.avatar import request_avatar
from components.button import create_icon_button
from core.web.api_data import (
    format_registered_date,
    format_username_history,
    get_user_index_data_by_id,
    get_user_summary_by_id,
)
from helpers.browser import open_url as open_url_in_browser
from helpers.cache import get_cache
from helpers.deferred import call_later
from helpers.fonts.fonts import FontType, get_font, set_font_role
from helpers.load import make_rounded_pixmap
from helpers.translate import on_language_changed, tr, TranslatableMixin


_AVATAR_SIZE = 120
_AVATAR_RADIUS = 15


class _ProfileIcons:
    """Centralized profile card icons"""
    _USER_ID = "🆔"
    _LEVEL = "🏅"
    _STATUS_ONLINE = "🟢"
    _STATUS_OFFLINE = "🔴"
    _ACCOUNT_ACTIVE = "⚡️"
    _ACCOUNT_BANNED = "🔒"
    _REGISTERED = "🗓️"
    _ACHIEVEMENTS = "🏆"
    _TOTAL_RACES = "🏁"
    _BEST_SPEED = "🚀"
    _RATING = "🎯"
    _FRIENDS = "🤝"
    _VOCABULARIES = "📖"
    _CARS = "🚘"
    _AVATAR_PLACEHOLDER = "👤"
    _USERNAME_HISTORY = "📜"


# RANKS: level -> (name, dark_color, light_color)
_RANKS = {
    1: ('Новичок',      '#C8C8C8', '#888888'),
    2: ('Любитель',     '#7DCFCD', '#2E8B8A'),
    3: ('Таксист',      '#3DC860', '#1A7A35'),
    4: ('Профи',        '#DFC800', '#7A6A00'),
    5: ('Гонщик',       '#FF9F20', '#B35E00'),
    6: ('Маньяк',       '#FF1A5E', '#A00030'),
    7: ('Супермен',     '#C96BFF', '#8020CC'),
    8: ('Кибергонщик',  '#7B9FFF', '#2D50D0'),
    9: ('Экстракибер',  '#29CCFF', '#0080AA'),
}


class _StatCard(QFrame):
    """Styled card for displaying a stat"""
    def __init__(self, icon: str, label: str, value: str, config, value_color: str = None):
        super().__init__()
        self.config = config
        self.setObjectName("statCard")

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Icon + Label row
        header = QHBoxLayout()
        header.setSpacing(6)

        self._icon_label = QLabel(icon)
        self._icon_label.setFont(get_font(FontType.TEXT, size=20))
        header.addWidget(self._icon_label)

        self._label_widget = QLabel(label)
        self._label_widget.setObjectName("statLabel")
        set_font_role(self._label_widget, FontType.TEXT)
        self._label_widget.setWordWrap(True)
        header.addWidget(self._label_widget, stretch=1)

        layout.addLayout(header)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setFont(get_font(FontType.TEXT, weight=QFont.Weight.Bold))
        self.value_label.setWordWrap(True)
        if value_color:
            self.value_label.setStyleSheet(f"color: {value_color};")
        layout.addWidget(self.value_label)

    def _set_label(self, label: str):
        self._label_widget.setText(label)


class _UsernameHistoryWidget(TranslatableMixin, QWidget):
    """Compact username history widget with card-style header and transparent scrollable list"""

    def __init__(self, config, is_dark: bool, max_height: int = 300):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.is_dark = is_dark
        self._max_height = max_height
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._history_data = None
        self._current_username = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Card-style header using StatCard
        self._header_card = _StatCard(
            _ProfileIcons._USERNAME_HISTORY,
            tr("Username History", "История ников"),
            "", config
        )
        self._header_card.value_label.hide()
        layout.addWidget(self._header_card)

        # Transparent scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("profileScroll")

        content = QWidget()
        content.setObjectName("profileContent")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(8, 0, 8, 0)
        self.content_layout.setSpacing(3)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.scroll = scroll
        scroll.wheelEvent = self._scroll_wheel_event
        self._content_widget = content

        on_language_changed(self._retranslate)

    def _retranslate(self, _code=None):
        self._header_card._set_label(tr("Username History", "История ников"))
        if self._history_data is not None:
            self._set_history(self._current_username, self._history_data)

    def _set_history(self, current_username: str, history_data: list):
        """Set username history data"""
        self._current_username = current_username
        self._history_data = history_data
        # Clear existing items
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Helper to create labels
        def create_label(text, is_current=False):
            lbl = QLabel(text)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setFont(get_font(FontType.TEXT, weight=QFont.Weight.Bold if is_current else QFont.Weight.Normal))
            if is_current:
                lbl.setObjectName("historyCurrent")
            self.content_layout.addWidget(lbl)

        # Current username (highlighted)
        create_label(f"<b>{current_username}</b>", is_current=True)

        # History items
        date_color = '#60a5fa' if self.is_dark else '#2563eb'
        until_word = tr("until", "до")
        for item in format_username_history(history_data):
            if isinstance(item, tuple):
                username, date = item
                text = (
                    f"{username} <span style='color: #888;'>{until_word}</span> "
                    f"<span style='color: {date_color};'>{date}</span>"
                    if date else username
                )
            else:
                text = str(item)
            create_label(text)

        QTimer.singleShot(0, self.adjust_height)

    def adjust_height(self):
        """Adjust widget height to fit content, capped at max_height scaled to font size"""
        self._content_widget.adjustSize()
        text_size = get_font(FontType.TEXT).pointSize()
        max_height = int(self._max_height * text_size / 17)
        header_height = self._header_card.sizeHint().height()
        content_height = self._content_widget.sizeHint().height()
        self.setFixedHeight(min(header_height + content_height + 30, max_height))

    def _scroll_wheel_event(self, event):
        bar = self.scroll.horizontalScrollBar() if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else self.scroll.verticalScrollBar()
        bar.setValue(bar.value() - event.angleDelta().y())

    def update_theme(self, is_dark: bool):
        """Update theme"""
        self.is_dark = is_dark
        QTimer.singleShot(0, self.adjust_height)


class ProfileWidget(TranslatableMixin, QWidget):
    """Widget displaying user profile with summary and index data"""

    back_requested = pyqtSignal()
    _data_fetched = pyqtSignal(int, dict, dict)

    def __init__(self, config, icons_path):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.current_user_id = None
        self.current_username = None
        self.cache = get_cache()
        self.is_dark = config.get("ui", "theme") == "dark"
        self._card_widgets = []
        self.history_widget = None

        self._data_fetched.connect(self._display_data)
        self._init_ui()
        on_language_changed(self._retranslate)

    def _init_ui(self):
        """Initialize UI layout"""
        margin = self.config.get("ui", "margins", "widget") or 5
        spacing = self.config.get("ui", "spacing", "widget_elements") or 6

        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)

        # Top bar with back button
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._back_button = create_icon_button(
            self.icons_path, "line/arrow-go-back-line.svg", "", config=self.config
        )
        self.tr_set(self._back_button.setToolTip, "Back to Messages", "Назад к сообщениям")
        self._back_button.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self._back_button)

        self._open_profile_button = create_icon_button(
            self.icons_path, "fill/user-3-fill.svg", "", config=self.config
        )
        self.tr_set(self._open_profile_button.setToolTip, "Open Profile in Browser", "Открыть профиль в браузере")
        self._open_profile_button.clicked.connect(self._open_profile_in_browser)
        self._open_profile_button.setEnabled(False)
        top_bar.addWidget(self._open_profile_button)

        self._title_label = QLabel()
        set_font_role(self._title_label, FontType.HEADER)
        top_bar.addWidget(self._title_label, stretch=1)
        layout.addLayout(top_bar)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        container = QWidget()
        self.content_layout = QVBoxLayout(container)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_layout.setSpacing(spacing)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)

        # Avatar section
        self._init_avatar_section()

        # Data cards container
        self._cards_container = QWidget()
        self._cards_layout = QGridLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 10, 0, 10)
        self._cards_layout.setSpacing(10)
        for i in range(3):
            self._cards_layout.setColumnStretch(i, 1)
        self.content_layout.addWidget(self._cards_container, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.content_layout.addStretch()

    def _init_avatar_section(self):
        """Initialize avatar display section"""
        # Single avatar label for both placeholder and image
        self.avatar_label = QLabel(_ProfileIcons._AVATAR_PLACEHOLDER)
        self.avatar_label.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFont(get_font(FontType.HEADER, size=48))
        self.avatar_label.setObjectName("profileAvatar")

        self.content_layout.addWidget(self.avatar_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.content_layout.addSpacing(10)

    def _open_profile_in_browser(self):
        if self.current_user_id:
            open_url_in_browser(
                f"https://klavogonki.ru/u/#/{self.current_user_id}/",
                self.config.get("browser") if self.config else None,
            )

    def load_profile(self, user_id: int, username: str):
        """Load and display user profile data.

        Skip network/UI reset when the same user is already loaded — repeated
        clicks from the userlist (or elsewhere) must not re-fetch.
        """
        if self.current_user_id == user_id:
            # Keep title in sync in case the login string changed
            self.current_username = username
            self._title_label.setText(username)
            self._open_profile_button.setEnabled(True)
            return

        self.current_user_id = user_id
        self.current_username = username
        self._title_label.setText(username)
        self._open_profile_button.setEnabled(True)

        # Reset to placeholder
        self.avatar_label.clear()
        self.avatar_label.setText(_ProfileIcons._AVATAR_PLACEHOLDER)

        if self.history_widget:
            self.history_widget.deleteLater()
            self.history_widget = None

        for card in self._card_widgets:
            card.value_label.setText("—")

        # Load data
        request_avatar(self, str(user_id), lambda pixmap: self._set_avatar(str(user_id), pixmap))
        call_later(self, 0, lambda: self._fetch_and_display_data(user_id))

    def _set_avatar(self, user_id: str, pixmap: QPixmap):
        """Set avatar pixmap — only applied if this user is still active"""
        if user_id != str(self.current_user_id):
            return
        if not pixmap.isNull():
            self.avatar_label.setPixmap(make_rounded_pixmap(pixmap, _AVATAR_SIZE, _AVATAR_RADIUS))
            self.avatar_label.setText("")  # Clear the emoji text

    def _fetch_and_display_data(self, user_id: int):
        """Fetch summary and index data in a background thread, then emit with user_id"""
        def _worker():
            try:
                summary = get_user_summary_by_id(user_id)
                index_data = get_user_index_data_by_id(user_id)
                self._data_fetched.emit(user_id, summary, index_data)
            except Exception as e:
                print(f"Error fetching profile data: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    @pyqtSlot(int, dict, dict)
    def _display_data(self, user_id: int, summary: dict, index_data: dict):
        """Display fetched data — silently discard if user has changed since fetch started"""
        if user_id != self.current_user_id:
            return

        if not summary or not index_data:
            return

        self._last_summary = summary
        self._last_index_data = index_data

        user_data = summary.get('user', {})
        history = user_data.get('history')

        # Display username history widget
        if history and isinstance(history, list):
            if not self.history_widget:
                self.history_widget = _UsernameHistoryWidget(self.config, self.is_dark)
                self.content_layout.insertWidget(2, self.history_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.history_widget._set_history(user_data.get('login', ''), history)

        self._populate_cards(summary, index_data)

    def _populate_cards(self, summary: dict, index_data: dict):
        """Populate data cards with user information"""
        user_data = summary.get('user', {})
        stats = index_data.get('stats', {})
        is_online = summary.get('is_online')
        is_blocked = user_data.get('blocked')

        level = summary.get('level')
        rank_name, rank_dark, rank_light = _RANKS.get(level, ('N/A', None, None))
        rank_color = rank_dark if self.is_dark else rank_light

        online_text = tr("Online", "В сети") if is_online else tr("Offline", "Не в сети")
        account_text = tr("Active", "Активен") if not is_blocked else tr("Banned", "Забанен")
        best_speed = stats.get('best_speed')
        speed_text = (
            f"{best_speed} {tr('cpm', 'зн/мин')}" if best_speed else 'N/A'
        )

        self.cards_data = [
            (_ProfileIcons._USER_ID, tr("User ID", "ID пользователя"), str(user_data.get('id', 'N/A')), None),
            (_ProfileIcons._LEVEL, tr("Rank", "Ранг"), rank_name, rank_color),
            (_ProfileIcons._STATUS_ONLINE if is_online else _ProfileIcons._STATUS_OFFLINE,
             tr("Status", "Статус"), online_text, None),
            (_ProfileIcons._ACCOUNT_ACTIVE if not is_blocked else _ProfileIcons._ACCOUNT_BANNED,
             tr("Account", "Аккаунт"), account_text, None),
            (_ProfileIcons._REGISTERED, tr("Registered", "Регистрация"),
             format_registered_date(stats.get('registered')) or 'N/A', None),
            (_ProfileIcons._ACHIEVEMENTS, tr("Achievements", "Достижения"),
             str(stats.get('achieves_cnt', 'N/A')), None),
            (_ProfileIcons._TOTAL_RACES, tr("Total Races", "Всего заездов"),
             str(stats.get('total_num_races', 'N/A')), None),
            (_ProfileIcons._BEST_SPEED, tr("Best Speed", "Лучшая скорость"), speed_text, None),
            (_ProfileIcons._RATING, tr("Rating", "Рейтинг"), str(stats.get('rating_level', 'N/A')), None),
            (_ProfileIcons._FRIENDS, tr("Friends", "Друзья"), str(stats.get('friends_cnt', 'N/A')), None),
            (_ProfileIcons._VOCABULARIES, tr("Vocabularies", "Словари"), str(stats.get('vocs_cnt', 'N/A')), None),
            (_ProfileIcons._CARS, tr("Cars", "Машины"), str(stats.get('cars_cnt', 'N/A')), None),
        ]

        cols = max(1, min(3, self.width() // self._grid_width(1)))
        self.last_cols = cols
        self.rebuild_card_layout(cols)

    def _grid_width(self, cols: int) -> int:
        """Compute shared fixed width for cards grid and history widget based on font size"""
        text_size = get_font(FontType.TEXT).pointSize()
        card_width = max(300, int(400 * text_size / 17))
        return card_width * cols + 10 * (cols - 1)

    def rebuild_card_layout(self, cols: int):
        """Rebuild card layout with specified number of columns"""
        if not hasattr(self, 'cards_data'):
            return

        # Clear existing
        self._card_widgets.clear()
        while self._cards_layout.count():
            self._cards_layout.takeAt(0).widget().deleteLater()

        # Update column stretch
        for i in range(3):
            self._cards_layout.setColumnStretch(i, 1 if i < cols else 0)

        # Create cards
        w = self._grid_width(cols)
        self._cards_container.setFixedWidth(w)
        if self.history_widget:
            self.history_widget.setFixedWidth(self._grid_width(1))
        for index, (icon, label, value, value_color) in enumerate(self.cards_data):
            card = _StatCard(icon, label, value, self.config, value_color)
            self._card_widgets.append(card)
            self._cards_layout.addWidget(card, index // cols, index % cols)

    def update_theme(self):
        """Update widget styling for theme changes"""
        self.is_dark = self.config.get("ui", "theme") == "dark"

        if self.history_widget:
            self.history_widget.update_theme(self.is_dark)

    def _retranslate(self, _code=None):
        self.retranslate_all()
        if self.current_user_id and hasattr(self, '_last_summary') and hasattr(self, '_last_index_data'):
            self._populate_cards(self._last_summary, self._last_index_data)

    def resizeEvent(self, event):
        """Handle resize to adjust card grid columns"""
        super().resizeEvent(event)
        cols = max(1, min(3, self.width() // self._grid_width(1)))  # font-aware col count
        if hasattr(self, 'last_cols') and self.last_cols != cols:
            self.last_cols = cols
            self.rebuild_card_layout(cols)

"""Profile display widget for user information"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QGridLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtGui import QPixmap, QFont

from helpers.create import create_icon_button
from helpers.load import make_rounded_pixmap
from helpers.cache import get_cache
from helpers.fonts import get_font, FontType
from core.api_data import(
    get_user_summary_by_id,
    get_user_index_data_by_id,
    format_registered_date,
    format_username_history
)


class ProfileIcons:
    """Centralized profile card icons"""
    USER_ID = "🆔"
    LEVEL = "🏅"
    STATUS_ONLINE = "🟢"
    STATUS_OFFLINE = "🔴"
    ACCOUNT_ACTIVE = "⚡️"
    ACCOUNT_BANNED = "🔒"
    REGISTERED = "🗓️"
    ACHIEVEMENTS = "🏆"
    TOTAL_RACES = "🏁"
    BEST_SPEED = "🚀"
    RATING = "🎯"
    FRIENDS = "🤝"
    VOCABULARIES = "📖"
    CARS = "🚘"
    AVATAR_PLACEHOLDER = "👤"
    USERNAME_HISTORY = "📜"


class ContainerStyleMixin:
    """Unified styling for elevated container components"""
    
    @staticmethod
    def get_container_style(is_dark: bool) -> str:
        """Get container background and border styling"""
        if is_dark:
            return """
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 4px;
            """
        return """
            background-color: rgba(0, 0, 0, 0.03);
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            padding: 4px;
        """
    
    @staticmethod
    def get_secondary_label_color(is_dark: bool) -> str:
        """Get secondary label color"""
        return "rgba(255, 255, 255, 0.6)" if is_dark else "rgba(0, 0, 0, 0.5)"


class StatCard(QFrame):
    """Styled card for displaying a stat"""
    def __init__(self, icon: str, label: str, value: str, config, is_dark: bool):
        super().__init__()
        self.config = config
        self.is_dark = is_dark
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(200)
        self.setMaximumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        # Icon + Label row
        header = QHBoxLayout()
        header.setSpacing(6)
        
        self.icon_label = QLabel(icon)
        self.icon_label.setFont(get_font(FontType.TEXT, size=20))
        header.addWidget(self.icon_label)
        
        self.label_widget = QLabel(label)
        self.label_widget.setFont(get_font(FontType.TEXT))
        header.addWidget(self.label_widget, stretch=1)
        
        layout.addLayout(header)
        
        # Value
        self.value_label = QLabel(value)
        self.value_label.setFont(get_font(FontType.TEXT, weight=QFont.Weight.Bold))
        layout.addWidget(self.value_label)
        
        self._update_style()
    
    def _update_style(self):
        """Update card and label styling"""
        self.setStyleSheet(f"QFrame {{ {ContainerStyleMixin.get_container_style(self.is_dark)} }}")
        if hasattr(self, 'label_widget'):
            self.label_widget.setStyleSheet(f"color: {ContainerStyleMixin.get_secondary_label_color(self.is_dark)};")
    
    def update_theme(self, is_dark: bool):
        """Update theme"""
        self.is_dark = is_dark
        self._update_style()


class UsernameHistoryWidget(QWidget):
    """Compact username history widget with card-style header and transparent scrollable list"""
    
    def __init__(self, config, is_dark: bool, max_height: int = 300):
        super().__init__()
        self.config = config
        self.is_dark = is_dark
        self._max_height = max_height
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Card-style header using StatCard
        self.header_card = StatCard(ProfileIcons.USERNAME_HISTORY, "Username History", "", config, is_dark)
        self.header_card.value_label.hide()  # Hide the value label for header-only card
        layout.addWidget(self.header_card)
        
        # Transparent scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(8, 0, 8, 0)
        self.content_layout.setSpacing(3)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.scroll = scroll
        self.content_widget = content

    def set_history(self, current_username: str, history_data: list):
        """Set username history data"""
        # Clear existing items
        while self.content_layout.count():
            self.content_layout.takeAt(0).widget().deleteLater()
        
        # Helper to create labels
        def create_label(text, color=None):
            lbl = QLabel(text)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setFont(get_font(FontType.TEXT, weight=QFont.Weight.Bold if color else QFont.Weight.Normal))
            style = f"color: {color}; background: transparent;" if color else "background: transparent;"
            lbl.setStyleSheet(style)
            self.content_layout.addWidget(lbl)
            return lbl
        
        # Current username (highlighted)
        self.current_label = create_label(
            f"<b>{current_username}</b> (current)", 
            '#00aaff' if self.is_dark else '#0066cc'
        )
        
        # History items
        for item in format_username_history(history_data):
            if isinstance(item, tuple):
                username, date = item
                text = f"{username} <span style='color: #888;'>→ {date}</span>" if date else username
            else:
                text = str(item)
            create_label(text)
        
        QTimer.singleShot(0, self._adjust_height)

    def _adjust_height(self):
        """Adjust widget height to fit content, capped at max_height"""
        self.content_widget.adjustSize()
        header_h = self.header_card.sizeHint().height()
        content_h = self.content_widget.sizeHint().height()
        total = min(header_h + content_h + 30, self._max_height)
        self.setFixedHeight(total)

    def update_theme(self, is_dark: bool):
        """Update theme"""
        self.is_dark = is_dark
        self.header_card.update_theme(is_dark)
        if hasattr(self, 'current_label'):
            self.current_label.setStyleSheet(f"color: {'#00aaff' if is_dark else '#0066cc'}; background: transparent;")
        QTimer.singleShot(0, self._adjust_height)


class ProfileWidget(QWidget):
    """Widget displaying user profile with summary and index data"""
    
    back_requested = pyqtSignal()
    _avatar_loaded = pyqtSignal(str, QPixmap)
    _data_fetched = pyqtSignal(dict, dict)
    
    def __init__(self, config, icons_path):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.current_user_id = None
        self.current_username = None
        self.cache = get_cache()
        self.is_dark = config.get("ui", "theme") == "dark"
        self.card_widgets = []
        self.history_widget = None
        
        self._avatar_loaded.connect(self._set_avatar)
        self._data_fetched.connect(self._display_data)
        self._init_ui()
    
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
        
        self.back_button = create_icon_button(
            self.icons_path, "go-back.svg", "Back to Messages", config=self.config
        )
        self.back_button.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self.back_button)
        
        self.title_label = QLabel()
        self.title_label.setFont(get_font(FontType.HEADER))
        top_bar.addWidget(self.title_label, stretch=1)
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
        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 10, 0, 10)
        self.cards_layout.setSpacing(10)
        for i in range(3):
            self.cards_layout.setColumnStretch(i, 1)
        self.content_layout.addWidget(self.cards_container)
        self.content_layout.addStretch()
    
    def _init_avatar_section(self):
        """Initialize avatar display section"""
        avatar_container = QWidget()
        avatar_container.setFixedSize(120, 120)
        
        # Placeholder
        self.avatar_placeholder = QLabel(ProfileIcons.AVATAR_PLACEHOLDER)
        self.avatar_placeholder.setFixedSize(120, 120)
        self.avatar_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_placeholder.setFont(get_font(FontType.HEADER, size=48))
        self._update_avatar_placeholder_style()
        
        # Actual avatar (overlaid)
        self.avatar_label = QLabel(parent=avatar_container)
        self.avatar_label.setFixedSize(120, 120)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setVisible(False)
        self.avatar_label.move(0, 0)
        
        QVBoxLayout(avatar_container).addWidget(self.avatar_placeholder)
        self.content_layout.addWidget(avatar_container, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.content_layout.addSpacing(10)
    
    def _update_avatar_placeholder_style(self):
        """Update avatar placeholder style based on theme"""
        style = f"""
            QLabel {{
                {ContainerStyleMixin.get_container_style(self.is_dark)}
                border-radius: 15px;
                border-width: 2px;
            }}
        """
        self.avatar_placeholder.setStyleSheet(style)
    
    def load_profile(self, user_id: int, username: str):
        """Load and display user profile data"""
        self.current_user_id = user_id
        self.current_username = username
        self.title_label.setText(username)
        
        # Reset UI
        self.avatar_label.clear()
        self.avatar_label.setVisible(False)
        self.avatar_placeholder.setVisible(True)
        
        if self.history_widget:
            self.history_widget.deleteLater()
            self.history_widget = None
        
        for card in self.card_widgets:
            card.value_label.setText("—")
        
        # Load data
        self.cache.load_avatar_async(str(user_id), 
            lambda uid, pm: uid == str(user_id) and self._avatar_loaded.emit(uid, pm), timeout=3)
        QTimer.singleShot(0, lambda: self._fetch_and_display_data(user_id))
    
    @pyqtSlot(str, QPixmap)
    def _set_avatar(self, user_id: str, pixmap: QPixmap):
        """Set avatar pixmap"""
        if pixmap and not pixmap.isNull():
            self.avatar_label.setPixmap(make_rounded_pixmap(pixmap, 120, 15))
            self.avatar_label.setVisible(True)
            self.avatar_placeholder.setVisible(False)
    
    def _fetch_and_display_data(self, user_id: int):
        """Fetch summary and index data, then display"""
        def _worker():
            try:
                summary = get_user_summary_by_id(user_id)
                index_data = get_user_index_data_by_id(user_id)
                self._data_fetched.emit(summary, index_data)
            except Exception as e:
                print(f"Error fetching profile data: {e}")
        
        import threading
        threading.Thread(target=_worker, daemon=True).start()
    
    @pyqtSlot(dict, dict)
    def _display_data(self, summary: dict, index_data: dict):
        """Display fetched data in UI"""
        if not summary or not index_data:
            return
        
        user_data = summary.get('user', {})
        history = user_data.get('history')
        
        # Display username history widget
        if history and isinstance(history, list):
            if not self.history_widget:
                self.history_widget = UsernameHistoryWidget(self.config, self.is_dark)
                self.content_layout.insertWidget(2, self.history_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.history_widget.set_history(user_data.get('login', ''), history)
        
        self._populate_cards(summary, index_data)
    
    def _populate_cards(self, summary: dict, index_data: dict):
        """Populate data cards with user information"""
        user_data = summary.get('user', {})
        stats = index_data.get('stats', {})
        is_online = summary.get('is_online')
        is_blocked = user_data.get('blocked')
        
        self._cards_data = [
            (ProfileIcons.USER_ID, "User ID", str(user_data.get('id', 'N/A'))),
            (ProfileIcons.LEVEL, "Level", str(summary.get('level', 'N/A'))),
            (ProfileIcons.STATUS_ONLINE if is_online else ProfileIcons.STATUS_OFFLINE, 
             "Status", "Online" if is_online else "Offline"),
            (ProfileIcons.ACCOUNT_ACTIVE if not is_blocked else ProfileIcons.ACCOUNT_BANNED, 
             "Account", "Active" if not is_blocked else "Banned"),
            (ProfileIcons.REGISTERED, "Registered", format_registered_date(stats.get('registered')) or 'N/A'),
            (ProfileIcons.ACHIEVEMENTS, "Achievements", str(stats.get('achieves_cnt', 'N/A'))),
            (ProfileIcons.TOTAL_RACES, "Total Races", str(stats.get('total_num_races', 'N/A'))),
            (ProfileIcons.BEST_SPEED, "Best Speed", 
             f"{stats.get('best_speed', 'N/A')} зн/мин" if stats.get('best_speed') else 'N/A'),
            (ProfileIcons.RATING, "Rating", str(stats.get('rating_level', 'N/A'))),
            (ProfileIcons.FRIENDS, "Friends", str(stats.get('friends_cnt', 'N/A'))),
            (ProfileIcons.VOCABULARIES, "Vocabularies", str(stats.get('vocs_cnt', 'N/A'))),
            (ProfileIcons.CARS, "Cars", str(stats.get('cars_cnt', 'N/A'))),
        ]
        
        cols = 1 if self.width() < 600 else 2 if self.width() < 900 else 3
        self._last_cols = cols
        self._rebuild_card_layout(cols)
    
    def _rebuild_card_layout(self, cols: int):
        """Rebuild card layout with specified number of columns"""
        if not hasattr(self, '_cards_data'):
            return
        
        # Clear existing
        self.card_widgets.clear()
        while self.cards_layout.count():
            self.cards_layout.takeAt(0).widget().deleteLater()
        
        # Update column stretch
        for i in range(3):
            self.cards_layout.setColumnStretch(i, 1 if i < cols else 0)
        
        # Create cards
        for idx, (icon, label, value) in enumerate(self._cards_data):
            card = StatCard(icon, label, value, self.config, self.is_dark)
            self.card_widgets.append(card)
            self.cards_layout.addWidget(card, idx // cols, idx % cols)
    
    def update_theme(self):
        """Update widget styling for theme changes"""
        self.is_dark = self.config.get("ui", "theme") == "dark"
        self._update_avatar_placeholder_style()
        
        if self.history_widget:
            self.history_widget.update_theme(self.is_dark)
        
        for card in self.card_widgets:
            card.update_theme(self.is_dark)
    
    def resizeEvent(self, event):
        """Handle resize to adjust card grid columns"""
        super().resizeEvent(event)
        cols = 1 if self.width() < 600 else 2 if self.width() < 900 else 3
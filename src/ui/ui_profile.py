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
from core.api_data import get_user_summary_by_id, get_user_index_data_by_id, format_registered_date


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


class StatCard(QFrame):
    """Styled card for displaying a stat"""
    def __init__(self, icon: str, label: str, value: str, config, is_dark: bool):
        super().__init__()
        self.config = config
        self.is_dark = is_dark
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self._update_card_style()
        
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        self.setLayout(layout)
        
        # Icon + Label row
        header = QHBoxLayout()
        header.setSpacing(6)
        
        self.icon_label = QLabel(icon)
        self.icon_label.setFont(get_font(FontType.TEXT, size=20))
        header.addWidget(self.icon_label)
        
        self.label_widget = QLabel(label)
        self.label_widget.setFont(get_font(FontType.TEXT))
        self._update_label_style()
        header.addWidget(self.label_widget, stretch=1)
        
        layout.addLayout(header)
        
        # Value
        self.value_label = QLabel(value)
        self.value_label.setFont(get_font(FontType.TEXT, weight=QFont.Weight.Bold))
        layout.addWidget(self.value_label)
    
    def _update_card_style(self):
        """Update card styling based on theme"""
        if self.is_dark:
            self.setStyleSheet("""
                QFrame {
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 8px;
                    padding: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: rgba(0, 0, 0, 0.03);
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 8px;
                    padding: 4px;
                }
            """)
    
    def _update_label_style(self):
        """Update label text color based on theme"""
        if self.is_dark:
            self.label_widget.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        else:
            self.label_widget.setStyleSheet("color: rgba(0, 0, 0, 0.5);")
    
    def update_theme(self, is_dark: bool):
        """Update theme for this card"""
        self.is_dark = is_dark
        self._update_card_style()
        self._update_label_style()


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
        
        self._avatar_loaded.connect(self._set_avatar)
        self._data_fetched.connect(self._display_data)
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI layout"""
        margin = self.config.get("ui", "margins", "widget") or 5
        spacing = self.config.get("ui", "spacing", "widget_elements") or 6
        
        layout = QVBoxLayout()
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)
        self.setLayout(layout)
        
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
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_layout.setSpacing(spacing)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        container.setLayout(self.content_layout)
        scroll.setWidget(container)
        
        # Avatar section
        avatar_container = QWidget()
        avatar_container.setFixedSize(120, 120)
        avatar_layout = QVBoxLayout()
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        avatar_layout.setSpacing(0)
        avatar_container.setLayout(avatar_layout)
        
        # Placeholder avatar
        self.avatar_placeholder = QLabel()
        self.avatar_placeholder.setFixedSize(120, 120)
        self.avatar_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_placeholder.setScaledContents(False)
        self._update_avatar_placeholder_style()
        self.avatar_placeholder.setText(ProfileIcons.AVATAR_PLACEHOLDER)
        self.avatar_placeholder.setFont(get_font(FontType.HEADER, size=48))
        
        # Actual avatar image
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(120, 120)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setScaledContents(False)
        self.avatar_label.setVisible(False)
        
        avatar_layout.addWidget(self.avatar_placeholder)
        self.avatar_label.setParent(avatar_container)
        self.avatar_label.move(0, 0)
        
        self.content_layout.addWidget(avatar_container, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # Status and title
        self.status_title_label = QLabel()
        self.status_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.status_title_label)
        
        # Data cards container
        self.cards_container = QWidget()
        self.cards_layout = QGridLayout()
        self.cards_layout.setContentsMargins(0, 10, 0, 10)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setColumnStretch(0, 1)
        self.cards_layout.setColumnStretch(1, 1)
        self.cards_layout.setColumnStretch(2, 1)
        self.cards_container.setLayout(self.cards_layout)
        self.content_layout.addWidget(self.cards_container)
        
        self.content_layout.addStretch()
    
    def _update_avatar_placeholder_style(self):
        """Update avatar placeholder style based on theme"""
        if self.is_dark:
            self.avatar_placeholder.setStyleSheet("""
                QLabel {
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 2px solid rgba(255, 255, 255, 0.1);
                    border-radius: 15px;
                }
            """)
        else:
            self.avatar_placeholder.setStyleSheet("""
                QLabel {
                    background-color: rgba(0, 0, 0, 0.03);
                    border: 2px solid rgba(0, 0, 0, 0.1);
                    border-radius: 15px;
                }
            """)
    
    def load_profile(self, user_id: int, username: str):
        """Load and display user profile data"""
        self.current_user_id = user_id
        self.current_username = username
        
        self._reset_avatar_to_placeholder()
        self.title_label.setText(username)
        self._load_avatar(str(user_id))
        
        QTimer.singleShot(0, lambda: self._fetch_and_display_data(user_id))
    
    def _load_avatar(self, user_id: str):
        """Load and display user avatar using cache"""
        def avatar_callback(uid: str, pixmap: QPixmap):
            if uid == user_id:
                self._avatar_loaded.emit(uid, pixmap)
        
        self.cache.load_avatar_async(user_id, avatar_callback, timeout=3)
    
    @pyqtSlot(str, QPixmap)
    def _set_avatar(self, user_id: str, pixmap: QPixmap):
        """Set avatar pixmap"""
        if pixmap and not pixmap.isNull():
            rounded = make_rounded_pixmap(pixmap, 120, 15)
            self.avatar_label.setPixmap(rounded)
            self.avatar_label.setVisible(True)
            self.avatar_placeholder.setVisible(False)
    
    def _reset_avatar_to_placeholder(self):
        """Reset to placeholder"""
        self.avatar_label.clear()
        self.avatar_label.setVisible(False)
        self.avatar_placeholder.setVisible(True)
    
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
        
        # Display status and title
        status_parts = []
        if user_data.get('title'):
            status_parts.append(user_data['title'])
        
        status_obj = user_data.get('status')
        if status_obj and isinstance(status_obj, dict):
            if status_obj.get('title'):
                status_parts.append(status_obj['title'])
        
        if status_parts:
            status_text = " • ".join(status_parts)
            self.status_title_label.setText(status_text)
            self.status_title_label.setVisible(True)
        else:
            self.status_title_label.setVisible(False)
        
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
        
        width = self.width()
        if width < 600:
            cols = 1
        elif width < 900:
            cols = 2
        else:
            cols = 3
        self._last_cols = cols
        
        self._rebuild_card_layout(cols)
    
    def _rebuild_card_layout(self, cols: int):
        """Rebuild card layout with specified number of columns"""
        if not hasattr(self, '_cards_data'):
            return
        
        # Clear existing cards
        self.card_widgets.clear()
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Update column stretch
        for i in range(3):
            self.cards_layout.setColumnStretch(i, 0)
        for i in range(cols):
            self.cards_layout.setColumnStretch(i, 1)
        
        # Create cards in grid
        for idx, (icon, label, value) in enumerate(self._cards_data):
            row = idx // cols
            col = idx % cols
            card = StatCard(icon, label, value, self.config, self.is_dark)
            self.card_widgets.append(card)
            self.cards_layout.addWidget(card, row, col)
    
    def update_theme(self):
        """Update widget styling for theme changes"""
        self.is_dark = self.config.get("ui", "theme") == "dark"
        self._update_avatar_placeholder_style()
        
        for card in self.card_widgets:
            card.update_theme(self.is_dark)
    
    def resizeEvent(self, event):
        """Handle resize to adjust card grid columns"""
        super().resizeEvent(event)
        width = self.width()
        
        if width < 600:
            cols = 1
        elif width < 900:
            cols = 2
        else:
            cols = 3
        
        if not hasattr(self, '_last_cols') or self._last_cols != cols:
            self._last_cols = cols
            self._rebuild_card_layout(cols)

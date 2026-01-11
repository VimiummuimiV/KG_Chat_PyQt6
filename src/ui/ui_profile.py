"""Profile display widget for user information"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QGridLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap

from helpers.create import create_icon_button
from helpers.load import make_rounded_pixmap
from helpers.cache import get_cache
from core.api_data import get_user_summary_by_id, get_user_index_data_by_id, format_registered_date


class StatCard(QFrame):
    """Styled card for displaying a stat"""
    def __init__(self, icon: str, label: str, value: str, config):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        self.setLayout(layout)
        
        # Icon + Label row
        header = QHBoxLayout()
        header.setSpacing(6)
        
        icon_label = QLabel(icon)
        icon_font = QFont(config.get("ui", "font_family"), config.get("ui", "font_size") + 2)
        icon_label.setFont(icon_font)
        header.addWidget(icon_label)
        
        label_widget = QLabel(label)
        label_font = QFont(config.get("ui", "font_family"), config.get("ui", "font_size") - 1)
        label_widget.setFont(label_font)
        label_widget.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        header.addWidget(label_widget, stretch=1)
        
        layout.addLayout(header)
        
        # Value
        value_label = QLabel(value)
        value_font = QFont(config.get("ui", "font_family"), config.get("ui", "font_size") + 3)
        value_font.setBold(True)
        value_label.setFont(value_font)
        layout.addWidget(value_label)


class ProfileWidget(QWidget):
    """Widget displaying user profile with summary and index data"""
    
    back_requested = pyqtSignal()
    _avatar_loaded = pyqtSignal(str, QPixmap)
    
    def __init__(self, config, icons_path):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.current_user_id = None
        self.current_username = None
        self.cache = get_cache()
        
        self._avatar_loaded.connect(self._set_avatar)
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
        title_font = QFont(self.config.get("ui", "font_family"), 
                          self.config.get("ui", "font_size") + 2)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
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
        self.avatar_placeholder.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.05);
                border: 2px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
            }
        """)
        self.avatar_placeholder.setText("👤")
        placeholder_font = QFont(self.config.get("ui", "font_family"), 48)
        self.avatar_placeholder.setFont(placeholder_font)
        
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
                
                QTimer.singleShot(0, lambda: self._display_data(summary, index_data))
            except Exception as e:
                print(f"Error fetching profile data: {e}")
        
        import threading
        threading.Thread(target=_worker, daemon=True).start()
    
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
        
        self._cards_data = [
            ("🆔", "User ID", str(user_data.get('id', 'N/A'))),
            ("⭐", "Level", str(summary.get('level', 'N/A'))),
            ("🟢" if summary.get('is_online') else "🔴", "Status", "Online" if summary.get('is_online') else "Offline"),
            ("✅" if not user_data.get('blocked') else "❌", "Account", "Active" if not user_data.get('blocked') else "Banned"),
            ("📅", "Registered", format_registered_date(stats.get('registered')) or 'N/A'),
            ("🏆", "Achievements", str(stats.get('achieves_cnt', 'N/A'))),
            ("🏁", "Total Races", str(stats.get('total_num_races', 'N/A'))),
            ("⚡", "Best Speed", f"{stats.get('best_speed', 'N/A')} зн/мин" if stats.get('best_speed') else 'N/A'),
            ("📊", "Rating", str(stats.get('rating_level', 'N/A'))),
            ("👥", "Friends", str(stats.get('friends_cnt', 'N/A'))),
            ("📚", "Vocabularies", str(stats.get('vocs_cnt', 'N/A'))),
            ("🚗", "Cars", str(stats.get('cars_cnt', 'N/A'))),
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
            card = StatCard(icon, label, value, self.config)
            self.cards_layout.addWidget(card, row, col)
    
    def update_theme(self):
        """Update widget styling for theme changes"""
        pass
    
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

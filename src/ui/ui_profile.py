"""Profile display widget for user information"""
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QGridLayout, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPixmap

from helpers.create import create_icon_button
from helpers.load import load_avatar_by_id, make_rounded_pixmap
from helpers.html_processor import process_bio_html
from core.api_data import get_user_summary_by_id, get_user_index_data_by_id


class ProfileWidget(QWidget):
    """Widget displaying user profile with summary and index data"""
    
    back_requested = pyqtSignal()
    
    def __init__(self, config, icons_path):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.current_user_id = None
        self.current_username = None
        
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
        
        self.title_label = QLabel("Profile")
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
        container.setLayout(self.content_layout)
        scroll.setWidget(container)
        
        # Avatar section
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(120, 120)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.avatar_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # Username
        self.username_label = QLabel()
        username_font = QFont(self.config.get("ui", "font_family"), 
                             self.config.get("ui", "font_size") + 4)
        username_font.setBold(True)
        self.username_label.setFont(username_font)
        self.username_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.username_label)
        
        # Status and title
        self.status_title_label = QLabel()
        self.status_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.status_title_label)
        
        # Data grid
        self.grid_container = QFrame()
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(0, 10, 0, 10)
        self.grid_container.setLayout(self.grid_layout)
        self.content_layout.addWidget(self.grid_container)
        
        # Bio section (hidden by default, shown when loaded)
        self.bio_label = QLabel("Biography")
        bio_font = QFont(self.config.get("ui", "font_family"), 
                        self.config.get("ui", "font_size") + 1)
        bio_font.setBold(True)
        self.bio_label.setFont(bio_font)
        self.bio_label.setVisible(False)
        self.content_layout.addWidget(self.bio_label)
        
        self.bio_content = QLabel()
        self.bio_content.setWordWrap(True)
        self.bio_content.setTextFormat(Qt.TextFormat.RichText)
        self.bio_content.setOpenExternalLinks(True)
        self.bio_content.setVisible(False)
        self.content_layout.addWidget(self.bio_content)
        
        self.content_layout.addStretch()
    
    def load_profile(self, user_id: int, username: str):
        """Load and display user profile data"""
        self.current_user_id = user_id
        self.current_username = username
        
        # Update title
        self.title_label.setText(f"Profile - {username}")
        self.username_label.setText(username)
        
        # Load avatar
        self._load_avatar(user_id)
        
        # Load data in background
        QTimer.singleShot(0, lambda: self._fetch_and_display_data(user_id))
    
    def _load_avatar(self, user_id: int):
        """Load and display user avatar"""
        def _worker():
            pixmap = load_avatar_by_id(str(user_id), timeout=3)
            if pixmap:
                QTimer.singleShot(0, lambda: self._set_avatar(pixmap))
        
        import threading
        threading.Thread(target=_worker, daemon=True).start()
    
    def _set_avatar(self, pixmap: QPixmap):
        """Set avatar pixmap"""
        if pixmap and not pixmap.isNull():
            rounded = make_rounded_pixmap(pixmap, 120, 15)
            self.avatar_label.setPixmap(rounded)
    
    def _fetch_and_display_data(self, user_id: int):
        """Fetch summary and index data, then display"""
        def _worker():
            try:
                # Fetch both APIs
                summary = get_user_summary_by_id(user_id)
                index_data = get_user_index_data_by_id(user_id)
                
                # Update UI on main thread
                QTimer.singleShot(0, lambda: self._display_data(summary, index_data))
            except Exception as e:
                print(f"Error fetching profile data: {e}")
        
        import threading
        threading.Thread(target=_worker, daemon=True).start()
    
    def _display_data(self, summary: dict, index_data: dict):
        """Display fetched data in UI"""
        if not summary or not index_data:
            return
        
        # Extract user data from summary
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
            self.status_title_label.setText(" • ".join(status_parts))
            self.status_title_label.setVisible(True)
        else:
            self.status_title_label.setVisible(False)
        
        # Populate grid with data
        self._populate_grid(summary, index_data)
        
        # Display bio if available
        self._display_bio(index_data)
    
    def _populate_grid(self, summary: dict, index_data: dict):
        """Populate data grid with user information"""
        # Clear existing grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        user_data = summary.get('user', {})
        stats = index_data.get('stats', {})
        
        font = QFont(self.config.get("ui", "font_family"), 
                    self.config.get("ui", "font_size"))
        
        # Define grid data
        grid_data = [
            ("User ID", str(user_data.get('id', 'N/A'))),
            ("Level", str(summary.get('level', 'N/A'))),
            ("Online", "🟢" if summary.get('is_online') else "🔴"),
            ("Blocked", "❌ Banned" if user_data.get('blocked') else "✅ Active"),
            ("Registered", self._format_date(stats.get('registered'))),
            ("Achievements", str(stats.get('achieves_cnt', 'N/A'))),
            ("Total Races", str(stats.get('total_num_races', 'N/A'))),
            ("Best Speed", str(stats.get('best_speed', 'N/A'))),
            ("Rating Level", str(stats.get('rating_level', 'N/A'))),
            ("Friends", str(stats.get('friends_cnt', 'N/A'))),
            ("Vocabularies", str(stats.get('vocs_cnt', 'N/A'))),
            ("Cars", str(stats.get('cars_cnt', 'N/A'))),
        ]
        
        # Add to grid (2 columns)
        row = 0
        col = 0
        for label_text, value_text in grid_data:
            # Label
            label = QLabel(f"{label_text}:")
            label.setFont(font)
            label.setStyleSheet("font-weight: bold;")
            self.grid_layout.addWidget(label, row, col * 2)
            
            # Value
            value = QLabel(value_text)
            value.setFont(font)
            self.grid_layout.addWidget(value, row, col * 2 + 1)
            
            # Move to next cell
            col += 1
            if col >= 2:
                col = 0
                row += 1
    
    def _format_date(self, date_dict):
        """Format date from timestamp dict"""
        if not date_dict or 'sec' not in date_dict:
            return 'N/A'
        try:
            dt = datetime.fromtimestamp(date_dict['sec'])
            return dt.strftime('%Y-%m-%d')
        except:
            return 'N/A'
    
    def _display_bio(self, index_data: dict):
        """Display user biography"""
        bio = index_data.get('bio', {})
        
        # Get bio text (prefer 'text' over 'old_text')
        bio_text = bio.get('text') or bio.get('old_text')
        
        if not bio_text:
            self.bio_label.setVisible(False)
            self.bio_content.setVisible(False)
            return
        
        # Process HTML
        processed_html = process_bio_html(bio_text)
        
        # Add edit date if available
        edited_date = bio.get('edited_date')
        if edited_date:
            date_str = self._format_date(edited_date)
            processed_html += f"<br><br><i style='color: #888;'>Last edited: {date_str}</i>"
        
        self.bio_content.setText(processed_html)
        self.bio_label.setVisible(True)
        self.bio_content.setVisible(True)
    
    def update_theme(self):
        """Update widget styling for theme changes"""
        # Theme changes are handled by global stylesheet
        pass
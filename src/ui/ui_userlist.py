"""User list display widget"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from helpers.color_contrast import optimize_color_contrast


class UserWidget(QWidget):
    """Widget for displaying a single user"""
    
    def __init__(self, user, bg_hex, config, color_cache=None, counter: int = None):
        super().__init__()
        self.user = user
        self.bg_hex = bg_hex
        self.config = config
        self.color_cache = color_cache or {}
        self.counter = counter
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        self.setLayout(layout)
        
        # Username with color (prefer cached color)
        login = getattr(self.user, 'login', None)
        if login and login in self.color_cache:
            bg_color = self.color_cache[login]
        else:
            bg_color_src = getattr(self.user, 'background', None)
            if bg_color_src:
                bg_color = optimize_color_contrast(bg_color_src, self.bg_hex, target_ratio=4.5)
                if login:
                    self.color_cache[login] = bg_color
            else:
                bg_color = "#AAAAAA"
        
        # Display name
        display_name = self.user.login
        self.username_label = QLabel(display_name)
        self.username_label.setStyleSheet(f"color: {bg_color}; font-weight: bold;")
        self.username_label.setFont(QFont(self.config.get("ui", "font_family"), 11))
        layout.addWidget(self.username_label, stretch=1)

        # Optional counter badge (separate element)
        self.counter_label = QLabel("")
        self.counter_label.setFont(QFont(self.config.get("ui", "font_family"), 10))
        self.counter_label.setStyleSheet("color: #FFFFFF; background-color: #444444; border-radius: 8px; padding: 2px 6px;")
        if self.counter and int(self.counter) > 0:
            self.counter_label.setText(str(self.counter))
            self.counter_label.setVisible(True)
        else:
            self.counter_label.setVisible(False)
        layout.addWidget(self.counter_label)    


class UserListWidget(QWidget):
    """Widget for displaying user list"""
    
    def __init__(self, config, input_field=None):
        super().__init__()
        self.config = config
        self.input_field = input_field
        self.user_widgets = []
        self.user_game_state = {}  # Track game counters
        self.color_cache = {}  # Allows external code to set shared cache
        
        # Get background color
        self.bg_color = config.get("ui", "theme")
        self.bg_hex = "#1E1E1E" if self.bg_color == "dark" else "#FFFFFF"
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        self.setLayout(layout)
        
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)
        
        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll_area)
        
        # Users container
        self.users_container = QWidget()
        self.users_layout = QVBoxLayout()
        self.users_layout.setContentsMargins(5, 5, 5, 5)
        self.users_layout.setSpacing(4)
        self.users_layout.addStretch()
        self.users_container.setLayout(self.users_layout)
        
        self.scroll_area.setWidget(self.users_container)
    
    def update_users(self, users):
        """Update the user list"""
        # Clear existing widgets
        for widget in self.user_widgets:
            self.users_layout.removeWidget(widget)
            widget.deleteLater()
        self.user_widgets.clear()
        
        # Filter online users
        online_users = [u for u in users if u.status == 'available']
        
        # Separate into in-chat and in-game
        in_chat = [u for u in online_users if not getattr(u, 'game_id', None)]
        in_game = [u for u in online_users if getattr(u, 'game_id', None)]
        
        # Update game counters
        for user in in_game:
            if user.login not in self.user_game_state:
                self.user_game_state[user.login] = {'game_id': user.game_id, 'counter': 1}
            elif self.user_game_state[user.login]['game_id'] != user.game_id:
                self.user_game_state[user.login]['counter'] += 1
                self.user_game_state[user.login]['game_id'] = user.game_id
        
        # Clear state for users back in chat
        for user in in_chat:
            if user.login in self.user_game_state:
                del self.user_game_state[user.login]
        
        # Sort users
        in_chat.sort(key=lambda u: u.login.lower())
        in_game.sort(key=lambda u: (
            -self.user_game_state.get(u.login, {}).get('counter', 0),
            u.login.lower()
        ))
        
        # Add chat label and users
        if in_chat:
            chat_label = QLabel("🗯️ Chat")
            chat_label.setFont(QFont(self.config.get("ui", "font_family"), 12, QFont.Weight.Bold))
            chat_label.setStyleSheet("color: #888888;")
            self.users_layout.insertWidget(self.users_layout.count() - 1, chat_label)
            self.user_widgets.append(chat_label)
            
            for user in in_chat:
                # Ensure color cached for this login
                if user.login and user.login not in self.color_cache:
                    bg_color = getattr(user, 'background', None)
                    if bg_color:
                        self.color_cache[user.login] = optimize_color_contrast(bg_color, self.bg_hex, target_ratio=4.5)
                    else:
                        self.color_cache[user.login] = "#AAAAAA"

                user_widget = UserWidget(user, self.bg_hex, self.config, color_cache=self.color_cache)
                self.users_layout.insertWidget(self.users_layout.count() - 1, user_widget)
                self.user_widgets.append(user_widget)
        
        # Add game label and users
        if in_game:
            if in_chat:
                # Add spacer
                spacer = QWidget()
                spacer.setFixedHeight(12)
                self.users_layout.insertWidget(self.users_layout.count() - 1, spacer)
                self.user_widgets.append(spacer)
            
            game_label = QLabel("🏁 Game")
            game_label.setFont(QFont(self.config.get("ui", "font_family"), 12, QFont.Weight.Bold))
            game_label.setStyleSheet("color: #888888;")
            self.users_layout.insertWidget(self.users_layout.count() - 1, game_label)
            self.user_widgets.append(game_label)
            
            for user in in_game:
                # Determine counter for display
                counter = self.user_game_state.get(user.login, {}).get('counter', 1)

                # Ensure color cached for this login
                if user.login and user.login not in self.color_cache:
                    bg_color = getattr(user, 'background', None)
                    if bg_color:
                        self.color_cache[user.login] = optimize_color_contrast(bg_color, self.bg_hex, target_ratio=4.5)
                    else:
                        self.color_cache[user.login] = "#AAAAAA"

                user_widget = UserWidget(user, self.bg_hex, self.config, color_cache=self.color_cache, counter=counter)
                self.users_layout.insertWidget(self.users_layout.count() - 1, user_widget)
                self.user_widgets.append(user_widget)
    
    def update_theme(self):
        """Update theme colors"""
        theme = self.config.get("ui", "theme")
        self.bg_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
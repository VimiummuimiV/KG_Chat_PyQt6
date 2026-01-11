from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QApplication
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QCursor, QPixmap
from helpers.load import make_rounded_pixmap
from helpers.create import _render_svg_icon
from helpers.cache import get_cache
from core.userlist import ChatUser


class UserWidget(QWidget):
    """Widget for a single user display"""
    AVATAR_SIZE = 36
    SVG_AVATAR_SIZE = 24
    
    profile_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    private_chat_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    
    def __init__(self, user, bg_hex, config, icons_path, is_dark_theme, counter=None):
        super().__init__()
        self.user = user
        self.cache = get_cache()
        
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(6)
        self.setLayout(layout)
        
        # Avatar
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(self.AVATAR_SIZE, self.AVATAR_SIZE)
        self.avatar_label.setStyleSheet("background: transparent; border: none; padding: 0; margin: 0;")
        self.avatar_label.setScaledContents(False)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Load avatar from cache
        if user.user_id:
            cached_avatar = self.cache.get_avatar(user.user_id)
            if cached_avatar:
                self.avatar_label.setPixmap(make_rounded_pixmap(cached_avatar, self.AVATAR_SIZE, 8))
            else:
                self.avatar_label.setPixmap(_render_svg_icon(icons_path / "user.svg", self.SVG_AVATAR_SIZE).pixmap(QSize(self.SVG_AVATAR_SIZE, self.SVG_AVATAR_SIZE)))
                self.cache.load_avatar_async(user.user_id, self._on_avatar_loaded)
        else:
            self.avatar_label.setPixmap(_render_svg_icon(icons_path / "user.svg", self.SVG_AVATAR_SIZE).pixmap(QSize(self.SVG_AVATAR_SIZE, self.SVG_AVATAR_SIZE)))
        
        layout.addWidget(self.avatar_label)
        
        # Username with cached color
        text_color = self.cache.get_or_calculate_color(user.login, user.background, bg_hex, 4.5)
        
        self.username_label = QLabel(user.login)
        self.username_label.setStyleSheet(f"color: {text_color};")
        self.username_label.setFont(QFont(config.get("ui", "font_family"), config.get("ui", "font_size")))
        layout.addWidget(self.username_label, stretch=1)
        
        # Counter
        self.counter_label = None
        if counter and counter > 0:
            self.counter_label = QLabel(f"{counter}")
            self.counter_label.setFont(QFont(config.get("ui", "font_family"), config.get("ui", "font_size")))
            self.counter_label.setStyleSheet(f"color: {text_color};")
            layout.addWidget(self.counter_label)
    
    def _on_avatar_loaded(self, user_id: str, pixmap: QPixmap):
        """Callback when avatar is loaded from cache"""
        try:
            if user_id == self.user.user_id and self.avatar_label:
                self.avatar_label.setPixmap(make_rounded_pixmap(pixmap, self.AVATAR_SIZE, 8))
        except RuntimeError:
            pass
    
    def update_color(self, color: str):
        """Update colors without rebuilding widget"""
        self.username_label.setStyleSheet(f"color: {color};")
        if self.counter_label:
            self.counter_label.setStyleSheet(f"color: {color};")
    
    def mousePressEvent(self, event):
        """Handle click events"""
        if event.button() == Qt.MouseButton.LeftButton:
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self.private_chat_requested.emit(self.user.jid, self.user.login, self.user.user_id)
            else:
                self.profile_requested.emit(self.user.jid, self.user.login, self.user.user_id)
        super().mousePressEvent(event)


class UserListWidget(QWidget):
    """Widget for displaying sorted user list with dynamic sections"""
    
    profile_requested = pyqtSignal(str, str, str)
    private_chat_requested = pyqtSignal(str, str, str)
    
    def __init__(self, config, input_field=None):
        super().__init__()
        self.config = config
        self.input_field = input_field
        self.user_widgets = {}
        self.user_game_state = {}
        self.cache = get_cache()
        self.bg_hex = "#1E1E1E" if config.get("ui", "theme") == "dark" else "#FFFFFF"
        self.is_dark_theme = config.get("ui", "theme") == "dark"
        
        self.icons_path = Path(__file__).parent.parent / "icons"
        
        widget_margin = config.get("ui", "margins", "widget") or 5
        widget_spacing = config.get("ui", "spacing", "widget_elements") or 6
        list_spacing = config.get("ui", "spacing", "list_items") or 2
        section_gap = config.get("ui", "spacing", "section_gap") or 12
        
        layout = QVBoxLayout()
        layout.setContentsMargins(widget_margin, widget_margin, widget_margin, widget_margin)
        layout.setSpacing(widget_spacing)
        self.setLayout(layout)
        self.setMinimumWidth(350)
        self.setMaximumWidth(350)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll)
        
        container = QWidget()
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(widget_spacing)
        container.setLayout(self.main_layout)
        scroll.setWidget(container)
        
        header_font = QFont(config.get("ui", "font_family"), config.get("ui", "font_size"))
        header_font.setBold(True)
        
        # Chat section
        self.chat_label = QLabel("🗯️ Chat")
        self.chat_label.setFont(header_font)
        self.chat_label.setStyleSheet("color: #888;")
        self.chat_label.setVisible(False)
        self.main_layout.addWidget(self.chat_label)
        
        self.chat_container = QVBoxLayout()
        self.chat_container.setSpacing(list_spacing)
        self.main_layout.addLayout(self.chat_container)
        
        self.section_spacer = QWidget()
        self.section_spacer.setFixedHeight(section_gap)
        self.section_spacer.setVisible(False)
        self.main_layout.addWidget(self.section_spacer)
        
        # Game section
        self.game_label = QLabel("🏁 Game")
        self.game_label.setFont(header_font)
        self.game_label.setStyleSheet("color: #888;")
        self.game_label.setVisible(False)
        self.main_layout.addWidget(self.game_label)
        
        self.game_container = QVBoxLayout()
        self.game_container.setSpacing(list_spacing)
        self.main_layout.addLayout(self.game_container)
        
        self.main_layout.addStretch()
    
    def _update_section_visibility(self):
        """Update visibility of section headers"""
        has_chat_users = self.chat_container.count() > 0
        has_game_users = self.game_container.count() > 0
        
        self.chat_label.setVisible(has_chat_users)
        self.game_label.setVisible(has_game_users)
        self.section_spacer.setVisible(has_chat_users and has_game_users)
    
    def _update_counter(self, user):
        """Update and return counter for user"""
        if user.game_id:
            state = self.user_game_state.get(user.login)
            if not state:
                counter = 1
            elif state.get('last_game_id') != user.game_id:
                counter = state.get('counter', 1) + 1
            else:
                counter = state.get('counter', 1)
            self.user_game_state[user.login] = {'last_game_id': user.game_id, 'counter': counter}
            return counter
        else:
            if user.login in self.user_game_state:
                self.user_game_state.pop(user.login, None)
            return None
    
    def _clear_container(self, container):
        """Safely clear a container layout"""
        widgets_to_delete = []
        while container.count() > 0:
            item = container.takeAt(0)
            if item.widget():
                widgets_to_delete.append(item.widget())
        
        # Delete widgets after removing from layout
        for widget in widgets_to_delete:
            try:
                widget.deleteLater()
            except Exception:
                pass
    
    def add_users(self, users=None, presence=None, bulk=False):
        """Add user(s) to appropriate section with sorting"""
        if presence:
            users = [ChatUser(
                user_id=presence.user_id or '',
                login=presence.login,
                jid=presence.from_jid,
                background=presence.background,
                game_id=presence.game_id,
                affiliation=presence.affiliation,
                role=presence.role,
                status='available'
            )]
        
        if not users:
            return
        
        # Update counters for all
        for user in users:
            self._update_counter(user)
        
        if bulk:
            # Clear all widgets safely
            for widget in list(self.user_widgets.values()):
                try:
                    widget.deleteLater()
                except Exception:
                    pass
            self.user_widgets.clear()
            
            # Clear containers
            self._clear_container(self.chat_container)
            self._clear_container(self.game_container)
            
            # Process deletions
            QApplication.processEvents()
            
            # Separate and sort
            in_chat = sorted([u for u in users if not u.game_id], key=lambda u: u.login.lower())
            in_game = sorted([u for u in users if u.game_id], 
                           key=lambda u: (-self.user_game_state.get(u.login, {}).get('counter', 1), u.login.lower()))
            
            # Add to chat
            for user in in_chat:
                try:
                    widget = UserWidget(user, self.bg_hex, self.config, self.icons_path, self.is_dark_theme)
                    widget.profile_requested.connect(self.profile_requested.emit)
                    widget.private_chat_requested.connect(self.private_chat_requested.emit)
                    self.chat_container.addWidget(widget)
                    self.user_widgets[user.jid] = widget
                except Exception as e:
                    print(f"❌ Error creating user widget: {e}")
            
            # Add to game
            for user in in_game:
                try:
                    counter = self.user_game_state.get(user.login, {}).get('counter', 1)
                    widget = UserWidget(user, self.bg_hex, self.config, self.icons_path, self.is_dark_theme, counter)
                    widget.profile_requested.connect(self.profile_requested.emit)
                    widget.private_chat_requested.connect(self.private_chat_requested.emit)
                    self.game_container.addWidget(widget)
                    self.user_widgets[user.jid] = widget
                except Exception as e:
                    print(f"❌ Error creating user widget: {e}")
            
            # Update section visibility after bulk load
            self._update_section_visibility()
        else:
            # Single user update
            user = users[0]
            
            # Remove old if exists
            if user.jid in self.user_widgets:
                try:
                    self.user_widgets[user.jid].deleteLater()
                    del self.user_widgets[user.jid]
                except Exception:
                    pass
            
            # Determine section and counter
            is_game = bool(user.game_id)
            counter = self.user_game_state.get(user.login, {}).get('counter', 1) if is_game else None
            container = self.game_container if is_game else self.chat_container
            
            # Create widget
            try:
                widget = UserWidget(user, self.bg_hex, self.config, self.icons_path, self.is_dark_theme, counter)
                widget.profile_requested.connect(self.profile_requested.emit)
                widget.private_chat_requested.connect(self.private_chat_requested.emit)
                self.user_widgets[user.jid] = widget
                
                # Find sorted position and insert
                inserted = False
                for i in range(container.count()):
                    item = container.itemAt(i)
                    if not item or not isinstance(item.widget(), UserWidget):
                        continue
                    existing = item.widget()
                    
                    if is_game:
                        # Sort by counter desc, then name asc
                        my_counter = counter or 1
                        their_counter = self.user_game_state.get(existing.user.login, {}).get('counter', 1)
                        if my_counter > their_counter or (my_counter == their_counter and user.login.lower() < existing.user.login.lower()):
                            container.insertWidget(i, widget)
                            inserted = True
                            break
                    else:
                        # Sort alphabetically
                        if user.login.lower() < existing.user.login.lower():
                            container.insertWidget(i, widget)
                            inserted = True
                            break
                
                if not inserted:
                    container.addWidget(widget)
                
                # Update section visibility after adding user
                self._update_section_visibility()

            except Exception as e:
                print(f"❌ Error adding user widget: {e}")
    
    def remove_users(self, jids=None, presence=None):
        """Remove user(s)"""
        if presence:
            jids = [presence.from_jid]
        
        if not jids:
            return
        
        from PyQt6.QtCore import QTimer
        for jid in jids:
            if jid in self.user_widgets:
                try:
                    self.user_widgets[jid].deleteLater()
                    del self.user_widgets[jid]
                except Exception:
                    pass
        
        # Update section visibility after removing users
        QTimer.singleShot(10, self._update_section_visibility)
    
    def clear_all(self):
        """Clear all users and reset state"""
        for widget in list(self.user_widgets.values()):
            try:
                widget.deleteLater()
            except Exception:
                pass
        self.user_widgets.clear()
        
        # Clear game state
        self.user_game_state.clear()
        
        # Clear containers
        self._clear_container(self.chat_container)
        self._clear_container(self.game_container)
        
        # Update visibility
        self._update_section_visibility()
        
        # Process deletions
        QApplication.processEvents()
    
    def update_theme(self):
        """Update theme colors"""
        theme = self.config.get("ui", "theme")
        self.bg_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
        self.is_dark_theme = theme == "dark"
        
        # Clear color cache on theme change
        self.cache.clear_colors()
        
        self.setUpdatesEnabled(False)
        for jid, widget in list(self.user_widgets.items()):
            try:
                username = widget.user.login
                background = widget.user.background
                new_color = self.cache.get_or_calculate_color(username, background, self.bg_hex, 4.5)
                widget.update_color(new_color)
            except (RuntimeError, AttributeError):
                pass
        self.setUpdatesEnabled(True)
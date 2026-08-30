from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QCursor, QPixmap, QFont
from PyQt6 import sip


from helpers.load import make_rounded_pixmap
from helpers.create import _render_svg_icon, get_user_svg_color
from helpers.cache import get_cache
from helpers.fonts import get_font, FontType
from helpers.scroll.auto_scroll import AutoScroller
from helpers.translate import tr, TranslatableMixin, on_language_changed
from components.context_menu.userlist import (
    show_userlist_context_menu,
    PROFILE,
    PRIVATE,
    PASTE_USERNAME,
    COPY_USERNAME,
    COPY_ID,
    OPEN_GAME,
    TRACK,
    UNTRACK
)
from core.userlist import ChatUser


class UserWidget(QWidget):
    """Widget for a single user display"""
    AVATAR_SIZE = 36
    SVG_AVATAR_SIZE = 24
    
    profile_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    private_chat_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    paste_requested = pyqtSignal(str)  # username
    open_game_requested = pyqtSignal(str)  # game_id
    track_requested = pyqtSignal(str, str, bool)  # user_id, login, track

    def __init__(self, user, config, icons_path, is_dark_theme, game_counter=None, is_tracked=False):
        super().__init__()
        self.user = user
        self.icons_path = icons_path
        self.is_tracked = is_tracked
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
        svg_color = get_user_svg_color(self.cache.has_user(user.user_id), is_dark_theme)
        if user.user_id:
            cached_avatar = self.cache.get_avatar(user.user_id)
            if cached_avatar:
                self.avatar_label.setPixmap(make_rounded_pixmap(cached_avatar, self.AVATAR_SIZE, 8))
            else:
                self.avatar_label.setPixmap(
                    _render_svg_icon(icons_path / "user.svg", self.SVG_AVATAR_SIZE, svg_color)
                    .pixmap(QSize(self.SVG_AVATAR_SIZE, self.SVG_AVATAR_SIZE))
                )
                self.cache.load_avatar_async(user.user_id, self._on_avatar_loaded)
        else:
            self.avatar_label.setPixmap(
                _render_svg_icon(icons_path / "user.svg", self.SVG_AVATAR_SIZE, svg_color)
                .pixmap(QSize(self.SVG_AVATAR_SIZE, self.SVG_AVATAR_SIZE))
            )
        
        layout.addWidget(self.avatar_label)
        
        if user.background:
            self.cache.update_user(user.user_id, user.login, user.background)
        elif user.user_id:
            self.cache.update_user(user.user_id, user.login)
        text_color = self.cache.get_username_color(user.login, is_dark_theme)
        
        self.username_label = QLabel()
        self.username_label.setFont(get_font(FontType.TEXT))
        
        # Build username text with role icon
        username_text = user.login
        
        if user.role in ('moderator', 'owner') or user.affiliation == 'owner' or user.moderator:
            username_text += " ⚔️"
            self.username_label.setToolTip(self._build_moderator_tooltip(user))

        if self.is_tracked:
            username_text += " ⭐"
            self.username_label.setToolTip(tr("Tracked", "Отслеживается"))

        if user.role == 'visitor':
            emoji_family = (config.get("font", "emoji_family") or "").lower()
            block_mark = " ⛔" if "segoe" in emoji_family else " 🚫"
            QTimer.singleShot(700, lambda: not sip.isdeleted(self.username_label)
                and self.user.role == 'visitor' and (
                    self.username_label.setText(self.username_label.text() + block_mark) or
                    self.username_label.setToolTip(tr("Blocked", "Заблокирован"))
                ))
        
        self.username_label.setText(username_text)
        self.username_label.setStyleSheet(f"color: {text_color};")
        layout.addWidget(self.username_label)

        # Game-session counter (distinct races this session)
        self.game_counter_label = None
        if game_counter and game_counter > 0:
            self.game_counter_label = QLabel(str(game_counter))
            self.game_counter_label.setFont(get_font(FontType.TEXT))
            self.game_counter_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            self.game_counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._game_counter_style(is_dark_theme)
            layout.addWidget(self.game_counter_label)
        layout.addStretch()
    
    def _build_moderator_tooltip(self, user):
        """Build tooltip text for moderator indicator"""
        parts = []
        
        # Add role if not just participant
        if user.role and user.role != 'participant':
            parts.append(f"{tr('Role', 'Роль')}: {user.role.capitalize()}")
        
        # Add affiliation if not just none
        if user.affiliation and user.affiliation != 'none':
            parts.append(f"{tr('Affiliation', 'Статус')}: {user.affiliation.capitalize()}")
        
        # Add moderator flag if set
        if user.moderator:
            parts.append(f"{tr('Moderator', 'Модератор')}: {tr('Yes', 'Да')}")
        
        return "\n".join(parts) if parts else tr("Moderator", "Модератор")
    
    def _on_avatar_loaded(self, user_id: str, pixmap: QPixmap):
        """Callback when avatar is loaded from cache"""
        try:
            if user_id == self.user.user_id and self.avatar_label:
                self.avatar_label.setPixmap(make_rounded_pixmap(pixmap, self.AVATAR_SIZE, 8))
        except RuntimeError:
            pass
    
    def _game_counter_style(self, is_dark: bool):
        color = "#CCCCCC" if is_dark else "#666666"
        self.game_counter_label.setStyleSheet(f"color:{color};")

    def update_color(self, color: str, is_dark: bool = None):
        """Update colors without rebuilding widget"""
        self.username_label.setStyleSheet(f"color: {color};")
        if self.game_counter_label and is_dark is not None:
            self._game_counter_style(is_dark)

    def set_tracked(self, tracked: bool):
        if tracked == self.is_tracked:
            return
        self.is_tracked = tracked
        text = self.username_label.text()
        self.username_label.setText(text + " ⭐" if tracked else text.replace(" ⭐", ""))
    
    def mousePressEvent(self, event):
        """Handle click events.

        Plain click  → Profile
        Ctrl+click   → Private Chat
        Middle click → Open game chat (if the user is currently in a race)
        """
        if event.button() == Qt.MouseButton.LeftButton:
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self.private_chat_requested.emit(self.user.jid, self.user.login, self.user.user_id)
            else:
                self.profile_requested.emit(self.user.jid, self.user.login, self.user.user_id)
        elif event.button() == Qt.MouseButton.MiddleButton:
            game_id = getattr(self.user, 'game_id', None)
            if game_id:
                self.open_game_requested.emit(str(game_id))
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        has_game = bool(getattr(self.user, 'game_id', None))
        tracker = getattr(self, 'user_tracker', None)
        is_tracked = bool(
            tracker and tracker.is_tracked(
                user_id=self.user.user_id, login=self.user.login
            )
        )
        my_username = getattr(self, 'my_username', None)
        is_own_user = bool(my_username) and self.user.login == my_username
        action = show_userlist_context_menu(
            self.icons_path, self, QCursor.pos(),
            has_game=has_game, is_tracked=is_tracked,
            show_track=not is_own_user, show_private=not is_own_user,
        )
        if action == PROFILE:
            self.profile_requested.emit(self.user.jid, self.user.login, self.user.user_id)
        elif action == PRIVATE:
            self.private_chat_requested.emit(self.user.jid, self.user.login, self.user.user_id)
        elif action == PASTE_USERNAME:
            self.paste_requested.emit(self.user.login)
        elif action == COPY_USERNAME:
            QApplication.clipboard().setText(self.user.login)
        elif action == COPY_ID:
            QApplication.clipboard().setText(str(self.user.user_id or ""))
        elif action == OPEN_GAME and has_game:
            self.open_game_requested.emit(str(self.user.game_id))
        elif action == TRACK:
            self.track_requested.emit(str(self.user.user_id or ""), self.user.login, True)
        elif action == UNTRACK:
            self.track_requested.emit(str(self.user.user_id or ""), self.user.login, False)


class UserListWidget(TranslatableMixin, QWidget):
    """Widget for displaying sorted user list with dynamic sections"""
    
    profile_requested = pyqtSignal(str, str, str)
    private_chat_requested = pyqtSignal(str, str, str)
    paste_requested = pyqtSignal(str)  # username
    open_game_requested = pyqtSignal(str)  # game_id
    track_requested = pyqtSignal(str, str, bool)  # user_id, login, track

    def __init__(self, config, input_field=None, ban_manager=None, user_tracker=None, my_username=None):
        super().__init__()
        self._init_translatable()
        self.config = config
        self.input_field = input_field
        self.ban_manager = ban_manager
        self.user_tracker = user_tracker
        self.my_username = my_username
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
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        self.auto_scroller = AutoScroller(scroll)
        
        container = QWidget()
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(widget_spacing)
        container.setLayout(self.main_layout)
        scroll.setWidget(container)
        
        section_label = get_font(FontType.TEXT, weight=QFont.Weight.Bold)

        # Chat section
        self.chat_label = QLabel(tr("Chat", "Чат"))
        self.chat_label.setFont(section_label)
        self.chat_label.setStyleSheet("color: #888;")
        self.chat_label.setVisible(False)
        self.main_layout.addWidget(self.chat_label)
        self._register_tr(self.chat_label.setText, tr("Chat", "Чат"))

        self.chat_container = QVBoxLayout()
        self.chat_container.setSpacing(list_spacing)
        self.main_layout.addLayout(self.chat_container)

        self.section_spacer = QWidget()
        self.section_spacer.setFixedHeight(section_gap)
        self.section_spacer.setVisible(False)
        self.main_layout.addWidget(self.section_spacer)

        # Game section
        self.game_label = QLabel(tr("Game", "Игра"))
        self.game_label.setFont(section_label)
        self.game_label.setStyleSheet("color: #888;")
        self.game_label.setVisible(False)
        self.main_layout.addWidget(self.game_label)
        self._register_tr(self.game_label.setText, tr("Game", "Игра"))
        
        self.game_container = QVBoxLayout()
        self.game_container.setSpacing(list_spacing)
        self.main_layout.addLayout(self.game_container)
        
        self.main_layout.addStretch()

        on_language_changed(self._retranslate)
    
    def _retranslate(self, _code=None):
        self._retranslate_all()
    
    def _update_section_visibility(self):
        """Update visibility of section headers"""
        has_chat_users = self.chat_container.count() > 0
        has_game_users = self.game_container.count() > 0
        
        self.chat_label.setVisible(has_chat_users)
        self.game_label.setVisible(has_game_users)
        self.section_spacer.setVisible(has_chat_users and has_game_users)
    
    def _update_game_counter(self, user):
        if user.game_id:
            state = self.user_game_state.get(user.login)
            if not state:
                game_counter = 1
            elif state.get('last_game_id') != user.game_id:
                game_counter = state.get('game_counter', 1) + 1
            else:
                game_counter = state.get('game_counter', 1)
            self.user_game_state[user.login] = {
                'last_game_id': user.game_id,
                'game_counter': game_counter,
            }
            return game_counter
        if user.login in self.user_game_state:
            self.user_game_state.pop(user.login, None)
        return None

    def _tracked_star_enabled(self) -> bool:
        return bool(self.config.get("user_tracker", "show_star_badge"))

    def _is_tracked(self, user) -> bool:
        return bool(
            self._tracked_star_enabled() and self.user_tracker
            and self.user_tracker.is_tracked(user_id=user.user_id, login=user.login)
        )

    def refresh_tracked_star(self, user_id: str = None, login: str = None):
        """Update tracked star on existing widgets. No args = all (settings toggle)."""
        for widget in self.user_widgets.values():
            if user_id and widget.user.user_id != user_id:
                continue
            if login and not user_id and widget.user.login != login:
                continue
            widget.set_tracked(self._is_tracked(widget.user))

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
        """Add user(s) to appropriate section with sorting and ban filtering"""
        if presence:
            users = [ChatUser(
                user_id=presence.user_id or '',
                login=presence.login,
                jid=presence.from_jid,
                background=presence.background,
                game_id=presence.game_id,
                affiliation=presence.affiliation,
                role=presence.role,
                moderator=getattr(presence, 'moderator', False),
                status='available'
            )]
        
        if not users:
            return
        
        # FILTER BANNED USERS
        if self.ban_manager:
            filtered_users = []
            for user in users:
                user_id = user.user_id
                
                # Check by user_id (primary)
                if user_id and self.ban_manager.is_banned_by_id(str(user_id)):
                    print(f"🚫 Filtering banned user from userlist: {user.login} (ID: {user_id})")
                    continue
                
                # Fallback check by username
                if not user_id and self.ban_manager.is_banned_by_username(user.login):
                    print(f"🚫 Filtering banned user from userlist: {user.login} (no ID)")
                    continue
                
                filtered_users.append(user)
            
            users = filtered_users
            
            if not users:
                return  # All users were banned
        
        # Update counters for all
        for user in users:
            self._update_game_counter(user)

        def _wire(widget):
            widget.user_tracker = self.user_tracker
            widget.my_username = self.my_username
            widget.profile_requested.connect(self.profile_requested.emit)
            widget.private_chat_requested.connect(self.private_chat_requested.emit)
            widget.paste_requested.connect(self.paste_requested.emit)
            widget.open_game_requested.connect(self.open_game_requested.emit)
            widget.track_requested.connect(self.track_requested.emit)
        
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
                           key=lambda u: (-self.user_game_state.get(u.login, {}).get('game_counter', 1), u.login.lower()))
            
            # Add to chat
            for user in in_chat:
                try:
                    widget = UserWidget(user, self.config, self.icons_path, self.is_dark_theme, is_tracked=self._is_tracked(user))
                    _wire(widget)
                    self.chat_container.addWidget(widget)
                    self.user_widgets[user.jid] = widget
                except Exception as e:
                    print(f"❌ Error creating user widget: {e}")
            
            # Add to game
            for user in in_game:
                try:
                    game_counter = self.user_game_state.get(user.login, {}).get('game_counter', 1)
                    widget = UserWidget(user, self.config, self.icons_path, self.is_dark_theme, game_counter, is_tracked=self._is_tracked(user))
                    _wire(widget)
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
            
            # Determine section and game counter
            is_game = bool(user.game_id)
            game_counter = self.user_game_state.get(user.login, {}).get('game_counter', 1) if is_game else None
            container = self.game_container if is_game else self.chat_container

            try:
                widget = UserWidget(user, self.config, self.icons_path, self.is_dark_theme, game_counter, is_tracked=self._is_tracked(user))
                _wire(widget)
                self.user_widgets[user.jid] = widget
                
                # Find sorted position and insert
                inserted = False
                for i in range(container.count()):
                    item = container.itemAt(i)
                    if not item or not isinstance(item.widget(), UserWidget):
                        continue
                    existing = item.widget()
                    
                    if is_game:
                        # Sort by game_counter desc, then name asc
                        my_counter = game_counter or 1
                        their_counter = self.user_game_state.get(existing.user.login, {}).get('game_counter', 1)
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
    
    def on_avatar_updated(self, user_id: str, pixmap) -> None:
        """Refresh avatar for matching user widget after disk update"""
        for w in self.user_widgets.values():
            try:
                if w.user.user_id == user_id:
                    w.avatar_label.setPixmap(make_rounded_pixmap(pixmap, w.AVATAR_SIZE, 8))
            except RuntimeError:
                pass

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
        
        self.setUpdatesEnabled(False)
        for widget in list(self.user_widgets.values()):
            try:
                new_color = self.cache.get_username_color(widget.user.login, self.is_dark_theme)
                widget.update_color(new_color, self.is_dark_theme)
            except (RuntimeError, AttributeError):
                pass
        self.setUpdatesEnabled(True)

    def cleanup(self):
        """Clean up resources"""
        self.auto_scroller.cleanup()
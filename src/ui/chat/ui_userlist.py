from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from components.avatar import (
    apply_user_avatar,
    make_avatar_label,
    refresh_avatar_placeholder,
    show_real_avatar,
)
from components.colored_label import ColoredLabel
from components.context_menu.userlist import (
    BAN_PERMANENT,
    BAN_TEMPORARY,
    COPY_ID,
    COPY_USERNAME,
    OPEN_GAME,
    PASTE_USERNAME,
    PRIVATE,
    PROFILE,
    SET_PRONUNCIATION,
    show_userlist_context_menu,
    TRACK,
    UNTRACK,
)
from components.toast import copy_text_with_toast
from components.tracked_mark import TrackedMarkMixin
from core.xmpp.userlist import ChatUser
from helpers.cache import get_cache
from helpers.data import get_resource_dir
from helpers.deferred import call_later
from helpers.fonts.fonts import FontType, get_font
from helpers.scroll.auto_scroll import AutoScroller
from helpers.translate import on_language_changed, tr, TranslatableMixin


class _UserWidget(TrackedMarkMixin, QWidget):
    """Widget for a single user display"""
    AVATAR_SIZE = 36
    SVG_AVATAR_SIZE = 24

    profile_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    private_chat_requested = pyqtSignal(str, str, str)  # jid, username, user_id
    paste_requested = pyqtSignal(str)  # username
    open_game_requested = pyqtSignal(str)  # game_id
    track_requested = pyqtSignal(str, str, bool)  # user_id, login, track
    ban_requested = pyqtSignal(str, str, str, bool, object)  # jid, username, user_id, permanent, duration
    pronunciation_requested = pyqtSignal(str)  # username

    def __init__(self, user, config, icons_path, is_dark_theme, game_counter=None, is_tracked=False,
                 user_tracker=None, my_username=None, pronunciation_manager=None):
        super().__init__()
        self.user = user
        self.icons_path = icons_path
        self.is_tracked = is_tracked
        self.is_blocked = False
        self.user_tracker = user_tracker
        self.my_username = my_username
        self.pronunciation_manager = pronunciation_manager
        self.cache = get_cache()

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(6)
        self.setLayout(layout)

        self.avatar_label = make_avatar_label(self.AVATAR_SIZE)
        apply_user_avatar(
            self.avatar_label, user.user_id, self.AVATAR_SIZE, self.SVG_AVATAR_SIZE, is_dark_theme, icons_path
        )
        layout.addWidget(self.avatar_label)

        if user.background:
            self.cache.update_user(user.user_id, user.login, user.background)
        elif user.user_id:
            self.cache.update_user(user.user_id, user.login)
        text_color = self.cache.get_username_color(user.login, is_dark_theme)

        self.username_label = ColoredLabel(color=text_color)
        self.username_label.setFont(get_font(FontType.TEXT))

        # Build username text with role icon
        username_text = user.login
        tooltip_parts = []

        self._is_moderator = user.role in ('moderator', 'owner') or user.affiliation == 'owner' or user.moderator
        if self._is_moderator:
            username_text += " ⚔️"
            tooltip_parts.append(self._build_moderator_tooltip(user))

        if self.is_tracked:
            username_text += " ⭐"
            tooltip_parts.append(tr("Tracked", "Отслеживается"))

        self._base_tooltip = "\n".join(tooltip_parts)
        if self._base_tooltip:
            self.username_label.setToolTip(self._base_tooltip)

        if user.role == 'visitor':
            emoji_family = (config.get("font", "emoji_family") or "").lower()
            block_mark = " ⛔" if "segoe" in emoji_family else " 🚫"

            def mark_blocked():
                if self.user.role == 'visitor':
                    self.username_label.setText(self.username_label.text() + block_mark)
                    self._set_blocked_tooltip()

            call_later(self.username_label, 700, mark_blocked)

        self.username_label.setText(username_text)
        layout.addWidget(self.username_label)

        # Game-session counter (distinct races this session)
        self.game_counter_label = None
        if game_counter and game_counter > 0:
            self.game_counter_label = QLabel(str(game_counter))
            self.game_counter_label.setFont(get_font(FontType.TEXT))
            self.game_counter_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            self.game_counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.game_counter_label.setObjectName("mutedLabel")
            layout.addWidget(self.game_counter_label)
        layout.addStretch()

    def _retranslate_tooltip(self):
        """Recompute the combined tooltip in the current language. Called by
        the parent list on language change since the tooltip is built from
        live user state, not a single static tr() call."""
        tooltip_parts = []
        if self._is_moderator:
            tooltip_parts.append(self._build_moderator_tooltip(self.user))
        if self.is_tracked:
            tooltip_parts.append(tr("Tracked", "Отслеживается"))
        self._base_tooltip = "\n".join(tooltip_parts)
        if getattr(self, "is_blocked", False):
            self._set_blocked_tooltip()
        elif self._base_tooltip:
            self.username_label.setToolTip(self._base_tooltip)

    def _set_blocked_tooltip(self):
        """Append the 'Blocked' status to whatever tooltip is already there,
        instead of overwriting a moderator/tracked tooltip that's also active."""
        self.is_blocked = True
        self.username_label.setToolTip(
            "\n".join(filter(None, [self._base_tooltip, tr("Blocked", "Заблокирован")]))
        )

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

    def update_color(self, color: str, is_dark: bool = None):
        """Update colors without rebuilding widget"""
        self.username_label.set_text_color(color)
        if is_dark is not None:
            refresh_avatar_placeholder(
                self.avatar_label, self.user.user_id, self.SVG_AVATAR_SIZE, is_dark, self.icons_path
            )

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
            if self.user.game_id:
                self.open_game_requested.emit(str(self.user.game_id))
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        has_game = bool(self.user.game_id)
        is_tracked = bool(
            self.user_tracker and self.user_tracker.is_tracked(
                user_id=self.user.user_id, login=self.user.login
            )
        )
        is_own_user = bool(self.my_username) and self.user.login == self.my_username
        has_pronunciation = bool(
            self.pronunciation_manager and self.user.login in self.pronunciation_manager.mappings
        )
        action = show_userlist_context_menu(
            self.icons_path, self, QCursor.pos(),
            has_game=has_game, is_tracked=is_tracked,
            show_track=not is_own_user, show_private=not is_own_user,
            show_ban=not is_own_user,
            has_pronunciation=has_pronunciation,
        )
        if action == PROFILE:
            self.profile_requested.emit(self.user.jid, self.user.login, self.user.user_id)
        elif action == PRIVATE:
            self.private_chat_requested.emit(self.user.jid, self.user.login, self.user.user_id)
        elif action == PASTE_USERNAME:
            self.paste_requested.emit(self.user.login)
        elif action == COPY_USERNAME:
            copy_text_with_toast(self, self.user.login)
        elif action == COPY_ID:
            copy_text_with_toast(self, str(self.user.user_id or ""))
        elif action == OPEN_GAME and has_game:
            self.open_game_requested.emit(str(self.user.game_id))
        elif action == TRACK:
            self.track_requested.emit(str(self.user.user_id or ""), self.user.login, True)
        elif action == UNTRACK:
            self.track_requested.emit(str(self.user.user_id or ""), self.user.login, False)
        elif action == BAN_PERMANENT:
            self.ban_requested.emit(self.user.jid, self.user.login, str(self.user.user_id or ""), True, None)
        elif action == BAN_TEMPORARY:
            self.ban_requested.emit(self.user.jid, self.user.login, str(self.user.user_id or ""), False, None)
        elif action == SET_PRONUNCIATION:
            self.pronunciation_requested.emit(self.user.login)


class UserListWidget(TranslatableMixin, QWidget):
    """Widget for displaying sorted user list with dynamic sections"""

    profile_requested = pyqtSignal(str, str, str)
    private_chat_requested = pyqtSignal(str, str, str)
    paste_requested = pyqtSignal(str)  # username
    open_game_requested = pyqtSignal(str)  # game_id
    track_requested = pyqtSignal(str, str, bool)  # user_id, login, track
    ban_requested = pyqtSignal(str, str, str, bool, object)  # jid, username, user_id, permanent, duration
    pronunciation_requested = pyqtSignal(str)  # username

    def __init__(self, config, input_field=None, ban_manager=None, user_tracker=None, my_username=None):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.input_field = input_field
        self.ban_manager = ban_manager
        self.user_tracker = user_tracker
        self.my_username = my_username
        self.pronunciation_manager = None
        self.user_widgets = {}
        self._user_game_state = {}
        self.cache = get_cache()
        self.background_hex = "#1E1E1E" if config.get("ui", "theme") == "dark" else "#FFFFFF"
        self.is_dark_theme = config.get("ui", "theme") == "dark"

        self.icons_path = get_resource_dir("icons")

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
        self._main_layout = QVBoxLayout()
        self._main_layout.setContentsMargins(5, 5, 5, 5)
        self._main_layout.setSpacing(widget_spacing)
        container.setLayout(self._main_layout)
        scroll.setWidget(container)

        section_label = get_font(FontType.TEXT, weight=QFont.Weight.Bold)

        # Chat section
        self.chat_label = QLabel(tr("Chat", "Чат"))
        self.chat_label.setFont(section_label)
        self.chat_label.setObjectName("mutedHint")
        self.chat_label.setVisible(False)
        self._main_layout.addWidget(self.chat_label)
        self.register_tr(self.chat_label.setText, tr("Chat", "Чат"))

        self._chat_container = QVBoxLayout()
        self._chat_container.setSpacing(list_spacing)
        self._main_layout.addLayout(self._chat_container)

        self._section_spacer = QWidget()
        self._section_spacer.setFixedHeight(section_gap)
        self._section_spacer.setVisible(False)
        self._main_layout.addWidget(self._section_spacer)

        # Game section
        self.game_label = QLabel(tr("Game", "Игра"))
        self.game_label.setFont(section_label)
        self.game_label.setObjectName("mutedHint")
        self.game_label.setVisible(False)
        self._main_layout.addWidget(self.game_label)
        self.register_tr(self.game_label.setText, tr("Game", "Игра"))

        self._game_container = QVBoxLayout()
        self._game_container.setSpacing(list_spacing)
        self._main_layout.addLayout(self._game_container)

        self._main_layout.addStretch()

        on_language_changed(self._retranslate)

    def _retranslate(self, _code=None):
        self.retranslate_all()
        for widget in self.user_widgets.values():
            widget._retranslate_tooltip()

    def _update_section_visibility(self):
        """Update visibility of section headers"""
        has_chat_users = self._chat_container.count() > 0
        has_game_users = self._game_container.count() > 0

        self.chat_label.setVisible(has_chat_users)
        self.game_label.setVisible(has_game_users)
        self._section_spacer.setVisible(has_chat_users and has_game_users)

    def _update_game_counter(self, user):
        if user.game_id:
            state = self._user_game_state.get(user.login)
            if not state:
                game_counter = 1
            elif state.get('last_game_id') != user.game_id:
                game_counter = state.get('game_counter', 1) + 1
            else:
                game_counter = state.get('game_counter', 1)
            self._user_game_state[user.login] = {
                'last_game_id': user.game_id,
                'game_counter': game_counter,
            }
            return game_counter
        if user.login in self._user_game_state:
            self._user_game_state.pop(user.login, None)
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
            widget.profile_requested.connect(self.profile_requested.emit)
            widget.private_chat_requested.connect(self.private_chat_requested.emit)
            widget.paste_requested.connect(self.paste_requested.emit)
            widget.open_game_requested.connect(self.open_game_requested.emit)
            widget.track_requested.connect(self.track_requested.emit)
            widget.ban_requested.connect(self.ban_requested.emit)
            widget.pronunciation_requested.connect(self.pronunciation_requested.emit)

        if bulk:
            # Clear all widgets safely
            for widget in list(self.user_widgets.values()):
                try:
                    widget.deleteLater()
                except Exception:
                    pass
            self.user_widgets.clear()

            # Clear containers
            self._clear_container(self._chat_container)
            self._clear_container(self._game_container)

            # Process deletions
            QApplication.processEvents()

            # Separate and sort
            in_chat = sorted([u for u in users if not u.game_id], key=lambda u: u.login.lower())
            in_game = sorted([u for u in users if u.game_id], 
                           key=lambda u: (-self._user_game_state.get(u.login, {}).get('game_counter', 1), u.login.lower()))

            # Add to chat
            for user in in_chat:
                try:
                    widget = _UserWidget(
                        user, self.config, self.icons_path, self.is_dark_theme,
                        is_tracked=self._is_tracked(user), user_tracker=self.user_tracker,
                        my_username=self.my_username, pronunciation_manager=self.pronunciation_manager,
                    )
                    _wire(widget)
                    self._chat_container.addWidget(widget)
                    self.user_widgets[user.jid] = widget
                except Exception as e:
                    print(f"❌ Error creating user widget: {e}")

            # Add to game
            for user in in_game:
                try:
                    game_counter = self._user_game_state.get(user.login, {}).get('game_counter', 1)
                    widget = _UserWidget(
                        user, self.config, self.icons_path, self.is_dark_theme, game_counter,
                        is_tracked=self._is_tracked(user), user_tracker=self.user_tracker,
                        my_username=self.my_username, pronunciation_manager=self.pronunciation_manager,
                    )
                    _wire(widget)
                    self._game_container.addWidget(widget)
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
            game_counter = self._user_game_state.get(user.login, {}).get('game_counter', 1) if is_game else None
            container = self._game_container if is_game else self._chat_container

            try:
                widget = _UserWidget(
                    user, self.config, self.icons_path, self.is_dark_theme, game_counter,
                    is_tracked=self._is_tracked(user), user_tracker=self.user_tracker,
                    my_username=self.my_username, pronunciation_manager=self.pronunciation_manager,
                )
                _wire(widget)
                self.user_widgets[user.jid] = widget

                # Find sorted position and insert
                inserted = False
                for i in range(container.count()):
                    item = container.itemAt(i)
                    if not item or not isinstance(item.widget(), _UserWidget):
                        continue
                    existing = item.widget()

                    if is_game:
                        # Sort by game_counter desc, then name asc
                        my_counter = game_counter or 1
                        their_counter = self._user_game_state.get(existing.user.login, {}).get('game_counter', 1)
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
                    show_real_avatar(w.avatar_label, pixmap, w.AVATAR_SIZE)
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
        self._user_game_state.clear()

        # Clear containers
        self._clear_container(self._chat_container)
        self._clear_container(self._game_container)

        # Update visibility
        self._update_section_visibility()

        # Process deletions
        QApplication.processEvents()

    def update_theme(self):
        """Update theme colors"""
        theme = self.config.get("ui", "theme")
        self.background_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
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

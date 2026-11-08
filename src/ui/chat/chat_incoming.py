"""ChatWindow: handling incoming messages and presence."""

import re

from core.xmpp.jid_utils import extract_user_data_from_jid, is_from_game_room
from helpers.text.me_action import format_me_action
from ui.messages.messages_separator import NewMessagesSeparator
from ui.notification.popup_manager import popup_manager


class ChatIncomingMixin:
    """ChatWindow: handling incoming messages and presence."""

    def add_local_message(self, msg):
        self.messages_widget.add_message(msg)

    def _is_ban_message(self, msg):
        """Detect if a message is a ban message from Клавобот"""
        if not msg.body or not msg.login:
            return False
        return msg.login == 'Клавобот' and all(word in msg.body for word in ['Пользователь', 'заблокирован'])

    def _is_user_banned(self, user_id: str = None, username: str = None) -> bool:
        """Check if a user is banned by ID or username"""
        if not self.ban_manager:
            return False

        # Check by user_id (primary)
        if user_id and self.ban_manager.is_banned_by_id(str(user_id)):
            return True

        # Fallback check by username
        if not user_id and username and self.ban_manager.is_banned_by_username(username):
            return True

        return False

    def on_message(self, msg):
        if self._is_ban_message(msg):
            self.track_self_ban(msg)

        # Check if initial load
        is_initial = getattr(msg, 'initial', False)

        from_jid = getattr(msg, 'from_jid', '') or ''
        room, unread_key, game_id = self.room_for_jid(from_jid)
        if room is not None:
            body = (msg.body or '').strip()
            if 'not anonymous' in body.lower():
                return
            if self.should_skip_own_echo(msg, is_initial):
                return
            if msg.login:
                user_id, _ = extract_user_data_from_jid(from_jid)
                if self._is_user_banned(user_id, msg.login):
                    return
                if user_id:
                    self.cache.update_user(user_id, msg.login)
            is_ban = self._is_ban_message(msg)
            msg.is_ban = is_ban
            msg.is_private = False
            display_body, is_system = format_me_action(msg.body, msg.login)
            room.add_message(msg)
            if not is_initial and self.current_room() is not room:
                self.bump_tab_unread(unread_key)
            self.notify_incoming_message(
                msg, display_body, is_ban, is_system, is_initial,
                room_jid=room.room_jid, add_message_fn=room.add_message,
                source_label=self.room_source_label(room),
                game_id=game_id,
            )
            return

        if is_initial:
            self.history_settle_timer.start(self.HISTORY_SETTLE_MS)

        if self.should_skip_own_echo(msg, is_initial):
            return

        # CHECK IF USER IS BANNED - BLOCK IMMEDIATELY
        if msg.login:
            user_id, _ = extract_user_data_from_jid(getattr(msg, 'from_jid', None))
            if self._is_user_banned(user_id, msg.login):
                return  # Silently drop banned user's messages
            # Persist login → user_id mapping automatically
            if user_id:
                self.cache.update_user(user_id, msg.login)

        msg.is_private = (msg.msg_type == 'chat')

        # Check if this is a ban message and mark it
        is_ban = self._is_ban_message(msg)
        msg.is_ban = is_ban

        # Format message body for display/TTS and detect if it's a /me action
        display_body, is_system = format_me_action(msg.body, msg.login)

        if not is_initial and not self.isVisible() and not self.has_new_messages_marker:
            self.messages_widget.model.add_message(NewMessagesSeparator.create_marker())
            self.has_new_messages_marker = True

        # Add original message to widget (delegate will format it)
        self.messages_widget.add_message(msg)

        # Mark General tab unread when the user is currently on a game-room tab
        if not is_initial and self.room_tabs and self.room_tabs.currentIndex() > 0:
            self.bump_tab_unread(None)

        # Increment unread count if window is hidden and not initial load
        if not is_initial and not self.isVisible() and self.app_controller:
            self.app_controller.increment_unread()

        self.notify_incoming_message(msg, display_body, is_ban, is_system, is_initial)

    def message_mentions_me(self, msg):
        if not self.account or not msg.body:
            return False
        my_username = (self.my_username or '').lower()
        if not my_username:
            return False
        pattern = r'\b' + re.escape(my_username) + r'\b'
        return bool(re.search(pattern, msg.body.lower()))

    def on_presence(self, pres):
        if not self.xmpp_client or self.initial_roster_loading:
            return

        # CHECK IF USER IS BANNED - BLOCK PRESENCE UPDATES
        if pres and pres.login:
            if self._is_user_banned(pres.user_id, pres.login):
                return  # Silently drop banned user's presence

        from_jid = getattr(pres, 'from_jid', '') or ''
        is_game = is_from_game_room(from_jid)

        room, _, _ = self.room_for_jid(from_jid)
        if room is not None:
            if pres.presence_type == 'available':
                if pres.login and pres.user_id:
                    self.cache.update_user(pres.user_id, pres.login, pres.background)
                if pres.user_id and pres.avatar:
                    self.cache.ensure_avatar(
                        pres.user_id, pres.avatar,
                        room.user_list_widget.on_avatar_updated
                    )
                room.add_users(presence=pres)
            elif pres.presence_type == 'unavailable':
                room.remove_users(presence=pres)
            return

        if pres and pres.presence_type == 'available' and pres.login == self.my_username:
            self.on_own_role(pres.role)

        if pres and pres.presence_type == 'available':
            if pres.login and pres.user_id:
                self.cache.update_user(pres.user_id, pres.login, pres.background)
            if pres.user_id and pres.avatar:
                self.cache.ensure_avatar(pres.user_id, pres.avatar, self.user_list_widget.on_avatar_updated)
            elif pres.user_id and not pres.avatar:
                self.cache.remove_avatar(pres.user_id)
            self.user_list_widget.add_users(presence=pres)
        elif pres and pres.presence_type == 'unavailable':
            self.user_list_widget.remove_users(presence=pres)

        # User tracker + optional chat presence log (tracked users only)
        if (self.user_tracker and self.user_tracker.is_enabled()
                and pres and pres.login
                and not is_game
                and pres.presence_type in ('available', 'unavailable')):
            if pres.login != self.my_username:
                event_type = 'join' if pres.presence_type == 'available' else 'left'
                game_id = getattr(pres, 'game_id', None)
                if not self.chat_ready or self.initial_roster_loading or self.history_settle_timer.isActive():
                    self.user_tracker.seed_state(pres.user_id, pres.login, event_type, game_id=game_id)
                else:
                    event = self.user_tracker.record_event(
                        pres.user_id, pres.login, event_type, game_id=game_id,
                    )
                    if event:
                        w = getattr(self, 'user_tracker_widget', None)
                        if w is not None and self.stacked_widget.currentWidget() is w:
                            w.append_event(event)
                        else:
                            self.button_panel.bump_tracker_unread(event.get('type'))
                        if self.presence_log_enabled():
                            self.ensure_presence_log_widget()
                            self.presence_log_widget.record_presence_event(
                                pres.login, event.get('type', event_type)
                            )
                            self.apply_presence_split_sizes()
                        avatar_pix = None
                        if pres.user_id and hasattr(self, 'cache') and self.cache:
                            try:
                                avatar_pix = self.cache.get_avatar(str(pres.user_id))
                            except Exception:
                                avatar_pix = None
                        event_ts = event.get('ts')
                        login = pres.login
                        popup_manager.show_presence(
                            login,
                            event_type=event.get('type', event_type),
                            avatar_pixmap=avatar_pix,
                            config=self.config,
                            cache=getattr(self, 'cache', None),
                            on_click=lambda l=login, ts=event_ts: self.on_presence_notification_click(l, ts),
                            event_ts=event_ts,
                            game_id=event.get('game_id'),
                        )

    def on_bulk_update_complete(self):
        self.history_settle_timer.start(self.HISTORY_SETTLE_MS)  # fallback in case no history messages follow
        if not self.xmpp_client:
            return
        users = self.xmpp_client.user_list.get_online()
        self.user_list_widget.add_users(users=users, bulk=True)
        own = next((u for u in users if u.login == self.my_username and self.is_general_jid(u.jid)), None)
        if own:
            self.on_own_role(own.role)

    def refresh_youtube_previews(self):
        """Re-layout message views so YouTube link text matches the current setting."""
        widgets = [
            self.messages_widget, self.presence_log_widget,
            self.chatlog_widget, self.chatlog_split_widget,
        ]
        widgets.extend(
            room.messages_widget for room in self.all_room_widgets()
            if room and room.messages_widget
        )
        for widget in widgets:
            if widget:
                widget.force_recalculate()

    def remove_message(self, msg, single: bool = True, direction: str = None, widget=None):
        """Remove message(s) without banning user.
        direction='down' → from msg to end; 'up' → from start to msg
        """
        widget = widget or self.messages_widget
        username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
        if not username:
            return

        try:
            timestamp = getattr(msg, 'timestamp', None)
            if direction == "down":
                widget.model.remove_messages_by_login(username, from_timestamp=timestamp)
            elif direction == "up":
                widget.model.remove_messages_by_login(username, to_timestamp=timestamp)
            else:
                widget.model.remove_messages_by_login(username, timestamp if single else None)
        except Exception as e:
            print(f"Error removing message(s): {e}")

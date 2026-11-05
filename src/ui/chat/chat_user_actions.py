"""ChatWindow: username clicks, context menu, ban, track and pronunciation actions."""

import threading

from PyQt6.QtWidgets import QApplication, QMessageBox

from components.context_menu.message import (
    BAN_PERMANENT,
    BAN_TEMPORARY,
    COPY_ID as MSG_COPY_ID,
    COPY_USERNAME as MSG_COPY_USERNAME,
    PRIVATE as MSG_PRIVATE,
    PROFILE as MSG_PROFILE,
    REMOVE_ALL,
    REMOVE_DOWN,
    REMOVE_MESSAGE,
    REMOVE_PRESENCE,
    REMOVE_UP,
    SET_PRONUNCIATION,
    show_message_user_context_menu,
    TRACK as MSG_TRACK,
    UNTRACK as MSG_UNTRACK,
)
from core.web.api_data import get_exact_user_id_by_name, validate_username_and_get_id
from core.xmpp.jid_utils import extract_user_data_from_jid
from helpers.translate import tr
from ui.dialogs.duration_dialog import DurationDialog
from ui.dialogs.pronunciation_dialog import PronunciationDialog


class ChatUserActionsMixin:
    """ChatWindow: username clicks, context menu, ban, track and pronunciation actions."""

    def _on_username_left_click(self, username: str, is_double_click: bool):
        """Handle username left-click - insert into input field"""
        if not hasattr(self, 'input_field') or not self.input_field:
            return

        current = (self.input_field.text() or "").strip()
        existing = [u.strip() for u in current.split(',') if u.strip()]

        if is_double_click:
            # Double-click: replace all with this username (or clear if already solo)
            if len(existing) == 1 and existing[0] == username:
                self.input_field.clear()
            else:
                self.input_field.setText(username + ", ")
        else:
            # Single-click: add to list if not already there
            if username not in existing:
                if existing:
                    self.input_field.setText(", ".join(existing + [username]) + ", ")
                else:
                    self.input_field.setText(username + ", ")

        self.input_field.setFocus()

    def _paste_username_to_input(self, username: str):
        """Paste username into the active input field (game room or general)."""
        field = self.active_input_field() if hasattr(self, 'active_input_field') else self.input_field
        if not field:
            return
        cursor_pos = field.cursorPosition()
        current = field.text() or ""
        if current.strip() and not current.strip().endswith((',', ' ')):
            to_insert = f", {username}"
        else:
            to_insert = f"{username}, "
        field.setText(current[:cursor_pos] + to_insert + current[cursor_pos:])
        field.setCursorPosition(cursor_pos + len(to_insert))
        field.setFocus()

    def _resolve_user_then(self, username: str, callback):
        """Resolve user_id for username: userlist → cache → API fallback (threaded)."""
        # 1. Userlist (instant, has jid too)
        if hasattr(self, 'user_list_widget') and self.user_list_widget:
            for jid, widget in self.user_list_widget.user_widgets.items():
                user = getattr(widget, 'user', None)
                if user and user.login == username:
                    callback(jid, user.login, user.user_id)
                    return
        # 2. Cache (instant, no jid)
        user_id = self.cache.get_user_id(username)
        if user_id:
            callback('', username, user_id)
            return
        # 3. API fallback (threaded)
        def _fetch():
            uid = get_exact_user_id_by_name(username)
            if uid:
                self.cache.update_user(str(uid), username)
                self._dispatch.emit(lambda: callback('', username, str(uid)))
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_username_ctrl_click(self, username: str):
        """Ctrl+LMB on message username → enter private chat"""
        self._resolve_user_then(username, lambda jid, login, uid: self.enter_private_mode(jid, login, uid))

    def _on_username_shift_click(self, username: str):
        """Shift+LMB on message username → open profile"""
        self._resolve_user_then(username, lambda jid, login, uid: self.show_profile_view(jid, login, uid))

    def _on_username_right_click(self, msg, global_pos, source_widget=None):
        """Show context menu when username is right-clicked in messages or chatlog."""
        source_widget = source_widget or self.messages_widget
        try:
            username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
            jid = getattr(msg, 'from_jid', None)
            uid, _ = extract_user_data_from_jid(jid) if jid else (None, None)
            if not uid and username and hasattr(self, 'cache'):
                uid = self.cache.get_user_id(username)

            is_tracked = bool(
                self.user_tracker and self.user_tracker.is_tracked(user_id=uid, login=username)
            )
            is_own = bool(username) and username == self.my_username
            is_presence = bool(getattr(msg, 'is_presence_log', False))

            has_pronunciation = bool(
                self.pronunciation_manager and username and username in self.pronunciation_manager.mappings
            )
            action = show_message_user_context_menu(
                self.icons_path, self, global_pos,
                is_tracked=is_tracked,
                show_track=not is_own,
                show_ban=not is_own,
                show_private=not is_own,
                show_message_removes=not is_presence,
                show_presence_remove=is_presence,
                has_pronunciation=has_pronunciation,
            )
            if not action:
                return

            if action == MSG_PROFILE:
                if username:
                    self._resolve_user_then(username, lambda jid, login, uid: self.show_profile_view(jid, login, uid))
            elif action == MSG_PRIVATE:
                if username:
                    self._resolve_user_then(username, lambda jid, login, uid: self.enter_private_mode(jid, login, uid))
            elif action == MSG_COPY_USERNAME:
                if username:
                    QApplication.clipboard().setText(username)
            elif action == MSG_COPY_ID:
                user_id = self.cache.get_user_id(username) if username else None
                QApplication.clipboard().setText(str(user_id or ""))
            elif action in (MSG_TRACK, MSG_UNTRACK):
                self._on_track_user_requested(str(uid or ""), username or "", action == MSG_TRACK)
            elif action == BAN_PERMANENT:
                self._ban_user_from_msg(msg, permanent=True, widget=source_widget)
            elif action == BAN_TEMPORARY:
                seconds, ok = DurationDialog.get_duration(self, default_seconds=3600)
                if ok:
                    self._ban_user_from_msg(msg, permanent=False, duration=seconds, widget=source_widget)
            elif action == SET_PRONUNCIATION:
                if username:
                    self._set_username_pronunciation(username)
            elif action == REMOVE_PRESENCE:
                row = getattr(msg, 'presence_row', None)
                if row is not None and hasattr(source_widget, 'model'):
                    source_widget.model.remove_message_at(row)
            elif action == REMOVE_MESSAGE:
                self._remove_message(msg, single=True, widget=source_widget)
            elif action == REMOVE_UP:
                self._remove_message(msg, direction="up", widget=source_widget)
            elif action == REMOVE_DOWN:
                self._remove_message(msg, direction="down", widget=source_widget)
            elif action == REMOVE_ALL:
                self._remove_message(msg, single=False, widget=source_widget)
        except Exception as e:
            print(f"Context menu error: {e}")

    def _on_track_user_requested(self, user_id: str, login: str, track: bool):
        if not self.user_tracker:
            return
        if track:
            uid = user_id
            if not uid and login:
                uid = validate_username_and_get_id(login) or ""
            if not uid or not login:
                QMessageBox.warning(self, tr("Error", "Ошибка"), tr("Could not resolve user for tracking", "Не удалось определить пользователя для отслеживания"))
                return
            self.user_tracker.add_selected(str(uid), login)
        else:
            if user_id:
                self.user_tracker.remove_selected(str(user_id))
            elif login:
                for uid, name in list(self.user_tracker.get_selected().items()):
                    if name == login:
                        self.user_tracker.remove_selected(uid)
                        break
        w = getattr(self, 'user_tracker_widget', None)
        if w is not None:
            w.refresh()
        self._refresh_tracked_star(user_id=user_id or None, login=login or None)

    def _refresh_tracked_star(self, user_id: str = None, login: str = None):
        """Update tracked star on general, room and chatlog userlists."""
        userlists = [self.user_list_widget, self.chatlog_userlist_widget]
        userlists.extend(room.user_list_widget for room in self._all_room_widgets())
        for widget in userlists:
            if widget is not None:
                widget.refresh_tracked_star(user_id=user_id, login=login)

    def _ban_user_from_msg(self, msg, permanent: bool = True, duration: int = None, widget=None):
        """Perform ban: update BanManager, remove messages, remove userlist entry"""
        widget = widget or self.messages_widget
        # Skip separators
        if getattr(msg, 'is_separator', False) or getattr(msg, 'is_new_messages_marker', False):
            return

        username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
        jid = getattr(msg, 'from_jid', None)

        # Extract user_id from JID using helper
        user_id, _ = extract_user_data_from_jid(jid)

        self._ban_user(jid=jid, username=username, user_id=user_id, permanent=permanent, duration=duration, widget=widget)

    def _on_ban_requested(self, jid, username, user_id, permanent, duration):
        """Handle ban from userlist context menu."""
        if not permanent and duration is None:
            seconds, ok = DurationDialog.get_duration(self, default_seconds=3600)
            if not ok:
                return
            duration = seconds
        self._ban_user(jid=jid or None, username=username, user_id=user_id or None, permanent=permanent, duration=duration)

    def _ban_user(self, jid=None, username=None, user_id=None, permanent: bool = True, duration: int = None, widget=None):
        """Core ban logic shared by message and userlist context menus."""
        widget = widget or self.messages_widget

        if not user_id and not username:
            return

        if username and not user_id:
            user_id = validate_username_and_get_id(username)

        if not user_id:
            QMessageBox.warning(
                self,
                tr("Error", "Ошибка"),
                tr(f"Could not find user ID for {username}", f"Не удалось найти ID пользователя для {username}"),
            )
            return

        if permanent:
            self.ban_manager.add_user(user_id, username or user_id)
        else:
            self.ban_manager.add_user(user_id, username or user_id, duration=duration)

        if username:
            try:
                widget.model.remove_messages_by_login(username)
            except Exception:
                pass

        if hasattr(self, 'user_list_widget') and self.user_list_widget:
            try:
                if jid:
                    self.user_list_widget.remove_users(jids=[jid])
                if username:
                    for ujid, uw in list(self.user_list_widget.user_widgets.items()):
                        ulogin = getattr(getattr(uw, 'user', None), 'login', None)
                        if ulogin == username:
                            self.user_list_widget.remove_users(jids=[ujid])
            except Exception:
                pass

        if hasattr(self, 'ban_list_widget') and self.ban_list_widget:
            try:
                self.ban_list_widget.load_bans()
            except Exception:
                pass

    def _set_username_pronunciation(self, username: str):
        """Open pronunciation dialog for a username and save the result.
        Empty input + OK removes the mapping."""
        if not username or not self.pronunciation_manager:
            return
        pronunciation, ok = PronunciationDialog.get_pronunciation_for_user(
            self, username=username
        )
        if not ok:
            return
        if pronunciation:
            self.pronunciation_manager.add_mapping(username, pronunciation)
        else:
            self.pronunciation_manager.remove_mapping(username)
        widget = getattr(self, 'pronunciation_widget', None)
        if widget is not None:
            widget.refresh()

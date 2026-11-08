"""ChatWindow: tracking the own ban state."""

import threading
from datetime import datetime

from core.state.self_ban import SelfBan
from core.xmpp.jid_utils import custom_room_name_from_jid, is_from_game_room


class ChatSelfBanMixin:
    """ChatWindow: tracking the own ban state."""

    def _self_ban_left(self) -> int | None:
        """Seconds left of our own ban (0 = muted, end unknown; None = not banned). Finalizes expiry."""
        if self.self_ban_until:
            now = datetime.now().timestamp()
            if self.self_ban_until > now:
                return int(self.self_ban_until - now) + 1
            self.self_ban_until = None
            self.self_ban_timer.stop()
            self.self_ban.clear(self.my_username)
        return 0 if self.self_muted else None

    def self_ban_placeholder(self) -> str | None:
        """Input placeholder while our own ban is active; None when not banned."""
        ban_left = self._self_ban_left()
        return None if ban_left is None else self.self_ban.placeholder(ban_left, self.self_ban_total)

    def on_own_role(self, role: str):
        """Own MUC role in the general room: 'visitor' = muted. Authoritative over notices/storage."""
        was_muted = self.self_muted
        self.self_muted = role == 'visitor'
        if not self.self_muted and self.self_ban_until:
            self.self_ban_until = None
            self.self_ban_timer.stop()
            self.self_ban.clear(self.my_username)
        elif self.self_muted and not was_muted and not self.self_ban_until:
            self._lookup_self_ban_in_chatlog()
        self.update_input_style()

    def _lookup_self_ban_in_chatlog(self):
        """Muted but no ban notice seen live: recover the duration from today's chatlog."""
        username = self.my_username

        def _fetch():
            try:
                ban = SelfBan.find_in_chatlog(username)
            except Exception:
                return
            if ban:
                self.dispatch.emit(lambda: self.self_muted and self._register_self_ban(*ban))

        threading.Thread(target=_fetch, daemon=True).start()

    def is_general_jid(self, jid: str) -> bool:
        return not is_from_game_room(jid) and not custom_room_name_from_jid(jid)

    def _set_self_ban(self, until: float, total: int):
        self.self_ban_until, self.self_ban_total = until, total
        self.self_ban_timer.start(1000)
        self.update_input_style()

    def restore_self_ban(self):
        ban = self.self_ban.get_active(self.my_username)
        if ban:
            self._set_self_ban(*ban)

    def _register_self_ban(self, until: float, total: int):
        if until <= max(datetime.now().timestamp(), self.self_ban_until or 0):
            return
        self.self_ban.store(self.my_username, until, total)
        self._set_self_ban(until, total)

    def track_self_ban(self, msg):
        """Bot ban notice for our own account (live or replayed from history)"""
        total = self.self_ban.parse(msg.body, self.my_username)
        if total:
            self._register_self_ban((msg.timestamp or datetime.now()).timestamp() + total, total)

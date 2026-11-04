"""Own-account chat bans announced by the chat bot: parsing, persistence, placeholder text."""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Optional, Tuple

from core.user_state import ByUserStore
from helpers.translate import tr

_BAN_RE = re.compile(r"Пользователь\s+(.+?)\s+заблокирован\s+на\s+(\d+)\s+([а-яё]+)", re.IGNORECASE)
_UNIT_SECONDS = (("сек", 1), ("мин", 60), ("час", 3600), ("ден", 86400), ("дн", 86400),
                 ("нед", 604800), ("мес", 2592000))
_BOT = "Клавобот"


class SelfBan:
    """Stores (until, total) of the active ban per username."""

    _store = ByUserStore("self_bans.json")

    @staticmethod
    def parse(body: str, username: str) -> Optional[int]:
        """Ban duration in seconds if the bot notice targets `username`."""
        m = _BAN_RE.search(body or "")
        if not m or not username or m.group(1).casefold() != username.casefold():
            return None
        unit = m.group(3).lower()
        mult = next((s for prefix, s in _UNIT_SECONDS if unit.startswith(prefix)), None)
        return int(m.group(2)) * mult if mult else None

    @staticmethod
    def find_in_chatlog(username: str) -> Optional[Tuple[float, int]]:
        """Latest still-active ban of `username` in today's chatlog (network call, run off the UI thread)."""
        from core.chatlogs import ChatlogsParser

        messages, _, _ = ChatlogsParser().get_messages(datetime.now().strftime("%Y-%m-%d"))
        now = time.time()
        for m in reversed(messages):
            total = SelfBan.parse(m.message, username) if m.username == _BOT else None
            if total:
                until = datetime.strptime(f"{m.date} {m.timestamp}", "%Y-%m-%d %H:%M:%S").timestamp() + total
                if until > now:
                    return until, total
        return None

    def get_active(self, username: str) -> Optional[Tuple[float, int]]:
        """(until_epoch, total_seconds) of the stored ban, or None once expired."""
        data = self._store.get(username)
        try:
            until, total = float(data["until"]), int(data["total"])
        except Exception:
            return None
        if until <= time.time():
            self.clear(username)
            return None
        return until, total

    def store(self, username: str, until: float, total: int) -> None:
        self._store.set(username, {"until": until, "total": total})

    def clear(self, username: str) -> None:
        self._store.set(username, None)

    @staticmethod
    def placeholder(left: int, total: int) -> str:
        if not left:
            return tr("Chat ban: duration unknown", "Бан чата: срок неизвестен")
        t, l = SelfBan._format_total(total), SelfBan._format_left(left)
        return tr(f"Chat ban: {t} · {l} left", f"Бан чата: {t} · осталось {l}")

    @staticmethod
    def _format_total(sec: int) -> str:
        units = ((sec // 86400, tr("d", "д")), (sec % 86400 // 3600, tr("h", "ч")),
                 (sec % 3600 // 60, tr("min", "мин")), (sec % 60, tr("s", "сек")))
        return " ".join(f"{v} {u}" for v, u in units if v)

    @staticmethod
    def _format_left(sec: int) -> str:
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
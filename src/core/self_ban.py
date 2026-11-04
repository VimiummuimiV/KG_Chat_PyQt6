"""Own-account chat bans announced by the chat bot: parsing, persistence, placeholder text."""
from __future__ import annotations

import re
import time
from typing import Optional, Tuple

from core.user_state import ByUserStore
from helpers.translate import tr

_BAN_RE = re.compile(r"Пользователь\s+(.+?)\s+заблокирован\s+на\s+(\d+)\s+([а-яё]+)", re.IGNORECASE)
_UNIT_SECONDS = (("сек", 1), ("мин", 60), ("час", 3600), ("ден", 86400), ("дн", 86400),
                 ("нед", 604800), ("мес", 2592000))

_store = ByUserStore("self_bans.json")


def parse_ban(body: str) -> Optional[Tuple[str, int]]:
    """bot notice (user blocked for N units) -> (login, seconds)."""
    m = _BAN_RE.search(body or "")
    if not m:
        return None
    unit = m.group(3).lower()
    mult = next((s for prefix, s in _UNIT_SECONDS if unit.startswith(prefix)), None)
    return (m.group(1), int(m.group(2)) * mult) if mult else None


def active_ban(username: str) -> Optional[Tuple[float, int]]:
    """(until_epoch, total_seconds) of the stored ban, or None once expired."""
    data = _store.get(username)
    try:
        until, total = float(data["until"]), int(data["total"])
    except Exception:
        return None
    if until <= time.time():
        clear_ban(username)
        return None
    return until, total


def store_ban(username: str, until: float, total: int) -> None:
    _store.set(username, {"until": until, "total": total})


def clear_ban(username: str) -> None:
    _store.set(username, None)


def _format_total(sec: int) -> str:
    units = ((sec // 86400, tr("d", "д")), (sec % 86400 // 3600, tr("h", "ч")),
             (sec % 3600 // 60, tr("min", "мин")), (sec % 60, tr("s", "сек")))
    return " ".join(f"{v} {u}" for v, u in units if v)


def _format_left(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def ban_placeholder(left: int, total: int) -> str:
    if not left:
        return tr("Chat ban: duration unknown", "Бан чата: срок неизвестен")
    t, l = _format_total(total), _format_left(left)
    return tr(f"Chat ban: {t} · {l} left", f"Бан чата: {t} · осталось {l}")
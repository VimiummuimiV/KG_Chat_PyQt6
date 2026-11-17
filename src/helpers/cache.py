"""Centralized cache system for avatars and user data"""

import bisect
import heapq
import itertools
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtGui import QPixmap

from core.state.json_state import dump_entries_per_line
from helpers.colors.color_contrast import optimize_color_contrast
from helpers.data import get_data_dir, get_state_dir
from helpers.load import fetch_avatar_bytes, load_avatar_from_disk
from helpers.text.mention_parser import fold_nickname
from helpers.text.nickname_match import FUZZY_MIN_QUERY, fuzzy_pattern, match_key


_AVATAR_RETRY_SECONDS = 600  # how long a user without an avatar on the site is not asked for it again


class _CacheManager:
    """Thread-safe singleton cache manager for avatars and user data.

    Persistent store: data/users.json  —  keyed by user_id (permanent).
    Schema per entry: { login, background?, light?, dark? }

    Rules on upsert (update_user):
      • Same user_id, new login   → rename; stale reverse-index entry removed.
      • Same user_id, new bg      → recompute both-theme colors.
      • No change at all          → no-op (no disk write).
    """

    _instance = None
    _lock = threading.Lock()
    _BACKGROUND_HEX = {"dark": "#1E1E1E", "light": "#FFFFFF"}

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._login_listeners: List[Callable[[str, str], None]] = []  # called when a login is new or changed
        self._avatar_stamps: Dict[str, str] = {}  # user_id → updated timestamp
        self._avatar_waiters: Dict[str, List[Callable]] = {}  # user_id → callbacks of the load in progress
        self._avatar_missing: Dict[str, float] = {}  # user_id → when the site last had no avatar of him
        self._data: Dict[str, Dict] = {}          # user_id → {login, background?, light?, dark?}
        self._login_index: Dict[str, str] = {}    # login → user_id
        self._sorted_logins: List[Tuple[str, str]] = []  # (folded login, login), sorted: prefix search by bisect
        self._logins_text: Optional[str] = None  # the logins joined by newlines, built on the first fuzzy search
        self._avatar_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cache_avatar_loader")
        self._cache_lock = threading.Lock()
        self._data_path = get_state_dir() / "users.json"
        self._initialized = True
        self._load_data()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load_data(self) -> None:
        try:
            raw = json.loads(self._data_path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                for uid, entry in raw.items():
                    if isinstance(entry, dict) and entry.get('login'):
                        self._data[str(uid)] = entry
                        self._login_index.setdefault(entry['login'], str(uid))
        except Exception:
            pass
        self._sorted_logins = sorted((fold_nickname(login), login) for login in self._login_index)

    def _save_data(self, snapshot: dict) -> None:
        try:
            self._data_path.write_text(dump_entries_per_line(snapshot), encoding='utf-8')
        except Exception as e:
            print(f"Error saving users.json: {e}")

    # ── User data API ─────────────────────────────────────────────────────────

    def update_user(self, user_id: str, login: str, background: str = None) -> None:
        """Upsert user entry. Corrects stale login, recomputes colors if background changed."""
        if not user_id or not login:
            return
        user_id, login = str(user_id), str(login)
        with self._cache_lock:
            entry = dict(self._data.get(user_id, {}))
            changed = False
            is_login_changed = entry.get('login') != login

            if is_login_changed:
                if self._login_index.get(entry.get('login')) == user_id:
                    self._remove_login(entry['login'])
                entry['login'] = login
                self._add_login(login, user_id)
                changed = True

            if background and entry.get('background') != background:
                entry['background'] = background
                entry['light'] = optimize_color_contrast(background, self._BACKGROUND_HEX['light'], 4.5)
                entry['dark']  = optimize_color_contrast(background, self._BACKGROUND_HEX['dark'],  4.5)
                changed = True

            if not changed:
                return
            self._data[user_id] = entry
            snapshot = self._data.copy()
            listeners = tuple(self._login_listeners) if is_login_changed else ()
        self._avatar_executor.submit(self._save_data, snapshot)
        for listener in listeners:
            listener(user_id, login)

    def add_login_listener(self, listener: Callable[[str, str], None]) -> None:
        """Call listener(user_id, login) whenever a login is first seen or changes."""
        with self._cache_lock:
            self._login_listeners.append(listener)

    def remove_login_listener(self, listener: Callable[[str, str], None]) -> None:
        """Stop calling a listener added with add_login_listener."""
        with self._cache_lock:
            if listener in self._login_listeners:
                self._login_listeners.remove(listener)

    def _add_login(self, login: str, user_id: str) -> None:
        """Index a login unless it is already taken; the caller holds the lock."""
        if login in self._login_index:
            return
        self._login_index[login] = user_id
        bisect.insort(self._sorted_logins, (fold_nickname(login), login))
        self._logins_text = None

    def _remove_login(self, login: str) -> None:
        """Drop a login from both indexes; the caller holds the lock."""
        del self._login_index[login]
        del self._sorted_logins[bisect.bisect_left(self._sorted_logins, (fold_nickname(login), login))]
        self._logins_text = None

    def find_logins(self, query: str, limit: int) -> List[str]:
        """Best known logins for a query (case-insensitive, е = ё), at most limit.

        Prefix matches come first; with at least FUZZY_MIN_QUERY letters the letters may also be
        skipped (TW finds TolikWorkaholic), best matches first.
        """
        key = fold_nickname(query)
        with self._cache_lock:
            start = bisect.bisect_left(self._sorted_logins, (key,))
            prefixed = []
            for folded, login in itertools.islice(self._sorted_logins, start, start + limit):
                if not folded.startswith(key):
                    break
                prefixed.append(login)
            if len(prefixed) >= limit or len(key) < FUZZY_MIN_QUERY:
                return prefixed
            if self._logins_text is None:
                self._logins_text = "\n".join(login for _, login in self._sorted_logins)
            logins_text = self._logins_text
        ranked = ((match_key(login, key), login) for login in fuzzy_pattern(key).findall(logins_text))
        return [login for _, login in heapq.nsmallest(limit, (item for item in ranked if item[0] is not None))]

    def get_user_id(self, login: str) -> Optional[str]:
        with self._cache_lock:
            return self._login_index.get(login)

    def get_login(self, user_id: str) -> Optional[str]:
        """Last known login of a user id."""
        with self._cache_lock:
            return self._data.get(str(user_id), {}).get('login')

    def get_username_color(self, login: str, is_dark: bool) -> str:
        """Return precomputed color for login, or theme default if unknown."""
        with self._cache_lock:
            entry = self._data.get(self._login_index.get(login), {})
            if entry.get('dark'):
                return entry['dark'] if is_dark else entry['light']
        return '#CCCCCC' if is_dark else '#666666'

    def has_user(self, user_id: str) -> bool:
        """Return True if user_id is present in the persistent data store."""
        return bool(user_id) and user_id in self._data

    # ── Avatar API ────────────────────────────────────────────────────────────

    def _dir(self):
        return get_data_dir("avatars")

    def _path(self, user_id, updated):
        return self._dir() / f"{user_id}_{updated}.png"

    @staticmethod
    def _parse_stamp(avatar_path):
        m = re.search(r'updated=(\d+)', avatar_path or '')
        return m.group(1) if m else None

    def _fetch_and_save(self, user_id: str, path, callback: Callable = None) -> bool:
        """Download the avatar into path; whether the site had one."""
        data = fetch_avatar_bytes(user_id)
        with self._cache_lock:
            if data:
                self._avatar_missing.pop(user_id, None)
            else:
                self._avatar_missing[user_id] = time.monotonic()
        if data:
            path.write_bytes(data)
            for f in self._dir().glob(f"{user_id}_*.png"):
                if f != path: f.unlink(missing_ok=True)
            if callback:
                px = load_avatar_from_disk(path)
                if px: callback(user_id, px)
        return bool(data)

    def get_avatar(self, user_id: str) -> Optional[QPixmap]:
        upd = self._avatar_stamps.get(user_id)
        return load_avatar_from_disk(self._path(user_id, upd)) if upd else None

    def ensure_avatar(self, user_id: str, avatar_path: str, callback: Callable = None) -> None:
        updated = self._parse_stamp(avatar_path)
        if not updated or not user_id:
            return
        with self._cache_lock:
            prev = self._avatar_stamps.get(user_id)
            self._avatar_stamps[user_id] = updated
            self._avatar_missing.pop(user_id, None)

        def _work():
            path = self._path(user_id, updated)
            if path.exists():
                if callback and prev != updated:
                    px = load_avatar_from_disk(path)
                    if px: callback(user_id, px)
            else:
                self._fetch_and_save(user_id, path, callback)

        self._avatar_executor.submit(_work)

    def load_avatar_async(self, user_id: str, callback: Callable, timeout: int = 2) -> None:
        """Call callback(user_id, pixmap) from a worker thread once the avatar is loaded.

        Askers of one user share a single load; a user the site has no avatar of is not asked again for a while."""
        with self._cache_lock:
            missing_since = self._avatar_missing.get(user_id)
            if missing_since is not None and time.monotonic() - missing_since < _AVATAR_RETRY_SECONDS:
                return
            waiters = self._avatar_waiters.get(user_id)
            if waiters is not None:
                waiters.append(callback)
                return
            self._avatar_waiters[user_id] = [callback]

        def _load() -> Optional[QPixmap]:
            upd = self._avatar_stamps.get(user_id)
            if upd:
                return load_avatar_from_disk(self._path(user_id, upd))
            for f in self._dir().glob(f"{user_id}_*.png"):
                px = load_avatar_from_disk(f)
                if px:
                    with self._cache_lock:
                        self._avatar_stamps[user_id] = f.stem.split("_", 1)[1]
                    return px
            path = self._dir() / f"{user_id}_0.png"
            return load_avatar_from_disk(path) if self._fetch_and_save(user_id, path) else None

        def _work():
            try:
                px = _load()
            finally:
                with self._cache_lock:
                    callbacks = self._avatar_waiters.pop(user_id)
            if px:
                for waiting_callback in callbacks:
                    waiting_callback(user_id, px)

        self._avatar_executor.submit(_work)

    def _clear_avatars(self) -> None:
        with self._cache_lock:
            self._avatar_stamps.clear()
            self._avatar_missing.clear()

    def remove_avatar(self, user_id: str) -> None:
        with self._cache_lock: self._avatar_stamps.pop(user_id, None)
        for f in self._dir().glob(f"{user_id}_*.png"):
            f.unlink(missing_ok=True)

    # ── Misc ──────────────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        self._clear_avatars()

    def shutdown(self) -> None:
        if hasattr(self, '_avatar_executor'):
            self._avatar_executor.shutdown(wait=False)


_cache_manager = _CacheManager()

def get_cache() -> _CacheManager:
    return _cache_manager

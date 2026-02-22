"""Centralized cache system for avatars and colors"""
import re, threading
from typing import Optional, Dict, Callable
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtGui import QPixmap
from helpers.load import fetch_avatar_bytes, load_avatar_from_disk
from helpers.data import get_data_dir
from helpers.color_contrast import optimize_color_contrast


class CacheManager:
    """Thread-safe singleton cache manager for avatars and colors"""

    _instance = None
    _lock = threading.Lock()

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
        self._avatar_stamps: Dict[str, str] = {}   # user_id → updated timestamp
        self._color_cache: Dict[str, str] = {}
        self._user_id_cache: Dict[str, str] = {}  # login → user_id
        self._avatar_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cache_avatar_loader")
        self._cache_lock = threading.Lock()
        self._initialized = True

    # ── internal helpers ────────────────────────────────────────────────────

    def _dir(self):
        return get_data_dir("avatars")

    def _path(self, user_id, updated):
        return self._dir() / f"{user_id}_{updated}.png"

    @staticmethod
    def _parse_stamp(avatar_path):
        m = re.search(r'updated=(\d+)', avatar_path or '')
        return m.group(1) if m else None

    def _fetch_and_save(self, user_id: str, path, callback: Callable = None) -> None:
        """Download avatar, save to path, prune stale files, fire callback"""
        data = fetch_avatar_bytes(user_id)
        if data:
            path.write_bytes(data)
            for f in self._dir().glob(f"{user_id}_*.png"):
                if f != path: f.unlink(missing_ok=True)
            if callback:
                px = load_avatar_from_disk(path)
                if px: callback(user_id, px)

    # ── Avatar API ──────────────────────────────────────────────────────────

    def get_avatar(self, user_id: str) -> Optional[QPixmap]:
        """Return cached avatar from disk (no network)"""
        upd = self._avatar_stamps.get(user_id)
        return load_avatar_from_disk(self._path(user_id, upd)) if upd else None

    def ensure_avatar(self, user_id: str, avatar_path: str,
                      callback: Callable = None) -> None:
        """Called on presence: download if updated value changed, fire callback with new pixmap"""
        updated = self._parse_stamp(avatar_path)
        if not updated or not user_id:
            return
        with self._cache_lock:
            prev = self._avatar_stamps.get(user_id)
            self._avatar_stamps[user_id] = updated

        def _work():
            path = self._path(user_id, updated)
            if path.exists():
                if callback and prev != updated:
                    px = load_avatar_from_disk(path)
                    if px: callback(user_id, px)
            else:
                self._fetch_and_save(user_id, path, callback)

        self._avatar_executor.submit(_work)

    def load_avatar_async(self, user_id: str, callback: Callable,
                          timeout: int = 2) -> None:
        """Disk-first async load; falls back to network only if no file found"""
        def _work():
            upd = self._avatar_stamps.get(user_id)
            if upd:
                px = load_avatar_from_disk(self._path(user_id, upd))
                if px: callback(user_id, px)
                return  # file pending download → ensure_avatar callback will fire
            for f in self._dir().glob(f"{user_id}_*.png"):
                px = load_avatar_from_disk(f)
                if px:
                    with self._cache_lock:
                        self._avatar_stamps[user_id] = f.stem.split("_", 1)[1]
                    callback(user_id, px); return
            self._fetch_and_save(user_id, self._dir() / f"{user_id}_0.png", callback)

        self._avatar_executor.submit(_work)

    def clear_avatars(self) -> None:
        with self._cache_lock: self._avatar_stamps.clear()

    def remove_avatar(self, user_id: str) -> None:
        """Delete disk files and mapping when user has no avatar"""
        with self._cache_lock: self._avatar_stamps.pop(user_id, None)
        for f in self._dir().glob(f"{user_id}_*.png"):
            f.unlink(missing_ok=True)

    # ── Color Cache ─────────────────────────────────────────────────────────

    def get_color(self, username: str) -> Optional[str]:
        with self._cache_lock: return self._color_cache.get(username)

    def set_color(self, username: str, color: str) -> None:
        with self._cache_lock: self._color_cache[username] = color

    def get_or_calculate_color(self, username: str, background: Optional[str],
                               bg_hex: str, contrast: float = 4.5) -> str:
        cached = self.get_color(username)
        if cached: return cached
        color = optimize_color_contrast(background, bg_hex, contrast) if background else "#AAAAAA"
        self.set_color(username, color)
        return color

    def clear_colors(self) -> None:
        with self._cache_lock: self._color_cache.clear()

    # ── User ID Cache ────────────────────────────────────────────────────────

    def get_user_id(self, login: str) -> Optional[str]:
        with self._cache_lock: return self._user_id_cache.get(login)

    def set_user_id(self, login: str, user_id: str) -> None:
        if login and user_id:
            with self._cache_lock: self._user_id_cache[str(login)] = str(user_id)

    # ── Misc ─────────────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        self.clear_avatars(); self.clear_colors()

    def shutdown(self) -> None:
        if hasattr(self, '_avatar_executor'):
            self._avatar_executor.shutdown(wait=False)


_cache_manager = CacheManager()

def get_cache() -> CacheManager:
    return _cache_manager
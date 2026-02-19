"""Centralized cache system for avatars and colors"""
from typing import Optional, Dict
from PyQt6.QtGui import QPixmap
from concurrent.futures import ThreadPoolExecutor
import threading

from helpers.load import load_avatar_by_id
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
        
        self._avatar_cache: Dict[str, QPixmap] = {}
        self._color_cache: Dict[str, str] = {}
        self._user_id_cache: Dict[str, str] = {}  # login → user_id
        self._avatar_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cache_avatar_loader")
        self._cache_lock = threading.Lock()
        self._initialized = True
    
    # Avatar Cache Methods
    def get_avatar(self, user_id: str) -> Optional[QPixmap]:
        """Get cached avatar by user ID"""
        with self._cache_lock:
            return self._avatar_cache.get(user_id)
    
    def set_avatar(self, user_id: str, pixmap: QPixmap) -> None:
        """Store avatar in cache"""
        with self._cache_lock:
            self._avatar_cache[user_id] = pixmap
    
    def load_avatar_async(self, user_id: str, callback, timeout: int = 2):
        """Load avatar asynchronously and call callback with result"""
        def _worker():
            # Check cache first
            cached = self.get_avatar(user_id)
            if cached:
                callback(user_id, cached)
                return
            
            # Load from network
            pixmap = load_avatar_by_id(user_id, timeout=timeout)
            if pixmap:
                self.set_avatar(user_id, pixmap)
                callback(user_id, pixmap)
        
        self._avatar_executor.submit(_worker)
    
    def clear_avatars(self) -> None:
        """Clear all cached avatars"""
        with self._cache_lock:
            self._avatar_cache.clear()
    
    # Color Cache Methods
    def get_color(self, username: str) -> Optional[str]:
        """Get cached color for username"""
        with self._cache_lock:
            return self._color_cache.get(username)
    
    def set_color(self, username: str, color: str) -> None:
        """Store color in cache"""
        with self._cache_lock:
            self._color_cache[username] = color
    
    def get_or_calculate_color(self, username: str, background: Optional[str], 
                              bg_hex: str, contrast: float = 4.5) -> str:
        """Get cached color or calculate new one"""
        # Check cache first
        cached = self.get_color(username)
        if cached:
            return cached
        
        # Calculate new color
        if background:
            color = optimize_color_contrast(background, bg_hex, contrast)
        else:
            color = "#AAAAAA"
        
        # Store and return
        self.set_color(username, color)
        return color
    
    def clear_colors(self) -> None:
        """Clear all cached colors (useful for theme changes)"""
        with self._cache_lock:
            self._color_cache.clear()
    
    # User ID Cache Methods
    def get_user_id(self, login: str) -> Optional[str]:
        """Get cached user_id by login"""
        with self._cache_lock:
            return self._user_id_cache.get(login)

    def set_user_id(self, login: str, user_id: str) -> None:
        """Store login → user_id mapping"""
        if login and user_id:
            with self._cache_lock:
                self._user_id_cache[str(login)] = str(user_id)
    
    def clear_all(self) -> None:
        """Clear all caches"""
        self.clear_avatars()
        self.clear_colors()
    
    def shutdown(self):
        """Shutdown executor (call on app exit)"""
        if hasattr(self, '_avatar_executor'):
            self._avatar_executor.shutdown(wait=False)


# Global singleton instance
_cache_manager = CacheManager()


def get_cache() -> CacheManager:
    """Get global cache manager instance"""
    return _cache_manager
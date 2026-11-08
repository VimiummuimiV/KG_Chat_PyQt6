"""Ban List Manager - Centralized user blocking system"""

import json
import time
from pathlib import Path
from typing import Dict, Optional


class BanManager:
    """Manages banned users (permanent + temporary in unified structure)"""

    def __init__(self, data_path: Path):
        self._file_path = data_path / "banlist.json"
        self._bans: Dict[str, Dict] = {}  # {user_id: {username, expires_at?}}
        self.load()

    def load(self):
        """Load bans from JSON"""
        if self._file_path.exists():
            try:
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    self._bans = json.load(f)
                self._purge_expired()
            except Exception as e:
                print(f"Error loading ban list: {e}")
                self._bans = {}
        else:
            self._bans = {}

    def save(self):
        """Save bans to JSON"""
        try:
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump(self._bans, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving ban list: {e}")

    def add_user(self, user_id: str, username: str, duration: Optional[int] = None):
        """Add ban. If duration is None = permanent, else temporary (duration in seconds)"""
        if not user_id or not username:
            return False

        ban_data = {'username': username}
        if duration:
            ban_data['expires_at'] = int(time.time()) + int(duration)

        self._bans[str(user_id)] = ban_data
        self.save()
        return True

    def _purge_expired(self):
        """Remove expired temporary bans"""
        now = int(time.time())
        expired = [uid for uid, data in self._bans.items() 
                   if 'expires_at' in data and data['expires_at'] <= now]
        for uid in expired:
            del self._bans[uid]
        if expired:
            self.save()

    def is_banned_by_id(self, user_id: str) -> bool:
        """Check if user is banned by ID"""
        if not user_id:
            return False
        self._purge_expired()
        return str(user_id) in self._bans

    def is_banned_by_username(self, username: str) -> bool:
        """Check if user is banned by username (fallback)"""
        if not username:
            return False
        self._purge_expired()
        return any(data.get('username') == username for data in self._bans.values())

    def get_all_bans(self):
        """Returns {user_id: {username, expires_at?, is_temporary}}"""
        self._purge_expired()
        result = {}
        for uid, data in self._bans.items():
            result[uid] = {
                'username': data['username'],
                'expires_at': data.get('expires_at'),
                'is_temporary': 'expires_at' in data
            }
        return result

    def clear_all(self):
        """Clear all bans"""
        self._bans.clear()
        self.save()

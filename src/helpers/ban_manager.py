"""Ban List Manager - Centralized user blocking system"""
import json
from pathlib import Path
from typing import Dict, Optional, Set


class BanManager:
    """Manages banned users list for blocking messages and visibility"""
    
    def __init__(self, settings_path: Path):
        self.settings_path = settings_path / "banlist.json"
        self.banned_users: Dict[str, str] = {}  # {user_id: username}
        self.load()
    
    def load(self):
        """Load ban list from JSON file"""
        if self.settings_path.exists():
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    self.banned_users = json.load(f)
            except Exception as e:
                print(f"Error loading ban list: {e}")
                self.banned_users = {}
        else:
            self.banned_users = {}
    
    def save(self):
        """Save ban list to JSON file"""
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.banned_users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving ban list: {e}")
    
    def add_user(self, user_id: str, username: str):
        """Add a user to ban list by user ID and username"""
        if user_id and username:
            self.banned_users[user_id] = username
            self.save()
            return True
        return False
    
    def remove_user(self, user_id: str):
        """Remove a user from ban list"""
        if user_id in self.banned_users:
            del self.banned_users[user_id]
            self.save()
            return True
        return False
    
    def is_banned_by_id(self, user_id: str) -> bool:
        """Check if a user is banned by their user ID"""
        if not user_id:
            return False
        return str(user_id) in self.banned_users
    
    def is_banned_by_username(self, username: str) -> bool:
        """Check if a user is banned by their username (fallback check)"""
        if not username:
            return False
        return username in self.banned_users.values()
    
    def get_banned_user_ids(self) -> Set[str]:
        """Get set of all banned user IDs"""
        return set(self.banned_users.keys())
    
    def get_all_bans(self) -> Dict[str, str]:
        """Get all banned users as {user_id: username} dictionary"""
        return self.banned_users.copy()
    
    def clear_all(self):
        """Clear all banned users"""
        self.banned_users.clear()
        self.save()
    
    def get_username(self, user_id: str) -> Optional[str]:
        """Get username for a banned user ID"""
        return self.banned_users.get(user_id)

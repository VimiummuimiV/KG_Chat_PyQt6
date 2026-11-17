"""Username Pronunciation Manager"""

import json
from pathlib import Path
from typing import Dict, List


class PronunciationManager:
    """Manages username pronunciation mappings for TTS, stored by user id like the ban list."""

    def __init__(self, data_path: Path):
        self._file_path = data_path / "pronunciation.json"
        self._entries: Dict[str, Dict[str, str]] = {}  # {user_id: {username, pronunciation}}
        self.load()

    def load(self):
        """Load pronunciation mappings from JSON file"""
        if self._file_path.exists():
            try:
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    self._entries = json.load(f)
            except Exception as e:
                print(f"Error loading pronunciation mappings: {e}")
                self._entries = {}
        else:
            self._entries = {}

    def save(self):
        """Save pronunciation mappings to JSON file"""
        try:
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump(self._entries, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving pronunciation mappings: {e}")

    def has_pronunciation(self, user_id: str) -> bool:
        """Whether a user id has a pronunciation."""
        return bool(user_id) and str(user_id) in self._entries

    def set_pronunciation(self, user_id: str, username: str, pronunciation: str):
        """Add or update the pronunciation of a user."""
        if user_id and username and pronunciation:
            self._entries[str(user_id)] = {'username': username, 'pronunciation': pronunciation}
            self.save()

    def remove_pronunciation(self, user_id: str):
        """Remove the pronunciation of a user."""
        if self._entries.pop(str(user_id), None) is not None:
            self.save()

    def get_pronunciation(self, user_id: str, username: str) -> str:
        """Pronunciation of a user, or the username itself when not mapped."""
        entry = self._entries.get(str(user_id)) if user_id else None
        return entry['pronunciation'] if entry else username

    def get_entries(self) -> Dict[str, Dict[str, str]]:
        """Copy of {user_id: {username, pronunciation}}."""
        return {user_id: dict(entry) for user_id, entry in self._entries.items()}

    def replace_all(self, entries: Dict[str, Dict[str, str]]):
        """Replace every entry with one write; nothing is written when they are the same."""
        if entries == self._entries:
            return
        self._entries = entries
        self.save()

    def user_ids(self) -> List[str]:
        """Ids of every user with a pronunciation."""
        return list(self._entries)

    def rename_user(self, user_id: str, username: str) -> bool:
        """Store the current username of a user; False when nothing changed."""
        entry = self._entries.get(str(user_id))
        if entry is None or entry['username'] == username:
            return False
        entry['username'] = username
        self.save()
        return True

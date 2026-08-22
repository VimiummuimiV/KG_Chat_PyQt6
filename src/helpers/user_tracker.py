"""User join/left tracker"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional


class UserTracker:
    RETENTION_SECONDS = 86400

    def __init__(self, data_path: Path, config):
        self.file_path = data_path / "tracked.json"
        self.config = config
        self.selected: Dict[str, str] = {}
        self.frozen: set = set()
        self.events: List[dict] = []
        # user_id -> 'join' | 'left'  (last recorded transition)
        self._last_state: Dict[str, str] = {}
        self.load()

    def load(self):
        if self.file_path.exists():
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.selected = data.get('selected', {}) or {}
                self.frozen = set(str(x) for x in (data.get('frozen') or []))
                self.events = data.get('events', []) or []
                self.prune()
                self._rebuild_last_state()
            except Exception as e:
                print(f"Error loading user tracker: {e}")
                self.selected = {}
                self.frozen = set()
                self.events = []
                self._last_state = {}
        else:
            self.selected = {}
            self.frozen = set()
            self.events = []
            self._last_state = {}

    def _rebuild_last_state(self):
        self._last_state = {}
        for event in self.events:
            key = self._key(event.get('user_id'), event.get('login'))
            if key and event.get('type') in ('join', 'left'):
                self._last_state[key] = event['type']

    def _key(self, user_id: str = None, login: str = None) -> str:
        if user_id:
            return f"id:{user_id}"
        if login:
            return f"login:{login}"
        return ""

    def save(self):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {
                        'selected': self.selected,
                        'frozen': sorted(self.frozen),
                        'events': self.events,
                    },
                    f, indent=2, ensure_ascii=False
                )
        except Exception as e:
            print(f"Error saving user tracker: {e}")

    def is_enabled(self) -> bool:
        value = self.config.get("user_tracker", "enabled")
        return True if value is None else bool(value)

    def set_enabled(self, enabled: bool):
        self.config.set("user_tracker", "enabled", value=bool(enabled))

    def retention_hours(self) -> int:
        value = self.config.get("user_tracker", "retention_hours")
        try:
            hours = int(value) if value is not None else 24
        except (TypeError, ValueError):
            hours = 24
        return max(1, min(168, hours))

    def set_retention_hours(self, hours: int):
        self.config.set("user_tracker", "retention_hours", value=max(1, min(168, int(hours))))

    def is_tracked(self, user_id: str = None, login: str = None) -> bool:
        if not self.selected:
            return False
        if user_id and str(user_id) in self.selected:
            return True
        if login:
            return any(name == login for name in self.selected.values())
        return False

    def is_frozen(self, user_id: str = None, login: str = None) -> bool:
        if user_id and str(user_id) in self.frozen:
            return True
        if login:
            for uid, name in self.selected.items():
                if name == login and uid in self.frozen:
                    return True
        return False

    def is_actively_tracked(self, user_id: str = None, login: str = None) -> bool:
        return self.is_tracked(user_id=user_id, login=login) and not self.is_frozen(
            user_id=user_id, login=login
        )

    def set_frozen(self, user_id: str, frozen: bool):
        uid = str(user_id)
        if frozen:
            self.frozen.add(uid)
        else:
            self.frozen.discard(uid)
        self.save()

    def add_selected(self, user_id: str, username: str) -> bool:
        if not user_id or not username:
            return False
        self.selected[str(user_id)] = username
        self.save()
        return True

    def remove_selected(self, user_id: str) -> bool:
        uid = str(user_id)
        if uid in self.selected:
            del self.selected[uid]
            self.frozen.discard(uid)
            self.save()
            return True
        return False

    def get_selected(self) -> Dict[str, str]:
        return dict(self.selected)

    def clear_selected(self):
        self.selected.clear()
        self.frozen.clear()
        self.save()

    def seed_state(self, user_id: str, login: str, event_type: str):
        """Set last known presence without writing a history event (initial roster)."""
        if event_type not in ("join", "left") or not login:
            return
        if not self.is_tracked(user_id=user_id, login=login):
            return
        key = self._key(user_id, login)
        if key:
            self._last_state[key] = event_type

    def record_event(self, user_id: str, login: str, event_type: str) -> Optional[dict]:
        if event_type not in ("join", "left"):
            return None
        if not login:
            return None
        if not self.is_actively_tracked(user_id=user_id, login=login):
            return None

        key = self._key(user_id, login)
        if not key:
            return None

        # Ignore duplicate presence (XMPP often re-sends available without unavailable)
        if self._last_state.get(key) == event_type:
            return None

        event = {
            'user_id': str(user_id) if user_id else '',
            'login': login,
            'type': event_type,
            'ts': time.time(),
        }
        self.events.append(event)
        self._last_state[key] = event_type
        self.prune(save=False)
        self.save()
        return event

    def get_events(self) -> List[dict]:
        self.prune()
        return list(self.events)

    def clear_events(self):
        self.events.clear()
        self._last_state.clear()
        self.save()

    def prune(self, save: bool = True):
        cutoff = time.time() - self.retention_hours() * 3600
        before = len(self.events)
        self.events = [e for e in self.events if e.get('ts', 0) >= cutoff]
        if len(self.events) != before:
            self._rebuild_last_state()
            if save:
                self.save()

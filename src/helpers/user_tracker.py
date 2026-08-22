"""User join/left/game tracker"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional


EVENT_TYPES = ("join", "left", "game")


class UserTracker:
    RETENTION_SECONDS = 86400

    def __init__(self, data_path: Path, config):
        self.file_path = data_path / "tracked.json"
        self.config = config
        self.selected: Dict[str, str] = {}
        self.frozen: set = set()
        self.events: List[dict] = []
        self._last_state: Dict[str, str] = {}
        self._last_game: Dict[str, Optional[str]] = {}
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
                self._last_game = {}
        else:
            self.selected = {}
            self.frozen = set()
            self.events = []
            self._last_state = {}
            self._last_game = {}

    def _rebuild_last_state(self):
        self._last_state = {}
        self._last_game = {}
        for event in self.events:
            key = self._key(event.get('user_id'), event.get('login'))
            if not key:
                continue
            et = event.get('type') or ''
            if et == 'left':
                self._last_state[key] = 'left'
                self._last_game[key] = None
            elif et == 'join':
                self._last_state[key] = 'join'
            elif et == 'game':
                self._last_state[key] = 'join'
                self._last_game[key] = str(event['game_id']) if event.get('game_id') else None

    def _key(self, user_id: str = None, login: str = None) -> str:
        uid = str(user_id) if user_id else None
        if not uid and login:
            for sid, name in self.selected.items():
                if name == login:
                    uid = str(sid)
                    break
        if uid:
            return f"id:{uid}"
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

    def seed_state(self, user_id: str, login: str, event_type: str, game_id: str = None):
        et = event_type
        if et not in ("join", "left") or not login:
            return
        if not self.is_tracked(user_id=user_id, login=login):
            return
        key = self._key(user_id, login)
        if not key:
            return
        self._last_state[key] = et
        self._last_game[key] = str(game_id) if (et == "join" and game_id) else None

    def _append(self, user_id: str, login: str, event_type: str, game_id: str = None) -> dict:
        event = {
            'user_id': str(user_id) if user_id else '',
            'login': login,
            'type': event_type,
            'ts': time.time(),
        }
        if game_id:
            event['game_id'] = str(game_id)
        self.events.append(event)
        return event

    def record_event(self, user_id: str, login: str, event_type: str,
                     game_id: str = None) -> Optional[dict]:
        et = event_type
        if et not in ("join", "left"):
            return None
        if not login:
            return None
        if not self.is_actively_tracked(user_id=user_id, login=login):
            return None

        key = self._key(user_id, login)
        if not key:
            return None

        new_gid = str(game_id) if game_id else None
        old_gid = self._last_game.get(key)
        old_gid = str(old_gid) if old_gid else None
        last = self._last_state.get(key)
        event = None

        if et == "left":
            if last == "left":
                return None
            event = self._append(user_id, login, "left")
            self._last_state[key] = "left"
            self._last_game[key] = None
        else:
            if last != "join":
                if new_gid:
                    event = self._append(user_id, login, "game", game_id=new_gid)
                else:
                    event = self._append(user_id, login, "join")
                self._last_state[key] = "join"
                self._last_game[key] = new_gid
            elif new_gid and new_gid != old_gid:
                event = self._append(user_id, login, "game", game_id=new_gid)
                self._last_game[key] = new_gid
            else:
                if new_gid is None and old_gid:
                    self._last_game[key] = None
                return None

        if event:
            self.prune(save=False)
            self.save()
        return event

    def get_events(self) -> List[dict]:
        self.prune()
        return list(self.events)

    def clear_events(self):
        self.events.clear()
        self._last_state.clear()
        self._last_game.clear()
        self.save()

    def prune(self, save: bool = True):
        cutoff = time.time() - self.retention_hours() * 3600
        before = len(self.events)
        self.events = [e for e in self.events if e.get('ts', 0) >= cutoff]
        if len(self.events) != before:
            self._rebuild_last_state()
            if save:
                self.save()

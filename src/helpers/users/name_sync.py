"""Keeps the usernames stored in the ban list, the tracker and the pronunciations equal to the current ones."""

import threading
import time
from typing import Dict

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from core.state.json_state import JsonState
from core.web.api_data import get_current_login
from helpers.cache import get_cache
from helpers.dates import now_seconds

_RECHECK_TTL_SECONDS = 7 * 24 * 3600
_RETRY_AFTER_SECONDS = 24 * 3600
_FIRST_PASS_DELAY_MS = 30 * 1000
_PASS_INTERVAL_MS = 6 * 3600 * 1000
_PASS_LIMIT = 25
_REQUEST_DELAY_SECONDS = 1.0
_MAX_CONSECUTIVE_FAILURES = 3


def _checked_at(checked: Dict[str, dict], user_id: str) -> int:
    return checked.get(user_id, {}).get("checked_at", 0)


class NameSync(QObject):
    """Applies a changed login to every store that keeps users by id.

    The chat shows a changed login at once, through the cache listener. A user who never shows up in the chat
    is asked from the site: the longest unchecked ids first, one request a second, a few at a time.
    """

    _renamed = pyqtSignal(str, str)  # queued to the main thread when emitted by the checking thread

    def __init__(self, stores: list):
        """Every store has usernames() -> {user_id: username} and rename_user(user_id, username)."""
        super().__init__()
        self._stores = stores
        self._cache = get_cache()
        self._state = JsonState("name_checks.json", one_line_entries=True)
        self._checked = {user_id: entry for user_id, entry in self._state.get().items() if isinstance(entry, dict)}  # {user_id: {"username", "checked_at"}}
        self._checked_lock = threading.Lock()  # the main thread and the checking thread both change _checked
        self._is_checking = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._start_pass)
        self._renamed.connect(self._apply_rename)
        self._cache.add_login_listener(self._on_login_changed)

    def start(self):
        """Catch up with the names the cache already knows, then check the stale ones after the start settles."""
        is_changed = False
        for user_id in self._known_usernames():
            login = self._cache.get_login(user_id)
            if login:
                self._rename_in_stores(user_id, login)
                is_changed = self._note_login(user_id, login) or is_changed
        if is_changed:
            self._save_checked()
        self._timer.start(_FIRST_PASS_DELAY_MS)

    def stop(self):
        """Stop the periodic check and the cache listener."""
        self._timer.stop()
        self._cache.remove_login_listener(self._on_login_changed)

    def _on_login_changed(self, user_id: str, login: str):
        self._renamed.emit(user_id, login)

    def _apply_rename(self, user_id: str, login: str):
        self._rename_in_stores(user_id, login)
        if self._note_login(user_id, login):
            self._save_checked()

    def _rename_in_stores(self, user_id: str, login: str):
        for store in self._stores:
            store.rename_user(user_id, login)

    def _note_login(self, user_id: str, login: str) -> bool:
        """Keep the username of the check record current; False when there is no record or it is the same."""
        with self._checked_lock:
            entry = self._checked.get(user_id)
            if entry is None or entry.get("username") == login:
                return False
            entry["username"] = login
            return True

    def _save_checked(self):
        with self._checked_lock:
            self._state.replace(dict(self._checked))

    def _known_usernames(self) -> Dict[str, str]:
        return {user_id: username for store in self._stores for user_id, username in store.usernames().items()}

    def _start_pass(self):
        self._timer.setInterval(_PASS_INTERVAL_MS)
        if self._is_checking:
            return
        known = self._known_usernames()
        with self._checked_lock:
            kept = {user_id: entry for user_id, entry in self._checked.items() if user_id in known}
            is_pruned = len(kept) != len(self._checked)
            self._checked = kept
        if is_pruned:
            self._save_checked()
        now = now_seconds()
        stale = sorted(
            (user_id for user_id in known if now - _checked_at(kept, user_id) >= _RECHECK_TTL_SECONDS),
            key=lambda user_id: _checked_at(kept, user_id),
        )[:_PASS_LIMIT]
        if not stale:
            return
        self._is_checking = True
        threading.Thread(target=self._check, args=(stale, known), daemon=True).start()

    def _check(self, user_ids: list, known: Dict[str, str]):
        """Ask the site for the current login of each id; runs in a worker thread."""
        failures = 0
        try:
            for index, user_id in enumerate(user_ids):
                if index:
                    time.sleep(_REQUEST_DELAY_SECONDS)
                login = get_current_login(user_id)
                now = now_seconds()
                if login:
                    failures = 0
                    with self._checked_lock:
                        self._checked[user_id] = {"username": login, "checked_at": now}
                    self._cache.update_user(user_id, login)
                    self._renamed.emit(user_id, login)
                    continue
                # A failed check is dated so that it is asked again after _RETRY_AFTER_SECONDS
                with self._checked_lock:
                    self._checked[user_id] = {"username": known[user_id], "checked_at": now - _RECHECK_TTL_SECONDS + _RETRY_AFTER_SECONDS}
                failures += 1
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    break
            self._save_checked()
        finally:
            self._is_checking = False

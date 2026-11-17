"""Keeps the usernames stored in the ban list, the tracker and the pronunciations equal to the current ones."""

import threading
import time
from typing import Dict

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from core.state.json_state import JsonState
from core.web.api_data import get_current_login
from helpers.cache import get_cache

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
        self._state = JsonState("name_checks.json")  # {"checked": {user_id: {"username", "checked_at"}}}
        self._is_checking = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._start_pass)
        self._renamed.connect(self._apply_rename)
        self._cache.add_login_listener(self._on_login_changed)

    def start(self):
        """Catch up with the names the cache already knows, then check the stale ones after the start settles."""
        for user_id in self._known_usernames():
            login = self._cache.get_login(user_id)
            if login:
                self._apply_rename(user_id, login)
        self._timer.start(_FIRST_PASS_DELAY_MS)

    def stop(self):
        """Stop the periodic check and the cache listener."""
        self._timer.stop()
        self._cache.remove_login_listener(self._on_login_changed)

    def _on_login_changed(self, user_id: str, login: str):
        self._renamed.emit(user_id, login)

    def _apply_rename(self, user_id: str, login: str):
        for store in self._stores:
            store.rename_user(user_id, login)

    def _known_usernames(self) -> Dict[str, str]:
        return {user_id: username for store in self._stores for user_id, username in store.usernames().items()}

    def _start_pass(self):
        self._timer.setInterval(_PASS_INTERVAL_MS)
        if self._is_checking:
            return
        known = self._known_usernames()
        saved = self._state.get("checked") or {}
        checked = {user_id: entry for user_id, entry in saved.items() if user_id in known and isinstance(entry, dict)}
        now = time.time()
        stale = sorted(
            (user_id for user_id in known if now - _checked_at(checked, user_id) >= _RECHECK_TTL_SECONDS),
            key=lambda user_id: _checked_at(checked, user_id),
        )[:_PASS_LIMIT]
        if not stale:
            return
        self._is_checking = True
        threading.Thread(target=self._check, args=(stale, known, checked), daemon=True).start()

    def _check(self, user_ids: list, known: Dict[str, str], checked: Dict[str, dict]):
        """Ask the site for the current login of each id; runs in a worker thread."""
        failures = 0
        try:
            for index, user_id in enumerate(user_ids):
                if index:
                    time.sleep(_REQUEST_DELAY_SECONDS)
                login = get_current_login(user_id)
                now = int(time.time())
                if login:
                    failures = 0
                    checked[user_id] = {"username": login, "checked_at": now}
                    self._cache.update_user(user_id, login)
                    self._renamed.emit(user_id, login)
                    continue
                # A failed check is dated so that it is asked again after _RETRY_AFTER_SECONDS
                checked[user_id] = {"username": known[user_id], "checked_at": now - _RECHECK_TTL_SECONDS + _RETRY_AFTER_SECONDS}
                failures += 1
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    break
            self._state.set("checked", value=checked)
        finally:
            self._is_checking = False

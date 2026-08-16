"""Rating competitions listener"""

import json
import random
import string
import time
import threading

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import websocket
except ImportError:
    websocket = None

_MULT_ORDER = {"x1": 1, "x2": 2, "x3": 3, "x5": 5}


def _rand_id(n=8):
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def _sockjs_send(ws, msg: str):
    ws.send(json.dumps([msg], separators=(",", ":")))


def _info_and_params(data: dict) -> tuple[dict | None, dict]:
    """Resolve the nested info/params dicts, handling both wrapped and flat payloads."""
    info = data.get("info") or data
    if not isinstance(info, dict):
        return None, {}
    return info, info.get("params") or {}


def _game_url(gid) -> str:
    return f"https://klavogonki.ru/g/?gmid={gid}"


def _multiplier(data: dict) -> str:
    if not isinstance(data, dict):
        return "?"
    if "regular_competition" in data:
        val = data["regular_competition"]
    else:
        _, params = _info_and_params(data)
        val = params.get("regular_competition")
    if val is None:
        return "?"
    return "x1" if val == 0 else f"x{val}"


def _is_rating(data) -> bool:
    if not data or not isinstance(data, dict):
        return False
    if data.get("competition") is True:
        return True
    _, params = _info_and_params(data)
    return bool(params.get("competition"))


def _game_info(data: dict) -> dict | None:
    """Full game object (gameCreated / initList item)."""
    info, params = _info_and_params(data)
    if info is None:
        return None
    gid = info.get("id") or data.get("id")
    if not gid:
        return None
    return {
        "game_id": gid,
        "status": info.get("status") or "?",
        "multiplier": _multiplier(data),
        "competition_id": params.get("competition"),
        "competition_cost": params.get("competition_cost"),
        "timeout": params.get("timeout"),
        "level_from": params.get("level_from"),
        "level_to": params.get("level_to"),
        "gametype": params.get("gametype"),
        "begintime": info.get("begintime"),
        "url": _game_url(gid),
    }


class RacesListener(QObject):
    """Emits competition_found for rating competition status updates."""

    competition_found = pyqtSignal(dict)
    status_changed = pyqtSignal(str)  # connecting | connected | disconnected

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop = threading.Event()
        self._games: dict = {}  # game_id -> last info dict
        self.min_multiplier = "x1+"

    def set_min_multiplier(self, value: str):
        self.min_multiplier = value or "x1+"

    def _passes_filter(self, mult: str) -> bool:
        need = _MULT_ORDER.get(self.min_multiplier.rstrip("+"), 1)
        have = _MULT_ORDER.get(mult, 0)
        return have >= need

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        if websocket is None:
            print("[races] websocket-client not installed")
            self.status_changed.emit("disconnected")
            return
        self._stop.clear()
        self.status_changed.emit("connecting")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.status_changed.emit("disconnected")

    def _run(self):
        while not self._stop.is_set():
            try:
                self.status_changed.emit("connecting")
                self._connect_once()
            except Exception as e:
                print(f"[races] error: {e}")
            if self._stop.is_set():
                break
            self.status_changed.emit("disconnected")
            time.sleep(3)

    def _connect_once(self):
        url = f"wss://klavogonki.ru/ws/{random.randint(0, 999)}/{_rand_id()}/websocket"
        ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=lambda *_: None,
            on_close=lambda *_: None,
            header={
                "Origin": "https://klavogonki.ru",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:153.0) "
                    "Gecko/20100101 Firefox/153.0"
                ),
            },
        )
        ws.run_forever(ping_interval=25, ping_timeout=10)

    def _on_open(self, ws):
        self.status_changed.emit("connected")
        for ch in (
            "gamelist/initList",
            "gamelist/gameCreated",
            "gamelist/gameUpdated",
            "gamelist/competitionStarts",
        ):
            _sockjs_send(ws, f"subscribe {ch}")

    def _on_message(self, ws, raw: str):
        if raw in ("o", "h") or raw.startswith("c") or not raw.startswith("a"):
            return
        try:
            messages = json.loads(raw[1:])
        except Exception:
            return

        for item in messages:
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except Exception:
                    continue
            if not (isinstance(item, list) and item):
                continue

            event = item[0]
            data = item[1] if len(item) > 1 else None

            if event == "gamelist/competitionStarts" and isinstance(data, dict):
                if not data.get("competition"):
                    continue
                gmid = data.get("gmid")
                self._emit({
                    "game_id": gmid,
                    "status": "waiting",
                    "multiplier": _multiplier(data),
                    "timeout": data.get("timeout"),
                    "level_from": data.get("level_from"),
                    "level_to": data.get("level_to"),
                    "gametype": data.get("gametype"),
                    "url": _game_url(gmid) if gmid else None,
                })

            elif event == "gamelist/initList" and isinstance(data, list):
                for g in data:
                    if _is_rating(g):
                        info = _game_info(g)
                        if info:
                            self._emit(info)

            elif event == "gamelist/gameCreated" and isinstance(data, dict):
                if _is_rating(data):
                    info = _game_info(data)
                    if info:
                        self._emit(info)

            elif event == "gamelist/gameUpdated" and isinstance(data, dict):
                # Diff form: {"g": 110033, "diff": {"status": "racing", ...}}
                gid = data.get("g") or data.get("id")
                diff = data.get("diff")
                if gid is not None and isinstance(diff, dict):
                    self._apply_diff(gid, diff)
                elif _is_rating(data):
                    info = _game_info(data)
                    if info:
                        self._emit(info)

    def _apply_diff(self, gid, diff: dict):
        """Merge status (and other) changes for a known competition."""
        prev = self._games.get(gid)
        if prev is None:
            # unknown game — only track if we somehow care later; skip
            return
        if "status" not in diff and "begintime" not in diff:
            return
        info = dict(prev)
        if "status" in diff:
            info["status"] = diff["status"]
        if "begintime" in diff:
            info["begintime"] = diff["begintime"]
        self._emit(info)

    def _emit(self, info: dict):
        gid = info.get("game_id")
        if not gid:
            return
        mult = info.get("multiplier") or "?"
        if not self._passes_filter(mult):
            return

        status = info.get("status") or "?"
        prev = self._games.get(gid)
        if prev is not None and prev.get("status") == status:
            # same status — keep cache, no signal
            self._games[gid] = info
            return

        self._games[gid] = info
        if len(self._games) > 300:
            for k in list(self._games.keys())[:100]:
                self._games.pop(k, None)

        self.competition_found.emit(info)
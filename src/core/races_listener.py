"""Rating competitions listener"""

import json
import random
import string
import time
import threading
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import websocket
except ImportError:
    websocket = None

_MULT_ORDER = {"x1": 1, "x2": 2, "x3": 3, "x5": 5}
_TRACKED_STATUSES = {"waiting", "racing"}


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


def _to_epoch(value):
    """Normalize begintime/endtime to unix seconds. The server sends unix seconds in
    gameUpdated diffs but ISO 8601 strings in full gameCreated/initList objects."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _game_fields(data: dict) -> dict | None:
    """Field subset for gameCreated / initList entries, keyed for merging into game state."""
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
        "begintime": _to_epoch(info.get("begintime")),
        "endtime": _to_epoch(info.get("endtime")),
        "url": _game_url(gid),
    }


class RacesListener(QObject):
    """Emits competition_found for status changes and players_changed for roster updates."""

    competition_found = pyqtSignal(dict)
    players_changed = pyqtSignal(int, list)
    status_changed = pyqtSignal(str)  # connecting | connected | disconnected

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop = threading.Event()
        self._games: dict = {}  # game_id -> {status, multiplier, ..., players: {slot: {...}}, _emitted_status}
        self.min_multiplier = "x1+"

    def set_min_multiplier(self, value: str):
        self.min_multiplier = value or "x1+"
        for gid, game in self._games.items():
            self._maybe_emit(gid, game)

    def passes_filter(self, mult: str) -> bool:
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
            "gamelist/playerUpdated",
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
            self._handle_event(event, data)

    def _handle_event(self, event, data):
        if event == "gamelist/competitionStarts" and isinstance(data, dict):
            if not data.get("competition"):
                return
            gmid = data.get("gmid")
            if not gmid:
                return
            self._merge_and_emit(gmid, {
                "status": "waiting",
                "multiplier": _multiplier(data),
                "timeout": data.get("timeout"),
                "level_from": data.get("level_from"),
                "level_to": data.get("level_to"),
                "gametype": data.get("gametype"),
                "url": _game_url(gmid),
            })

        elif event == "gamelist/initList" and isinstance(data, list):
            for g in data:
                if _is_rating(g):
                    fields = _game_fields(g)
                    if fields:
                        gid = fields.pop("game_id")
                        self._merge_and_emit(gid, fields)

        elif event == "gamelist/gameCreated" and isinstance(data, dict):
            if _is_rating(data):
                fields = _game_fields(data)
                if fields:
                    gid = fields.pop("game_id")
                    self._merge_and_emit(gid, fields)

        elif event == "gamelist/gameUpdated" and isinstance(data, dict):
            gid = data.get("g") or data.get("id")
            diff = data.get("diff")
            if gid is None or gid not in self._games or not isinstance(diff, dict):
                return
            fields = {k: diff[k] for k in ("status", "begintime", "endtime") if k in diff}
            for key in ("begintime", "endtime"):
                if key in fields:
                    fields[key] = _to_epoch(fields[key])
            if fields:
                self._merge_and_emit(gid, fields)

        elif event == "gamelist/playerUpdated" and isinstance(data, dict):
            gid = data.get("g")
            slot = data.get("p")
            diff = data.get("diff")
            if gid in self._games and slot is not None and isinstance(diff, dict):
                self._apply_player_diff(gid, slot, diff)

    def _merge_and_emit(self, gid, fields: dict):
        game = self._games.get(gid)
        if game is None:
            game = {"players": {}}
            self._games[gid] = game
            self._trim_games()
        for key, value in fields.items():
            if value is not None:
                game[key] = value
        self._maybe_emit(gid, game)

    def _maybe_emit(self, gid, game: dict):
        status = game.get("status")
        mult = game.get("multiplier") or "?"
        if status not in _TRACKED_STATUSES or not self.passes_filter(mult):
            return
        if game.get("_emitted_status") == status:
            return
        game["_emitted_status"] = status
        self.competition_found.emit(self._public_info(gid, game))

    def _apply_player_diff(self, gid, slot, diff: dict):
        game = self._games[gid]
        players = game["players"]
        if diff.get("leave"):
            players.pop(slot, None)
        else:
            entry = players.pop(slot, {})  # re-insert to move to the end (arrival order)
            if "name" in diff:
                entry["name"] = diff["name"]
            user = diff.get("user")
            if isinstance(user, dict) and user.get("login"):
                entry["login"] = user["login"]
            players[slot] = entry

        if game.get("status") == "waiting" and self.passes_filter(game.get("multiplier") or "?"):
            self.players_changed.emit(gid, self._ordered_players(game))

    @staticmethod
    def _ordered_players(game: dict) -> list:
        return list(game["players"].values())

    def _public_info(self, gid, game: dict) -> dict:
        return {
            "game_id": gid,
            "status": game.get("status") or "?",
            "multiplier": game.get("multiplier") or "?",
            "competition_id": game.get("competition_id"),
            "competition_cost": game.get("competition_cost"),
            "timeout": game.get("timeout"),
            "level_from": game.get("level_from"),
            "level_to": game.get("level_to"),
            "gametype": game.get("gametype"),
            "begintime": game.get("begintime"),
            "endtime": game.get("endtime"),
            "url": game.get("url") or _game_url(gid),
            "players": self._ordered_players(game),
        }

    def _trim_games(self):
        if len(self._games) > 300:
            for k in list(self._games.keys())[:100]:
                self._games.pop(k, None)
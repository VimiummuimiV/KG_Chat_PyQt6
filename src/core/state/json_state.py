"""JSON state file in KG_Chat_Data/data: nested get / set / remove, read from disk on every call."""

from __future__ import annotations

import json

from helpers.data import get_state_dir


class JsonState:
    """One JSON object file; a key path addresses a value inside nested objects."""

    def __init__(self, filename: str):
        self._filename = filename

    def _read(self) -> dict:
        try:
            raw = json.loads((get_state_dir() / self._filename).read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        try:
            path = get_state_dir() / self._filename
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get(self, *keys):
        """Value at the key path, or None when any step is missing."""
        value = self._read()
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    def set(self, *keys, value) -> None:
        data = self._read()
        node = data
        for key in keys[:-1]:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        node[keys[-1]] = value
        self._write(data)

    def remove(self, *keys) -> None:
        data = self._read()
        node = data
        for key in keys[:-1]:
            node = node.get(key)
            if not isinstance(node, dict):
                return
        if node.pop(keys[-1], None) is not None:
            self._write(data)

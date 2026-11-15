"""Configuration manager"""

import json
from pathlib import Path

from helpers.data import get_data_dir


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "settings" / "config.json"
_USER_CONFIG_PATH = get_data_dir("settings") / "config.json"


def get_config_path() -> Path:
    if _USER_CONFIG_PATH.exists():
        return _USER_CONFIG_PATH
    return _DEFAULT_CONFIG_PATH


class Config:
    def __init__(self, path=None):
        if path is None:
            path = get_config_path()
        self.path = Path(path)
        self.data = self.load()

    def load(self):
        # utf-8-sig transparently strips a BOM if present (e.g. from tools that save as "UTF-8")
        with open(self.path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)

    def save(self):
        user_path = _USER_CONFIG_PATH
        user_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = user_path
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, *keys):
        value = self.data
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    def set(self, *keys, value):
        d = self.data
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value
        self.save()


def read_bounded_int(config, keys: tuple, default: int, bounds: tuple[int, int]) -> int:
    """Integer setting clamped to bounds; the default when it is missing or not a number."""
    value = config.get(*keys) if config else None
    try:
        return max(bounds[0], min(bounds[1], int(value)))
    except (TypeError, ValueError):
        return default

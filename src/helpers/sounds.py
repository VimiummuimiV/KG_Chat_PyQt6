"""Alert sound lookup: bundled and user directories, selection and freeze state."""

from pathlib import Path

from helpers.data import get_data_dir


# kind == folder name == config key: "mention" | "ban" | "competition"
def get_system_sound_dir(sound_root: Path, kind: str) -> Path:
    """Project-bundled sounds (read-only for the user)."""
    if not sound_root:
        return Path()
    return sound_root / (kind or "").strip().lower()


def get_user_sound_dir(kind: str) -> Path:
    """User-writable sounds under KG_Chat_Data/sounds/<kind>/."""
    return get_data_dir("sounds") / (kind or "").strip().lower()


def get_sound_files(sound_dir: Path) -> list[str]:
    """Return sorted MP3 names from one directory."""
    if not sound_dir or not sound_dir.exists():
        return []
    return sorted(
        [p.name for p in sound_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp3"],
        key=lambda name: name.lower(),
    )


def get_merged_sound_files(system_dir: Path, user_dir: Path) -> list[str]:
    """Unique filenames from system + user dirs (user overrides on name clash)."""
    names = set(get_sound_files(system_dir)) | set(get_sound_files(user_dir))
    return sorted(names, key=lambda n: n.lower())


def resolve_sound_file(name: str, system_dir: Path, user_dir: Path) -> Path | None:
    """Prefer user copy, then system."""
    if not name:
        return None
    user_path = user_dir / name
    if user_path.is_file():
        return user_path
    system_path = system_dir / name
    if system_path.is_file():
        return system_path
    return None


def _read_selected_name(config, kind: str) -> str | None:
    """Read sound.selected.<kind>."""
    if isinstance(config, dict):
        selected = (config.get("sound") or {}).get("selected") or {}
    else:
        selected = config.get("sound", "selected") or {}
    if not isinstance(selected, dict):
        return None
    return selected.get(kind)


def is_sound_frozen(config, kind: str) -> bool:
    """Whether the alert sound for this kind is muted via the freeze toggle."""
    frozen = config.get("sound", "frozen") or {}
    return isinstance(frozen, dict) and bool(frozen.get((kind or "").strip().lower(), False))


def set_sound_frozen(config, kind: str, frozen: bool):
    current = config.get("sound", "frozen") or {}
    current = dict(current) if isinstance(current, dict) else {}
    current[(kind or "").strip().lower()] = frozen
    config.set("sound", "frozen", value=current)


def get_sound_name(sound_root: Path, kind: str, config) -> str | None:
    """Filename currently chosen for this kind, or a sensible default."""
    system_dir = get_system_sound_dir(sound_root, kind)
    user_dir = get_user_sound_dir(kind)
    files = get_merged_sound_files(system_dir, user_dir)
    if not files:
        return None

    name = _read_selected_name(config, kind)
    if name and name in files:
        return name

    # Prefer <kind>.mp3 if present, else first file
    preferred = f"{(kind or '').strip().lower()}.mp3"
    if preferred in files:
        return preferred
    return files[0]


def get_sound_path(sound_root: Path, kind: str, config) -> Path | None:
    """Full path to the active sound for this kind (user dir wins over system)."""
    name = get_sound_name(sound_root, kind, config)
    if not name:
        return None
    return resolve_sound_file(
        name,
        get_system_sound_dir(sound_root, kind),
        get_user_sound_dir(kind),
    )

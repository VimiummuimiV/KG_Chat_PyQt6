"""Self-update from GitHub: compare the installed commit with the branch head, stage the changed files, apply them at the next start."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

import requests
from PyQt6.QtCore import QProcess

from core.state.ui_state import ui_state
from helpers.config import read_bounded_int
from helpers.data import get_app_dir, get_data_dir


_REPOSITORY = "VimiummuimiV/KG_Chat_PyQt6"
_BRANCH = "main"
CHECK_INTERVAL_DAYS_RANGE = (1, 30)
DEFAULT_CHECK_INTERVAL_DAYS = 1
_SHORT_COMMIT_LENGTH = 7

_API_URL = f"https://api.github.com/repos/{_REPOSITORY}"
_RAW_URL = f"https://raw.githubusercontent.com/{_REPOSITORY}"
_ARCHIVE_URL = f"https://github.com/{_REPOSITORY}/archive"
_SOURCE_PREFIX = "src/"
_INSTALLED_COMMIT_FILE = "installed_commit.txt"
_MANIFEST_NAME = "manifest.json"
_STAGED_FILES_NAME = "files"
_ARCHIVE_NAME = "archive.zip"
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_COMPARE_FILE_LIMIT = 300
_DOWNLOAD_WORKERS = 8
_DOWNLOAD_CHUNK_BYTES = 1 << 16
_CHECK_TIMEOUT_SECONDS = 20
_DOWNLOAD_TIMEOUT_SECONDS = 60
_YTDLP_REQUIREMENT = "yt-dlp"
_YTDLP_UPGRADE_TIMEOUT_SECONDS = 300


@dataclass
class UpdateInfo:
    """An available update: the commit to install, its release notes and the files it changes."""

    latest_commit: str
    messages: list[str]  # commit messages between the installed and the latest commit, newest first
    written_paths: list[str]  # repository paths to download
    removed_paths: list[str]  # repository paths to delete
    outside_paths: list[str]  # changed files outside src/: the app cannot apply them
    needs_archive: bool = False  # the changes cannot be listed: download the whole repository once


def short_commit(commit: str) -> str:
    """The first characters of a commit hash, as GitHub shows it."""
    return commit[:_SHORT_COMMIT_LENGTH]


def changes_url(info: UpdateInfo) -> str:
    """The GitHub page of the update: the commits and changed files, or the latest commit when the history cannot be compared."""
    current = installed_commit()
    if current is None or not info.messages:
        return f"https://github.com/{_REPOSITORY}/commit/{info.latest_commit}"
    return f"https://github.com/{_REPOSITORY}/compare/{current}...{info.latest_commit}"


def is_development_checkout() -> bool:
    """True when the app runs from a git working copy, which an update must never overwrite."""
    return (get_app_dir().parent / ".git").exists()


def installed_commit() -> str | None:
    """The commit the files of the app come from; None until the first check records it."""
    try:
        commit = (get_app_dir() / _INSTALLED_COMMIT_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return commit if _COMMIT_PATTERN.fullmatch(commit) else None


def is_auto_check_enabled(config) -> bool:
    """The automatic update check is on unless the setting says otherwise."""
    value = config.get("update", "auto_check") if config else None
    return True if value is None else bool(value)


def check_interval_days(config) -> int:
    """Days between automatic checks."""
    return read_bounded_int(config, ("update", "interval_days"), DEFAULT_CHECK_INTERVAL_DAYS, CHECK_INTERVAL_DAYS_RANGE)


def last_checked_at() -> int | None:
    """Time of the last finished check in whole seconds."""
    value = ui_state.get("update", "last_checked_at")
    return value if isinstance(value, int) else None


def saved_update() -> UpdateInfo | None:
    """The update found by an earlier check that is still newer than the installed files."""
    data = ui_state.get("update", "available")
    try:
        info = UpdateInfo(**data)
    except TypeError:
        return None
    current = installed_commit()
    return None if current is None or info.latest_commit == current else info


def save_check_result(info: UpdateInfo | None, checked_at: int) -> None:
    """Remember when the check ran and the update it found, if any."""
    ui_state.set("update", value={"last_checked_at": checked_at, "available": asdict(info) if info else None})


def check_for_update() -> UpdateInfo | None:
    """The available update, or None when the app is current. The first run only records the installed commit."""
    if is_development_checkout():
        return None
    latest = _fetch_latest_commit()
    current = installed_commit()
    if current is None:
        (get_app_dir() / _INSTALLED_COMMIT_FILE).write_text(latest, encoding="utf-8")
        return None
    if current == latest:
        return None
    return _build_update_info(current, latest)


def _fetch_latest_commit() -> str:
    response = requests.get(
        f"{_API_URL}/commits/{_BRANCH}", headers={"Accept": "application/vnd.github.sha"}, timeout=_CHECK_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    commit = response.text.strip()
    if not _COMMIT_PATTERN.fullmatch(commit):
        raise ValueError(f"Unexpected commit answer: {commit[:80]}")
    return commit


def _build_update_info(current: str, latest: str) -> UpdateInfo:
    response = requests.get(f"{_API_URL}/compare/{current}...{latest}", timeout=_CHECK_TIMEOUT_SECONDS)
    if response.status_code == 404:  # the installed commit is gone from the history
        return UpdateInfo(latest, [], [], [], [], needs_archive=True)
    response.raise_for_status()
    data = response.json()

    written, removed, outside = [], [], []
    for entry in data.get("files", []):
        path, status = entry["filename"], entry["status"]
        previous_path = entry.get("previous_filename")
        if status in ("removed", "renamed") and (previous_path or path).startswith(_SOURCE_PREFIX):
            removed.append(previous_path or path)
        if status in ("removed", "unchanged"):
            continue
        (written if path.startswith(_SOURCE_PREFIX) else outside).append(path)
    messages = [commit["commit"]["message"].strip() for commit in reversed(data.get("commits", []))]
    needs_archive = data.get("status") != "ahead" or len(data.get("files", [])) >= _COMPARE_FILE_LIMIT
    return UpdateInfo(latest, messages, written, removed, outside, needs_archive)


def stage_update(info: UpdateInfo) -> None:
    """Download the update into KG_Chat_Data/update; apply_pending_update installs it at the next start."""
    staging = get_data_dir("update")
    shutil.rmtree(staging, ignore_errors=True)
    staged_files = staging / _STAGED_FILES_NAME
    staged_files.mkdir(parents=True)
    if info.needs_archive:
        _stage_archive(info.latest_commit, staging, staged_files)
    else:
        with ThreadPoolExecutor(max_workers=_DOWNLOAD_WORKERS) as pool:
            list(pool.map(lambda path: _stage_file(info.latest_commit, path, staged_files), info.written_paths))
    removed = [] if info.needs_archive else [path[len(_SOURCE_PREFIX):] for path in info.removed_paths]
    manifest = {"commit": info.latest_commit, "removed": removed}
    (staging / _MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")  # last: marks a complete download


def _stage_file(commit: str, path: str, staged_files: Path) -> None:
    target = staged_files / path[len(_SOURCE_PREFIX):]
    target.parent.mkdir(parents=True, exist_ok=True)
    _download(f"{_RAW_URL}/{commit}/{quote(path)}", target)


def _stage_archive(commit: str, staging: Path, staged_files: Path) -> None:
    archive_path = staging / _ARCHIVE_NAME
    _download(f"{_ARCHIVE_URL}/{commit}.zip", archive_path)
    root = staged_files.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            _, _, path = member.filename.partition("/")  # the first folder is the repository name
            if member.is_dir() or not path.startswith(_SOURCE_PREFIX):
                continue
            target = (staged_files / path[len(_SOURCE_PREFIX):]).resolve()
            if root not in target.parents:
                raise ValueError(f"Unsafe path in the archive: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as destination:
                shutil.copyfileobj(source, destination)
    archive_path.unlink()


def _download(url: str, target: Path) -> None:
    with requests.get(url, stream=True, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
        response.raise_for_status()
        with open(target, "wb") as file:
            for chunk in response.iter_content(_DOWNLOAD_CHUNK_BYTES):
                file.write(chunk)


def apply_pending_update() -> bool:
    """Install the staged update into the app folder; True when files were replaced and the app must restart."""
    staging = get_data_dir("update")
    manifest_path = staging / _MANIFEST_NAME
    if not manifest_path.exists():
        return False
    app_dir = get_app_dir()
    staged_files = staging / _STAGED_FILES_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative_path in manifest["removed"]:
            _remove_file(app_dir, app_dir / relative_path)
        relative_paths = [path.relative_to(staged_files) for path in staged_files.rglob("*") if path.is_file()]
        for relative_path in sorted(relative_paths, key=lambda path: path == Path("main.py")):  # the entry point goes last
            target = app_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_files / relative_path, target)
        (app_dir / _INSTALLED_COMMIT_FILE).write_text(manifest["commit"], encoding="utf-8")
    except Exception as error:
        print(f"⚠️ Update was not applied: {error}")
        return False
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return True


def _remove_file(app_dir: Path, path: Path) -> None:
    """Delete a file and the folders it leaves empty, never above the app folder."""
    path.unlink(missing_ok=True)
    for folder in path.parents:
        if folder == app_dir or not folder.is_dir() or any(folder.iterdir()):
            return
        folder.rmdir()


def upgrade_ytdlp() -> bool:
    """Upgrade the pip package of yt-dlp that the video player runs; False when pip failed."""
    command = [sys.executable, "-m", "pip", "install", "--upgrade", _YTDLP_REQUIREMENT]
    options = {"capture_output": True, "stdin": subprocess.DEVNULL, "timeout": _YTDLP_UPGRADE_TIMEOUT_SECONDS}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        return subprocess.run(command, **options).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def relaunch_application() -> None:
    """Start a new instance of the app that outlives this process."""
    QProcess.startDetached(sys.executable, sys.argv)

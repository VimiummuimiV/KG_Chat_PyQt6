"""Background image downloader with an in-memory LRU cache, shared by the viewer and its thumbnails."""

from collections import OrderedDict
from typing import Collection, Optional

import requests
from PyQt6.QtCore import pyqtBoundSignal, pyqtSignal, QObject, QRunnable, QThreadPool


_CONNECT_TIMEOUT_SECONDS = 5
_READ_TIMEOUT_SECONDS = 15
_DOWNLOAD_CHUNK_BYTES = 8192
_DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0"}
_FOREGROUND_DOWNLOADS = 2
_BACKGROUND_DOWNLOADS = 1
_CACHE_LIMIT_BYTES = 32 * 1024 * 1024
_UNKNOWN_TOTAL_BYTES = 256 * 1024  # without Content-Length the progress guess reaches one half at this size


def _create_pool(thread_count: int) -> QThreadPool:
    pool = QThreadPool()
    pool.setMaxThreadCount(thread_count)
    return pool


# Shared by every loader and owned by none: a pool waits for its running downloads when destroyed,
# so a pool destroyed with a viewer froze the UI for as long as those requests lasted
_FOREGROUND_POOL = _create_pool(_FOREGROUND_DOWNLOADS)
_BACKGROUND_POOL = _create_pool(_BACKGROUND_DOWNLOADS)


class _DownloadTask(QRunnable):
    """One download running in the loader's thread pool."""

    def __init__(self, url: str, pool: QThreadPool, finished: pyqtBoundSignal):
        super().__init__()
        self.setAutoDelete(False)
        self.url = url
        self._pool = pool
        self.cancelled = False
        self.received_bytes = 0
        self.total_bytes = 0  # zero while the server did not announce the size
        self._finished = finished

    def progress(self) -> float:
        """Fraction of the download done; a guess when the size is unknown."""
        total = self.total_bytes or self.received_bytes + _UNKNOWN_TOTAL_BYTES
        return min(1.0, self.received_bytes / total)

    def run(self):
        data = self._download()
        if self.cancelled:
            return
        try:
            self._finished.emit(self.url, data or b"", data is None)
        except RuntimeError:
            pass  # the loader was destroyed while this download was running

    def _download(self) -> Optional[bytes]:
        """Return the image bytes, or None on failure or cancellation."""
        try:
            response = requests.get(
                self.url, headers=_DOWNLOAD_HEADERS, timeout=(_CONNECT_TIMEOUT_SECONDS, _READ_TIMEOUT_SECONDS), stream=True
            )
            if response.status_code != 200:
                return None
            announced_size = response.headers.get("Content-Length", "")
            self.total_bytes = int(announced_size) if announced_size.isdigit() else 0
            chunks = []
            for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                if self.cancelled:
                    return None
                if chunk:
                    chunks.append(chunk)
                    self.received_bytes += len(chunk)
            return b"".join(chunks)
        except Exception as error:
            if not self.cancelled:
                print(f"Failed to load {self.url}: {error}")
            return None


class ImageLoader(QObject):
    """Downloads the image being viewed right away and the rest one at a time, keeping the recent ones in memory."""

    loaded = pyqtSignal(str, bytes, bool)  # url, data, is_error
    _task_finished = pyqtSignal(str, bytes, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._cache_bytes = 0
        self._tasks: dict[str, _DownloadTask] = {}
        self._failed: set[str] = set()
        self._task_finished.connect(self._on_task_finished)

    def request(self, url: str, priority: int = 0, background: bool = False) -> Optional[bytes]:
        """Return the cached bytes, or start a download (emits loaded when done) and return None.
        Background downloads run one at a time, highest priority first, and never hold up foreground ones."""
        data = self._cache.get(url)
        if data is not None:
            self._cache.move_to_end(url)
            return data
        if url not in self._tasks and url not in self._failed:
            task = _DownloadTask(url, _BACKGROUND_POOL if background else _FOREGROUND_POOL, self._task_finished)
            self._tasks[url] = task
            task._pool.start(task, priority)
        return None

    def has_failed(self, url: str) -> bool:
        """True when a previous download of this url failed (it is not retried until reset)."""
        return url in self._failed

    def loading_progress(self, url: str) -> Optional[float]:
        """Fraction (0..1) of a running download, or None while the url is not being downloaded."""
        task = self._tasks.get(url)
        return None if task is None else task.progress()

    def is_settled(self, url: str) -> bool:
        """True when the url is cached or has failed, so nothing more is coming for it."""
        return url in self._cache or url in self._failed

    def cancel_except(self, keep_urls: Collection[str]):
        """Cancel every other download so the images being waited for get the whole connection."""
        for url in [url for url in self._tasks if url not in keep_urls]:
            task = self._tasks.pop(url)
            task.cancelled = True
            task._pool.tryTake(task)

    def retain_only(self, urls: Collection[str]):
        """Cancel downloads and drop cached images that are not in urls."""
        self.cancel_except(urls)
        for url in [url for url in self._cache if url not in urls]:
            self._cache_bytes -= len(self._cache.pop(url))

    def reset(self):
        """Cancel every download and drop the cache."""
        self.cancel_except(())
        self._failed.clear()
        self._cache.clear()
        self._cache_bytes = 0

    def _on_task_finished(self, url: str, data: bytes, is_error: bool):
        if self._tasks.pop(url, None) is None:
            return
        if is_error:
            self._failed.add(url)
        else:
            self._store(url, data)
        self.loaded.emit(url, data, is_error)

    def _store(self, url: str, data: bytes):
        self._cache[url] = data
        self._cache_bytes += len(data)
        while self._cache_bytes > _CACHE_LIMIT_BYTES and len(self._cache) > 1:
            _, evicted = self._cache.popitem(last=False)
            self._cache_bytes -= len(evicted)

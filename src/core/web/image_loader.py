"""Background image downloader with an in-memory LRU cache, shared by the viewer and its thumbnails."""

from collections import OrderedDict
from typing import Callable, Collection, Optional

import requests
from PyQt6.QtCore import pyqtBoundSignal, pyqtSignal, QObject, QRunnable, QThreadPool


DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_CHUNK_BYTES = 8192
DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0"}
FOREGROUND_DOWNLOADS = 2
BACKGROUND_DOWNLOADS = 1
CACHE_LIMIT_BYTES = 32 * 1024 * 1024


def _download(url: str, is_cancelled: Callable[[], bool]) -> Optional[bytes]:
    """Return the image bytes, or None on failure or cancellation."""
    try:
        response = requests.get(url, headers=DOWNLOAD_HEADERS, timeout=DOWNLOAD_TIMEOUT_SECONDS, stream=True)
        if response.status_code != 200:
            return None
        chunks = []
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
            if is_cancelled():
                return None
            if chunk:
                chunks.append(chunk)
        return b"".join(chunks)
    except Exception as error:
        print(f"Failed to load {url}: {error}")
        return None


class _DownloadTask(QRunnable):
    """One download running in the loader's thread pool."""

    def __init__(self, url: str, pool: QThreadPool, finished: pyqtBoundSignal):
        super().__init__()
        self.setAutoDelete(False)
        self.url = url
        self.pool = pool
        self.cancelled = False
        self._finished = finished

    def run(self):
        data = _download(self.url, lambda: self.cancelled)
        if not self.cancelled:
            self._finished.emit(self.url, data or b"", data is None)


class ImageLoader(QObject):
    """Downloads the image being viewed right away and the rest one at a time, keeping the recent ones in memory."""

    loaded = pyqtSignal(str, bytes, bool)  # url, data, is_error
    _task_finished = pyqtSignal(str, bytes, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._foreground_pool = QThreadPool(self)
        self._foreground_pool.setMaxThreadCount(FOREGROUND_DOWNLOADS)
        self._background_pool = QThreadPool(self)
        self._background_pool.setMaxThreadCount(BACKGROUND_DOWNLOADS)
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
            task = _DownloadTask(url, self._background_pool if background else self._foreground_pool, self._task_finished)
            self._tasks[url] = task
            task.pool.start(task, priority)
        return None

    def has_failed(self, url: str) -> bool:
        """True when a previous download of this url failed (it is not retried until reset)."""
        return url in self._failed

    def is_settled(self, url: str) -> bool:
        """True when the url is cached or has failed, so nothing more is coming for it."""
        return url in self._cache or url in self._failed

    def cancel_except(self, keep_urls: Collection[str]):
        """Cancel every other download so the images being waited for get the whole connection."""
        for url in [url for url in self._tasks if url not in keep_urls]:
            task = self._tasks.pop(url)
            task.cancelled = True
            task.pool.tryTake(task)

    def retain_only(self, urls: Collection[str]):
        """Cancel downloads and drop cached images that are not in urls."""
        self.cancel_except(urls)
        for url in [url for url in self._cache if url not in urls]:
            self._cache_bytes -= len(self._cache.pop(url))

    def reset(self):
        """Cancel every download and drop the cache."""
        for task in self._tasks.values():
            task.cancelled = True
        self._foreground_pool.clear()
        self._background_pool.clear()
        self._tasks.clear()
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
        while self._cache_bytes > CACHE_LIMIT_BYTES and len(self._cache) > 1:
            _, evicted = self._cache.popitem(last=False)
            self._cache_bytes -= len(evicted)

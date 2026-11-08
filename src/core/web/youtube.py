"""YouTube link processor - memory cache only"""

import re
import threading
from typing import Callable, Dict, Optional, Tuple

import requests
from PyQt6.QtCore import pyqtSignal, QObject


_OEMBED_URL = "https://www.youtube.com/oembed"
_UNAVAILABLE_STATUS_CODES = (401, 403, 404)

# Shared pattern - defined once at module level
YOUTUBE_URL_PATTERN = re.compile(
    r'https?://(?:www\.|m\.)?(?:youtube\.com/(?:shorts/|live/|watch\?v=|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})',
    re.IGNORECASE
)


# Global signal for YouTube metadata updates
class _YouTubeSignals(QObject):
    metadata_cached = pyqtSignal(str)
youtube_signals = _YouTubeSignals()


def _extract_youtube_info(url: str) -> Optional[Dict[str, str]]:
    """Extract video ID and type from YouTube URL"""
    match = YOUTUBE_URL_PATTERN.search(url)
    if not match:
        return None

    video_id = match.group(1)
    url_lower = url.lower()
    video_type = (
        'Shorts' if 'shorts/' in url_lower else
        'Live' if 'live/' in url_lower else
        'Video' if 'watch?v=' in url_lower else
        'Share' if 'youtu.be/' in url_lower else
        'YouTube'
    )

    return {'video_id': video_id, 'video_type': video_type, 'url': url}


def _format_youtube_display(video_type: str, channel: str, title: str, use_emojis: bool = True) -> str:
    """Format YouTube info as display text"""
    max_length = 50  # Adjust to control title width

    # Truncate title if too long
    if len(title) > max_length:
        title = title[:max_length - 3] + "..."

    if use_emojis:
        # Format: ▶️ [ Type ] Channel - Title
        type_labels = {
            'Shorts': 'Shorts',
            'Live': 'Live',
            'Share': 'Share',
            'Video': 'Video',
        }
        type_label = type_labels.get(video_type, 'YouTube')
        return f"▶️ [ {type_label} ] {channel} - {title}"

    return f"[{video_type}] {channel} - {title}"


class _YouTubeProcessor:
    """YouTube link processor with memory cache"""

    # Use the shared module-level pattern
    _PATTERN = YOUTUBE_URL_PATTERN

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self._cache: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._active_fetches: set = set()

    def is_youtube_url(self, url: str) -> bool:
        """Check if URL is YouTube"""
        return bool(self._PATTERN.search(url))

    def _fetch_metadata(self, video_id: str, url: str = None) -> Dict[str, str]:
        """Fetch metadata from YouTube oEmbed API"""
        if video_id in self._cache:
            return self._cache[video_id]

        watch_url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            response = self.session.get(_OEMBED_URL, params={"url": watch_url, "format": "json"}, timeout=5)
            response.raise_for_status()
            data = response.json()

            result = {
                'title': data.get('title', 'Title not found'),
                'channel': data.get('author_name', 'Channel not found')
            }

            with self._lock:
                self._cache[video_id] = result

            if url:
                youtube_signals.metadata_cached.emit(url)

            return result

        except Exception as e:
            is_unavailable = isinstance(e, requests.HTTPError) and e.response.status_code in _UNAVAILABLE_STATUS_CODES
            if not is_unavailable:  # deleted, private and non-embeddable videos are expected
                print(f"Error fetching YouTube metadata for {video_id}: {e}")
            # Cache the error to prevent retry loops
            error_result = {'title': 'Video unavailable', 'channel': 'YouTube'}
            with self._lock:
                self._cache[video_id] = error_result

            if url:
                youtube_signals.metadata_cached.emit(url)

            return error_result

    def _get_cached_metadata(self, video_id: str) -> Optional[Dict[str, str]]:
        """Get metadata from cache only"""
        return self._cache.get(video_id)

    def fetch_async(self, url: str, callback: Callable = None) -> bool:
        """
        Fetch YouTube metadata in background (handles deduplication)

        Returns:
            True if fetch was started, False if already fetching
        """
        fetch_key = f"yt_{url}"

        if fetch_key in self._active_fetches:
            return False

        self._active_fetches.add(fetch_key)

        def _fetch():
            try:
                info = _extract_youtube_info(url)
                if info:
                    metadata = self._fetch_metadata(info['video_id'], url)
                    result = {**info, **metadata}
                    if callback:
                        callback(result)
            finally:
                self._active_fetches.discard(fetch_key)

        threading.Thread(target=_fetch, daemon=True).start()
        return True

    def clear_cache(self):
        """Clear memory cache"""
        with self._lock:
            self._cache.clear()


# Global processor instance
_processor: Optional[_YouTubeProcessor] = None
_lock = threading.Lock()


def _get_processor() -> _YouTubeProcessor:
    """Get or create global processor instance"""
    global _processor
    if _processor is None:
        with _lock:
            if _processor is None:
                _processor = _YouTubeProcessor()
    return _processor


def is_youtube_url(url: str) -> bool:
    """Check if URL is YouTube"""
    return _get_processor().is_youtube_url(url)


def get_cached_info(url: str, use_emojis: bool = True) -> Optional[Tuple[str, bool]]:
    """
    Get formatted YouTube info from cache only

    Returns:
        Tuple of (formatted_text, is_cached) or None if not YouTube
    """
    info = _extract_youtube_info(url)
    if not info:
        return None

    cached = _get_processor()._get_cached_metadata(info['video_id'])
    if cached:
        formatted = _format_youtube_display(info['video_type'], cached['channel'], cached['title'], use_emojis)
        return (formatted, True)

    return (url, False)


def fetch_async(url: str, callback: Callable = None) -> bool:
    """
    Fetch YouTube metadata in background (handles deduplication)

    Returns:
        True if fetch was started, False if already fetching
    """
    return _get_processor().fetch_async(url, callback)


def clear_cache():
    """Clear the memory cache"""
    _get_processor().clear_cache()

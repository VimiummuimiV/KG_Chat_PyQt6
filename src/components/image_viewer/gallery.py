"""Image URL recognition and the gallery of images found in a list of messages."""

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Callable, Iterable, NamedTuple, Optional

from PyQt6.QtCore import pyqtBoundSignal


URL_PATTERN = re.compile(r'https?://[^\s<>"]+')
_IMAGE_PATTERNS = [
    re.compile(r'https?://[^\s<>"]+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^\s<>"]*)?', re.IGNORECASE),
    re.compile(r'https?://.*\.(?:giphy|tenor|gfycat)\.com/[^\s<>"]+', re.IGNORECASE),
]


def is_image_url(url: str) -> bool:
    return any(pattern.search(url or '') for pattern in _IMAGE_PATTERNS)


def extract_image_url(url: str) -> Optional[str]:
    """Extract the image URL from text, or None."""
    if not url:
        return None
    for pattern in _IMAGE_PATTERNS:
        if match := pattern.search(url):
            return match.group(0)
    return None


class GalleryImage(NamedTuple):
    """One image link with the message it was posted in."""
    url: str
    username: str = ""
    timestamp: Optional[datetime] = None
    source: object = None  # the message; handed back through ImageGallery.on_source


def _collect_images(messages: Iterable) -> list[GalleryImage]:
    """Every image link of the messages in order."""
    images = []
    seen = set()
    for message in messages:
        for match in URL_PATTERN.finditer(getattr(message, "body", "") or ""):
            url = extract_image_url(match.group(0))
            if not url or (url, id(message)) in seen:
                continue
            seen.add((url, id(message)))
            images.append(GalleryImage(
                url, getattr(message, "username", "") or "", getattr(message, "timestamp", None), message
            ))
    return images


class DayState(NamedTuple):
    """Chatlog day behind the viewer and whether its neighbours exist."""
    day: date
    has_previous: bool
    has_next: bool


class DayNavigation(NamedTuple):
    """Chatlog day switching the viewer can drive."""
    step: Callable[[int], None]  # go to the previous (-1) or next (+1) day
    state: Callable[[], Optional[DayState]]  # None while days do not apply (parser results)


@dataclass
class ImageGallery:
    """Images the viewer can page through, and which one was opened."""
    images: list[GalleryImage]
    start_index: int = 0
    on_source: Optional[Callable[[object], None]] = None  # called with the message of the current image
    get_messages: Optional[Callable[[], Iterable]] = None  # current messages the images were collected from
    messages_replaced: Optional[pyqtBoundSignal] = None  # emitted when get_messages starts returning other messages
    day_navigation: Optional[DayNavigation] = None  # chatlog views only

    @classmethod
    def single(cls, url: str) -> "ImageGallery":
        return cls([GalleryImage(url)])

    @classmethod
    def from_messages(cls, get_messages: Callable[[], Iterable], clicked_message, clicked_url: str,
                      on_source: Callable[[object], None], messages_replaced: pyqtBoundSignal,
                      day_navigation: Optional[DayNavigation] = None) -> "ImageGallery":
        """Collect every image link of the messages; start at the clicked one and follow later message changes."""
        clicked_url = extract_image_url(clicked_url)
        images = _collect_images(get_messages())
        start_index = next(
            (index for index, image in enumerate(images) if image.source is clicked_message and image.url == clicked_url),
            None,
        )
        if start_index is None:
            return cls.single(clicked_url)
        return cls(images, start_index, on_source, get_messages, messages_replaced, day_navigation)

    def reloaded(self, current_url: str) -> "ImageGallery":
        """Gallery rebuilt from the current messages; with no image left only the one being viewed stays."""
        images = _collect_images(self.get_messages()) or [GalleryImage(current_url)]
        return replace(self, images=images, start_index=0)

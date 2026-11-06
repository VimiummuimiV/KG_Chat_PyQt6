"""Image URL recognition and the gallery of images found in a list of messages."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, NamedTuple, Optional


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


@dataclass
class ImageGallery:
    """Images the viewer can page through, and which one was opened."""
    images: list[GalleryImage]
    start_index: int = 0
    on_source: Optional[Callable[[object], None]] = None  # called with the message of the current image

    @classmethod
    def single(cls, url: str) -> "ImageGallery":
        return cls([GalleryImage(url)])

    @classmethod
    def from_messages(cls, messages: Iterable, clicked_message, clicked_url: str,
                      on_source: Callable[[object], None]) -> "ImageGallery":
        """Collect every image link of the messages in order; start at the clicked one."""
        clicked_url = extract_image_url(clicked_url)
        images = []
        seen = set()
        start_index = None
        for message in messages:
            for match in URL_PATTERN.finditer(getattr(message, "body", "") or ""):
                url = extract_image_url(match.group(0))
                if not url or (url, id(message)) in seen:
                    continue
                seen.add((url, id(message)))
                if start_index is None and message is clicked_message and url == clicked_url:
                    start_index = len(images)
                images.append(GalleryImage(
                    url, getattr(message, "username", "") or "", getattr(message, "timestamp", None), message
                ))
        if start_index is None:
            return cls.single(clicked_url)
        return cls(images, start_index, on_source)

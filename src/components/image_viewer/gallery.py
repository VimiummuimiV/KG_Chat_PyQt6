"""Image URL recognition and the gallery of images found in a list of messages."""

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Callable, Iterable, Iterator, NamedTuple, Optional

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


def _iter_images(messages: Iterable) -> Iterator[GalleryImage]:
    """Every image link of the messages in order."""
    seen = set()
    for message in messages:
        for match in URL_PATTERN.finditer(getattr(message, "body", "") or ""):
            url = extract_image_url(match.group(0))
            if not url or (url, id(message)) in seen:
                continue
            seen.add((url, id(message)))
            yield GalleryImage(
                url, getattr(message, "username", "") or "", getattr(message, "timestamp", None), message
            )


def first_image(messages: Iterable) -> Optional[GalleryImage]:
    """The first image link of the messages, or None."""
    return next(_iter_images(messages), None)


class DayState(NamedTuple):
    """Chatlog day behind the viewer and whether its neighbours exist."""
    day: date
    has_previous: bool
    has_next: bool


class DayNavigation(NamedTuple):
    """Chatlog day switching the viewer can drive."""
    step: Callable[[int], None]  # go to the previous (-1) or next (+1) day
    state: Callable[[], Optional[DayState]]  # None while days do not apply (parser results)
    loaded: pyqtBoundSignal  # emitted when a day finished loading, with or without messages


class InlineReply(NamedTuple):
    """What the viewer needs to write a reply without closing."""
    prefill: Callable[[object], str]  # reply text for a message
    send: Callable[[str], None]
    emoticon_selector: Callable[[], Optional[object]]  # the shared selector widget, None while it does not exist


@dataclass
class ImageGallery:
    """Images the viewer can page through, and which one was opened."""
    images: list[GalleryImage]
    start_index: int = 0
    on_source: Optional[Callable[[object], None]] = None  # called with the message of the current image
    get_messages: Optional[Callable[[], Iterable]] = None  # current messages the images were collected from
    messages_replaced: Optional[pyqtBoundSignal] = None  # emitted when get_messages starts returning other messages
    day_navigation: Optional[DayNavigation] = None  # chatlog views only
    on_reply: Optional[Callable[[object], None]] = None  # called with the message of the current image
    inline_reply: Optional[InlineReply] = None

    @classmethod
    def single(cls, url: str) -> "ImageGallery":
        return cls([GalleryImage(url)])

    @classmethod
    def from_messages(cls, get_messages: Callable[[], Iterable], clicked_message, clicked_url: str,
                      on_source: Callable[[object], None], messages_replaced: pyqtBoundSignal,
                      day_navigation: Optional[DayNavigation] = None,
                      on_reply: Optional[Callable[[object], None]] = None,
                      inline_reply: Optional[InlineReply] = None) -> "ImageGallery":
        """Collect every image link of the messages; start at the clicked one and follow later message changes."""
        clicked_url = extract_image_url(clicked_url)
        images = list(_iter_images(get_messages()))
        start_index = next(
            (index for index, image in enumerate(images) if image.source is clicked_message and image.url == clicked_url),
            None,
        )
        if start_index is None:
            return cls.single(clicked_url)
        return cls(images, start_index, on_source, get_messages, messages_replaced, day_navigation, on_reply, inline_reply)

    def reloaded(self, current_url: Optional[str]) -> "ImageGallery":
        """Gallery rebuilt from the current messages; with no image left only the one being viewed stays."""
        images = list(_iter_images(self.get_messages())) or ([GalleryImage(current_url)] if current_url else [])
        return replace(self, images=images, start_index=0)

    def without_images(self) -> "ImageGallery":
        return replace(self, images=[], start_index=0)

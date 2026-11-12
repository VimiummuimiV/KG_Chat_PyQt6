"""Avatar helpers: rounded real avatar, or a theme-colored SVG placeholder, loaded in the background."""

from pathlib import Path
from typing import Callable, Optional

from PyQt6 import sip
from PyQt6.QtCore import pyqtSignal, QObject, QSize, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel

from components.button import get_user_svg_color, render_svg_icon
from helpers.cache import get_cache
from helpers.load import make_rounded_pixmap


_AVATAR_RADIUS = 8
_USER_ID_PROPERTY = "avatar_user_id"
_PLACEHOLDER_PROPERTY = "avatar_is_placeholder"


class _AvatarLoadBridge(QObject):
    """Hands an avatar from the loader thread over to the GUI thread."""

    loaded = pyqtSignal(QPixmap)


def _svg_avatar_pixmap(icons_path, size: int, color=None, icon_name: str = "fill/user-3-fill.svg"):
    """Fallback icon pixmap rendered at the given size."""
    icon = render_svg_icon(icons_path / icon_name, size, color) if color is not None \
        else render_svg_icon(icons_path / icon_name, size)
    return icon.pixmap(QSize(size, size))


def make_avatar_label(size: int = 36) -> QLabel:
    """Styled, fixed-size avatar placeholder shared by all avatar layouts."""
    label = QLabel()
    label.setFixedSize(size, size)
    label.setObjectName("avatar")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def make_rounded_avatar(pixmap: QPixmap, size: int) -> QPixmap:
    """Real avatar cropped to the shared rounded shape."""
    return make_rounded_pixmap(pixmap, size, _AVATAR_RADIUS)


def make_avatar_pixmap(icons_path, raw_pixmap, size: int = 36, svg_size: int = 24, color=None, icon_name: str = "fill/user-3-fill.svg"):
    """Rounded real avatar if one is available, else the SVG fallback icon."""
    if raw_pixmap is not None and not raw_pixmap.isNull():
        return make_rounded_avatar(raw_pixmap, size)
    return _svg_avatar_pixmap(icons_path, svg_size, color, icon_name)


def _emit_loaded(bridge: _AvatarLoadBridge, pixmap: QPixmap):
    try:
        bridge.loaded.emit(pixmap)
    except RuntimeError:
        pass  # the owner was deleted before the avatar arrived


def _fetch_avatar(owner: QObject, user_id: str, on_loaded: Callable[[QPixmap], None]):
    """Load the avatar in the background and pass it to on_loaded in the GUI thread."""
    bridge = _AvatarLoadBridge(owner)
    is_delivered = False

    def deliver(pixmap: QPixmap):
        nonlocal is_delivered
        if is_delivered or sip.isdeleted(bridge):  # a queued repeat or a delivery to an owner that is already gone
            return
        is_delivered = True
        bridge.deleteLater()
        on_loaded(pixmap)

    bridge.loaded.connect(deliver)
    get_cache().load_avatar_async(user_id, lambda _loaded_id, pixmap: _emit_loaded(bridge, pixmap))


def request_avatar(owner: QObject, user_id: str, on_loaded: Callable[[QPixmap], None]):
    """Pass the user's avatar to on_loaded: at once when cached, else from the GUI thread once loaded."""
    cached_avatar = get_cache().get_avatar(user_id)
    if cached_avatar:
        on_loaded(cached_avatar)
    else:
        _fetch_avatar(owner, user_id, on_loaded)


def show_real_avatar(label: QLabel, pixmap: QPixmap, size: int):
    """Show a loaded avatar; it no longer follows the theme."""
    label.setProperty(_PLACEHOLDER_PROPERTY, False)
    label.setPixmap(make_rounded_avatar(pixmap, size))


def _show_loaded_avatar(label: QLabel, user_id: str, pixmap: QPixmap, size: int):
    if label.property(_USER_ID_PROPERTY) == user_id:
        show_real_avatar(label, pixmap, size)


def refresh_avatar_placeholder(label: QLabel, user_id: Optional[str], svg_size: int, is_dark: bool,
                               icons_path: Path, icon_name: str = "fill/user-3-fill.svg"):
    """Recolor a themed placeholder after a theme change; a real avatar is left as is."""
    if not label.property(_PLACEHOLDER_PROPERTY):
        return
    color = get_user_svg_color(get_cache().has_user(user_id), is_dark)
    label.setPixmap(_svg_avatar_pixmap(icons_path, svg_size, color, icon_name))


def apply_user_avatar(label: QLabel, user_id: Optional[str], size: int, svg_size: int, is_dark: bool,
                      icons_path: Path, icon_name: str = "fill/user-3-fill.svg"):
    """Show the user's avatar (or the themed placeholder) in the label; fetch it in the background if missing."""
    cache = get_cache()
    cached_avatar = cache.get_avatar(user_id) if user_id else None
    color = get_user_svg_color(cache.has_user(user_id), is_dark)
    label.setProperty(_USER_ID_PROPERTY, user_id)
    label.setProperty(_PLACEHOLDER_PROPERTY, not cached_avatar)
    label.setPixmap(make_avatar_pixmap(icons_path, cached_avatar, size, svg_size, color, icon_name))
    if user_id and not cached_avatar:
        _fetch_avatar(label, user_id, lambda pixmap: _show_loaded_avatar(label, user_id, pixmap, size))

"""Data of the user rows: the columns a list adds and the row itself."""

from dataclasses import dataclass, field
from typing import Callable, Optional

from PyQt6.QtGui import QPixmap


AVATAR_SIZE = 36
SVG_AVATAR_SIZE = 24
USERNAME_BASE_WIDTH = 220
USER_ID_BASE_WIDTH = 125
ARROW_SIZE = 26
ARROW_COLOR = "#888888"
DEFAULT_INPUT_HEIGHT = 44
DEFAULT_SPACING = 6
COLUMN_TOGGLE = "toggle"  # icon button that flips a bool of the row
COLUMN_BUTTON = "button"  # text button that asks its list to act
COLUMN_FIELD = "field"  # text field edited in place
VALIDATION_TOOLTIPS = {
    "missing": ("Fill username before adding new item", "Заполните имя пользователя перед добавлением новой записи"),
    "invalid": ("User not found", "Пользователь не найден"),
}


@dataclass(frozen=True)
class ExtraColumn:
    """A column a list adds between the user id and the remove button; its value lives in UserRow.extras[key]."""

    key: str
    kind: str
    icon: str = ""  # toggle
    tooltips: tuple = ()  # toggle: ((off English, off Russian), (on English, on Russian))
    text_of: Optional[Callable[["UserRow"], str]] = None  # button: the text it shows
    placeholder: tuple = ("", "")  # field
    base_width: int = 0  # field: width before the font scale; button: the least width
    dims_row: bool = False  # toggle: the username, the user id and the button are dimmed while it is on


@dataclass(eq=False)
class UserRow:
    """One user of a list; the avatar is made when the row is first painted."""

    username: str = ""
    user_id: str = ""
    extras: dict = field(default_factory=dict)
    is_valid: bool = True
    is_missing_marked: bool = False
    avatar: Optional[QPixmap] = None
    is_avatar_real: bool = False
    is_avatar_requested: bool = False

    @property
    def validation(self) -> str:
        """Which highlight the username field has: "", "missing" or "invalid"."""
        if not self.username:
            return "missing" if self.is_missing_marked else ""
        return "" if self.is_valid else "invalid"

    @property
    def is_confirmed(self) -> bool:
        """Whether the username is a user the site knows."""
        return bool(self.username and self.user_id and self.is_valid)

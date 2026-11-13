"""Shared row widget: avatar + colored username + count, with filter highlight and click-to-filter."""

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from components.avatar import apply_user_avatar, make_avatar_label, refresh_avatar_placeholder
from components.colored_label import ColoredLabel
from helpers.cache import get_cache
from helpers.fonts.fonts import FontType, get_font
from themes.stylesheet import set_style_property


class UserCountRow(QWidget):
    """Avatar + username + count row. Base for chatlog userlist rows and tracker filter chips."""
    AVATAR_SIZE = 36
    SVG_AVATAR_SIZE = 24

    clicked = pyqtSignal(str, bool)  # username, ctrl_pressed

    def __init__(self, username, count, config, icons_path, user_id=None,
                 margins=(2, 0, 2, 0), spacing=6):
        super().__init__()
        self.setObjectName("userCountRow")
        self.username = username
        self.user_id = user_id
        self.icons_path = icons_path
        self._cache = get_cache()

        layout = QHBoxLayout()
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        self.setLayout(layout)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        is_dark = config.get("ui", "theme") == "dark"

        self.avatar_label = make_avatar_label(self.AVATAR_SIZE)
        apply_user_avatar(self.avatar_label, user_id, self.AVATAR_SIZE, self.SVG_AVATAR_SIZE, is_dark, icons_path)
        layout.addWidget(self.avatar_label)

        self.username_label = ColoredLabel(username, self._cache.get_username_color(username, is_dark))
        self.username_label.setObjectName("userName")
        self.username_label.setFont(get_font(FontType.TEXT))
        self.username_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.username_label.setMinimumWidth(20)
        self.username_label.setTextFormat(Qt.TextFormat.PlainText)
        # Elide long names so trailing count/buttons aren't clipped when panel is narrow
        self.username_label.setWordWrap(False)
        layout.addWidget(self.username_label, stretch=1)

        self.count_label = QLabel(str(count))
        self.count_label.setObjectName("mutedLabel")
        self.count_label.setFont(get_font(FontType.TEXT))
        self.count_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.count_label)

    def set_filtered(self, filtered: bool):
        """Highlight name and count; the property sits on the labels because a parent's property does not repolish children."""
        set_style_property(self.username_label, "filtered", filtered)
        set_style_property(self.count_label, "filtered", filtered)

    def update_theme(self, is_dark: bool):
        """Username color re-read from the cache; placeholder avatar recolored; the count follows the stylesheet."""
        self.username_label.set_text_color(self._cache.get_username_color(self.username, is_dark))
        refresh_avatar_placeholder(self.avatar_label, self.user_id, self.SVG_AVATAR_SIZE, is_dark, self.icons_path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.clicked.emit(self.username, ctrl_pressed)
        super().mousePressEvent(event)

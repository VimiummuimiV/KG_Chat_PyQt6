"""Shared row widget: avatar + colored username + count, with filter highlight and click-to-filter."""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QCursor

from helpers.create import _render_svg_icon, get_user_svg_color
from helpers.load import make_rounded_pixmap
from helpers.cache import get_cache
from helpers.fonts import get_font, FontType


class UserCountRow(QWidget):
    """Avatar + username + count row. Base for chatlog userlist rows and tracker filter chips."""
    AVATAR_SIZE = 36
    SVG_AVATAR_SIZE = 24

    clicked = pyqtSignal(str, bool)  # username, ctrl_pressed

    def __init__(self, username, count, config, icons_path, user_id=None,
                 margins=(2, 0, 2, 0), spacing=6, filter_radius=4):
        super().__init__()
        self.username = username
        self.user_id = user_id
        self.icons_path = icons_path
        self.is_filtered = False
        self._filter_radius = filter_radius
        self._cache = get_cache()

        layout = QHBoxLayout()
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        self.setLayout(layout)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        is_dark = config.get("ui", "theme") == "dark"

        # Avatar
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(self.AVATAR_SIZE, self.AVATAR_SIZE)
        self.avatar_label.setStyleSheet("background: transparent; border: none; padding: 0; margin: 0;")
        self.avatar_label.setScaledContents(False)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cached_avatar = self._cache.get_avatar(user_id) if user_id else None
        if cached_avatar:
            self.avatar_label.setPixmap(make_rounded_pixmap(cached_avatar, self.AVATAR_SIZE, 8))
        else:
            svg_color = get_user_svg_color(self._cache.has_user(user_id), is_dark)
            self.avatar_label.setPixmap(
                _render_svg_icon(icons_path / "user.svg", self.SVG_AVATAR_SIZE, svg_color)
                .pixmap(QSize(self.SVG_AVATAR_SIZE, self.SVG_AVATAR_SIZE))
            )
            if user_id:
                self._cache.load_avatar_async(user_id, self._on_avatar_loaded)
        layout.addWidget(self.avatar_label)

        self.username_label = QLabel(username)
        self.username_label.setFont(get_font(FontType.TEXT))
        self.username_label.setStyleSheet(f"color: {self._cache.get_username_color(username, is_dark)};")
        self.username_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.username_label.setMinimumWidth(20)
        self.username_label.setTextFormat(Qt.TextFormat.PlainText)
        # Elide long names so trailing count/buttons aren't clipped when panel is narrow
        self.username_label.setWordWrap(False)
        layout.addWidget(self.username_label, stretch=1)

        count_color = "#CCCCCC" if is_dark else "#666666"
        self.count_label = QLabel(str(count))
        self.count_label.setFont(get_font(FontType.TEXT))
        self.count_label.setStyleSheet(f"color: {count_color};")
        self.count_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.count_label)

    def _on_avatar_loaded(self, user_id: str, pixmap):
        try:
            if user_id == self.user_id and self.avatar_label:
                self.avatar_label.setPixmap(make_rounded_pixmap(pixmap, self.AVATAR_SIZE, 8))
        except RuntimeError:
            pass

    def set_filtered(self, filtered: bool):
        """Update visual state when filtered"""
        self.is_filtered = filtered
        if filtered:
            self.setStyleSheet(
                f"background-color: rgba(226, 135, 67, 0.2); border-radius: {self._filter_radius}px;"
            )
        else:
            self.setStyleSheet("")

    def update_color(self, color: str):
        """Update count label color (neutral theme color); username re-reads from cache."""
        self.count_label.setStyleSheet(f"color: {color};")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.clicked.emit(self.username, ctrl_pressed)
        super().mousePressEvent(event)
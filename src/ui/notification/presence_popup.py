"""Compact presence (join/left/game) popup."""

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from components.avatar import make_avatar_label, make_avatar_pixmap
from components.presence_badge import make_game_id_label, make_presence_badge
from helpers.data import get_resource_dir
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import tr
from ui.notification.auto_hide_popup import AutoHidePopupMixin
from ui.notification.notification_settings import (
    NOTIFICATION_DURATION_MS_DEFAULT,
    resolve_margin_spacing,
)
from ui.notification.popup_helpers import (
    icon_btn,
    safe_call,
    setup_popup_window,
)


class PresenceMiniPopup(AutoHidePopupMixin, QWidget):
    """Compact join/left notification — same chrome/hover rules as PopupNotification."""

    def __init__(self, manager, login: str, event_type: str = 'join', avatar_pixmap=None,
                 config=None, duration_ms: int = NOTIFICATION_DURATION_MS_DEFAULT, on_click=None, event_ts=None,
                 cache=None, game_id=None, force_duration: bool = False):
        super().__init__()
        self.manager = manager
        self.config = config
        self.reply_field_visible = False
        self.is_hovered = False
        self.cursor_moved = False
        self.cursor_check_timer = None
        self.initial_cursor_pos = QCursor.pos()
        self.data = None
        self.on_click = on_click
        self.event_ts = event_ts
        self.login = login
        self.event_type = event_type
        self.duration = duration_ms
        self.hide_timer = None
        self._force_duration = force_duration
        self.icons_path = get_resource_dir("icons")

        setup_popup_window(self)

        margin, spacing = resolve_margin_spacing(config)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)

        AVATAR_SIZE = 36
        SVG_AVATAR_SIZE = 24

        avatar = make_avatar_label(AVATAR_SIZE)
        avatar.setPixmap(make_avatar_pixmap(self.icons_path, avatar_pixmap, AVATAR_SIZE, SVG_AVATAR_SIZE))
        layout.addWidget(avatar)

        ts = QLabel(datetime.now().strftime("%H:%M:%S"))
        ts.setFont(get_font(FontType.TEXT))
        ts.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        ts.setStyleSheet("color: #888;")
        layout.addWidget(ts)

        is_dark = (config.get("ui", "theme") == "dark") if config else True
        layout.addWidget(make_presence_badge(event_type, is_dark=is_dark))

        gid = make_game_id_label(event_type, game_id)
        if gid is not None:
            layout.addWidget(gid)

        name = QLabel(f"<b>{login}</b>")
        name.setFont(get_font(FontType.TEXT))
        name.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if cache is not None:
            username_color = cache.get_username_color(login, is_dark)
        else:
            username_color = "#AAAAAA"
        name.setStyleSheet(f"color: {username_color}; background: transparent;")
        layout.addWidget(name, stretch=1)

        self.close_button = icon_btn(self.icons_path, "close.svg", tr("Close", "Закрыть"), config)
        self.close_button.clicked.connect(self.manager.close_all)
        layout.addWidget(self.close_button)

        self.adjustSize()
        self.setFixedHeight(max(AVATAR_SIZE + margin * 2, self.sizeHint().height()))
        self.setMinimumWidth(min(360, self.sizeHint().width() + 20))

        self.setWindowOpacity(0.0)
        self.show()
        QTimer.singleShot(0, self.animate_in)
        self.start_cursor_monitoring()

    def self_hides_after_duration(self) -> bool:
        return self._force_duration

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.childAt(event.pos()) is self.close_button:
                return super().mousePressEvent(event)
            if self.on_click:
                safe_call(self.on_click, err_msg="Presence notification click")
            self.manager.close_all()
            return
        super().mousePressEvent(event)

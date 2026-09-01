"""Full room pane. Used as a tab page for both game/competition rooms and custom rooms."""
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal

from helpers.create import create_icon_button, HoverIconButton
from helpers.fonts import get_font, FontType, get_userlist_width
from helpers.font_scaler import FontScaleSlider
from helpers.translate import tr, on_language_changed, TranslatableMixin
from ui.ui_messages import MessagesWidget
from ui.ui_userlist import UserListWidget
from core.xmpp import XMPPClient


class RoomWidget(TranslatableMixin, QWidget):
    """Self-contained chat for one MUC room — either a gameXXXX@conference
    game/competition room or a custom room.
    Layout matches the main general chat body:
    """
    send_requested = pyqtSignal(str)
    profile_requested = pyqtSignal(str, str, str)
    private_chat_requested = pyqtSignal(str, str, str)
    paste_requested = pyqtSignal(str)
    open_game_requested = pyqtSignal(str)
    track_requested = pyqtSignal(str, str, bool)
    ban_requested = pyqtSignal(str, str, str, bool, object)
    pronunciation_requested = pyqtSignal(str)
    emoticon_requested = pyqtSignal()
    username_left_clicked = pyqtSignal(str, bool)
    username_right_clicked = pyqtSignal(object, object)
    username_ctrl_clicked = pyqtSignal(str)
    username_shift_clicked = pyqtSignal(str)

    def __init__(
        self,
        config,
        emoticon_manager,
        icons_path: Path,
        account=None,
        ban_manager=None,
        user_tracker=None,
        game_id=None,
        room_name: str = None,
        room_label: str = "Game",
        font_scaler=None,
        parent=None,
    ):
        super().__init__(parent)
        self._init_translatable()
        self.config = config
        self.emoticon_manager = emoticon_manager
        self.icons_path = icons_path
        self.account = account
        self.ban_manager = ban_manager
        self.user_tracker = user_tracker
        self.game_id = game_id
        self.room_name = (room_name or "").strip().lower() or None
        if self.room_name:
            self.room_label = room_label if room_label and room_label != "Game" else self.room_name
            self.room_jid = XMPPClient.custom_room_jid(self.room_name)
        else:
            self.room_label = room_label  # "Game" or "Competition" — cosmetic, set once at open time
            self.room_jid = XMPPClient.game_room_jid(game_id) if game_id else None
        self.font_scaler = font_scaler
        self.auto_hide_userlist = True  # reset to True whenever the compact threshold is crossed
        self._init_ui()
        on_language_changed(self._retranslate_all)

    @property
    def my_username(self):
        return (self.account or {}).get("chat_username") or None

    def _init_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        self.setLayout(root)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(self.config.get("ui", "spacing", "widget_content") or 6)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)

        self.messages_widget = MessagesWidget(
            self.config, self.emoticon_manager, my_username=self.my_username
        )
        self.messages_widget.username_left_clicked.connect(self.username_left_clicked.emit)
        self.messages_widget.username_right_clicked.connect(self.username_right_clicked.emit)
        self.messages_widget.username_ctrl_clicked.connect(self.username_ctrl_clicked.emit)
        self.messages_widget.username_shift_clicked.connect(self.username_shift_clicked.emit)
        left.addWidget(self.messages_widget, stretch=1)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(self.config.get("ui", "buttons", "spacing") or 8)

        self.input_field = QLineEdit()
        self.input_field.setFont(get_font(FontType.TEXT))
        self.input_field.setFixedHeight(48)
        self.input_field.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input_field, stretch=1)

        self.send_button = create_icon_button(
            self.icons_path, "send.svg", "", size_type="large", config=self.config
        )
        self._tr_set(self.send_button.setToolTip, "Send message", "Отправить сообщение")
        self.send_button.clicked.connect(self._on_send)
        input_row.addWidget(self.send_button)

        self.emoticon_button = HoverIconButton(
            self.icons_path,
            "emotion-normal.svg",
            "emotion-happy.svg",
            "",
        )
        self._tr_set(self.emoticon_button.setToolTip, "Toggle Emoticon Selector", "Селектор эмотиконов")
        self.emoticon_button.clicked.connect(self.emoticon_requested.emit)
        input_row.addWidget(self.emoticon_button)

        left.addLayout(input_row)
        body.addLayout(left, stretch=3)

        # Right column: userlist + font slider (same layout as general chat)
        self.userlist_panel = QWidget()
        ul_layout = QVBoxLayout()
        ul_layout.setContentsMargins(0, 0, 0, 0)
        ul_layout.setSpacing(4)

        self.user_list_widget = UserListWidget(
            self.config, input_field=self.input_field, ban_manager=self.ban_manager,
            user_tracker=self.user_tracker, my_username=self.my_username
        )
        self.user_list_widget.profile_requested.connect(self.profile_requested.emit)
        self.user_list_widget.private_chat_requested.connect(self.private_chat_requested.emit)
        self.user_list_widget.paste_requested.connect(self.paste_requested.emit)
        self.user_list_widget.open_game_requested.connect(self.open_game_requested.emit)
        self.user_list_widget.track_requested.connect(self.track_requested.emit)
        self.user_list_widget.ban_requested.connect(self.ban_requested.emit)
        self.user_list_widget.pronunciation_requested.connect(self.pronunciation_requested.emit)
        ul_layout.addWidget(self.user_list_widget, stretch=1)

        if self.font_scaler is not None:
            self.font_scale_slider = FontScaleSlider(self.font_scaler)
            self.font_scale_slider.setFixedHeight(self.input_field.minimumHeight())
            ul_layout.addWidget(self.font_scale_slider)
            self.font_scaler.font_size_committed.connect(
                lambda: self.userlist_panel.setFixedWidth(get_userlist_width())
            )
        else:
            self.font_scale_slider = None

        self.userlist_panel.setLayout(ul_layout)
        self.userlist_panel.setFixedWidth(get_userlist_width())
        body.addWidget(self.userlist_panel)

        root.addLayout(body, stretch=1)

    def tab_title(self) -> str:
        if self.room_name:
            return self.room_label
        return f"{self.room_label} #{self.game_id}" if self.game_id else self.room_label

    def _on_send(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.send_requested.emit(text)

    def set_game_id(self, game_id):
        self.game_id = game_id
        self.room_jid = XMPPClient.game_room_jid(game_id)
        self.messages_widget.clear()
        self.user_list_widget.clear_all()

    def add_message(self, msg):
        self.messages_widget.add_message(msg)

    def add_users(self, users=None, presence=None, bulk=False):
        self.user_list_widget.add_users(users=users, presence=presence, bulk=bulk)

    def remove_users(self, jids=None, presence=None):
        self.user_list_widget.remove_users(jids=jids, presence=presence)

    def update_theme(self):
        self.messages_widget.update_theme()
        self.user_list_widget.update_theme()

    def set_compact_mode(self, compact: bool):
        """Mirror the main chat's compact-width behaviour, which the central
        resize handler doesn't know about since room tabs live outside it:
        shrink the message layout and, unless the user pinned it open here,
        hide this room's own userlist to free up space."""
        self.messages_widget.set_compact_mode(compact)
        if self.auto_hide_userlist:
            self.userlist_panel.setVisible(not compact)

    def toggle_userlist(self) -> bool:
        """Manually show/hide this room's userlist; pins the choice so the
        next resize's auto-hide doesn't immediately override it."""
        visible = not self.userlist_panel.isVisible()
        self.userlist_panel.setVisible(visible)
        self.auto_hide_userlist = False
        return visible

    def cleanup(self):
        if hasattr(self, "messages_widget") and self.messages_widget:
            self.messages_widget.cleanup()
        if hasattr(self, "user_list_widget") and self.user_list_widget:
            self.user_list_widget.cleanup()
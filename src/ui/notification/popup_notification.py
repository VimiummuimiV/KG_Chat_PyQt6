"""Message popup with reply, mute and room actions."""

import threading
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QEasingCurve, QEvent, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QCursor, QFontMetrics
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from components.avatar import apply_user_avatar, make_avatar_label, make_avatar_pixmap
from components.button import get_user_svg_color, set_button_icon
from components.input_row import InputRow
from core.xmpp.messages import Message
from helpers.colors.color_utils import get_game_message_colors
from helpers.data import get_resource_dir
from helpers.fonts.fonts import FontType, get_font
from helpers.input_style import resolve_input_style
from helpers.translate import tr
from ui.chat.ui_emoticon_selector import release_selector
from ui.messages.message_renderer import MessageRenderer
from ui.notification.auto_hide_popup import AutoHidePopupMixin
from ui.notification.message_body import MessageBodyWidget
from ui.notification.notification_data import NotificationData
from ui.notification.notification_settings import (
    expanded_reply_width,
    resolve_centered_style,
    resolve_fade_ms,
    resolve_margin_spacing,
)
from ui.notification.popup_helpers import (
    icon_btn,
    safe_call,
    setup_popup_window,
)


class PopupNotification(AutoHidePopupMixin, QWidget):

    def __init__(self, data: NotificationData, manager, width: int):
        super().__init__()
        self.data = data
        self.manager = manager
        self.config = data.config
        self.duration = data.duration
        self.is_hovered = False
        self.cursor_moved = False
        self.initial_cursor_pos = QCursor.pos()
        self.hide_timer = None
        self.cursor_check_timer = None
        self.reply_field_visible = False
        self._message_widget = None
        self.icons_path = get_resource_dir("icons")
        self.base_width = width
        self._width_anim = None

        # Window setup
        setup_popup_window(self)

        # Get spacing/margin from config
        self.margin, self.spacing = resolve_margin_spacing(data.config)
        margin = self.margin
        spacing = self.spacing

        # Determine theme
        is_dark = data.config.get("ui", "theme") == "dark" if data.config else True
        self.is_dark = is_dark

        # Initialize MessageRenderer
        self.message_renderer = MessageRenderer(
            data.config,
            data.emoticon_manager,
            is_dark,
            parent_widget=self
        )

        # Set username for mention highlighting
        my_username = data.account.get('chat_username') if data.account else None
        if my_username:
            self.message_renderer.set_my_username(my_username)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(margin, margin, margin, margin)
        main_layout.setSpacing(0)

        # TOP ROW: Username (left) + Buttons (right)
        top_row = QHBoxLayout()
        top_row.setSpacing(0)
        top_row.setContentsMargins(0, 0, 0, 0)

        # Source accent
        kind = data.source_label
        if not kind and data.is_competition:
            kind = "competition"
        if kind == "competition":
            accent = self.message_renderer.competition_colors["text"]
        elif kind == "game":
            accent = get_game_message_colors(data.config, is_dark)["text"]
        else:
            accent = None

        # Title
        if data.is_competition:
            username_color = accent
        elif data.is_parser:
            username_color = self.message_renderer.parser_colors["text"]
        elif data.is_system:
            username_color = self.message_renderer.system_colors["text"]
        elif data.cache:
            username_color = data.cache.get_username_color(data.title, is_dark)
        else:
            username_color = "#AAAAAA"
        self.username_label = QLabel(f"<b>{data.title}</b>")
        self.username_label.setStyleSheet(f"color: {username_color};")
        self.username_label.setFont(get_font(FontType.TEXT))
        self.username_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if data.profile_callback and not data.is_parser and not data.is_competition:
            self.username_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Timestamp
        ts_str = (data.timestamp or datetime.now()).strftime("%H:%M:%S")
        self._timestamp_label = QLabel(ts_str)
        if accent:
            ts_color = accent
        else:
            ts_color = self.message_renderer.get_timestamp_color(
                data.is_ban, data.is_private, data.is_system, data.is_competition, data.is_parser
            )
        self._timestamp_label.setStyleSheet(f"color: {ts_color};")
        self._timestamp_label.setFont(get_font(FontType.TEXT))
        self._timestamp_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Avatar label - shown before timestamp for non-system messages
        AVATAR_SIZE = 36
        SVG_AVATAR_SIZE = 24

        self.avatar_label = make_avatar_label(AVATAR_SIZE)

        avatar_pixmap = None
        if data.is_parser:
            color = self.message_renderer.parser_colors["text"]
            avatar_pixmap = make_avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, "line/at-line.svg")
        elif data.is_competition:
            color = self.message_renderer.competition_colors["text"]
            avatar_pixmap = make_avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, "fill/trophy-fill.svg")
        elif data.is_system:
            color = self.message_renderer.system_colors["text"]
            avatar_pixmap = make_avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, "line/information-line.svg")
        elif not data.is_system and data.cache:
            apply_user_avatar(
                self.avatar_label, data.cache.get_user_id(data.title), AVATAR_SIZE, SVG_AVATAR_SIZE, is_dark,
                self.icons_path,
            )
        elif not data.is_system and data.icon:
            color = get_user_svg_color(False, is_dark)
            avatar_pixmap = make_avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, data.icon)

        if avatar_pixmap:
            self.avatar_label.setPixmap(avatar_pixmap)

        if avatar_pixmap or (not data.is_system and not data.is_parser):
            top_row.addWidget(self.avatar_label, stretch=0)
            top_row.addSpacing(self.spacing)

        top_row.addWidget(self._timestamp_label, stretch=0)
        if not data.is_system:
            top_row.addSpacing(self.spacing)
            top_row.addWidget(self.username_label, stretch=0)

        top_row.addStretch(1)

        # Buttons container (right side)
        button_spacing = data.config.get("ui", "buttons", "spacing") if data.config else 8
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(button_spacing)
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        # Position toggle button
        current_position = data.config.get("ui", "notification_position") if data.config else "right"
        position_icons = {"left": "line/align-left-line.svg", "center": "line/align-center-line.svg", "right": "line/align-right-line.svg"}
        self._position_button = icon_btn(
            self.icons_path, position_icons.get(current_position or "right", "line/align-right-line.svg"),
            tr("Change Position", "Сменить расположение"), data.config
        )
        self._position_button.clicked.connect(self._on_toggle_position)
        buttons_layout.addWidget(self._position_button)

        # Answer button - hide for ban, system, competition, parser messages
        if not data.is_ban and not data.is_system and not data.is_parser and not data.is_competition:
            self._answer_button = icon_btn(self.icons_path, "fill/reply-fill.svg", tr("Reply", "Ответить"), data.config)
            self._answer_button.clicked.connect(self._on_answer)
            buttons_layout.addWidget(self._answer_button)
        else:
            self._answer_button = None

        if data.is_competition and data.open_room_callback and data.competition_game_id is not None:
            self._open_room_button = icon_btn(self.icons_path, "fill/chat-1-fill.svg", tr("Open competition room", "Открыть комнату соревнования"), data.config)
            self._open_room_button.clicked.connect(self._on_open_room)
            buttons_layout.addWidget(self._open_room_button)
        else:
            self._open_room_button = None

        # Mute button
        self._mute_button = icon_btn(self.icons_path, "line/shut-down-line.svg", tr("Mute Notifications", "Отключить уведомления"), data.config)
        self._mute_button.clicked.connect(self._on_mute)
        buttons_layout.addWidget(self._mute_button)

        # Close button
        self.close_button = icon_btn(self.icons_path, "line/close-large-line.svg", tr("Close", "Закрыть"), data.config)
        self.close_button.clicked.connect(self.manager.close_all)
        buttons_layout.addWidget(self.close_button)

        top_row.addLayout(buttons_layout)
        main_layout.addLayout(top_row)

        # Elide username if it doesn't fit next to the buttons
        if not data.is_system:
            other_width = top_row.sizeHint().width() - self.username_label.sizeHint().width()
            available_width = self.base_width - 2 * margin - other_width
            bold_font = self.username_label.font()
            bold_font.setBold(True)
            elided_title = QFontMetrics(bold_font).elidedText(
                data.title, Qt.TextElideMode.ElideRight, max(available_width, 0)
            )
            self.username_label.setText(f"<b>{elided_title}</b>")
            if elided_title != data.title:
                self.username_label.setToolTip(data.title)

        # MIDDLE ROW: Message body
        msg_container = QWidget()
        msg_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        msg_layout = QVBoxLayout(msg_container)
        msg_layout.setContentsMargins(spacing, spacing, spacing, spacing)
        msg_layout.setSpacing(0)
        self._message_widget = MessageBodyWidget(
            self.message_renderer,
            data.message,
            data.is_private,
            data.is_ban,
            data.is_system,
            data.is_competition,
            data.is_parser,
            data.players,
        )
        self._message_widget.content_resized.connect(self._on_content_resized)
        msg_layout.addWidget(self._message_widget)
        main_layout.addWidget(msg_container, stretch=1)

        # BOTTOM ROW: Reply field - hide for ban and system messages
        # Initialize emoticon attributes for all cases
        self.emoticon_selector = None
        self.emoticon_button = None

        if not data.is_ban and not data.is_system and not data.is_parser:
            self._reply_container = InputRow(self.icons_path, data.config, with_emoticons=bool(data.emoticon_manager))
            self._reply_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self._reply_container.submitted.connect(self._on_send_reply)
            self._reply_container.emoticon_requested.connect(self._toggle_emoticon_selector)
            self._reply_field = self._reply_container.input_field
            self._reply_field.installEventFilter(self)
            self.send_button = self._reply_container.send_button
            self.emoticon_button = self._reply_container.emoticon_button
            self._reply_container.setVisible(False)
            main_layout.addWidget(self._reply_container, stretch=0)
        else:
            self._reply_container = None
            self._reply_field = None
            self.send_button = None

        # Set fixed width and adjust size
        self.setFixedWidth(width)
        self.adjustSize()

        # Initialize opacity and show
        self.setWindowOpacity(0.0)
        self.show()
        QTimer.singleShot(0, self.animate_in)
        self.start_cursor_monitoring()

    def update_message(self, text: str, players: Optional[list] = None):
        """Update the body text (and player chips) in place, no new popup created."""
        if self._message_widget:
            self._message_widget.update_content(text, players)

    def _on_content_resized(self):
        """Body grew/shrank (e.g. player roster changed) - resize and reflow the stack."""
        self.adjustSize()
        self.manager.position_and_cleanup()

    def mousePressEvent(self, event):
        """Handle clicks: buttons, links, or show window"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is on a button
            clicked_widgets = [self.close_button, self._mute_button, self._position_button]
            if self._answer_button:
                clicked_widgets.append(self._answer_button)
            if self._open_room_button:
                clicked_widgets.append(self._open_room_button)
            if self.send_button:
                clicked_widgets.append(self.send_button)
            if self.emoticon_button:
                clicked_widgets.append(self.emoticon_button)

            if self.childAt(event.pos()) in clicked_widgets:
                return super().mousePressEvent(event)

            # Username in the header - opens profile (skip synthetic titles: system/parser/competition)
            if (self.childAt(event.pos()) is self.username_label and self.data.profile_callback
                    and not self.data.is_parser and not self.data.is_competition):
                safe_call(self.data.window_show_callback, err_msg="Error showing window")
                safe_call(self.data.profile_callback, self.data.title, err_msg="Profile from notification username")
                return

            # Chip / link clicks in message body
            if self._message_widget:
                widget_pos = self._message_widget.mapFrom(self, event.pos())
                if self._message_widget.rect().contains(widget_pos):
                    chip_name = self._message_widget.get_chip_at_pos(widget_pos)
                    if chip_name and self.data.profile_callback:
                        if self.data.window_show_callback:
                            try:
                                self.data.window_show_callback()
                            except Exception:
                                pass
                        safe_call(self.data.profile_callback, chip_name, err_msg="Profile from notification chip")
                        return
                    link_data = self._message_widget.get_link_at_pos(widget_pos)
                    if link_data:
                        url, is_media = link_data
                        global_pos = self.mapToGlobal(event.pos())
                        is_ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
                        is_shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                        self.message_renderer.handle_link_lmb(url, is_media, global_pos, is_ctrl, is_shift)
                        if self.data.is_competition and self.data.competition_game_id is not None:
                            safe_call(self.data.competition_entered_callback, self.data.competition_game_id,
                                       err_msg="Competition entered callback")
                        return

            # Show chat window if callback exists
            safe_call(self.data.window_show_callback, err_msg="Error showing window")

            self.manager.close_all()
        elif event.button() == Qt.MouseButton.RightButton:
            if self._message_widget:
                widget_pos = self._message_widget.mapFrom(self, event.pos())
                if self._message_widget.rect().contains(widget_pos):
                    link_data = self._message_widget.get_link_at_pos(widget_pos)
                    if link_data:
                        self.message_renderer.handle_link_rmb(link_data[0])
                        return
            super().mousePressEvent(event)
        elif event.button() == Qt.MouseButton.MiddleButton:
            if self._answer_button and self._message_widget:
                widget_pos = self._message_widget.mapFrom(self, event.pos())
                if self._message_widget.rect().contains(widget_pos):
                    self._on_answer()
                    return
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def _release_emoticon_selector(self):
        """Remove the borrowed selector from this popup's layout and release ownership."""
        sel = self.manager.emoticon_selector
        if sel and sel.parent() is self:
            release_selector(sel)

    def cleanup_widgets(self):
        """Cleanup widgets on close - release borrowed selector without destroying it"""
        self._release_emoticon_selector()
        if self._message_widget:
            self._message_widget.cleanup()

    def _on_open_room(self):
        gid = self.data.competition_game_id
        safe_call(self.data.window_show_callback, err_msg="Error showing window")
        if gid is not None:
            safe_call(self.data.open_room_callback, gid, err_msg="Error opening room")
        self.manager.close_all()

    def _reply_style(self) -> str:
        """notification.reply_style: inline (default) | center."""
        return resolve_centered_style(self.config, "notification", "reply_style")

    def eventFilter(self, obj, event):
        """Widen the popup while the reply field is focused (centered mode only),
        and shrink it back to base_width on focus loss."""
        if obj is self._reply_field:
            if event.type() == QEvent.Type.FocusIn:
                self.animate_width(self._focused_width())
            elif event.type() == QEvent.Type.FocusOut:
                self.animate_width(self.base_width)
        return super().eventFilter(obj, event)

    def _focused_width(self) -> int:
        """Target width while typing a reply. Never narrower than base_width."""
        if self._reply_style() != "center":
            return self.base_width
        screen = self.screen().availableGeometry() if self.screen() else QApplication.primaryScreen().availableGeometry()
        return expanded_reply_width(self.config, self.base_width, screen.width())

    def animate_width(self, target: int):
        if self._width_anim is not None:
            self._width_anim.stop()
        if self.width() == target:
            return
        anim = QVariantAnimation(self)
        anim.setDuration(resolve_fade_ms(self.config))
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(self.width())
        anim.setEndValue(target)
        anim.valueChanged.connect(lambda v: (self.setFixedWidth(int(v)), self.manager.position_and_cleanup()))
        anim.start()
        self._width_anim = anim

    def _apply_reply_style(self):
        """Same input look as the chat: private recipient, own ban, regular."""
        if not self.config:
            return
        ban_callback = self.data.self_ban_placeholder_callback
        sheet, placeholder = resolve_input_style(
            self.config, self.is_dark,
            self.data.title if self.data.is_private else None,
            ban_callback() if ban_callback else None,
        )
        self._reply_field.setStyleSheet(sheet)
        self._reply_field.setPlaceholderText(placeholder)

    def _on_answer(self):
        """Toggle reply field visibility. In 'center' reply_style, the popup
        also detaches from its stack and joins the centered focus group."""
        if not self._reply_container or not self._reply_field:
            return

        # Toggle behavior
        if self.reply_field_visible:
            # Hide reply field
            self.reply_field_visible = False
            self._reply_field.clearFocus()
            self._reply_container.setVisible(False)
            self._reply_field.clear()
            if self in self.manager.focused_popups:
                self.manager.focused_popups.remove(self)
                self.manager.popups.append(self)

            # Re-enable auto-close if cursor moved and not hovering
            if self.cursor_moved and not self.is_hovered:
                self.start_hide_timer()
        else:
            # Show reply field
            self.reply_field_visible = True
            self._reply_container.setVisible(True)
            self._apply_reply_style()
            if self._reply_style() == "center" and self in self.manager.popups:
                self.manager.popups.remove(self)
                self.manager.focused_popups.append(self)

            # Pre-fill with sender's username
            self._reply_field.setText(f"{self.data.title}, ")
            self._reply_field.setFocus()
            self._reply_field.setCursorPosition(len(self._reply_field.text()))

            # Stop hide timers
            if self.hide_timer and self.hide_timer.isActive():
                self.hide_timer.stop()
            if self.cursor_check_timer and self.cursor_check_timer.isActive():
                self.cursor_check_timer.stop()

        # Recalculate size with reply field visible/hidden
        self.adjustSize()
        self.manager.position_and_cleanup()

    def self_hides_after_duration(self) -> bool:
        return bool(self.data.auto_hide_after_duration)

    def _on_mute(self):
        """Mute notifications and close all popups"""
        self.manager.set_muted(True)

        if self.data.config:
            self.data.config.set("notification", "muted", value=True)

        self.manager.close_all()
        print("🔇 Notifications muted")

    def _on_toggle_position(self):
        """Cycle notification position left → center → right and reposition in realtime"""
        cycle = {"left": "center", "center": "right", "right": "left"}
        icons = {"left": "line/align-left-line.svg", "center": "line/align-center-line.svg", "right": "line/align-right-line.svg"}
        current = self.data.config.get("ui", "notification_position") or "right"
        new_pos = cycle.get(current, "right")
        self.data.config.set("ui", "notification_position", value=new_pos)
        # Update icon on all popup position buttons for consistency
        for popup in self.manager.popups:
            if hasattr(popup, '_position_button'):
                set_button_icon(popup._position_button, icons[new_pos])
        self.manager.position_and_cleanup()

    def _toggle_emoticon_selector(self):
        """Toggle the shared emoticon selector - borrow from ChatWindow or release it."""
        sel = self.manager.emoticon_selector
        if sel is None:
            return  # ChatWindow not open yet; nothing to borrow

        if sel.parent() is self:
            self._release_emoticon_selector()
        else:
            sel.attach(self, self._on_emoticon_selected, self.layout(), self.spacing)

        self.emoticon_selector = sel
        self.adjustSize()
        self.manager.position_and_cleanup()

    def _on_emoticon_selected(self, emoticon_name: str):
        """Insert emoticon into reply field"""
        if self._reply_container:
            self._reply_container.insert_emoticon(emoticon_name)

    def _on_send_reply(self, text: str):
        """Send reply message"""
        if not self.data.xmpp_client:
            return

        # room_jid routes the reply to its room; without it send_message falls back to General
        msg_type = 'chat' if self.data.is_private and self.data.recipient_jid else 'groupchat'
        to_jid = self.data.recipient_jid if msg_type == 'chat' else self.data.room_jid

        # Add message locally to UI
        if self.data.local_message_callback and self.data.account:
            try:

                effective_bg = self.data.account.get('custom_background') or self.data.account.get('background')

                own_msg = Message(
                    from_jid=self.data.xmpp_client.jid,
                    body=text,
                    msg_type=msg_type,
                    login=self.data.account.get('chat_username'),
                    avatar=self.data.account.get('avatar'),
                    background=effective_bg,
                    timestamp=datetime.now(),
                    initial=False
                )

                own_msg.is_private = (msg_type == 'chat')
                own_msg.is_system = False

                self.data.local_message_callback(own_msg)
            except Exception as e:
                print(f"❌ Error adding local message: {e}")

        def _send():
            try:
                if not self.data.xmpp_client.send_message(text, to_jid, msg_type):
                    print(f"❌ Failed to send reply: {text}")
            except Exception as e:
                print(f"❌ Error sending reply: {e}")

        threading.Thread(target=_send, daemon=True).start()
        QTimer.singleShot(100, self.on_close)

    def wheelEvent(self, event):
        """Scroll through the notification stack in scroll mode"""
        if self.manager.notification_mode == "scroll":
            self.manager.scroll_by(event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

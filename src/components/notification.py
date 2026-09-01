"""Popup notification system with persistent reply support"""
from dataclasses import dataclass
from typing import List, Callable, Optional, Any, Tuple
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QVariantAnimation, QEasingCurve, QEvent, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QCursor, QPixmap
from pathlib import Path
from datetime import datetime
import threading

from helpers.translate import tr
from helpers.create import create_icon_button, HoverIconButton, _render_svg_icon, get_user_svg_color
from helpers.load import make_rounded_pixmap
from helpers.fonts import get_font, FontType
from components.presence_badge import make_presence_badge, make_game_id_label
from helpers.input_activity import activity_detected
from helpers.color_utils import get_game_message_colors
from ui.message_renderer import MessageRenderer
from ui.ui_emoticon_selector import release_selector


NOTIFICATION_DEFAULT_WIDTH = 550
FADE_DURATION_MS_DEFAULT = 300
NOTIFICATION_DURATION_MS_DEFAULT = 5000
REPLY_FOCUS_WIDTH_EXPAND_DEFAULT = 200


def _resolve_focus_expand_width(config=None) -> int:
    """Extra px added to popup width on reply focus, from
    config('notification', 'reply_focus_expand_width')."""
    if config is not None:
        value = config.get("notification", "reply_focus_expand_width")
        if value is not None:
            try:
                return max(0, min(600, int(value)))
            except (TypeError, ValueError):
                pass
    return REPLY_FOCUS_WIDTH_EXPAND_DEFAULT


def _resolve_fade_ms(config=None) -> int:
    if config is not None:
        value = config.get("notification", "fade_ms")
        if value is not None:
            try:
                return max(50, min(2000, int(value)))
            except (TypeError, ValueError):
                pass
    return FADE_DURATION_MS_DEFAULT


def _resolve_duration_ms(config=None) -> int:
    """Auto-hide duration in ms, from config('notification', 'duration_ms')."""
    if config is not None:
        value = config.get("notification", "duration_ms")
        if value is not None:
            try:
                return max(1000, int(value))
            except (TypeError, ValueError):
                pass
    return NOTIFICATION_DURATION_MS_DEFAULT


def _mute_bypass_mode(config, key: str) -> str:
    """Read notification.*_bypass_mute: off | default | duration."""
    if not config:
        return "off"
    value = config.get("notification", key)
    return value if value in ("default", "duration") else "off"


def _apply_mute_bypass(data: "NotificationData", muted: bool, key: str) -> bool:
    """Return True if notification may show. Sets auto_hide_after_duration on data."""
    mode = _mute_bypass_mode(data.config, key)
    if mode == "off":
        return not muted
    if mode == "duration":
        data.auto_hide_after_duration = True
    return True


def _fade_opacity(widget, start: float, end: float, on_finished=None, duration_ms=None):
    """Shared windowOpacity animation for notification popups."""
    if duration_ms is None:
        cfg = getattr(widget, "config", None)
        if cfg is None:
            data = getattr(widget, "data", None)
            cfg = getattr(data, "config", None) if data is not None else None
        if cfg is None:
            manager = getattr(widget, "manager", None)
            cfg = getattr(manager, "config", None) if manager is not None else None
        duration_ms = _resolve_fade_ms(cfg)
    anim = QPropertyAnimation(widget, b"windowOpacity")
    anim.setDuration(int(duration_ms))
    anim.setStartValue(start)
    anim.setEndValue(end)
    if on_finished is not None:
        anim.finished.connect(on_finished)
    anim.start()
    return anim


def _hold_all_popups(manager):
    """Stop hide timers / fade-outs and restore full opacity on the whole stack."""
    for p in manager.popups:
        if getattr(p, "hide_timer", None) and p.hide_timer.isActive():
            p.hide_timer.stop()
        fade = getattr(p, "fade_out", None)
        if fade is not None and fade.state() == QPropertyAnimation.State.Running:
            fade.stop()
        p.setWindowOpacity(1.0)


def _resume_all_hide_timers(manager):
    """Restart auto-hide on every popup when none are hovered."""
    if any(getattr(p, "is_hovered", False) for p in manager.popups):
        return
    for p in manager.popups:
        if getattr(p, "cursor_moved", False) and not getattr(p, "reply_field_visible", False):
            start = getattr(p, "_start_hide_timer", None)
            if start:
                start()


def _setup_popup_window(widget):
    """Frameless, always-on-top, click-through-to-show popup chrome shared by all toasts."""
    widget.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.Tool |
        Qt.WindowType.WindowStaysOnTopHint
    )
    widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    widget.setMouseTracking(True)


def _paint_rounded_background(widget, radius: int = 10):
    """Shared rounded-rect background painter for popup widgets."""
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(widget.rect().toRectF(), radius, radius)
    painter.fillPath(path, widget.palette().window())
    painter.setPen(widget.palette().mid().color())
    painter.drawPath(path)


def _resolve_margin_spacing(config) -> Tuple[int, int]:
    """(margin, spacing) for popup layouts, from config with shared defaults."""
    margin = (config.get("ui", "margins", "notification") if config else None) or 8
    spacing = (config.get("ui", "spacing", "widget_elements") if config else None) or 4
    return margin, spacing


def _safe_call(fn, *args, err_msg: str = "Callback error"):
    """Invoke an optional callback, swallowing and logging any exception."""
    if fn is None:
        return
    try:
        fn(*args)
    except Exception as e:
        print(f"❌ {err_msg}: {e}")


def _svg_avatar_pixmap(icons_path, size: int, color=None, icon_name: str = "user.svg"):
    """Fallback icon pixmap rendered at the given size."""
    icon = _render_svg_icon(icons_path / icon_name, size, color) if color is not None \
        else _render_svg_icon(icons_path / icon_name, size)
    return icon.pixmap(QSize(size, size))


def _make_avatar_label(size: int = 36) -> QLabel:
    """Styled, fixed-size avatar placeholder shared by all popup layouts."""
    label = QLabel()
    label.setFixedSize(size, size)
    label.setStyleSheet("background: transparent; border: none; padding: 0; margin: 0;")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _avatar_pixmap(icons_path, raw_pixmap, size: int = 36, svg_size: int = 24, color=None, icon_name: str = "user.svg"):
    """Rounded real avatar if one is available, else the SVG fallback icon."""
    if raw_pixmap is not None and not raw_pixmap.isNull():
        return make_rounded_pixmap(raw_pixmap, size, 8)
    return _svg_avatar_pixmap(icons_path, svg_size, color, icon_name)

def _icon_btn(icons_path, icon_name: str, tooltip: str, config, size_type: str = "small"):
    """Shortcut for the repeated create_icon_button(icons_path, ..., config=config) calls."""
    return create_icon_button(icons_path, icon_name, tooltip, size_type=size_type, config=config)


def _resolve_centered_style(config, section: str, key: str) -> str:
    """Shared 'inline' | 'center' resolution for reply/competition placement.
    Falls back to inline when notifications are already centered — a detached
    centered group would sit on the same X as the regular stack and overlap it."""
    if not config:
        return "inline"
    if (config.get("ui", "notification_position") or "").lower() == "center":
        return "inline"
    value = config.get(section, key)
    return value if value == "center" else "inline"


@dataclass
class NotificationData:
    """Encapsulates all notification parameters to avoid code duplication"""
    title: str
    message: str
    duration: int = NOTIFICATION_DURATION_MS_DEFAULT
    xmpp_client: Optional[Any] = None
    cache: Optional[Any] = None
    config: Optional[Any] = None
    emoticon_manager: Optional[Any] = None
    local_message_callback: Optional[Callable] = None
    account: Optional[dict] = None
    window_show_callback: Optional[Callable] = None
    is_private: bool = False
    recipient_jid: Optional[str] = None
    room_jid: Optional[str] = None
    source_label: Optional[str] = None
    is_ban: bool = False
    is_system: bool = False
    is_parser: bool = False
    is_competition: bool = False
    is_mention: bool = False
    auto_hide_after_duration: bool = False
    timestamp: Optional[datetime] = None
    tag: Optional[str] = None
    players: Optional[list] = None
    competition_game_id: Optional[int] = None
    open_room_callback: Optional[Callable] = None
    profile_callback: Optional[Callable] = None  # username → open profile
    competition_entered_callback: Optional[Callable] = None  # game_id → remove chat message + close this notification
    icon: Optional[str] = None  # svg filename fallback avatar for non-user notifications


class MessageBodyWidget(QWidget):
    """Custom widget that uses MessageRenderer for painting message body"""

    content_resized = pyqtSignal()

    def __init__(self, message_renderer: MessageRenderer, text: str, 
                 is_private: bool = False, is_ban: bool = False, is_system: bool = False,
                 is_competition: bool = False, is_parser: bool = False,
                 players: Optional[list] = None):
        super().__init__()
        self.message_renderer = message_renderer
        self.text = MessageRenderer._emoji_prefix(text, is_private, is_ban, is_system, is_competition, is_parser)
        self.is_private = is_private
        self.is_ban = is_ban
        self.is_system = is_system
        self.is_competition = is_competition
        self.is_parser = is_parser
        self.players = players or []
        self.link_rects: List[Tuple[QRect, str, bool]] = []
        self.chip_rects: List[Tuple[QRect, str]] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        # Initial height estimate
        self.setFixedHeight(50)
        
        # Repaint when copy highlight clears
        self.message_renderer.refresh_view.connect(self.update)
        
        # Animation timer for animated emoticons (GIFs)
        self.animation_timer = None
        if self.message_renderer.has_animated_emoticons(text):
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self.update)  # Trigger repaint
            self.animation_timer.start(33)  # ~30 FPS

    def _calculate_height(self, width: int) -> int:
        height = self.message_renderer.calculate_content_height(self.text, width)
        if self.players:
            height += 6 + self.message_renderer.calculate_chips_height(self.players, width)
        return height

    def update_content(self, text: str, players: Optional[list] = None):
        """Update text and player chips in place, without recreating the notification."""
        self.text = MessageRenderer._emoji_prefix(text, self.is_private, self.is_ban, self.is_system,
                                                  self.is_competition, self.is_parser)
        if players is not None:
            self.players = players
        new_height = self._calculate_height(self.width() if self.width() > 0 else 400)
        if new_height != self.height():
            self.setFixedHeight(new_height)
            self.content_resized.emit()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Paint content and get link rectangles
        self.link_rects = self.message_renderer.paint_content(
            painter,
            0, 0,
            self.width(),
            self.text,
            None,  # row
            self.is_private,
            self.is_ban,
            self.is_system,
            self.is_competition,
            self.is_parser,
        )

        if self.players:
            content_height = self.message_renderer.calculate_content_height(self.text, self.width())
            _, self.chip_rects = self.message_renderer.paint_chips(
                painter, 0, content_height + 6, self.width(), self.players, self.message_renderer.is_dark_theme
            )
        else:
            self.chip_rects = []
        
        # Update height if needed
        calculated_height = self._calculate_height(self.width())
        if self.height() != calculated_height:
            self.setFixedHeight(calculated_height)
    
    def sizeHint(self):
        width = self.width() if self.width() > 0 else 400
        return QSize(width, self._calculate_height(width))
    
    def mouseMoveEvent(self, event):
        is_over_link = MessageRenderer.is_over_link(self.link_rects, event.pos())
        is_over_chip = any(r.contains(event.pos()) for r, name in self.chip_rects if name and name != "…")
        self.setCursor(QCursor(
            Qt.CursorShape.PointingHandCursor if (is_over_link or is_over_chip)
            else Qt.CursorShape.ArrowCursor
        ))
        super().mouseMoveEvent(event)
    
    def get_link_at_pos(self, pos) -> Optional[Tuple[str, bool]]:
        return MessageRenderer.get_link_at_pos(self.link_rects, pos)

    def get_chip_at_pos(self, pos) -> Optional[str]:
        for rect, name in self.chip_rects:
            if rect.contains(pos) and name and name != "…":
                return name
        return None
    
    def cleanup(self):
        """Cleanup animation timer"""
        if self.animation_timer:
            self.animation_timer.stop()
            self.animation_timer = None


class _AutoHidePopupMixin:
    """Shared hover/cursor-tracking/fade/hide-timer behavior for popup widgets.
    Host class must set: manager, config, duration, is_hovered, cursor_moved,
    reply_field_visible, initial_cursor_pos, hide_timer, cursor_check_timer."""

    def _self_hides_after_duration(self) -> bool:
        """Override to ignore hide_on and close purely after duration."""
        return False

    def _hide_on_mode(self) -> str:
        """notification.hide_on: manual | mouse | keyboard | mouse_keyboard (default)."""
        if self.config:
            mode = self.config.get("notification", "hide_on")
            if mode in ("manual", "mouse", "keyboard", "mouse_keyboard"):
                return mode
        return "mouse_keyboard"

    def _start_cursor_monitoring(self):
        """Monitor activity (per hide_on setting) to trigger auto-hide."""
        if self._self_hides_after_duration():
            self.cursor_moved = True
            self._start_hide_timer()
            return
        if self._hide_on_mode() == "manual":
            return
        self.cursor_check_timer = QTimer(self)
        self.cursor_check_timer.timeout.connect(self._check_cursor_movement)
        self.cursor_check_timer.start(100)

    def _check_cursor_movement(self):
        if self.cursor_moved or self.reply_field_visible:
            return
        if activity_detected(self.initial_cursor_pos, self._hide_on_mode()):
            self.cursor_moved = True
            self.cursor_check_timer.stop()
            self._start_hide_timer()

    def _start_hide_timer(self):
        if self.is_hovered or self.reply_field_visible:
            return
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._animate_out)
        self.hide_timer.start(self.duration)

    def _animate_in(self):
        self.fade_in = _fade_opacity(self, 0.0, 1.0)

    def _animate_out(self, force: bool = False):
        if self.reply_field_visible or (self.is_hovered and not force):
            return
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        self.fade_out = _fade_opacity(self, self.windowOpacity(), 0.0, self._on_close)

    def paintEvent(self, event):
        _paint_rounded_background(self)

    def enterEvent(self, event):
        self.is_hovered = True
        _hold_all_popups(self.manager)

    def leaveEvent(self, event):
        self.is_hovered = False
        _resume_all_hide_timers(self.manager)

    def _cleanup_widgets(self):
        """Override for widgets owning extra resources (e.g. emoticon selector)."""
        pass

    def close_immediately(self):
        """Close notification immediately without animation. Doesn't touch
        manager.popups - callers manage the list themselves."""
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        if self.cursor_check_timer and self.cursor_check_timer.isActive():
            self.cursor_check_timer.stop()
        fade = getattr(self, "fade_out", None)
        if fade is not None and fade.state() == QPropertyAnimation.State.Running:
            fade.stop()
        self._cleanup_widgets()
        self.close()

    def _on_close(self):
        self._cleanup_widgets()
        self.manager.remove_popup(self)
        self.close()
        self.deleteLater()


class PopupNotification(_AutoHidePopupMixin, QWidget):
  
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
        self.message_widget = None
        self.icons_path = Path(__file__).parent.parent / "icons"
        self.base_width = width
        self._width_anim = None
      
        # Window setup
        _setup_popup_window(self)
      
        # Get spacing/margin from config
        self.margin, self.spacing = _resolve_margin_spacing(data.config)
        margin = self.margin
        spacing = self.spacing
      
        # Determine theme
        is_dark = data.config.get("ui", "theme") == "dark" if data.config else True
        
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
        
        # Timestamp
        ts_str = (data.timestamp or datetime.now()).strftime("%H:%M:%S")
        self.timestamp_label = QLabel(ts_str)
        if accent:
            ts_color = accent
        else:
            ts_color = self.message_renderer.get_timestamp_color(
                data.is_ban, data.is_private, data.is_system, data.is_competition, data.is_parser
            )
        self.timestamp_label.setStyleSheet(f"color: {ts_color};")
        self.timestamp_label.setFont(get_font(FontType.TEXT))
        self.timestamp_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Avatar label - shown before timestamp for non-system messages
        AVATAR_SIZE = 36
        SVG_AVATAR_SIZE = 24

        self.avatar_label = _make_avatar_label(AVATAR_SIZE)

        avatar_pixmap = None
        if data.is_parser:
            color = self.message_renderer.parser_colors["text"]
            avatar_pixmap = _avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, "at-line.svg")
        elif data.is_competition:
            color = self.message_renderer.competition_colors["text"]
            avatar_pixmap = _avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, "trophy.svg")
        elif data.is_system:
            color = self.message_renderer.system_colors["text"]
            avatar_pixmap = _avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, "information.svg")
        elif not data.is_system and data.cache:
            user_id = data.cache.get_user_id(data.title)
            color = get_user_svg_color(data.cache.has_user(user_id), is_dark)
            cached_avatar = data.cache.get_avatar(user_id) if user_id else None
            if cached_avatar and not cached_avatar.isNull():
                avatar_pixmap = _avatar_pixmap(self.icons_path, cached_avatar, AVATAR_SIZE, SVG_AVATAR_SIZE, color, "user.svg")
            else:
                avatar_pixmap = _avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, "user.svg")
                if user_id and not cached_avatar:
                    data.cache.load_avatar_async(user_id, self._on_avatar_loaded)
        elif not data.is_system and data.icon:
            color = get_user_svg_color(False, is_dark)
            avatar_pixmap = _avatar_pixmap(self.icons_path, None, AVATAR_SIZE, SVG_AVATAR_SIZE, color, data.icon)

        if avatar_pixmap:
            self.avatar_label.setPixmap(avatar_pixmap)

        if avatar_pixmap or (not data.is_system and not data.is_parser):
            top_row.addWidget(self.avatar_label, stretch=0)
            top_row.addSpacing(self.spacing)

        top_row.addWidget(self.timestamp_label, stretch=0)
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
        position_icons = {"left": "align-left.svg", "center": "align-center.svg", "right": "align-right.svg"}
        self.position_button = _icon_btn(
            self.icons_path, position_icons.get(current_position or "right", "align-right.svg"),
            tr("Change Position", "Сменить расположение"), data.config
        )
        self.position_button.clicked.connect(self._on_toggle_position)
        buttons_layout.addWidget(self.position_button)

        # Answer button - hide for ban, system, competition, parser messages
        if not data.is_ban and not data.is_system and not data.is_parser and not data.is_competition:
            self.answer_button = _icon_btn(self.icons_path, "reply.svg", tr("Reply", "Ответить"), data.config)
            self.answer_button.clicked.connect(self._on_answer)
            buttons_layout.addWidget(self.answer_button)
        else:
            self.answer_button = None

        if data.is_competition and data.open_room_callback and data.competition_game_id is not None:
            self.open_room_button = _icon_btn(self.icons_path, "chat.svg", tr("Open competition room", "Открыть комнату соревнования"), data.config)
            self.open_room_button.clicked.connect(self._on_open_room)
            buttons_layout.addWidget(self.open_room_button)
        else:
            self.open_room_button = None
      
        # Mute button
        self.mute_button = _icon_btn(self.icons_path, "shut-down.svg", tr("Mute Notifications", "Отключить уведомления"), data.config)
        self.mute_button.clicked.connect(self._on_mute)
        buttons_layout.addWidget(self.mute_button)
      
        # Close button
        self.close_button = _icon_btn(self.icons_path, "close.svg", tr("Close", "Закрыть"), data.config)
        self.close_button.clicked.connect(self.manager.close_all)
        buttons_layout.addWidget(self.close_button)
      
        top_row.addLayout(buttons_layout)
        main_layout.addLayout(top_row)
      
        # MIDDLE ROW: Message body
        msg_container = QWidget()
        msg_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        msg_layout = QVBoxLayout(msg_container)
        msg_layout.setContentsMargins(spacing, spacing, spacing, spacing)
        msg_layout.setSpacing(0)
        self.message_widget = MessageBodyWidget(
            self.message_renderer,
            data.message,
            data.is_private,
            data.is_ban,
            data.is_system,
            data.is_competition,
            data.is_parser,
            data.players,
        )
        self.message_widget.content_resized.connect(self._on_content_resized)
        msg_layout.addWidget(self.message_widget)
        main_layout.addWidget(msg_container, stretch=1)
      
        # BOTTOM ROW: Reply field - hide for ban and system messages
        # Initialize emoticon attributes for all cases
        self.emoticon_selector = None
        self.emoticon_button = None
        
        if not data.is_ban and not data.is_system and not data.is_parser:
            self.reply_container = QWidget()
            self.reply_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            reply_layout = QHBoxLayout(self.reply_container)
            reply_layout.setContentsMargins(0, 0, 0, 0)
            reply_layout.setSpacing(button_spacing)
          
            send_button_size = data.config.get("ui", "buttons", "large_button", "button_size") if data.config else 48
          
            self.reply_field = QLineEdit()
            self.reply_field.setFont(get_font(FontType.TEXT))
            self.reply_field.setFixedHeight(send_button_size)
            self.reply_field.returnPressed.connect(self._on_send_reply)
            self.reply_field.installEventFilter(self)
            reply_layout.addWidget(self.reply_field, stretch=1)
          
            self.send_button = _icon_btn(
                self.icons_path, "send.svg", tr("Send message", "Отправить сообщение"), data.config, size_type="large"
            )
            self.send_button.clicked.connect(self._on_send_reply)
            reply_layout.addWidget(self.send_button)
          
            if data.emoticon_manager:
                self.emoticon_button = HoverIconButton(
                    self.icons_path,
                    "emotion-normal.svg",
                    "emotion-happy.svg",
                    tr("Toggle Emoticon Selector", "Селектор эмотиконов"),
                )
                self.emoticon_button.clicked.connect(self._toggle_emoticon_selector)
                reply_layout.addWidget(self.emoticon_button)
          
            self.reply_container.setVisible(False)
            main_layout.addWidget(self.reply_container, stretch=0)
        else:
            self.reply_container = None
            self.reply_field = None
            self.send_button = None
      
        # Set fixed width and adjust size
        self.setFixedWidth(width)
        self.adjustSize()
      
        # Initialize opacity and show
        self.setWindowOpacity(0.0)
        self.show()
        QTimer.singleShot(0, self._animate_in)
        self._start_cursor_monitoring()
  
    def update_message(self, text: str, players: Optional[list] = None):
        """Update the body text (and player chips) in place, no new popup created."""
        if self.message_widget:
            self.message_widget.update_content(text, players)

    def _on_content_resized(self):
        """Body grew/shrank (e.g. player roster changed) - resize and reflow the stack."""
        self.adjustSize()
        self.manager._position_and_cleanup()

    def _on_avatar_loaded(self, user_id: str, pixmap: QPixmap):
        """Callback fired when avatar is loaded from disk or network"""
        try:
            if self.avatar_label:
                self.avatar_label.setPixmap(make_rounded_pixmap(pixmap, 36, 8))
        except RuntimeError:
            pass  # Widget deleted before callback fired

    def mousePressEvent(self, event):
        """Handle clicks: buttons, links, or show window"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is on a button
            clicked_widgets = [self.close_button, self.mute_button, self.position_button]
            if self.answer_button:
                clicked_widgets.append(self.answer_button)
            if self.open_room_button:
                clicked_widgets.append(self.open_room_button)
            if self.send_button:
                clicked_widgets.append(self.send_button)
            if self.emoticon_button:
                clicked_widgets.append(self.emoticon_button)
           
            if self.childAt(event.pos()) in clicked_widgets:
                return super().mousePressEvent(event)

            # Username in the header - opens profile (skip synthetic titles: system/parser/competition)
            if (self.childAt(event.pos()) is self.username_label and self.data.profile_callback
                    and not self.data.is_parser and not self.data.is_competition):
                _safe_call(self.data.window_show_callback, err_msg="Error showing window")
                _safe_call(self.data.profile_callback, self.data.title, err_msg="Profile from notification username")
                return

            # Chip / link clicks in message body
            if self.message_widget:
                widget_pos = self.message_widget.mapFrom(self, event.pos())
                if self.message_widget.rect().contains(widget_pos):
                    chip_name = self.message_widget.get_chip_at_pos(widget_pos)
                    if chip_name and self.data.profile_callback:
                        if self.data.window_show_callback:
                            try:
                                self.data.window_show_callback()
                            except Exception:
                                pass
                        _safe_call(self.data.profile_callback, chip_name, err_msg="Profile from notification chip")
                        return
                    link_data = self.message_widget.get_link_at_pos(widget_pos)
                    if link_data:
                        url, is_media = link_data
                        global_pos = self.mapToGlobal(event.pos())
                        is_ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
                        self.message_renderer.handle_link_lmb(url, is_media, global_pos, is_ctrl)
                        if self.data.is_competition and self.data.competition_game_id is not None:
                            _safe_call(self.data.competition_entered_callback, self.data.competition_game_id,
                                       err_msg="Competition entered callback")
                        return
          
            # Show chat window if callback exists
            _safe_call(self.data.window_show_callback, err_msg="Error showing window")
          
            self.manager.close_all()
        elif event.button() == Qt.MouseButton.RightButton:
            if self.message_widget:
                widget_pos = self.message_widget.mapFrom(self, event.pos())
                if self.message_widget.rect().contains(widget_pos):
                    link_data = self.message_widget.get_link_at_pos(widget_pos)
                    if link_data:
                        self.message_renderer.handle_link_rmb(link_data[0])
                        return
            super().mousePressEvent(event)
        elif event.button() == Qt.MouseButton.MiddleButton:
            if self.answer_button and self.message_widget:
                widget_pos = self.message_widget.mapFrom(self, event.pos())
                if self.message_widget.rect().contains(widget_pos):
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

    def _cleanup_widgets(self):
        """Cleanup widgets on close - release borrowed selector without destroying it"""
        self._release_emoticon_selector()
        if self.message_widget:
            self.message_widget.cleanup()
  
    def _on_open_room(self):
        gid = self.data.competition_game_id
        _safe_call(self.data.window_show_callback, err_msg="Error showing window")
        if gid is not None:
            _safe_call(self.data.open_room_callback, gid, err_msg="Error opening room")
        self.manager.close_all()

    def _reply_style(self) -> str:
        """notification.reply_style: inline (default) | center."""
        return _resolve_centered_style(self.config, "notification", "reply_style")

    def eventFilter(self, obj, event):
        """Widen the popup while the reply field is focused (centered mode only),
        and shrink it back to base_width on focus loss."""
        if obj is self.reply_field:
            if event.type() == QEvent.Type.FocusIn:
                self._animate_width(self._focused_width())
            elif event.type() == QEvent.Type.FocusOut:
                self._animate_width(self.base_width)
        return super().eventFilter(obj, event)

    def _focused_width(self) -> int:
        """Target width while typing a reply. Never narrower than base_width."""
        if self._reply_style() != "center":
            return self.base_width
        screen = self.screen().availableGeometry() if self.screen() else QApplication.primaryScreen().availableGeometry()
        expand = _resolve_focus_expand_width(self.config)
        return max(self.base_width, min(int(screen.width() * 0.8), self.base_width + expand))

    def _animate_width(self, target: int):
        if self._width_anim is not None:
            self._width_anim.stop()
        if self.width() == target:
            return
        anim = QVariantAnimation(self)
        anim.setDuration(_resolve_fade_ms(self.config))
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(self.width())
        anim.setEndValue(target)
        anim.valueChanged.connect(lambda v: (self.setFixedWidth(int(v)), self.manager._position_and_cleanup()))
        anim.start()
        self._width_anim = anim

    def _on_answer(self):
        """Toggle reply field visibility. In 'center' reply_style, the popup
        also detaches from its stack and joins the centered focus group."""
        if not self.reply_container or not self.reply_field:
            return
       
        # Toggle behavior
        if self.reply_field_visible:
            # Hide reply field
            self.reply_field_visible = False
            self.reply_field.clearFocus()
            self.reply_container.setVisible(False)
            self.reply_field.clear()
            if self in self.manager.focused_popups:
                self.manager.focused_popups.remove(self)
                self.manager.popups.append(self)
            
            # Re-enable auto-close if cursor moved and not hovering
            if self.cursor_moved and not self.is_hovered:
                self._start_hide_timer()
        else:
            # Show reply field
            self.reply_field_visible = True
            self.reply_container.setVisible(True)
            if self._reply_style() == "center" and self in self.manager.popups:
                self.manager.popups.remove(self)
                self.manager.focused_popups.append(self)
          
            # Pre-fill with sender's username
            sender_name = self.username_label.text().replace('<b>', '').replace('</b>', '')
            self.reply_field.setText(f"{sender_name}, ")
            self.reply_field.setFocus()
            self.reply_field.setCursorPosition(len(self.reply_field.text()))
          
            # Stop hide timers
            if self.hide_timer and self.hide_timer.isActive():
                self.hide_timer.stop()
            if self.cursor_check_timer and self.cursor_check_timer.isActive():
                self.cursor_check_timer.stop()
      
        # Recalculate size with reply field visible/hidden
        self.adjustSize()
        self.manager._position_and_cleanup()
  
    def _self_hides_after_duration(self) -> bool:
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
        icons = {"left": "align-left.svg", "center": "align-center.svg", "right": "align-right.svg"}
        current = self.data.config.get("ui", "notification_position") or "right"
        new_pos = cycle.get(current, "right")
        self.data.config.set("ui", "notification_position", value=new_pos)
        # Update icon on all popup position buttons for consistency
        for popup in self.manager.popups:
            if hasattr(popup, 'position_button'):
                new_btn = _icon_btn(self.icons_path, icons[new_pos], tr("Change Position", "Сменить расположение"), self.data.config)
                popup.position_button.setIcon(new_btn.icon())
                new_btn.deleteLater()
        self.manager._position_and_cleanup()

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
        self.manager._position_and_cleanup()
    
    def _on_emoticon_selected(self, emoticon_name: str):
        """Insert emoticon into reply field"""
        if not self.reply_field:
            return
        
        cursor_pos = self.reply_field.cursorPosition()
        emoticon_code = f":{emoticon_name}: "
        text = self.reply_field.text()
        
        self.reply_field.setText(text[:cursor_pos] + emoticon_code + text[cursor_pos:])
        self.reply_field.setCursorPosition(cursor_pos + len(emoticon_code))
        self.reply_field.setFocus()

    def _on_send_reply(self):
        """Send reply message"""
        if not self.reply_field:
            return
       
        text = self.reply_field.text().strip()
        if not text or not self.data.xmpp_client:
            return
      
        self.reply_field.clear()
      
        # Determine message type and recipient. For groupchat, room_jid routes
        # the reply back to the room the notification came from (e.g. a game
        # room) — without it, XMPPClient.send_message falls back to General.
        msg_type = 'chat' if self.data.is_private and self.data.recipient_jid else 'groupchat'
        to_jid = self.data.recipient_jid if msg_type == 'chat' else self.data.room_jid
      
        # Add message locally to UI
        if self.data.local_message_callback and self.data.account:
            try:
                from core.messages import Message
              
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
        QTimer.singleShot(100, self._on_close)
  
    def wheelEvent(self, event):
        """Scroll through the notification stack in scroll mode"""
        if self.manager.notification_mode == "scroll":
            self.manager.scroll_by(event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

class PresenceMiniPopup(_AutoHidePopupMixin, QWidget):
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
        self.icons_path = Path(__file__).parent.parent / "icons"

        _setup_popup_window(self)

        margin, spacing = _resolve_margin_spacing(config)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)

        AVATAR_SIZE = 36
        SVG_AVATAR_SIZE = 24

        avatar = _make_avatar_label(AVATAR_SIZE)
        avatar.setPixmap(_avatar_pixmap(self.icons_path, avatar_pixmap, AVATAR_SIZE, SVG_AVATAR_SIZE))
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

        self.close_button = _icon_btn(self.icons_path, "close.svg", tr("Close", "Закрыть"), config)
        self.close_button.clicked.connect(self.manager.close_all)
        layout.addWidget(self.close_button)

        self.adjustSize()
        self.setFixedHeight(max(AVATAR_SIZE + margin * 2, self.sizeHint().height()))
        self.setMinimumWidth(min(360, self.sizeHint().width() + 20))

        self.setWindowOpacity(0.0)
        self.show()
        QTimer.singleShot(0, self._animate_in)
        self._start_cursor_monitoring()

    def _self_hides_after_duration(self) -> bool:
        return self._force_duration

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.childAt(event.pos()) is self.close_button:
                return super().mousePressEvent(event)
            if self.on_click:
                _safe_call(self.on_click, err_msg="Presence notification click")
            self.manager.close_all()
            return
        super().mousePressEvent(event)


class PopupManager:
  
    def __init__(self):
        self.popups: List[PopupNotification] = []
        self.focused_popups: List[PopupNotification] = []  # detached for centered reply
        self.gap = 10
        self.config = None
        self.notification_mode = "stack"
        self.muted = False
        self.scroll_offset = 0
        self.emoticon_selector = None  # Single shared instance, created on first use
  
    def set_notification_mode(self, mode: str):
        """Set notification mode: 'stack', 'replace' or 'scroll'"""
        if mode in ["stack", "replace", "scroll"]:
            self.notification_mode = mode

    def scroll_by(self, delta: int):
        """Shift the notification stack in scroll mode; clamped in _position_and_cleanup"""
        if self.notification_mode != "scroll" or not self.popups:
            return
        self.scroll_offset = max(0, self.scroll_offset - delta)
        self._position_and_cleanup()
  
    def set_muted(self, muted: bool):
        """Set muted state"""
        self.muted = muted

    def show_presence(self, login: str, event_type: str = 'join', avatar_pixmap=None, config=None,
                      on_click=None, event_ts=None, cache=None, game_id=None, is_join=None):
        """Compact presence toast. When muted, only if tracked_bypass_mute.
        is_join kept for backward compat → maps to join/left."""
        if is_join is not None and event_type == 'join':
            event_type = 'join' if is_join else 'left'
        cfg = config or self.config
        if cfg is not None and cfg.get("user_tracker", "notifications") is False:
            return None
        mode = _mute_bypass_mode(cfg, "tracked_bypass_mute")
        if mode == "off" and self.muted:
            return None
        self.config = cfg
        duration_ms = _resolve_duration_ms(cfg)
        force_duration = mode == "duration"
        popup = PresenceMiniPopup(
            self, login, event_type=event_type, avatar_pixmap=avatar_pixmap,
            config=cfg, duration_ms=duration_ms,
            on_click=on_click, event_ts=event_ts, cache=cache, game_id=game_id,
            force_duration=force_duration,
        )
        self.popups.append(popup)
        self._position_and_cleanup()
        return popup

  
    def _competition_style(self) -> str:
        """competitions.notification_style: inline (default) | center."""
        return _resolve_centered_style(self.config, "competitions", "notification_style")

    def show_notification(self, data: NotificationData):
        """Create and show notification (unless muted). Mute-bypass modes per type."""
        if data.is_competition:
            key = "competitions_bypass_mute"
        elif data.is_mention or data.is_private:
            key = "mentions_bypass_mute"
        elif data.is_ban:
            key = "bans_bypass_mute"
        elif not data.is_system and not data.is_parser:
            key = "messages_bypass_mute"
        else:
            key = None
        if key is not None:
            if not _apply_mute_bypass(data, self.muted, key):
                return None
        elif self.muted:
            return None
       
        self.config = data.config
       
        # In replace mode, close existing notifications EXCEPT those with active reply fields
        if self.notification_mode == "replace":
            for popup in list(self.popups) + list(self.focused_popups):
                # Keep notifications with visible reply field
                if not popup.reply_field_visible:
                    popup.close_immediately()
                    (self.focused_popups if popup in self.focused_popups else self.popups).remove(popup)
      
        # Calculate width before creating popup (max 50% of screen)
        screen = QApplication.primaryScreen().availableGeometry()
        notification_width = self.config.get("ui", "notification_width") if self.config else NOTIFICATION_DEFAULT_WIDTH
        width = min(int(screen.width() * 0.50), notification_width or NOTIFICATION_DEFAULT_WIDTH)

        popup = PopupNotification(data, self, width)
        if data.is_competition and self._competition_style() == "center":
            self.focused_popups.append(popup)
        else:
            self.popups.append(popup)
        self._position_and_cleanup()
        return popup
  
    def remove_popup(self, popup: PopupNotification):
        """Remove popup (from whichever list holds it) and reposition"""
        for lst in (self.popups, self.focused_popups):
            if popup in lst:
                lst.remove(popup)
        if not self.popups:
            self.scroll_offset = 0
        self._position_and_cleanup()
  
    def close_all(self):
        """Close all notifications"""
        for popup in list(self.popups) + list(self.focused_popups):
            popup.close_immediately()
        self.popups.clear()
        self.focused_popups.clear()
        self.scroll_offset = 0

    def close_by_tag(self, tag: str):
        """Close notifications with the given tag"""
        if not tag:
            return
        for popup in list(self.popups) + list(self.focused_popups):
            if getattr(popup.data, "tag", None) == tag:
                popup._animate_out(force=True)

    def find_by_tag(self, tag: str) -> Optional["PopupNotification"]:
        """Find an open notification by tag, for in-place content updates."""
        if not tag:
            return None
        return next((p for p in self.popups + self.focused_popups if getattr(p.data, "tag", None) == tag), None)
  
    def _popup_x(self, screen, position: str, popup_width: int) -> int:
        if position == "left":
            return screen.x() + 20
        if position == "right":
            return screen.x() + screen.width() - popup_width - 20
        return screen.x() + (screen.width() - popup_width) // 2

    def _stack_popups(self, popups, x_fn, start_y):
        """Shared top-down vertical stacking, used for both the side stack
        and the centered focused group. Returns the y past the last popup."""
        current_y = start_y
        for popup in popups:
            popup.move(x_fn(popup), current_y)
            current_y += popup.height() + self.gap
        return current_y

    def _group_height(self, popups):
        """(heights, total stacked height incl. gaps) for a group of popups."""
        heights = [p.height() for p in popups]
        return heights, sum(heights) + self.gap * max(0, len(heights) - 1)

    def _position_focused_popups(self):
        """Center the detached (reply-in-progress) popups as their own
        stacked group, so several open reply fields never overlap.
        Y is centered by default, adjustable via notification.reply_center_offset_y."""
        if not self.focused_popups:
            return
        screen = self.focused_popups[0].screen().availableGeometry()
        _, total_height = self._group_height(self.focused_popups)
        offset_y = self.config.get("notification", "reply_center_offset_y") if self.config else 0
        try:
            offset_y = int(offset_y or 0)
        except (TypeError, ValueError):
            offset_y = 0
        base_y = screen.y() + (screen.height() - total_height) // 2 + offset_y
        min_y = screen.y() + 20
        max_y = screen.y() + screen.height() - 20 - total_height
        start_y = max(min_y, min(base_y, max(min_y, max_y)))
        self._stack_popups(
            self.focused_popups,
            x_fn=lambda p: self._popup_x(screen, "center", p.width()),
            start_y=start_y,
        )

    def _position_and_cleanup(self):
        """Position every popup group, then drop stack-mode overflow that doesn't fit."""
        self._position_focused_popups()
        self._position_popups()

    def _position_popups(self):
        """Stack the regular (non-focused) popups top-down at their configured edge."""
        if not self.popups:
            return

        screen = self.popups[0].screen().availableGeometry()
        position = self.config.get("ui", "notification_position") if self.config else "center"
        position = (position or "center").lower()

        heights, total_height = self._group_height(self.popups)
        available_height = screen.height() - 40

        # In scroll mode, clamp offset instead of dropping popups
        if self.notification_mode == "scroll":
            max_offset = max(0, total_height - available_height)
            self.scroll_offset = min(self.scroll_offset, max_offset)

        start_y = screen.y() + 20 - (self.scroll_offset if self.notification_mode == "scroll" else 0)
        self._stack_popups(self.popups, lambda p: self._popup_x(screen, position, p.width()), start_y)

        if self.notification_mode == "stack":
            self._cleanup_overflow(screen, position, heights, total_height, available_height)

    def _cleanup_overflow(self, screen, position, heights, total_height, available_height):
        """Drop the oldest popups without an active reply field until the stack fits."""
        while total_height > available_height and len(self.popups) > 1:
            # Find the oldest notification that doesn't have an active reply field
            removed = False
            for i, popup in enumerate(self.popups):
                if not popup.reply_field_visible:
                    # Remove this notification
                    self.popups.pop(i)
                    popup.close()
                    total_height -= (heights.pop(i) + self.gap)
                    removed = True
                    break

            # If all notifications have active reply fields, stop trying to remove
            if not removed:
                break

            # Reposition remaining popups
            self._stack_popups(self.popups, lambda p: self._popup_x(screen, position, p.width()), screen.y() + 20)


# Global manager
popup_manager = PopupManager()


def show_notification(**kwargs):
    # Resolve duration from config (seconds → ms) when the caller didn't pass one.
    if "duration" not in kwargs:
        kwargs["duration"] = _resolve_duration_ms(kwargs.get("config"))
    data = NotificationData(**kwargs)
    return popup_manager.show_notification(data)
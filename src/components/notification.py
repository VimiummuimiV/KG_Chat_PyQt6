from PyQt6.QtWidgets import(
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QLineEdit, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QCursor, QPainter, QPainterPath
from typing import List, Callable, Optional, Any
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
import threading

from helpers.create import create_icon_button
from helpers.color_utils import(
    get_private_message_colors,
    get_ban_message_colors,
    get_system_message_colors
)
from helpers.fonts import get_font, FontType


@dataclass
class NotificationData:
    """Encapsulates all notification parameters to avoid code duplication"""
    title: str
    message: str
    duration: int = 5000
    xmpp_client: Optional[Any] = None
    cache: Optional[Any] = None
    config: Optional[Any] = None
    local_message_callback: Optional[Callable] = None
    account: Optional[dict] = None
    window_show_callback: Optional[Callable] = None
    is_private: bool = False
    recipient_jid: Optional[str] = None
    is_ban: bool = False
    is_system: bool = False


class PopupNotification(QWidget):
   
    def __init__(self, data: NotificationData, manager, width: int):
        super().__init__()
        self.data = data
        self.manager = manager
        self.is_hovered = False
        self.cursor_moved = False
        self.initial_cursor_pos = QCursor.pos()
        self.hide_timer = None
        self.cursor_check_timer = None
        self.reply_field_visible = False
        self.icons_path = Path(__file__).parent.parent / "icons"
       
        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
       
        # Get spacing/margin from config
        margin = data.config.get("ui", "margins", "notification") if data.config else 8
        spacing = data.config.get("ui", "spacing", "widget_elements") if data.config else 4
       
        # Determine theme and colors
        is_dark = data.config.get("ui", "theme") == "dark" if data.config else True
        bg_hex = "#1E1E1E" if is_dark else "#FFFFFF"
       
        # Load message colors from config based on message type
        message_color = None
        if data.is_system and data.config:
            # System message colors
            system_colors = get_system_message_colors(data.config, is_dark)
            message_color = system_colors["text"]
        elif data.is_ban and data.config:
            # Ban message colors
            ban_colors = get_ban_message_colors(data.config, is_dark)
            message_color = ban_colors["text"]
        elif data.is_private and data.config:
            # Private message colors
            private_colors = get_private_message_colors(data.config, is_dark)
            message_color = private_colors["text"]
       
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(margin, margin, margin, margin)
        main_layout.setSpacing(spacing)
       
        # Top row: message + buttons
        top_row = QHBoxLayout()
        top_row.setSpacing(spacing)
       
        # Message container
        message_layout = QVBoxLayout()
        message_layout.setSpacing(spacing)
       
        # Username label
        username_color = data.cache.get_or_calculate_color(data.title, None, bg_hex, 4.5) if data.cache else "#AAAAAA"
        self.username_label = QLabel(f"<b>{data.title}</b>")
        self.username_label.setStyleSheet(f"color: {username_color};")
        self.username_label.setFont(get_font(FontType.TEXT))
        self.username_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        message_layout.addWidget(self.username_label)
       
        # Message label
        self.message_label = QLabel(data.message)
        self.message_label.setWordWrap(True)
        self.message_label.setFont(get_font(FontType.TEXT))
        self.message_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if message_color:
            self.message_label.setStyleSheet(f"color: {message_color};")
        message_layout.addWidget(self.message_label)
       
        top_row.addLayout(message_layout, stretch=1)
       
        # Buttons container
        button_spacing = data.config.get("ui", "buttons", "spacing") if data.config else 8
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(button_spacing)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
       
        # Answer button (small) - hide for ban messages and system messages
        if not data.is_ban and not data.is_system:
            self.answer_button = create_icon_button(
                self.icons_path, "answer.svg", "Reply",
                size_type="small", config=data.config
            )
            self.answer_button.clicked.connect(self._on_answer)
            buttons_layout.addWidget(self.answer_button)
        else:
            self.answer_button = None
       
        # Mute button (small)
        self.mute_button = create_icon_button(
            self.icons_path, "shut-down.svg", "Mute Notifications",
            size_type="small", config=data.config
        )
        self.mute_button.clicked.connect(self._on_mute)
        buttons_layout.addWidget(self.mute_button)
       
        # Close button (small)
        self.close_button = create_icon_button(
            self.icons_path, "close.svg", "Close",
            size_type="small", config=data.config
        )
        self.close_button.clicked.connect(self.manager.close_all)
        buttons_layout.addWidget(self.close_button)
       
        top_row.addLayout(buttons_layout)
        main_layout.addLayout(top_row)
       
        # Reply field container (hidden by default) - only for non-ban and non-system messages
        if not data.is_ban and not data.is_system:
            self.reply_container = QWidget()
            reply_layout = QHBoxLayout(self.reply_container)
            reply_layout.setContentsMargins(0, 0, 0, 0)
            reply_layout.setSpacing(button_spacing)
           
            # Get button size for reply field height
            send_button_size = data.config.get("ui", "buttons", "large_button", "button_size") if data.config else 48
           
            self.reply_field = QLineEdit()
            self.reply_field.setFont(get_font(FontType.TEXT))
            self.reply_field.setFixedHeight(send_button_size)
            self.reply_field.returnPressed.connect(self._on_send_reply)
            reply_layout.addWidget(self.reply_field, stretch=1)
           
            self.send_button = create_icon_button(
                self.icons_path, "send.svg", "Send",
                size_type="large", config=data.config
            )
            self.send_button.clicked.connect(self._on_send_reply)
            reply_layout.addWidget(self.send_button)
           
            self.reply_container.setVisible(False)
            main_layout.addWidget(self.reply_container)
        else:
            self.reply_container = None
            self.reply_field = None
            self.send_button = None
       
        # Set fixed width early for accurate sizeHint with wrapping
        self.setFixedWidth(width)
        self.adjustSize()
       
        # Initialize opacity and show
        self.setWindowOpacity(0.0)
        self.show()
        QTimer.singleShot(0, self._animate_in)
        self._start_cursor_monitoring()
   
    def paintEvent(self, event):
        """Custom paint for rounded corners"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF(), 10, 10)
        painter.fillPath(path, self.palette().window())
        painter.setPen(self.palette().mid().color())
        painter.drawPath(path)
   
    def mousePressEvent(self, event):
        """Click on notification body to show chat window and close notification"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is on a button (don't trigger on button clicks)
            clicked_widgets = [self.close_button, self.mute_button]
            if self.answer_button:
                clicked_widgets.append(self.answer_button)
            if self.send_button:
                clicked_widgets.append(self.send_button)
            
            if self.childAt(event.pos()) in clicked_widgets:
                return super().mousePressEvent(event)
           
            # Show chat window if callback exists
            if self.data.window_show_callback:
                try:
                    self.data.window_show_callback()
                except Exception as e:
                    print(f"❌ Error showing window: {e}")
           
            self._on_close()
        else:
            super().mousePressEvent(event)
   
    def _start_cursor_monitoring(self):
        """Monitor cursor movement to trigger auto-hide"""
        self.cursor_check_timer = QTimer(self)
        self.cursor_check_timer.timeout.connect(self._check_cursor_movement)
        self.cursor_check_timer.start(100)
   
    def _check_cursor_movement(self):
        """Check if cursor moved significantly"""
        if self.cursor_moved or self.reply_field_visible:
            return
       
        if (QCursor.pos() - self.initial_cursor_pos).manhattanLength() > 50:
            self.cursor_moved = True
            self.cursor_check_timer.stop()
            self._start_hide_timer()
   
    def _start_hide_timer(self):
        """Start auto-hide timer"""
        if not self.is_hovered and not self.reply_field_visible:
            self.hide_timer = QTimer(self)
            self.hide_timer.setSingleShot(True)
            self.hide_timer.timeout.connect(self._animate_out)
            self.hide_timer.start(self.data.duration)
   
    def _animate_in(self):
        """Fade in animation"""
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.start()
   
    def _animate_out(self):
        """Fade out animation"""
        if self.is_hovered or self.reply_field_visible:
            return
       
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(300)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.finished.connect(self._on_close)
        self.fade_out.start()
   
    def close_immediately(self):
        """Close notification immediately without animation"""
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        if self.cursor_check_timer and self.cursor_check_timer.isActive():
            self.cursor_check_timer.stop()
        self.close()
   
    def _on_close(self):
        """Close notification"""
        self.manager.remove_popup(self)
        self.close()
   
    def _on_answer(self):
        """Show reply field"""
        if not self.reply_container or not self.reply_field:
            return
        
        self.reply_field_visible = True
        self.reply_container.setVisible(True)
       
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
       
        # Recalculate size with reply field visible
        self.adjustSize()
        self.manager._position_and_cleanup()
   
    def _on_mute(self):
        """Mute notifications and close all popups"""
        # Set muted state in manager
        self.manager.set_muted(True)
        
        # Save to config if available
        if self.data.config:
            self.data.config.set("notification_muted", value=True)
        
        # Close all notifications
        self.manager.close_all()
        
        print("🔇 Notifications muted")

    def _on_send_reply(self):
        """Send reply message"""
        if not self.reply_field:
            return
        
        text = self.reply_field.text().strip()
        if not text or not self.data.xmpp_client:
            return
       
        self.reply_field.clear()
       
        # Determine message type and recipient based on notification data
        msg_type = 'chat' if self.data.is_private and self.data.recipient_jid else 'groupchat'
        to_jid = self.data.recipient_jid if msg_type == 'chat' else None
       
        # Add message locally to UI before sending to server
        if self.data.local_message_callback and self.data.account:
            try:
                from core.messages import Message
               
                # Get effective background color (custom_background or server background)
                effective_bg = self.data.account.get('custom_background') or self.data.account.get('background')
               
                # Create local message object
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
                
                # Mark as private if replying to private message
                own_msg.is_private = (msg_type == 'chat')
                own_msg.is_system = False  # Replies are never system messages
               
                # Add to UI locally
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
   
    def enterEvent(self, event):
        """Mouse entered - stop hiding"""
        self.is_hovered = True
        if self.hide_timer and self.hide_timer.isActive():
            self.hide_timer.stop()
        if hasattr(self, 'fade_out') and self.fade_out.state() == QPropertyAnimation.State.Running:
            self.fade_out.stop()
            self.fade_reveal = QPropertyAnimation(self, b"windowOpacity")
            self.fade_reveal.setDuration(300)
            self.fade_reveal.setStartValue(self.windowOpacity())
            self.fade_reveal.setEndValue(1.0)
            self.fade_reveal.start()
        else:
            self.setWindowOpacity(1.0)
   
    def leaveEvent(self, event):
        """Mouse left - restart hide timer"""
        self.is_hovered = False
        if self.cursor_moved and not self.reply_field_visible:
            self._start_hide_timer()


class PopupManager:
   
    def __init__(self):
        self.popups: List[PopupNotification] = []
        self.gap = 10
        self.config = None
        self.notification_mode = "stack"  # "stack" or "replace"
        self.muted = False  # Muted state
   
    def set_notification_mode(self, mode: str):
        """Set notification mode: 'stack' or 'replace'"""
        if mode in ["stack", "replace"]:
            self.notification_mode = mode
   
    def set_muted(self, muted: bool):
        """Set muted state - if True, notifications won't be shown"""
        self.muted = muted
   
    def show_notification(self, data: NotificationData):
        """Create and show notification (unless muted)"""
        # If muted, don't show notification
        if self.muted:
            return None
        
        self.config = data.config
        
        # In replace mode, close all existing notifications immediately
        if self.notification_mode == "replace" and self.popups:
            for popup in list(self.popups):
                popup.close_immediately()
            self.popups.clear()
       
        # Calculate width before creating popup (max 50% of screen)
        screen = QApplication.primaryScreen().availableGeometry()
        notification_width = self.config.get("ui", "notification_width") if self.config else 500
        width = min(int(screen.width() * 0.50), notification_width or 500)
       
        popup = PopupNotification(data, self, width)
        self.popups.append(popup)
        self._position_and_cleanup()
        return popup
   
    def remove_popup(self, popup: PopupNotification):
        """Remove popup and reposition"""
        if popup in self.popups:
            self.popups.remove(popup)
            self._position_and_cleanup()
   
    def close_all(self):
        """Close all notifications"""
        for popup in list(self.popups):
            popup.close()
        self.popups.clear()
   
    def _position_and_cleanup(self):
        """Combined positioning and overflow cleanup with accurate sizing"""
        if not self.popups:
            return
       
        screen = self.popups[0].screen().availableGeometry()
       
        # Get notification position from config (default "center")
        position = self.config.get("ui", "notification_position") if self.config else "center"
        position = (position or "center").lower()
       
        # Calculate x position based on setting
        popup_width = self.popups[0].width()
        if position == "left":
            x = screen.x() + 20
        elif position == "right":
            x = screen.x() + screen.width() - popup_width - 20
        else:  # center (default)
            x = screen.x() + (screen.width() - popup_width) // 2
       
        # In replace mode, only position the single popup
        if self.notification_mode == "replace":
            if self.popups:
                self.popups[0].move(x, screen.y() + 20)
            return
       
        # Stack mode - position all popups and handle overflow
        # Calculate total height and cleanup overflow
        heights = [p.height() for p in self.popups]
        total_height = sum(heights) + self.gap * max(0, len(heights) - 1)
        available_height = screen.height() - 40
       
        while total_height > available_height and len(self.popups) > 1:
            oldest = self.popups.pop(0)
            oldest.close()
            total_height -= (heights.pop(0) + self.gap)
       
        # Position remaining popups
        current_y = screen.y() + 20
        for popup in self.popups:
            popup.move(x, current_y)
            current_y += popup.height() + self.gap


# Global manager
popup_manager = PopupManager()


def show_notification(**kwargs):
    """
    Show notification with click-to-show functionality
   
    Accepts all NotificationData parameters as keyword arguments:
        title (str): Notification title (username)
        message (str): Message content
        duration (int): Auto-hide duration in milliseconds (default: 5000)
        xmpp_client: XMPP client for sending replies
        cache: Cache object for username colors
        config: Application config
        local_message_callback (Callable): Callback to add messages locally
        account (dict): User account dict
        window_show_callback (Callable): Callback to show/focus the chat window
        is_private (bool): Whether this is a private message (default: False)
        recipient_jid (str): JID to send reply to (for private messages)
        is_ban (bool): Whether this is a ban message (default: False)
        is_system (bool): Whether this is a system message (default: False)
    """
    data = NotificationData(**kwargs)
    return popup_manager.show_notification(data)

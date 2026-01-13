from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QCursor, QPainter, QPainterPath
from typing import List, Callable, Optional, Any
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
import threading

from helpers.create import create_icon_button
from helpers.color_utils import get_private_message_colors
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


class PopupNotification(QWidget):
   
    def __init__(self, data: NotificationData, manager):
        super().__init__()
        self.data = data
        self.manager = manager
        self.is_hovered = False
        self.cursor_moved = False
        self.initial_cursor_pos = None
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
       
        # Load private message colors from config
        if data.is_private and data.config:
            private_colors = get_private_message_colors(data.config, is_dark)
            message_color = private_colors["text"]
        else:
            message_color = None # Will use theme default
       
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
        if data.cache:
            username_color = data.cache.get_or_calculate_color(data.title, None, bg_hex, 4.5)
        else:
            username_color = "#AAAAAA"
        
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
       
        # Only set color for private messages
        if message_color:
            self.message_label.setStyleSheet(f"color: {message_color};")
        message_layout.addWidget(self.message_label)
       
        top_row.addLayout(message_layout, stretch=1)
       
        # Buttons container
        button_spacing = data.config.get("ui", "buttons", "spacing") if data.config else 8
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(button_spacing)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
       
        # Answer button (small)
        self.answer_button = create_icon_button(
            self.icons_path, "answer.svg", "Reply",
            size_type="small", config=data.config
        )
        self.answer_button.clicked.connect(self._on_answer)
        buttons_layout.addWidget(self.answer_button)
       
        # Close button (small)
        self.close_button = create_icon_button(
            self.icons_path, "close.svg", "Close",
            size_type="small", config=data.config
        )
        self.close_button.clicked.connect(self.manager.close_all)
        buttons_layout.addWidget(self.close_button)
       
        top_row.addLayout(buttons_layout)
        main_layout.addLayout(top_row)
       
        # Reply field container (hidden by default)
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
       
        # Initialize
        self.setWindowOpacity(0.0)
        self.show()
        QTimer.singleShot(0, self._animate_in)
        self.initial_cursor_pos = QCursor.pos()
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
            clicked_widget = self.childAt(event.pos())
            if clicked_widget in [self.answer_button, self.close_button, self.send_button]:
                super().mousePressEvent(event)
                return
           
            # Show chat window if callback exists
            if self.data.window_show_callback:
                try:
                    self.data.window_show_callback()
                except Exception as e:
                    print(f"❌ Error showing window: {e}")
           
            # Close notification
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
       
        current_pos = QCursor.pos()
        if self.initial_cursor_pos:
            distance = (current_pos - self.initial_cursor_pos).manhattanLength()
            if distance > 50:
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
   
    def _on_close(self):
        """Close notification"""
        self.manager.remove_popup(self)
        self.close()
   
    def _on_answer(self):
        """Show reply field"""
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
       
        self.manager._reposition_all()
   
    def _on_send_reply(self):
        """Send reply message"""
        text = self.reply_field.text().strip()
        if not text:
            return
       
        if not self.data.xmpp_client:
            print("❌ No XMPP client - cannot send reply")
            return
       
        self.reply_field.clear()
       
        # Add message locally to UI before sending to server
        if self.data.local_message_callback and self.data.account:
            try:
                # Import here to avoid circular imports
                from core.messages import Message
               
                # Get effective background color (custom_background or server background)
                effective_bg = self.data.account.get('custom_background') or self.data.account.get('background')
               
                # Create local message object
                own_msg = Message(
                    from_jid=self.data.xmpp_client.jid,
                    body=text,
                    msg_type='groupchat',
                    login=self.data.account.get('chat_username'),
                    avatar=self.data.account.get('avatar'),
                    background=effective_bg,
                    timestamp=datetime.now(),
                    initial=False
                )
               
                # Add to UI locally
                self.data.local_message_callback(own_msg)
            except Exception as e:
                print(f"❌ Error adding local message: {e}")
       
        def _send():
            try:
                result = self.data.xmpp_client.send_message(text)
                if not result:
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
   
    def show_notification(self, data: NotificationData):
        """Create and show notification"""
        self.config = data.config
        popup = PopupNotification(data, self)
        self.popups.append(popup)
        self._cleanup_overflow()
        self._reposition_all()
        return popup
   
    def remove_popup(self, popup: PopupNotification):
        """Remove popup and reposition"""
        if popup in self.popups:
            self.popups.remove(popup)
            self._reposition_all()
   
    def close_all(self):
        """Close all notifications"""
        for popup in list(self.popups):
            popup.close()
        self.popups.clear()
   
    def _cleanup_overflow(self):
        """Remove oldest notifications if they don't fit"""
        if not self.popups:
            return
       
        screen = self.popups[0].screen().availableGeometry()
        available_height = screen.height() - 40
       
        total_height = sum(p.sizeHint().height() + self.gap for p in self.popups)
       
        while total_height > available_height and len(self.popups) > 1:
            oldest = self.popups[0]
            total_height -= (oldest.sizeHint().height() + self.gap)
            oldest.close()
            self.popups.remove(oldest)
   
    def _reposition_all(self):
        """Stack all popups vertically with configurable position"""
        if not self.popups:
            return
       
        screen = self.popups[0].screen().availableGeometry()
       
        # Get notification width from config (default 500, max 50% of screen)
        notification_width = self.config.get("ui", "notification_width") if self.config else 500
        width = min(int(screen.width() * 0.50), notification_width or 500)
       
        # Get notification position from config (default "center")
        position = self.config.get("ui", "notification_position") if self.config else "center"
        position = (position or "center").lower()
       
        # Calculate x position based on setting
        if position == "left":
            x = screen.x() + 20
        elif position == "right":
            x = screen.x() + screen.width() - width - 20
        else: # center (default)
            x = screen.x() + (screen.width() - width) // 2
       
        current_y = screen.y() + 20
       
        for popup in self.popups:
            height = popup.sizeHint().height()
            popup.setGeometry(x, current_y, width, height)
            current_y += height + self.gap


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
    """
    data = NotificationData(**kwargs)
    return popup_manager.show_notification(data)

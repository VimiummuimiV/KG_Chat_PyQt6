"""Popup notification system with persistent reply support"""
from dataclasses import dataclass
from typing import List, Callable, Optional, Any, Tuple
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QSize
from PyQt6.QtGui import QPainter, QPainterPath, QCursor
from pathlib import Path
from datetime import datetime
import threading

from helpers.create import create_icon_button
from helpers.fonts import get_font, FontType
from ui.message_renderer import MessageRenderer


@dataclass
class NotificationData:
    """Encapsulates all notification parameters to avoid code duplication"""
    title: str
    message: str
    duration: int = 5000
    xmpp_client: Optional[Any] = None
    cache: Optional[Any] = None
    config: Optional[Any] = None
    emoticon_manager: Optional[Any] = None
    local_message_callback: Optional[Callable] = None
    account: Optional[dict] = None
    window_show_callback: Optional[Callable] = None
    is_private: bool = False
    recipient_jid: Optional[str] = None
    is_ban: bool = False
    is_system: bool = False


class MessageBodyWidget(QWidget):
    """Custom widget that uses MessageRenderer for painting message body"""
    
    def __init__(self, message_renderer: MessageRenderer, text: str, 
                 is_private: bool = False, is_ban: bool = False, is_system: bool = False):
        super().__init__()
        self.message_renderer = message_renderer
        self.text = text
        self.is_private = is_private
        self.is_ban = is_ban
        self.is_system = is_system
        self.link_rects: List[Tuple[QRect, str, bool]] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        # Initial height estimate
        self.setFixedHeight(50)
        
        # Animation timer for animated emoticons (GIFs)
        self.animation_timer = None
        if self.message_renderer.has_animated_emoticons(text):
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self.update)  # Trigger repaint
            self.animation_timer.start(33)  # ~30 FPS
    
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
            self.is_system
        )
        
        # Update height if needed
        calculated_height = self.message_renderer.calculate_content_height(self.text, self.width())
        if self.height() != calculated_height:
            self.setFixedHeight(calculated_height)
    
    def sizeHint(self):
        height = self.message_renderer.calculate_content_height(
            self.text, 
            self.width() if self.width() > 0 else 400
        )
        return QSize(self.width() if self.width() > 0 else 400, height)
    
    def mouseMoveEvent(self, event):
        # Update cursor based on whether hovering over link
        is_over_link = MessageRenderer.is_over_link(self.link_rects, event.pos())
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor if is_over_link else Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)
    
    def get_link_at_pos(self, pos) -> Optional[Tuple[str, bool]]:
        """Get link at position"""
        return MessageRenderer.get_link_at_pos(self.link_rects, pos)
    
    def cleanup(self):
        """Cleanup animation timer"""
        if self.animation_timer:
            self.animation_timer.stop()
            self.animation_timer = None


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
        self.message_widget = None
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
      
        # Determine theme
        is_dark = data.config.get("ui", "theme") == "dark" if data.config else True
        bg_hex = "#1E1E1E" if is_dark else "#FFFFFF"
        
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
      
        # Username label (left side) - hide for system messages
        username_color = data.cache.get_or_calculate_color(data.title, None, bg_hex, 4.5) if data.cache else "#AAAAAA"
        self.username_label = QLabel(f"<b>{data.title}</b>")
        self.username_label.setStyleSheet(f"color: {username_color};")
        self.username_label.setFont(get_font(FontType.TEXT))
        self.username_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        if not data.is_system:
            top_row.addWidget(self.username_label, stretch=1)
        else:
            top_row.addStretch(1)
      
        # Buttons container (right side)
        button_spacing = data.config.get("ui", "buttons", "spacing") if data.config else 8
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(button_spacing)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
      
        # Answer button - hide for ban and system messages
        if not data.is_ban and not data.is_system:
            self.answer_button = create_icon_button(
                self.icons_path, "answer.svg", "Reply",
                size_type="small", config=data.config
            )
            self.answer_button.clicked.connect(self._on_answer)
            buttons_layout.addWidget(self.answer_button)
        else:
            self.answer_button = None
      
        # Mute button
        self.mute_button = create_icon_button(
            self.icons_path, "shut-down.svg", "Mute Notifications",
            size_type="small", config=data.config
        )
        self.mute_button.clicked.connect(self._on_mute)
        buttons_layout.addWidget(self.mute_button)
      
        # Close button
        self.close_button = create_icon_button(
            self.icons_path, "close.svg", "Close",
            size_type="small", config=data.config
        )
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
            data.is_system
        )
        msg_layout.addWidget(self.message_widget)
        main_layout.addWidget(msg_container, stretch=1)
      
        # BOTTOM ROW: Reply field - hide for ban and system messages
        if not data.is_ban and not data.is_system:
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
            reply_layout.addWidget(self.reply_field, stretch=1)
          
            self.send_button = create_icon_button(
                self.icons_path, "send.svg", "Send",
                size_type="large", config=data.config
            )
            self.send_button.clicked.connect(self._on_send_reply)
            reply_layout.addWidget(self.send_button)
          
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
        """Handle clicks: buttons, links, or show window"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is on a button
            clicked_widgets = [self.close_button, self.mute_button]
            if self.answer_button:
                clicked_widgets.append(self.answer_button)
            if self.send_button:
                clicked_widgets.append(self.send_button)
           
            if self.childAt(event.pos()) in clicked_widgets:
                return super().mousePressEvent(event)
            
            # Check if click is on a link in message body
            if self.message_widget:
                widget_pos = self.message_widget.mapFrom(self, event.pos())
                if self.message_widget.rect().contains(widget_pos):
                    link_data = self.message_widget.get_link_at_pos(widget_pos)
                    if link_data:
                        url, is_media = link_data
                        global_pos = self.mapToGlobal(event.pos())
                        is_ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
                        self.message_renderer.handle_link_click(url, is_media, global_pos, is_ctrl)
                        # Don't close notification when link is clicked
                        return
          
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
        # Cleanup message widget animation
        if self.message_widget:
            self.message_widget.cleanup()
        self.close()
  
    def _on_close(self):
        """Close notification"""
        # Cleanup message widget animation
        if self.message_widget:
            self.message_widget.cleanup()
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
        self.manager.set_muted(True)
       
        if self.data.config:
            self.data.config.set("notification", "muted", value=True)
       
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
      
        # Determine message type and recipient
        msg_type = 'chat' if self.data.is_private and self.data.recipient_jid else 'groupchat'
        to_jid = self.data.recipient_jid if msg_type == 'chat' else None
      
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
        self.notification_mode = "stack"
        self.muted = False
  
    def set_notification_mode(self, mode: str):
        """Set notification mode: 'stack' or 'replace'"""
        if mode in ["stack", "replace"]:
            self.notification_mode = mode
  
    def set_muted(self, muted: bool):
        """Set muted state"""
        self.muted = muted
  
    def show_notification(self, data: NotificationData):
        """Create and show notification (unless muted)"""
        # If muted, don't show notification
        if self.muted:
            return None
       
        self.config = data.config
       
        # In replace mode, close existing notifications EXCEPT those with active reply fields
        if self.notification_mode == "replace" and self.popups:
            for popup in list(self.popups):
                # Keep notifications with visible reply field
                if not popup.reply_field_visible:
                    popup.close_immediately()
                    self.popups.remove(popup)
      
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
        """Position all popups and handle overflow"""
        if not self.popups:
            return
      
        screen = self.popups[0].screen().availableGeometry()
      
        # Get notification position from config (default "center")
        position = self.config.get("ui", "notification_position") if self.config else "center"
        position = (position or "center").lower()
      
        # Calculate x position based on setting (use first popup's width)
        popup_width = self.popups[0].width()
        if position == "left":
            x = screen.x() + 20
        elif position == "right":
            x = screen.x() + screen.width() - popup_width - 20
        else: # center (default)
            x = screen.x() + (screen.width() - popup_width) // 2
      
        # Position all popups from top down
        current_y = screen.y() + 20
        for popup in self.popups:
            popup.move(x, current_y)
            current_y += popup.height() + self.gap
        
        # Only handle overflow in stack mode
        if self.notification_mode == "stack":
            heights = [p.height() for p in self.popups]
            total_height = sum(heights) + self.gap * max(0, len(heights) - 1)
            available_height = screen.height() - 40
          
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
                current_y = screen.y() + 20
                for popup in self.popups:
                    popup.move(x, current_y)
                    current_y += popup.height() + self.gap


# Global manager
popup_manager = PopupManager()


def show_notification(**kwargs):
    data = NotificationData(**kwargs)
    return popup_manager.show_notification(data)
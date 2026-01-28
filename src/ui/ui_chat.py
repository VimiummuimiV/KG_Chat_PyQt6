"""Chat window with XMPP integration"""
import threading
import re
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import(
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QApplication,
    QStackedWidget, QStatusBar, QLabel, QProgressBar, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QEvent

from helpers.config import Config
from helpers.create import create_icon_button, update_all_icons, set_theme, HoverIconButton
from helpers.resize import handle_chat_resize, recalculate_layout
from helpers.color_utils import get_private_message_colors
from helpers.scroll import scroll
from helpers.cache import get_cache
from helpers.username_color_manager import(
    change_username_color,
    reset_username_color,
    update_from_server
)
from helpers.fonts import get_font, FontType
from helpers.voice_engine import get_voice_engine, play_sound
from helpers.me_action import format_me_action
from themes.theme import ThemeManager
from core.xmpp import XMPPClient
from core.messages import Message
from ui.ui_messages import MessagesWidget
from ui.ui_userlist import UserListWidget
from ui.ui_chatlog import ChatlogWidget
from ui.ui_chatlog_userlist import ChatlogUserlistWidget
from ui.ui_profile import ProfileWidget
from ui.ui_emoticon_selector import EmoticonSelectorWidget
from ui.ui_pronunciation import PronunciationWidget
from ui.ui_banlist import BanListWidget
from ui.ui_buttons import ButtonPanel
from components.notification import show_notification
from components.messages_separator import NewMessagesSeparator


class SignalEmitter(QObject):
    message_received = pyqtSignal(object)
    presence_received = pyqtSignal(object)
    bulk_update_complete = pyqtSignal()
    connection_changed = pyqtSignal(str)

class ChatWindow(QWidget):
    def __init__(
        self,
        account=None,
        app_controller=None,
        pronunciation_manager=None,
        ban_manager=None
        ):
        super().__init__()

        self.app_controller = app_controller
        self.pronunciation_manager = pronunciation_manager
        self.ban_manager = ban_manager
        self.tray_mode = False
        self.really_close = False
        self.account = account
        self.xmpp_client = None
        self.signal_emitter = SignalEmitter()
        self.cache = get_cache()
        self.initial_roster_loading = False
        self.auto_hide_messages_userlist = True
        self.auto_hide_chatlog_userlist = True

        # Simple connection state tracking
        self.is_connecting = False # True when attempting to connect
        self.allow_reconnect = True # Disable when switching accounts

        # Private messaging state
        self.private_mode = False
        self.private_chat_jid = None
        self.private_chat_username = None
        self.private_chat_user_id = None

        # Track new messages marker
        self.has_new_messages_marker = False

        # Initialize paths and config
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.icons_path = Path(__file__).parent.parent / "icons"

        self.config = Config(str(self.config_path))
        self.theme_manager = ThemeManager(self.config)
        self.theme_manager.apply_theme()
        set_theme(self.theme_manager.is_dark())

        # Initialize voice engine
        self.voice_engine = get_voice_engine()
        # Pass pronunciation manager to voice engine
        if self.pronunciation_manager:
            self.voice_engine.set_pronunciation_manager(self.pronunciation_manager)
        self.mention_sound_path = None
        self.ban_sound_path = None
        self._setup_sounds()

        self._init_ui()

        self.signal_emitter.message_received.connect(self.on_message)
        self.signal_emitter.presence_received.connect(self.on_presence)
        self.signal_emitter.bulk_update_complete.connect(self.on_bulk_update_complete)
        self.signal_emitter.connection_changed.connect(self.set_connection_status)

        if account:
            self.set_connection_status('connecting')
            self.connect_xmpp()

        # Parse status references (created dynamically)
        self.parse_status_widget = None
        self.parse_progress_bar = None
        self.parse_current_label = None

    def set_tray_mode(self, enabled: bool):
        self.tray_mode = enabled

    def on_change_username_color(self):
        """Called from ButtonPanel to change own username color."""
        if not self.app_controller:
            QMessageBox.warning(self, "Unavailable", "This action requires the application controller.")
            return
        self.app_controller._refresh_own_username_color(change_username_color)

    def on_reset_username_color(self):
        """Called from ButtonPanel to reset own username color."""
        if not self.app_controller:
            QMessageBox.warning(self, "Unavailable", "This action requires the application controller.")
            return
        self.app_controller._refresh_own_username_color(reset_username_color)

    def on_update_username_color(self):
        """Called from ButtonPanel to update own username color from server."""
        if not self.app_controller:
            QMessageBox.warning(self, "Unavailable", "This action requires the application controller.")
            return
        self.app_controller._refresh_own_username_color(update_from_server)

    def on_toggle_voice_sound(self):
        """Toggle TTS (Voice Sound) from the panel button."""
        current = self.config.get("sound", "tts_enabled") or False
        new = not current
        
        # Persist centrally via app controller so tray stays in sync
        config = self.app_controller.config if self.app_controller else self.config
        config.set("sound", "tts_enabled", value=new)
        # Also update local config data to keep in sync
        if self.app_controller:
            self.config.data = self.app_controller.config.data
        
        # update tray menu state immediately
        if self.app_controller and hasattr(self.app_controller, 'update_sound_menu'):
            self.app_controller.update_sound_menu()
        
        # Update engine and visual
        self.voice_engine.set_enabled(new)
        self.button_panel.set_button_state(self.button_panel.voice_button, new)

    def update_voice_button_state(self):
        """Sync voice button visual and engine state with config."""
        enabled = self.config.get("sound", "tts_enabled") or False
        self.voice_engine.set_enabled(enabled)
        
        # Defensive: button may not exist yet in some tests
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'voice_button', None):
            self.button_panel.set_button_state(self.button_panel.voice_button, enabled)

    def on_toggle_mention_beep(self):
        """Toggle mention beep on/off from the panel button."""
        current = self.config.get("sound", "mention_sound_enabled")
        if current is None:
            current = True
        new = not current

        # Persist centrally via app controller so tray stays in sync
        config = self.app_controller.config if self.app_controller else self.config
        config.set("sound", "mention_sound_enabled", value=new)
        # Also update local config data to keep in sync
        if self.app_controller:
            self.config.data = self.app_controller.config.data

        # update tray menu state immediately
        if self.app_controller and hasattr(self.app_controller, 'update_sound_menu'):
            self.app_controller.update_sound_menu()

        # Update visual
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'mention_button', None):
            self.button_panel.set_button_state(self.button_panel.mention_button, new)

    def update_mention_button_state(self):
        """Sync mention button visual to config state."""
        enabled = self.config.get("sound", "mention_sound_enabled")
        if enabled is None:
            enabled = True
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'mention_button', None):
            self.button_panel.set_button_state(self.button_panel.mention_button, enabled)

    def _setup_sounds(self):
        """Setup mention and ban sound paths"""
        sounds_dir = Path(__file__).parent.parent / "sounds"
        
        # Setup mention sound
        mention_sound_path = sounds_dir / "mention.mp3"
        self.mention_sound_path = str(mention_sound_path) if mention_sound_path.exists() else None
        
        # Setup ban sound
        ban_sound_path = sounds_dir / "banned.mp3"
        self.ban_sound_path = str(ban_sound_path) if ban_sound_path.exists() else None

    def _init_ui(self):
        window_title = f"Chat - {self.account['chat_username']}" if self.account else "Chat"
        self.setWindowTitle(window_title)
        geo = QApplication.primaryScreen().availableGeometry()
      
        # Calculate width: 70% of viewport width, or full width if viewport < 1000px
        window_width = geo.width() if geo.width() < 1000 else int(geo.width() * 0.7)
      
        # Set window size: dynamic width and full height minus 32px for taskbar/spacing
        self.resize(window_width, geo.height() - 32)
      
        # Center window horizontally, align to top of screen
        self.move(geo.x() + (geo.width() - window_width) // 2, geo.y())
      
        # Set minimum window dimensions
        self.setMinimumSize(400, 400)

        # Use config for margins and spacing
        window_margin = self.config.get("ui", "margins", "window") or 10
        window_spacing = self.config.get("ui", "spacing", "window_content") or 10
    
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(window_margin, window_margin, window_margin, window_margin)
        main_layout.setSpacing(window_spacing)
        self.setLayout(main_layout)

        # Create wrapper layout for content + button panel
        content_wrapper = QHBoxLayout()
        content_spacing = self.config.get("ui", "spacing", "widget_content") or 6
        content_wrapper.setSpacing(content_spacing)
        main_layout.addLayout(content_wrapper, stretch=1)

        # Content layout: left (messages/chatlog) + right (userlist)
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(content_spacing)
        content_wrapper.addLayout(self.content_layout, stretch=1)

        # Left side layout
        left_layout = QVBoxLayout()
        left_layout.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        self.content_layout.addLayout(left_layout, stretch=3)

        # Stacked widget for Messages/Chatlog views
        self.stacked_widget = QStackedWidget()
        left_layout.addWidget(self.stacked_widget, stretch=1)

        my_username = self.account.get('chat_username') if self.account else None
        self.messages_widget = MessagesWidget(self.config, my_username=my_username)
        self.stacked_widget.addWidget(self.messages_widget)
        self.chatlog_widget = None
        self.chatlog_userlist_widget = None

        # Input area
        self.input_container = QWidget()
        input_main_layout = QVBoxLayout()
        input_main_layout.setContentsMargins(0, 0, 0, 0)
        input_main_layout.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        self.input_container.setLayout(input_main_layout)
        left_layout.addWidget(self.input_container, alignment=Qt.AlignmentFlag.AlignBottom)
    
        button_spacing = self.config.get("ui", "buttons", "spacing") or 8
    
        self.input_top_layout = QHBoxLayout()
        self.input_top_layout.setSpacing(button_spacing)
        input_main_layout.addLayout(self.input_top_layout)
    
        self.input_bottom_layout = QHBoxLayout()
        self.input_bottom_layout.setSpacing(button_spacing)
        input_main_layout.addLayout(self.input_bottom_layout)
    
        self.input_field = QLineEdit()
        self.input_field.setFont(get_font(FontType.TEXT))
        self.input_field.setFixedHeight(48)
        self.input_field.returnPressed.connect(self.send_message)
        self.input_top_layout.addWidget(self.input_field, stretch=1)
    
        self.messages_widget.set_input_field(self.input_field)
    
        self.send_button = create_icon_button(self.icons_path, "send.svg", "Send Message", config=self.config)
        self.send_button.clicked.connect(self.send_message)
        self.input_top_layout.addWidget(self.send_button)
    
        # Exit private mode button reference (created dynamically when needed)
        self.exit_private_button = None
    
        # Emoticon button with hover icons
        self.emoticon_button = HoverIconButton(
            self.icons_path,
            "emotion-normal.svg",
            "emotion-happy.svg",
            "Toggle Emoticon Selector"
        )
        self.emoticon_button.clicked.connect(self._toggle_emoticon_selector)
        self.input_top_layout.addWidget(self.emoticon_button)
    
        # Messages userlist with private mode callback
        self.user_list_widget = UserListWidget(self.config, self.input_field, self.ban_manager)
        self.user_list_widget.profile_requested.connect(self.show_profile_view)
        self.user_list_widget.private_chat_requested.connect(self.enter_private_mode)

        messages_userlist_visible = self.config.get("ui", "messages_userlist_visible")
        if messages_userlist_visible is not None:
            self.user_list_widget.setVisible(messages_userlist_visible)
        else:
            self.user_list_widget.setVisible(True)
        self.content_layout.addWidget(self.user_list_widget, stretch=1)
     
        # Create button panel (right side, vertical scrollable)
        # Add to content_wrapper so it's always on the right
        self.button_panel = ButtonPanel(self.config, self.icons_path, self.theme_manager)
        self.button_panel.toggle_userlist_requested.connect(self.toggle_user_list)
        self.button_panel.toggle_theme_requested.connect(self.toggle_theme)
        self.button_panel.switch_account_requested.connect(self._on_switch_account)
        self.button_panel.toggle_voice_requested.connect(self.on_toggle_voice_sound)
        self.button_panel.pronunciation_requested.connect(self.show_pronunciation_view)
        self.button_panel.toggle_mention_requested.connect(self.on_toggle_mention_beep)
        # Color management connections (change / reset / update-from-server)
        self.button_panel.change_color_requested.connect(self.on_change_username_color)
        self.button_panel.reset_color_requested.connect(self.on_reset_username_color)
        self.button_panel.update_color_requested.connect(self.on_update_username_color)
        content_wrapper.addWidget(self.button_panel, stretch=0)

        # Initialize voice and mention button state
        self.update_voice_button_state()
        self.update_mention_button_state()

     
        # Initialize userlist button state
        messages_userlist_visible = self.config.get("ui", "messages_userlist_visible")
        if messages_userlist_visible is not None:
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, messages_userlist_visible)
        else:
            # Default to visible
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, True)
     
        # Emoticon selector widget (overlay - positioned absolutely)
        # Create AFTER userlist so positioning works correctly
        # Share emoticon_manager from messages_widget to avoid loading emoticons twice
        self.emoticon_selector = EmoticonSelectorWidget(
            self.config,
            self.messages_widget.emoticon_manager, # Reuse from MessagesWidget
            self.icons_path
        )
        self.emoticon_selector.emoticon_selected.connect(self._on_emoticon_selected)
        self.emoticon_selector.setParent(self) # Make it float above other widgets
     
        # Install a minimal event filter to detect clicks outside selector
        # (install on window and application with a single line to keep it simple)
        self.installEventFilter(self)
        try:
            app = QApplication.instance()
            if app:
                app.installEventFilter(self)
        except Exception:
            pass

        # Position will be set in showEvent
        QTimer.singleShot(50, self._position_emoticon_selector)
     
        self.messages_widget.timestamp_clicked.connect(self.show_chatlog_view)
    
        self._update_input_style()

    def _toggle_emoticon_selector(self):
        """Toggle emoticon selector visibility"""
        if hasattr(self, 'emoticon_selector'):
            self.emoticon_selector.toggle_visibility()
            self._position_emoticon_selector()
 
    def _on_emoticon_selected(self, emoticon_name: str):
        """Handle emoticon selection"""
        # Insert emoticon code at cursor position
        cursor_pos = self.input_field.cursorPosition()
        current_text = self.input_field.text()
        emoticon_code = f":{emoticon_name}:"
     
        new_text = current_text[:cursor_pos] + emoticon_code + current_text[cursor_pos:]
        self.input_field.setText(new_text)
     
        # Move cursor after inserted emoticon
        self.input_field.setCursorPosition(cursor_pos + len(emoticon_code))
     
        # Focus input field
        self.input_field.setFocus()
 
    def _position_emoticon_selector(self):
        """Place selector aligned to emoticon button (simple, predictable)."""
        if not hasattr(self, 'emoticon_selector'):
            return

        # Clamp size to available space
        available = max(200, self.height() - self.input_container.height() - 40)
        h = max(250, min(650, available))
        w = 420
        self.emoticon_selector.setFixedSize(w, h)

        # Align selector right edge to emoticon button right edge
        btn_global = self.emoticon_button.mapToGlobal(self.emoticon_button.rect().topRight())
        btn_top_right = self.mapFromGlobal(btn_global)
        x = btn_top_right.x() - w

        # Place above input area with small margin and keep on-screen
        y = max(16, self.height() - self.input_container.height() - h - 16)
        x = max(8, min(x, self.width() - w - 8))

        self.emoticon_selector.move(x, y)
        self.emoticon_selector.raise_()

    def eventFilter(self, obj, event):
        """Event filter to handle clicks outside emoticon selector"""
        if event.type() == QEvent.Type.MouseButtonPress:
            if hasattr(self, 'emoticon_selector') and self.emoticon_selector.isVisible():
                try:
                    gp = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                    w = QApplication.widgetAt(gp)
                    # Walk up parents to see if click landed inside selector or on the button
                    inside = False
                    while w:
                        if w == self.emoticon_selector or w == self.emoticon_button:
                            inside = True
                            break
                        w = w.parentWidget()
                    if not inside:
                        self.emoticon_selector.setVisible(False)
                        self.config.set("ui", "emoticon_selector_visible", value=False)
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        """Handle window show events"""
        super().showEvent(event)
        
        # Reset unread count when window becomes visible
        if self.app_controller:
            self.app_controller.reset_unread()

        # Position emoticon selector when showing
        if hasattr(self, 'emoticon_selector'):
            QTimer.singleShot(50, self._position_emoticon_selector)
            if self.emoticon_selector.isVisible():
                QTimer.singleShot(100, self.emoticon_selector.resume_animations)

        # Restore delegate references and restart animations when showing
        try:
            if self.messages_widget and getattr(self.messages_widget, 'delegate', None):
                self.messages_widget.delegate.set_list_view(self.messages_widget.list_view)
                # Ensure timer is running
                if not self.messages_widget.delegate.animation_timer.isActive():
                    self.messages_widget.delegate.animation_timer.start(33)
                # Restart any QMovie instances
                for movie in self.messages_widget.delegate._movie_cache.values():
                    try:
                        movie.start()
                    except Exception:
                        pass
        except Exception as e:
            print(f"ShowEvent resume animations error: {e}")

    def disable_reconnect(self):
        """Disable auto-reconnect (called when switching accounts)"""
        self.allow_reconnect = False

    def _clear_for_reconnect(self):
        """Clear messages and userlist for fresh reconnection"""
        # Clear all messages to avoid duplicates (server will send last 20 again)
        self.messages_widget.clear()
    
        # Clear userlist completely (will rebuild from fresh roster)
        if hasattr(self.user_list_widget, 'clear_all'):
            self.user_list_widget.clear_all()
    
        # Exit private mode if active
        if self.private_mode:
            self.exit_private_mode()

    def _is_connected(self):
        """Check if XMPP client is connected"""
        return self.xmpp_client and hasattr(self.xmpp_client, 'sid') and self.xmpp_client.sid

    def enter_private_mode(self, jid: str, username: str, user_id: str):
        """Enter private chat mode with a user"""
        # If switching to a different user, clear previous private messages
        if self.private_mode and self.private_chat_jid != jid:
            self._clear_private_messages()
    
        self.private_mode = True
        # Prefer explicit private recipient JID (user_id#username@domain/web) for private messages
        private_recipient_jid = jid
        if user_id and username:
            domain = None
            # Prefer XMPP client configured domain if available
            if hasattr(self, 'xmpp_client') and self.xmpp_client and getattr(self.xmpp_client, 'domain', None):
                domain = self.xmpp_client.domain
            else:
                # Fallback: try to extract domain from the provided jid
                if '@' in jid:
                    try:
                        domain = jid.split('@', 1)[1].split('/')[0]
                    except Exception:
                        domain = None
            if domain:
                private_recipient_jid = f"{user_id}#{username}@{domain}/web"

        self.private_chat_jid = private_recipient_jid
        self.private_chat_username = username
        self.private_chat_user_id = user_id

        # Clear input field
        self.input_field.clear()
    
        # Create exit button if it doesn't exist
        if self.exit_private_button is None:
            self.exit_private_button = create_icon_button(
                self.icons_path, "close.svg", "Exit Private Chat", config=self.config
            )
            self.exit_private_button.clicked.connect(self.exit_private_mode)
        
            # Insert after emoticon button
            emoticon_button_index = self.input_top_layout.indexOf(self.emoticon_button)
            self.input_top_layout.insertWidget(emoticon_button_index + 1, self.exit_private_button)
        else:
            self.exit_private_button.setVisible(True)
    
        # Update UI
        self._update_input_style()

        # Focus input for immediate typing
        self.input_field.setFocus()
    
        # Update window title
        base = f"Chat - {self.account['chat_username']}" if self.account else "Chat"
        status = self.windowTitle().split(' - ')[-1] if ' - ' in self.windowTitle() else ""
        if status in ['Online', 'Offline', 'Connecting']:
            self.setWindowTitle(f"{base} - Private with {username} - {status}")
        else:
            self.setWindowTitle(f"{base} - Private with {username}")
    
        print(f"🔒 Entered private mode with {username}")

    def exit_private_mode(self):
        """Exit private chat mode"""
        # Clear all private messages
        self._clear_private_messages()
    
        self.private_mode = False
        self.private_chat_jid = None
        self.private_chat_username = None
        self.private_chat_user_id = None
    
        # Remove and destroy exit button
        if self.exit_private_button is not None:
            # Remove from layout and destroy
            self.input_top_layout.removeWidget(self.exit_private_button)
            self.exit_private_button.deleteLater()
            self.exit_private_button = None
    
        # Update UI
        self._update_input_style()
    
        # Restore window title
        self.set_connection_status(self.windowTitle().split(' - ')[-1] if ' - ' in self.windowTitle() else 'Online')
    
        print("🔓 Exited private mode")

    def _clear_private_messages(self):
        """Clear all private messages from the messages widget"""
        self.messages_widget.clear_private_messages()

    def _update_input_style(self):
        """Update input field styling based on private mode"""
        is_dark = self.theme_manager.is_dark()
    
        if self.private_mode:
            # Get private message colors from config
            colors = get_private_message_colors(self.config, is_dark)
        
            self.input_field.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {colors["input_bg"]};
                    color: {colors["text"]};
                    border: 2px solid {colors["input_border"]};
                    border-radius: 4px;
                    padding: 8px;
                }}
            """)
            self.input_field.setPlaceholderText(f"Private message to {self.private_chat_username}...")
        else:
            # Normal mode - remove custom styling
            self.input_field.setStyleSheet("")
            self.input_field.setPlaceholderText("")

    def show_messages_view(self):
        """Switch back to messages and conditionally destroy chatlog widgets"""
        # Cleanup and destroy chatlog userlist
        if self.chatlog_userlist_widget:
            try:
                self.chatlog_userlist_widget.filter_requested.disconnect()
                self.chatlog_userlist_widget.clear_cache()
            except:
                pass
            self.content_layout.removeWidget(self.chatlog_userlist_widget)
            self.chatlog_userlist_widget.deleteLater()
            self.chatlog_userlist_widget = None

        # For chatlog widget, destroy only if not parsing
        if self.chatlog_widget:
            if self.chatlog_widget.parser_widget.is_parsing:
                # Keep alive during parsing, just switch view
                pass
            else:
                try:
                    self.chatlog_widget.back_requested.disconnect()
                    self.chatlog_widget.messages_loaded.disconnect()
                    self.chatlog_widget.filter_changed.disconnect()
                    self.chatlog_widget.cleanup()
                except:
                    pass
                self.stacked_widget.removeWidget(self.chatlog_widget)
                self.chatlog_widget.deleteLater()
                self.chatlog_widget = None

        self.stacked_widget.setCurrentWidget(self.messages_widget)

        # Restore messages userlist based on width
        width = self.width()
        messages_userlist_visible = self.config.get("ui", "messages_userlist_visible")
        if messages_userlist_visible is None:
            messages_userlist_visible = True

        if width > 800 and messages_userlist_visible:
            self.user_list_widget.setVisible(True)
        elif width <= 800:
            self.user_list_widget.setVisible(False)

        # Sync button state for messages userlist
        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(
                self.button_panel.toggle_userlist_button,
                self.user_list_widget.isVisible()
            )

        QTimer.singleShot(50, lambda: scroll(self.messages_widget.scroll_area, mode="bottom"))

        # If parsing ongoing, show status widget
        if self.chatlog_widget and self.chatlog_widget.parser_widget.is_parsing:
            self.start_parse_status()

    def show_chatlog_view(self, timestamp: str = None):
        """Open chatlog for today"""
        # Hide messages userlist
        if self.user_list_widget.isVisible():
            self.user_list_widget.setVisible(False)
       
        if not self.chatlog_widget:
            # Pass parent_window=self for modal dialogs and ban_manager
            self.chatlog_widget = ChatlogWidget(
                self.config, 
                self.icons_path, 
                self.account, 
                parent_window=self,
                ban_manager=self.ban_manager
            )
            self.chatlog_widget.back_requested.connect(self.show_messages_view)
            self.chatlog_widget.messages_loaded.connect(self._on_chatlog_messages_loaded)
            self.chatlog_widget.filter_changed.connect(self._on_chatlog_filter_changed)
            self.stacked_widget.addWidget(self.chatlog_widget)
           
            width = self.width()
            self.chatlog_widget.set_compact_mode(width <= 1000)
            self.chatlog_widget.set_compact_layout(width <= 1000)
       
        if not self.chatlog_userlist_widget:
            self.chatlog_userlist_widget = ChatlogUserlistWidget(
                self.config,
                self.icons_path,
                self.cache._color_cache,
                self.ban_manager
            )
            self.chatlog_userlist_widget.filter_requested.connect(self._on_filter_requested)
            self.content_layout.addWidget(self.chatlog_userlist_widget, stretch=1)
       
        # Show chatlog userlist based on config and width
        width = self.width()
        chatlog_userlist_visible = self.config.get("ui", "chatlog_userlist_visible")
        if chatlog_userlist_visible is None:
            chatlog_userlist_visible = True
       
        if width > 800 and chatlog_userlist_visible:
            self.chatlog_userlist_widget.setVisible(True)
        else:
            self.chatlog_userlist_widget.setVisible(False)

        # Sync button state for chatlog userlist
        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(
                self.button_panel.toggle_userlist_button,
                self.chatlog_userlist_widget.isVisible()
            )
       
        # Sync userlist ban visibility with chatlog parse mode
        if self.chatlog_widget and self.chatlog_userlist_widget:
            self.chatlog_userlist_widget.set_show_banned(self.chatlog_widget.is_parsing)
       
        # Only load daily chatlog if not in parser mode
        if not self.chatlog_widget.parser_visible:
            self.chatlog_widget.current_date = datetime.now().date()
            self.chatlog_widget._update_date_display()
            self.chatlog_widget.load_current_date()
       
        self.stacked_widget.setCurrentWidget(self.chatlog_widget)

    def show_parser_view(self):
        """Switch to chatlog view and show parser"""
        self.show_chatlog_view()
        if self.chatlog_widget and not self.chatlog_widget.parser_visible:
            self.chatlog_widget._toggle_parser()
        if self.parse_status_widget:
            self.parse_status_widget.setVisible(False)

    def _create_parse_status_widget(self):
        """Create the parse status widget dynamically"""
        parse_status_widget = QWidget()
        parse_status_layout = QHBoxLayout()
        parse_status_widget.setLayout(parse_status_layout)

        parse_progress_bar = QProgressBar()
        parse_status_layout.addWidget(parse_progress_bar, stretch=1)

        parse_current_label = QLabel("")
        parse_status_layout.addWidget(parse_current_label)

        stop_parse_btn = create_icon_button(self.icons_path, "stop.svg", "Stop Parsing", config=self.config)
        stop_parse_btn.setObjectName("stop_parse_btn")
        stop_parse_btn.clicked.connect(lambda: self.chatlog_widget._on_parse_cancelled() if self.chatlog_widget else None)
        parse_status_layout.addWidget(stop_parse_btn)

        view_parser_btn = create_icon_button(self.icons_path, "list.svg", "View Parser", config=self.config)
        view_parser_btn.clicked.connect(self.show_parser_view)
        parse_status_layout.addWidget(view_parser_btn)

        # Add to main layout
        main_layout = self.layout()
        main_layout.addWidget(parse_status_widget)

        return parse_status_widget, parse_progress_bar, parse_current_label

    def start_parse_status(self):
        """Start showing parse status"""
        if self.parse_status_widget is None:
            self.parse_status_widget, self.parse_progress_bar, self.parse_current_label = self._create_parse_status_widget()
        self.parse_status_widget.setVisible(True)
        self.parse_progress_bar.setValue(0)
        self.parse_current_label.setText("")

    def stop_parse_status(self):
        """Stop showing parse status and destroy widget"""
        if self.parse_status_widget:
            main_layout = self.layout()
            main_layout.removeWidget(self.parse_status_widget)
            self.parse_status_widget.deleteLater()
            self.parse_status_widget = None
            self.parse_progress_bar = None
            self.parse_current_label = None

    def update_parse_progress(self, start_date: str, current_date: str, percent: int):
        if self.parse_progress_bar:
            self.parse_progress_bar.setValue(percent)
            self.parse_current_label.setText(f"{start_date} - {current_date}")

    def on_parse_finished(self):
        self.handle_parse_finished()

    def handle_parse_finished(self):
        """Keep parse status visible but update to finished state"""
        if self.parse_status_widget:
            # Hide stop button
            stop_btn = self.parse_status_widget.findChild(QPushButton, "stop_parse_btn")
            if stop_btn:
                stop_btn.setVisible(False)
            # Update label
            self.parse_current_label.setText("Parsing finished")

    def on_parse_error(self, error_msg: str):
        self.stop_parse_status()
        show_notification(title="Parse Error", message=error_msg, config=self.config, account=self.account)

    def _on_chatlog_messages_loaded(self, messages):
        if self.chatlog_userlist_widget and messages:
            # Sync show_banned state with chatlog parse mode
            if self.chatlog_widget:
                self.chatlog_userlist_widget.set_show_banned(self.chatlog_widget.is_parsing)
            
            self.chatlog_userlist_widget.load_from_messages(messages)

    def _on_filter_requested(self, usernames: set):
        """Handle filter request from userlist"""
        if self.chatlog_widget:
            self.chatlog_widget.set_username_filter(usernames)

    def _on_chatlog_filter_changed(self, usernames: set):
        """Handle filter change from chatlog widget"""
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        handle_chat_resize(self, self.width())

    def _complete_resize_recalculation(self):
        """Complete resize with aggressive recalculation"""
        current = self.stacked_widget.currentWidget()
        if current == self.messages_widget:
            self.messages_widget._force_recalculate()
            QTimer.singleShot(50, lambda: scroll(self.messages_widget.scroll_area, mode="bottom"))
        elif current == self.chatlog_widget and self.chatlog_widget:
            self.chatlog_widget._force_recalculate()
            QTimer.singleShot(50, lambda: scroll(self.chatlog_widget.list_view, mode="bottom"))

    def connect_xmpp(self):
        def _worker():
            self.is_connecting = True
            try:
                # Clear old state before reconnecting
                QTimer.singleShot(0, self._clear_for_reconnect)
            
                self.xmpp_client = XMPPClient(str(self.config_path))
                if not self.xmpp_client.connect(self.account):
                    QTimer.singleShot(0, lambda: show_notification(
                        title="Connection Failed",
                        message="Could not connect to XMPP server",
                        config=self.config,
                        account=self.account
                    ))
                    self.signal_emitter.connection_changed.emit('offline')
                    return

                self.xmpp_client.set_message_callback(self.message_callback)
                self.xmpp_client.set_presence_callback(self.presence_callback)

                self.initial_roster_loading = True
                rooms = self.xmpp_client.account_manager.get_rooms()
                for room in rooms:
                    if room.get('auto_join'):
                        try:
                            self.xmpp_client.join_room(room['jid'])
                        except:
                            pass

                self.initial_roster_loading = False
                QTimer.singleShot(0, lambda: self.signal_emitter.bulk_update_complete.emit())
            
                self.signal_emitter.connection_changed.emit('online')

                listen_thread = threading.Thread(target=self.xmpp_client.listen, daemon=True)
                listen_thread.start()
                listen_thread.join()
            
                # Connection ended - clear sid to allow reconnection
                if self.xmpp_client:
                    self.xmpp_client.sid = None
                    self.xmpp_client.jid = None
            
                self.signal_emitter.connection_changed.emit('offline')
            except Exception as e:
                # Clear sid on error too
                if self.xmpp_client:
                    self.xmpp_client.sid = None
                    self.xmpp_client.jid = None
            
                QTimer.singleShot(0, lambda: show_notification(
                    title="Error",
                    message=f"Connection error: {e}",
                    config=self.config,
                    account=self.account
                ))
                self.signal_emitter.connection_changed.emit('offline')
            finally:
                self.is_connecting = False

        threading.Thread(target=_worker, daemon=True).start()

    def message_callback(self, msg):
        self.signal_emitter.message_received.emit(msg)

    def presence_callback(self, pres):
        self.signal_emitter.presence_received.emit(pres)

    def add_local_message(self, msg):
        self.messages_widget.add_message(msg)

    def _is_ban_message(self, msg):
        """Detect if a message is a ban message from Клавобот"""
        if not msg.body or not msg.login:
            return False
        return msg.login == 'Клавобот' and all(word in msg.body for word in ['Пользователь', 'заблокирован'])
    
    def _extract_user_id_from_message(self, msg):
        """Extract user ID from message JID"""
        if not msg.from_jid:
            return None
        
        try:
            # JID format: room@domain/user_id#username
            if '#' in msg.from_jid:
                parts = msg.from_jid.split('/')[-1].split('#')
                if len(parts) >= 2:
                    return parts[0]
        except:
            pass
        
        return None
    
    def _is_user_banned(self, user_id: str = None, username: str = None) -> bool:
        """Check if a user is banned by ID or username"""
        if not self.ban_manager:
            return False
        
        # Check by user_id (primary)
        if user_id and self.ban_manager.is_banned_by_id(str(user_id)):
            return True
        
        # Fallback check by username
        if not user_id and username and self.ban_manager.is_banned_by_username(username):
            return True
        
        return False

    def on_message(self, msg):
        # Check if initial load
        is_initial = getattr(msg, 'initial', False)

        # Skip own messages (server echoes groupchat messages back)
        if msg.login == self.account.get('chat_username') and not is_initial:
            return

        # CHECK IF USER IS BANNED - BLOCK IMMEDIATELY
        if msg.login:
            user_id = self._extract_user_id_from_message(msg)
            if self._is_user_banned(user_id, msg.login):
                return  # Silently drop banned user's messages

        msg.is_private = (msg.msg_type == 'chat')
        
        # Check if this is a ban message and mark it
        is_ban = self._is_ban_message(msg)
        msg.is_ban = is_ban
        
        # Format message body for display/TTS and detect if it's a /me action
        display_body, is_system = format_me_action(msg.body, msg.login)

        if not is_initial and not self.isVisible() and not self.has_new_messages_marker:
            self.messages_widget.model.add_message(NewMessagesSeparator.create_marker())
            self.has_new_messages_marker = True

        # Add original message to widget (delegate will format it)
        self.messages_widget.add_message(msg)

        # Increment unread count if window is hidden and not initial load
        if not is_initial and not self.isVisible() and self.app_controller:
            self.app_controller.increment_unread()

        # Only speak if not initial load, has login, and window not active
        if not is_initial and msg.login and not self.isActiveWindow():
            tts_enabled = self.config.get("sound", "tts_enabled")
            if tts_enabled:
                # Update voice engine state
                self.voice_engine.set_enabled(True)
                my_username = self.account.get('chat_username', '')
                
                self.voice_engine.speak_message(
                    username=msg.login,
                    message=display_body,
                    my_username=my_username,
                    is_initial=is_initial,
                    is_private=msg.is_private,
                    is_ban=is_ban,
                    is_system=is_system
                )
            else:
                # Ensure voice engine is disabled
                self.voice_engine.set_enabled(False)

        # Only show notifications and play sounds if not initial load and window not active
        if not is_initial and not self.isActiveWindow():
            # Check for ban message first
            if is_ban:
                self._play_ban_sound()
            # Then check for mention
            elif self._message_mentions_me(msg):
                self._play_mention_sound()
        
            try:
                show_notification(
                    title=msg.login,
                    message=display_body,
                    xmpp_client=self.xmpp_client,
                    cache=self.cache,
                    config=self.config,
                    local_message_callback=self.add_local_message,
                    account=self.account,
                    window_show_callback=self._show_and_focus_window,
                    is_private=msg.is_private,
                    recipient_jid=msg.from_jid if msg.is_private else None,
                    is_ban=is_ban,
                    is_system=is_system
                )
            except Exception as e:
                print(f"Notification error: {e}")

    def _show_and_focus_window(self):
        if not self.isVisible():
            self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.activateWindow()
        self.raise_()

    def _message_mentions_me(self, msg):
        if not self.account or not msg.body:
            return False
        my_username = self.account.get('chat_username', '').lower()
        if not my_username:
            return False
        pattern = r'\b' + re.escape(my_username) + r'\b'
        return bool(re.search(pattern, msg.body.lower()))

    def _play_mention_sound(self):
        """Play mention sound"""
        mention_sound_enabled = self.config.get("sound", "mention_sound_enabled")
        if mention_sound_enabled is None:
            mention_sound_enabled = True  # Default to enabled
        
        if not mention_sound_enabled:
            print("🔇 Mention sound disabled")
            return
        
        if not self.mention_sound_path:
            try:
                QApplication.instance().beep()
            except Exception as e:
                print(f"System beep error: {e}")
            return
        
        def _play():
            try:
                play_sound(self.mention_sound_path)
            except Exception as e:
                print(f"Mention sound playback error: {e}")
        
        threading.Thread(target=_play, daemon=True).start()

    def _play_ban_sound(self):
        """Play ban sound"""
        def _play():
            try:
                play_sound(self.ban_sound_path)
            except Exception as e:
                print(f"Ban sound playback error: {e}")
        
        threading.Thread(target=_play, daemon=True).start()

    def on_presence(self, pres):
        if not self.xmpp_client or self.initial_roster_loading:
            return
    
        # CHECK IF USER IS BANNED - BLOCK PRESENCE UPDATES
        if pres and pres.login:
            if self._is_user_banned(pres.user_id, pres.login):
                return  # Silently drop banned user's presence
    
        if pres and pres.presence_type == 'available':
            self.user_list_widget.add_users(presence=pres)
        elif pres and pres.presence_type == 'unavailable':
            self.user_list_widget.remove_users(presence=pres)

    def on_bulk_update_complete(self):
        if not self.xmpp_client:
            return
        users = self.xmpp_client.user_list.get_online()
        self.user_list_widget.add_users(users=users, bulk=True)

    def on_font_size_changed(self):
        """Handle font size changes from font scaler - refresh all text"""
        # Debounce: prevent multiple rapid calls
        if hasattr(self, '_font_size_timer') and self._font_size_timer.isActive():
            return
        
        new_font = get_font(FontType.TEXT)
        font_size = new_font.pointSize()
        
        # Update message delegates
        for widget in [self.messages_widget, self.chatlog_widget]:
            if widget:
                widget.delegate.body_font = new_font
                widget.delegate.timestamp_font = new_font
                widget._force_recalculate()
        
        # Update message input field
        if self.input_field:
            self.input_field.setFont(new_font)
        
        # Update userlist widgets
        if self.user_list_widget:
            # Update section labels font size
            self.user_list_widget.chat_label.setFont(new_font)
            self.user_list_widget.game_label.setFont(new_font)
            
            # Update user widgets
            for user_widget in self.user_list_widget.user_widgets.values():
                user_widget.username_label.setFont(new_font)
            self.user_list_widget.update_width()
            self.user_list_widget.update()
        
        if self.chatlog_userlist_widget:
            for user_widget in self.chatlog_userlist_widget.user_widgets.values():
                user_widget.username_label.setFont(new_font)
                user_widget.count_label.setFont(new_font)
            self.chatlog_userlist_widget.update_width()
            self.chatlog_userlist_widget.update()
        
        # Update profile widget
        if hasattr(self, 'profile_widget') and self.profile_widget:
            self.profile_widget.username_history_label.setFont(new_font)
            for card in self.profile_widget.card_widgets:
                card.icon_label.setFont(new_font)
                card.label_widget.setFont(new_font)
                card.value_label.setFont(new_font)
            self.profile_widget.update()
        
        # Update pronunciation widget inputs
        if hasattr(self, 'pronunciation_widget') and self.pronunciation_widget:
            for item in self.pronunciation_widget.items:
                item.original_input.setFont(new_font)
                item.pronunciation_input.setFont(new_font)
            self.pronunciation_widget.update()
        
        # Update ban list widget inputs
        if hasattr(self, 'ban_list_widget') and self.ban_list_widget:
            for item in self.ban_list_widget.items:
                item.username_input.setFont(new_font)
                item.user_id_input.setFont(new_font)
            self.ban_list_widget.update()
        
        # Show font size in title, restore after 1500ms of no changes
        if not hasattr(self, '_base_title'):
            self._base_title = self.windowTitle()
        self.setWindowTitle(f"{self._base_title} - {font_size}")
        if hasattr(self, '_title_restore_timer'):
            self._title_restore_timer.stop()
        else:
            self._title_restore_timer = QTimer(self)
            self._title_restore_timer.setSingleShot(True)
            self._title_restore_timer.timeout.connect(lambda: self.setWindowTitle(self._base_title))
        self._title_restore_timer.start(1500)
        
        # Debounce timer
        self._font_size_timer = QTimer(self)
        self._font_size_timer.setSingleShot(True)
        self._font_size_timer.start(100)

    def send_message(self):
        text = self.input_field.text().strip()
        if not text or not self.xmpp_client:
            return

        self.input_field.clear()

        # Determine message type and recipient
        if self.private_mode and self.private_chat_jid:
            msg_type = 'chat'
            recipient_jid = self.private_chat_jid
        else:
            msg_type = 'groupchat'
            recipient_jid = None

        # Get own user data
        own_user = None
        for user in self.xmpp_client.user_list.get_all():
            if self.account.get('chat_username') in user.jid or user.login == self.account.get('chat_username'):
                own_user = user
                break

        # Chunk message if over 300 characters
        chunks = self._chunk_message(text, 300)

        # Send each chunk
        for i, chunk in enumerate(chunks):
            # Create and display own message immediately
            own_msg = Message(
                from_jid=self.xmpp_client.jid,
                body=chunk,
                msg_type=msg_type,
                login=self.account.get('chat_username'),
                avatar=None,
                background=own_user.background if own_user else None,
                timestamp=datetime.now(),
                initial=False
            )
            own_msg.is_private = (msg_type == 'chat')
        
            self.messages_widget.add_message(own_msg)
        
            delay = i * 0.8 # 800ms delay between chunks
            threading.Timer(
                delay,
                self.xmpp_client.send_message,
                args=(chunk, recipient_jid, msg_type)
            ).start()

    def _chunk_message(self, text: str, max_len: int) -> list:
        """Break message into chunks, keeping URLs intact"""
        if len(text) <= max_len:
            return [text]
    
        chunks = []
        url_pattern = re.compile(r'https?://[^\s]+')
    
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
        
            # Find a good break point
            chunk = text[:max_len]
        
            # Check if we're breaking a URL
            urls_in_chunk = list(url_pattern.finditer(chunk))
            if urls_in_chunk:
                last_url = urls_in_chunk[-1]
                # If URL extends beyond chunk, break before it
                if last_url.end() >= max_len - 10: # Give some buffer
                    # Check if there's content before the URL
                    if last_url.start() > 0:
                        chunk = text[:last_url.start()].rstrip()
                    else:
                        # URL at start, must include it even if long
                        chunk = text[:max_len]
            else:
                # Try to break at last space
                last_space = chunk.rfind(' ')
                if last_space > max_len * 0.7: # At least 70% filled
                    chunk = text[:last_space]
        
            chunks.append(chunk)
            text = text[len(chunk):].lstrip()
    
        return chunks

    def set_connection_status(self, status: str):
        status = (status or '').lower()
        text = {'connecting': 'Connecting', 'online': 'Online'}.get(status, 'Offline')
        base = f"Chat - {self.account['chat_username']}" if self.account else "Chat"

        # Preserve private mode in title
        if self.private_mode and self.private_chat_username:
            self.setWindowTitle(f"{base} - Private with {self.private_chat_username} - {text}")
        else:
            self.setWindowTitle(f"{base} - {text}")
        
        # AUTO-RECONNECT: If connection went offline, immediately attempt to reconnect
        if status == 'offline' and self.allow_reconnect and not self.is_connecting and self.account:
            print("🔄 Connection lost - initiating auto-reconnect...")
            QTimer.singleShot(100, self._auto_reconnect)

    def _auto_reconnect(self):
        """Automatic reconnection after connection loss"""
        # Double-check conditions before reconnecting
        if (self.allow_reconnect and 
            not self.is_connecting and 
            not self._is_connected() and 
            self.account):
            
            print("🔌 Auto-reconnecting...")
            self.set_connection_status('connecting')
            self.connect_xmpp()

    def toggle_user_list(self):
        """Toggle userlist based on current view with proper recalculation"""
    
        current_view = self.stacked_widget.currentWidget()
        is_chatlog_view = (current_view == self.chatlog_widget)
        width = self.width()
    
        if is_chatlog_view and self.chatlog_userlist_widget:
            # Toggle chatlog userlist
            visible = not self.chatlog_userlist_widget.isVisible()
            self.chatlog_userlist_widget.setVisible(visible)
            self.config.set("ui", "chatlog_userlist_visible", value=visible)
            self.auto_hide_chatlog_userlist = False
        else:
            # Toggle messages userlist
            visible = not self.user_list_widget.isVisible()
            self.user_list_widget.setVisible(visible)
            self.config.set("ui", "messages_userlist_visible", value=visible)
            self.auto_hide_messages_userlist = False
    
        # Update button visual state
        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, visible)

        # Force resize handler to sync everything
        QTimer.singleShot(10, lambda: handle_chat_resize(self, width))
    
        # Force recalculation after visibility change
        QTimer.singleShot(20, lambda: recalculate_layout(self))
    
    def _on_switch_account(self):
        """Handle switch account request from button panel"""
        if self.app_controller:
            self.app_controller.show_account_switcher()
    
    def show_profile_view(self, jid: str, username: str, user_id: str):
        """Show profile view for a user"""
        if not user_id:
            return

        if not hasattr(self, 'profile_widget') or not self.profile_widget:
            self.profile_widget = ProfileWidget(self.config, self.icons_path)
            self.profile_widget.back_requested.connect(self.show_messages_view)
            self.stacked_widget.addWidget(self.profile_widget)

        self.profile_widget.load_profile(int(user_id), username)
        self.stacked_widget.setCurrentWidget(self.profile_widget)
    
    def show_pronunciation_view(self):
        """Show pronunciation management view"""
        if not hasattr(self, 'pronunciation_widget') or not self.pronunciation_widget:
            self.pronunciation_widget = PronunciationWidget(
                self.config, 
                self.icons_path,
                self.pronunciation_manager
            )
            self.pronunciation_widget.back_requested.connect(self.show_messages_view)
            self.stacked_widget.addWidget(self.pronunciation_widget)
        
        self.stacked_widget.setCurrentWidget(self.pronunciation_widget)
    
    def show_ban_list_view(self):
        """Show ban list management view"""
        if not hasattr(self, 'ban_list_widget') or not self.ban_list_widget:
            self.ban_list_widget = BanListWidget(
                self.config, 
                self.icons_path,
                self.ban_manager
            )
            self.ban_list_widget.back_requested.connect(self.show_messages_view)
            self.stacked_widget.addWidget(self.ban_list_widget)
        
        self.stacked_widget.setCurrentWidget(self.ban_list_widget)
    
    def toggle_theme(self):
        try:
            self.theme_manager.toggle_theme()
            is_dark = self.theme_manager.is_dark()
            set_theme(is_dark)
         
            # Update theme button icon via button panel
            self.button_panel.update_theme_button_icon()
         
            # Clear cache so colors get recalculated
            self.cache.clear_colors()
         
            # Update input styling for theme
            self._update_input_style()
         
            update_all_icons()
         
            # Update messages emoticon manager theme
            self.messages_widget.emoticon_manager.set_theme(is_dark)
         
            # Update widgets
            self.messages_widget.update_theme()
            self.user_list_widget.update_theme()
         
            if self.chatlog_widget:
                # Update chatlog emoticon manager theme
                self.chatlog_widget.emoticon_manager.set_theme(is_dark)
                self.chatlog_widget.update_theme()
         
            if self.chatlog_userlist_widget:
                self.chatlog_userlist_widget.update_theme()
         
            if hasattr(self, 'profile_widget') and self.profile_widget:
                self.profile_widget.update_theme()
         
            # Update emoticon selector theme
            if hasattr(self, 'emoticon_selector'):
                self.emoticon_selector.update_theme()
         
            # Update button panel theme
            if hasattr(self, 'button_panel'):
                self.button_panel.update_theme()
         
            self.messages_widget.rebuild_messages()
         
            if self.chatlog_widget and self.stacked_widget.currentWidget() == self.chatlog_widget:
                self.chatlog_widget._force_recalculate()
         
            QApplication.processEvents()
        except Exception as e:
            print(f"Theme toggle error: {e}")

    def closeEvent(self, event):
        # Cleanup emoticon selector
        if hasattr(self, 'emoticon_selector'):
            self.emoticon_selector.cleanup()

        # Remove new messages marker when closing
        if self.has_new_messages_marker:
            NewMessagesSeparator.remove_from_model(self.messages_widget.model)
            self.has_new_messages_marker = False
    
        # If hiding to tray, do not perform full cleanup so animations and
        # delegate state remain intact. Full cleanup happens only when the
        # app is actually closing.
        if self.tray_mode and not self.really_close:
            event.ignore()
            self.hide()
            return

        # Reset unread when actually closing
        if self.app_controller:
            self.app_controller.reset_unread()

        # Proceed with full cleanup when actually closing
        if self.messages_widget:
            if hasattr(self.messages_widget, 'auto_scroller'):
                try:
                    self.messages_widget.auto_scroller.cleanup()
                except:
                    pass
            self.messages_widget.cleanup()
        if self.chatlog_widget:
            self.chatlog_widget.cleanup()

        if self.xmpp_client:
            try:
                self.xmpp_client.disconnect()
            except:
                pass
        self.set_connection_status('offline')

        # Shutdown voice engine
        if hasattr(self, 'voice_engine'):
            self.voice_engine.shutdown()
        event.accept()

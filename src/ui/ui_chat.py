"""Chat window with XMPP integration"""
import threading
import re
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QApplication, QStackedWidget
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont

from playsound3 import playsound

from helpers.config import Config
from helpers.create import create_icon_button, update_all_icons, set_theme
from helpers.resize import handle_chat_resize, recalculate_layout
from themes.theme import ThemeManager
from core.xmpp import XMPPClient
from core.messages import Message
from ui.ui_messages import MessagesWidget
from ui.ui_userlist import UserListWidget
from ui.ui_chatlog import ChatlogWidget
from ui.ui_chatlog_userlist import ChatlogUserlistWidget
from components.notification import show_notification
from helpers.scroll import scroll


class SignalEmitter(QObject):
    message_received = pyqtSignal(object)
    presence_received = pyqtSignal(object)
    bulk_update_complete = pyqtSignal()
    connection_changed = pyqtSignal(str)


class ChatWindow(QWidget):
    def __init__(self, account=None):
        super().__init__()
        
        self.tray_mode = False
        self.really_close = False
        self.account = account
        self.xmpp_client = None
        self.signal_emitter = SignalEmitter()
        self.color_cache = {}
        self.avatar_cache = {}
        self.initial_roster_loading = False
        self.auto_hide_messages_userlist = True
        self.auto_hide_chatlog_userlist = True
        
        self.mention_sound_path = None
        self._setup_mention_sound()
        
        self.config_path = Path(__file__).parent.parent / "settings" / "config.json"
        self.icons_path = Path(__file__).parent.parent / "icons"
        
        self.config = Config(str(self.config_path))
        self.theme_manager = ThemeManager(self.config)
        self.theme_manager.apply_theme()
        set_theme(self.theme_manager.is_dark())
        
        # Migrate old config if needed
        self._migrate_userlist_config()
        
        self._init_ui()
        
        self.signal_emitter.message_received.connect(self.on_message)
        self.signal_emitter.presence_received.connect(self.on_presence)
        self.signal_emitter.bulk_update_complete.connect(self.on_bulk_update_complete)
        self.signal_emitter.connection_changed.connect(self.set_connection_status)
        
        if account:
            self.set_connection_status('connecting')
            self.connect_xmpp()
    
    def _migrate_userlist_config(self):
        """Migrate old userlist_visible to separate configs"""
        old_visible = self.config.get("ui", "userlist_visible")
        if old_visible is not None and self.config.get("ui", "messages_userlist_visible") is None:
            # Set both to old value only if new keys don't exist
            self.config.set("ui", "messages_userlist_visible", value=old_visible)
            self.config.set("ui", "chatlog_userlist_visible", value=old_visible)
        
        # Ensure defaults exist
        if self.config.get("ui", "messages_userlist_visible") is None:
            self.config.set("ui", "messages_userlist_visible", value=True)
        if self.config.get("ui", "chatlog_userlist_visible") is None:
            self.config.set("ui", "chatlog_userlist_visible", value=True)
        if self.config.get("ui", "chatlog_search_visible") is None:
            self.config.set("ui", "chatlog_search_visible", value=False)
    
    def set_tray_mode(self, enabled: bool):
        self.tray_mode = enabled
    
    def _setup_mention_sound(self):
        sound_path = Path(__file__).parent.parent / "sounds" / "mention.mp3"
        self.mention_sound_path = str(sound_path) if sound_path.exists() else None
    
    def _init_ui(self):
        window_title = f"Chat - {self.account['login']}" if self.account else "Chat"
        self.setWindowTitle(window_title)
        self.resize(1500, 800)
        self.setMinimumSize(400, 400)

        # Use config for margins and spacing
        window_margin = self.config.get("ui", "margins", "window") or 10
        window_spacing = self.config.get("ui", "spacing", "window_content") or 10
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(window_margin, window_margin, window_margin, window_margin)
        main_layout.setSpacing(window_spacing)
        self.setLayout(main_layout)

        # Content layout: left (messages/chatlog) + right (userlist)
        content_spacing = self.config.get("ui", "spacing", "widget_content") or 6
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(content_spacing)
        main_layout.addLayout(self.content_layout, stretch=1)

        # Left side layout
        left_layout = QVBoxLayout()
        left_layout.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        self.content_layout.addLayout(left_layout, stretch=3)

        # Stacked widget for Messages/Chatlog views
        self.stacked_widget = QStackedWidget()
        left_layout.addWidget(self.stacked_widget, stretch=1)

        self.messages_widget = MessagesWidget(self.config)
        self.messages_widget.set_color_cache(self.color_cache)
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
        self.input_field.setFont(QFont(self.config.get("ui", "font_family"), self.config.get("ui", "font_size")))
        self.input_field.setFixedHeight(48)
        self.input_field.returnPressed.connect(self.send_message)
        self.input_top_layout.addWidget(self.input_field, stretch=1)
        
        self.messages_widget.set_input_field(self.input_field)
        
        self.send_button = create_icon_button(self.icons_path, "send.svg", "Send Message", config=self.config)
        self.send_button.clicked.connect(self.send_message)
        self.input_top_layout.addWidget(self.send_button)
        
        self.toggle_userlist_button = create_icon_button(self.icons_path, "user.svg", "Toggle User List", config=self.config)
        self.toggle_userlist_button.clicked.connect(self.toggle_user_list)
        self.input_top_layout.addWidget(self.toggle_userlist_button)
        
        is_dark = self.theme_manager.is_dark()
        theme_icon = "moon.svg" if is_dark else "sun.svg"
        self.theme_button = create_icon_button(self.icons_path, theme_icon, 
                                               "Switch to Light Mode" if is_dark else "Switch to Dark Mode",
                                               config=self.config)
        self.theme_button.clicked.connect(self.toggle_theme)
        self.input_top_layout.addWidget(self.theme_button)
        
        self.buttons_on_bottom = False
        self.movable_buttons = [self.toggle_userlist_button, self.theme_button]  # Both move to bottom
        
        # Widgets to hide at < 500px (all except toggle_userlist_button)
        self.narrow_hideable_widgets = [self.input_field, self.send_button, self.theme_button]
        
        # Messages userlist
        self.user_list_widget = UserListWidget(self.config, self.input_field)
        self.user_list_widget.color_cache = self.color_cache
        self.user_list_widget.avatar_cache = self.avatar_cache
        messages_userlist_visible = self.config.get("ui", "messages_userlist_visible")
        if messages_userlist_visible is not None:
            self.user_list_widget.setVisible(messages_userlist_visible)
        else:
            self.user_list_widget.setVisible(True)  # Default
        self.content_layout.addWidget(self.user_list_widget, stretch=1)

        self.messages_widget.timestamp_clicked.connect(self.show_chatlog_view)

    def show_messages_view(self):
        """Switch back to messages and destroy chatlog widgets"""
        # Cleanup and destroy chatlog widget
        if self.chatlog_widget:
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
        
        QTimer.singleShot(50, lambda: scroll(self.messages_widget.scroll_area, mode="bottom"))

    def show_chatlog_view(self, timestamp: str = None):
        """Open chatlog for today"""
        # Hide messages userlist
        if self.user_list_widget.isVisible():
            self.user_list_widget.setVisible(False)
        
        if not self.chatlog_widget:
            self.chatlog_widget = ChatlogWidget(self.config, self.icons_path)
            self.chatlog_widget.back_requested.connect(self.show_messages_view)
            self.chatlog_widget.messages_loaded.connect(self._on_chatlog_messages_loaded)
            self.chatlog_widget.filter_changed.connect(self._on_chatlog_filter_changed)
            self.stacked_widget.addWidget(self.chatlog_widget)
            
            width = self.width()
            self.chatlog_widget.set_compact_mode(width <= 800)
            self.chatlog_widget.set_compact_layout(width <= 800)
        
        if not self.chatlog_userlist_widget:
            self.chatlog_userlist_widget = ChatlogUserlistWidget(
                self.config, 
                self.icons_path, 
                self.color_cache
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
        
        self.chatlog_widget.current_date = datetime.now().date()
        self.chatlog_widget._update_date_display()
        self.chatlog_widget.load_current_date()
        
        self.stacked_widget.setCurrentWidget(self.chatlog_widget)
    
    def _on_chatlog_messages_loaded(self, messages):
        if self.chatlog_userlist_widget and messages:
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
            try:
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
                self.signal_emitter.connection_changed.emit('offline')
            except Exception as e:
                QTimer.singleShot(0, lambda: show_notification(
                    title="Error",
                    message=f"Connection error: {e}",
                    config=self.config,
                    account=self.account
                ))
                self.signal_emitter.connection_changed.emit('offline')

        threading.Thread(target=_worker, daemon=True).start()
    
    def message_callback(self, msg):
        self.signal_emitter.message_received.emit(msg)
    
    def presence_callback(self, pres):
        self.signal_emitter.presence_received.emit(pres)
    
    def add_local_message(self, msg):
        self.messages_widget.add_message(msg)
    
    def on_message(self, msg):
        if msg.login == self.account.get('login') and not getattr(msg, 'initial', False):
            return
        
        self.messages_widget.add_message(msg)
        
        if not getattr(msg, 'initial', False) and not self.isActiveWindow():
            if self._message_mentions_me(msg):
                self._play_mention_sound()
            
            try:
                show_notification(
                    title=msg.login,
                    message=msg.body,
                    xmpp_client=self.xmpp_client,
                    color_cache=self.color_cache,
                    config=self.config,
                    local_message_callback=self.add_local_message,
                    account=self.account,
                    window_show_callback=self._show_and_focus_window
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
        my_username = self.account.get('login', '').lower()
        if not my_username:
            return False
        pattern = r'\b' + re.escape(my_username) + r'\b'
        return bool(re.search(pattern, msg.body.lower()))
    
    def _play_mention_sound(self):
        if not self.mention_sound_path:
            try:
                QApplication.instance().beep()
            except Exception as e:
                print(f"System beep error: {e}")
            return
        
        def _play():
            try:
                playsound(self.mention_sound_path, block=False)
            except Exception as e:
                print(f"Sound playback error: {e}")
        
        threading.Thread(target=_play, daemon=True).start()
    
    def on_presence(self, pres):
        if not self.xmpp_client or self.initial_roster_loading:
            return
        
        if pres and pres.presence_type == 'available':
            self.user_list_widget.add_users(presence=pres)
        elif pres and pres.presence_type == 'unavailable':
            self.user_list_widget.remove_users(presence=pres)
    
    def on_bulk_update_complete(self):
        if not self.xmpp_client:
            return
        users = self.xmpp_client.user_list.get_online()
        self.user_list_widget.add_users(users=users, bulk=True)
    
    def send_message(self):
        text = self.input_field.text().strip()
        if not text or not self.xmpp_client:
            return
        
        self.input_field.clear()
        
        own_user = None
        for user in self.xmpp_client.user_list.get_all():
            if self.account.get('login') in user.jid or user.login == self.account.get('login'):
                own_user = user
                break
        
        own_msg = Message(
            from_jid=self.xmpp_client.jid,
            body=text,
            msg_type='groupchat',
            login=self.account.get('login'),
            avatar=None,
            background=own_user.background if own_user else None,
            timestamp=datetime.now(),
            initial=False
        )
        
        self.messages_widget.add_message(own_msg)
        threading.Thread(target=self.xmpp_client.send_message, args=(text,), daemon=True).start()

    def set_connection_status(self, status: str):
        status = (status or '').lower()
        text = {'connecting': 'Connecting', 'online': 'Online'}.get(status, 'Offline')
        base = f"Chat - {self.account['login']}" if self.account else "Chat"
        self.setWindowTitle(f"{base} - {text}")

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
            
            # Below 500px: manually hide/show widgets
            if width < 500:
                self.stacked_widget.setVisible(not visible)
                for widget in self.narrow_hideable_widgets:
                    widget.setVisible(not visible)
        else:
            # Toggle messages userlist
            visible = not self.user_list_widget.isVisible()
            self.user_list_widget.setVisible(visible)
            self.config.set("ui", "messages_userlist_visible", value=visible)
            self.auto_hide_messages_userlist = False
            
            # Below 500px: manually hide/show widgets
            if width < 500:
                self.stacked_widget.setVisible(not visible)
                for widget in self.narrow_hideable_widgets:
                    widget.setVisible(not visible)
        
        # Force resize handler to sync everything
        QTimer.singleShot(10, lambda: handle_chat_resize(self, width))
        
        # Force recalculation after visibility change (only needed when messages visible)
        if width >= 500 or not visible:
            QTimer.singleShot(20, lambda: recalculate_layout(self))
    
    def toggle_theme(self):
        self.theme_button.setEnabled(False)
        try:
            self.theme_manager.toggle_theme()
            is_dark = self.theme_manager.is_dark()
            set_theme(is_dark)
            
            self.theme_button._icon_name = "moon.svg" if is_dark else "sun.svg"
            self.theme_button.setToolTip("Switch to Light Mode" if is_dark else "Switch to Dark Mode")
            
            # Clear cache so colors get recalculated
            self.color_cache.clear()
            
            update_all_icons()
            self.messages_widget.update_theme()
            self.user_list_widget.update_theme()
            
            if self.chatlog_widget:
                self.chatlog_widget.update_theme()
            if self.chatlog_userlist_widget:
                self.chatlog_userlist_widget.update_theme()
            
            self.messages_widget.rebuild_messages()
            
            if self.chatlog_widget and self.stacked_widget.currentWidget() == self.chatlog_widget:
                self.chatlog_widget._force_recalculate()
            
            QApplication.processEvents()
        except Exception as e:
            print(f"Theme toggle error: {e}")
        finally:
            self.theme_button.setEnabled(True)
    
    def closeEvent(self, event):
        # Cleanup widgets
        if self.messages_widget:
            self.messages_widget.cleanup()
        if self.chatlog_widget:
            self.chatlog_widget.cleanup()
        
        if self.tray_mode and not self.really_close:
            event.ignore()
            self.hide()
        else:
            if self.xmpp_client:
                try:
                    self.xmpp_client.disconnect()
                except:
                    pass
            self.set_connection_status('offline')
            event.accept()
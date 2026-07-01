"""Messages display widget"""
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListView
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from helpers.scroll import scroll
from helpers.cache import get_cache
from helpers.auto_scroll import AutoScroller
from ui.message_model import MessageListModel, MessageData
from ui.message_delegate import MessageDelegate
from helpers.message_interactions import MessageInteractions
from helpers.fonts import get_font, FontType
from helpers.scroll_button import ScrollToBottomButton

class MessagesWidget(QWidget):
    """Widget for displaying chat messages with virtual scrolling"""
    timestamp_left_clicked = pyqtSignal(str) # Opens chatlog for current day
    timestamp_right_clicked = pyqtSignal(str) # RMB on timestamp: date_str ("%Y-%m-%d"), opens chatlog as split view
    username_left_clicked = pyqtSignal(str, bool) # Set username in input field, bool indicates double-click
    username_right_clicked = pyqtSignal(object, object) # Show context menu for user
    username_ctrl_clicked = pyqtSignal(str)   # Ctrl+LMB → enter private
    username_shift_clicked = pyqtSignal(str)  # Shift+LMB → open profile
    chatlog_link_clicked = pyqtSignal(str, str)  # date_str, time_str ("" if none) - chatlog URL clicked in a message body

    def __init__(self, config, emoticon_manager, my_username: str = None):
        super().__init__()
        self.config = config
        self.cache = get_cache()
        self.emoticon_manager = emoticon_manager
       
        self.model = MessageListModel(max_messages=1000)
        self.delegate = MessageDelegate(config, self.emoticon_manager)
        
        if my_username:
            self.delegate.set_my_username(my_username)
       
        self._setup_ui()
        
        # Initialize auto-scroller after UI is set up
        self.auto_scroller = AutoScroller(self.list_view)
        
        # Connect message click for row highlighting (still from delegate)
        self.delegate.message_clicked.connect(self._on_message_clicked)
        self.delegate.chatlog_link_clicked.connect(self.chatlog_link_clicked.emit)
        
        # Shared username/timestamp click detection (also used by ChatlogWidget)
        self.interactions = MessageInteractions(self.list_view, self.delegate)
        self.interactions.timestamp_left_clicked.connect(self.timestamp_left_clicked.emit)
        self.interactions.timestamp_right_clicked.connect(self.timestamp_right_clicked.emit)
        self.interactions.username_left_clicked.connect(self.username_left_clicked.emit)
        self.interactions.username_right_clicked.connect(self.username_right_clicked.emit)
        self.interactions.username_ctrl_clicked.connect(self.username_ctrl_clicked.emit)
        self.interactions.username_shift_clicked.connect(self.username_shift_clicked.emit)

    def set_my_username(self, username: str):
        """Set the current user's username for mention highlighting"""
        if self.delegate:
            self.delegate.set_my_username(username)

    def set_input_field(self, input_field):
        """Set input field reference for reply and paste actions"""
        def _reply(username, text, timestamp=None):
            reply_text = MessageDelegate.format_reply_text(username, text, timestamp)
            input_field.setText(reply_text)
            input_field.setCursorPosition(len(reply_text))
            input_field.setFocus()
        def _paste(text):
            cursor_pos = input_field.cursorPosition()
            current = input_field.text()
            input_field.setText(current[:cursor_pos] + text + current[cursor_pos:])
            input_field.setCursorPosition(cursor_pos + len(text))
            input_field.setFocus()
        self.delegate.reply_callback = _reply
        self.delegate.paste_callback = _paste

    @property
    def reply_callback(self):
        return self.delegate.reply_callback
    
    def _on_message_clicked(self, row: int):
        """Handle message click - scroll to middle with highlight"""
        scroll(self.list_view, mode="middle", target_row=row, delay=100)
        QTimer.singleShot(250, lambda: self.delegate.highlight_row(row))
   
    def set_compact_mode(self, compact: bool):
        if self.delegate.compact_mode != compact:
            self.delegate.set_compact_mode(compact)
            self._force_recalculate()
   
    def _setup_ui(self):
        spacing = self.config.get("ui", "spacing", "widget_elements") or 4
       
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        self.setLayout(layout)
       
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.delegate.set_list_view(self.list_view)
       
        self.list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.list_view.setUniformItemSizes(False)
        self.list_view.setSpacing(0)
       
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_view.setWordWrap(False)
        self.list_view.setMouseTracking(True)
        self.list_view.viewport().setMouseTracking(True)
       
        layout.addWidget(self.list_view)
       
        # Add scroll-to-bottom button
        self.scroll_button = ScrollToBottomButton(self.list_view, parent=self)
   
    def add_message(self, msg):
        if msg.login and getattr(msg, 'background', None):
            user_id = self.cache.get_user_id(msg.login)
            if user_id:
                self.cache.update_user(user_id, msg.login, msg.background)
       
        msg_data = MessageData(
            getattr(msg, 'timestamp', None) or datetime.now(),
            msg.login if msg.login else "Unknown",
            msg.body,
            getattr(msg, 'background', None),
            msg.login,
            getattr(msg, 'is_private', False),
            is_ban=getattr(msg, 'is_ban', False),
            is_system=getattr(msg, 'is_system', False)
        )
        sb = self.list_view.verticalScrollBar()
        at_bottom = (sb.maximum() - sb.value()) <= 100

        self.model.add_message(msg_data)

        if at_bottom:
            QTimer.singleShot(0, lambda: scroll(self.list_view, mode="bottom", delay=100))
   
    def clear_private_messages(self):
        """Clear all private messages"""
        self.model.clear_private_messages()

    def remove_messages_by_login(self, login: str, timestamp=None, from_timestamp=None, to_timestamp=None):
        """Remove all messages belonging to a login, or a subset by timestamp/range"""
        self.model.remove_messages_by_login(login, timestamp, from_timestamp, to_timestamp)
   
    def rebuild_messages(self):
        self.delegate.update_theme()
        if self.delegate.message_renderer:
            self.delegate.message_renderer._emoticon_cache.clear()
        self._force_recalculate()
   
    def update_theme(self):
        theme = self.config.get("ui", "theme")
        self.delegate.is_dark_theme = (theme == "dark")
        self.delegate.bg_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
   
    def _force_recalculate(self):
        """Aggressive force recalculation of all item sizes"""
        self.list_view.setUpdatesEnabled(False)
        self.list_view.reset()
        self.list_view.clearSelection()
        self.list_view.scheduleDelayedItemsLayout()
        self.model.layoutChanged.emit()
        self.list_view.setUpdatesEnabled(True)
        self.list_view.viewport().update()
        QTimer.singleShot(10, lambda: self.list_view.viewport().update())
   
    def cleanup(self):
        """Cleanup delegate to stop animation timer"""
        if self.delegate:
            self.delegate.cleanup()
        if hasattr(self, 'scroll_button'):
            self.scroll_button.cleanup()
        if hasattr(self, 'auto_scroller'):
            self.auto_scroller.cleanup()
   
    def clear(self):
        self.model.clear()
   
    @property
    def scroll_area(self):
        """Compatibility property for scroll helpers"""
        return self.list_view
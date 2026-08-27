"""Messages display widget"""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListView
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from helpers.scroll.scroll import scroll
from helpers.cache import get_cache
from helpers.scroll.auto_scroll import AutoScroller
from ui.message_model import MessageListModel, MessageData
from ui.message_delegate import MessageDelegate
from components.search import MessageSearchBar
from helpers.message_interactions import MessageInteractions
from helpers.fonts import get_font, FontType
from helpers.scroll.scroll_buttons import ScrollButtonsPanel
from helpers.presence_log import add_presence_entry, presence_entries_to_text
from ui.ui_settings import DEFAULTS

class MessagesWidget(QWidget):
    """Widget for displaying chat messages with virtual scrolling"""
    timestamp_left_clicked = pyqtSignal(str) # Opens chatlog for current day
    timestamp_right_clicked = pyqtSignal(str) # RMB on timestamp: date_str ("%Y-%m-%d"), opens chatlog as split view
    competition_timestamp_left_clicked = pyqtSignal(object)  # LMB on competition timestamp → open competition room
    username_left_clicked = pyqtSignal(str, bool) # Set username in input field, bool indicates double-click
    username_right_clicked = pyqtSignal(object, object) # Show context menu for user
    username_ctrl_clicked = pyqtSignal(str)   # Ctrl+LMB → enter private
    username_shift_clicked = pyqtSignal(str)  # Shift+LMB → open profile
    chip_clicked = pyqtSignal(str)  # competition player chip → open profile
    chatlog_link_clicked = pyqtSignal(str, str)  # date_str, time_str ("" if none) - chatlog URL clicked in a message body

    def __init__(self, config, emoticon_manager, my_username: str = None):
        super().__init__()
        self.config = config
        self.cache = get_cache()
        self.emoticon_manager = emoticon_manager
        self.icons_path = Path(__file__).parent.parent / "icons"

        self.model = MessageListModel(max_messages=self._max_messages_limit())
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
        self.interactions.competition_timestamp_left_clicked.connect(self.competition_timestamp_left_clicked.emit)
        self.interactions.username_left_clicked.connect(self.username_left_clicked.emit)
        self.interactions.username_right_clicked.connect(self.username_right_clicked.emit)
        self.interactions.username_ctrl_clicked.connect(self.username_ctrl_clicked.emit)
        self.interactions.username_shift_clicked.connect(self.username_shift_clicked.emit)
        self.interactions.chip_clicked.connect(self.chip_clicked.emit)
        self.delegate.presence_log_clicked.connect(self._on_presence_log_clicked)

    @property
    def search_visible(self) -> bool:
        return self.search.visible_state

    def _max_messages_limit(self) -> int:
        value = self.config.get("ui", "chat", "max_messages")
        if value is None:
            return DEFAULTS["chat"]["max_messages"]
        return max(
            DEFAULTS["chat"]["max_messages_min"],
            min(DEFAULTS["chat"]["max_messages_max"], int(value)),
        )

    def apply_max_messages_limit(self):
        """Apply current config limit to the model, trimming oldest messages if it shrank."""
        self.model.max_messages = self._max_messages_limit()
        self.model.trim_to_limit()

    def set_my_username(self, username: str):
        """Set the current user's username for mention highlighting"""
        if self.delegate:
            self.delegate.set_my_username(username)

    def set_input_field(self, input_field):
        """Enable Reply and Paste options in message context menu"""
        if self.delegate:
            self.delegate.set_input_field(input_field, include_timestamp=False)

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
        layout.setContentsMargins(4, 0, 4, 0)  # Add left and right margins to match chatlog
        layout.setSpacing(spacing)
        self.setLayout(layout)

        self.search = MessageSearchBar(
            self.config, self.icons_path,
            get_messages=lambda: self.model._messages,
            set_messages=self.model.set_messages,
        )
        self.search.text_changed.connect(self.delegate.set_highlight_text)
        layout.addWidget(self.search)
       
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
       
        # Add scroll buttons panel for quick navigation
        self.scroll_buttons = ScrollButtonsPanel(self.list_view, parent=self)

    def _toggle_search(self):
        self.search.toggle()
   
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
            is_system=getattr(msg, 'is_system', False),
            is_competition=getattr(msg, 'is_competition', False),
            competition_game_id=getattr(msg, 'competition_game_id', None),
            competition_players=getattr(msg, 'competition_players', None),
            is_presence_log=getattr(msg, 'is_presence_log', False),
            presence_entries=getattr(msg, 'presence_entries', None),
        )
        if not self.search.register_message(msg_data, self.model.max_messages):
            return -1

        sb = self.list_view.verticalScrollBar()
        at_bottom = (sb.maximum() - sb.value()) <= 100

        row = self.model.add_message(msg_data)

        if at_bottom:
            QTimer.singleShot(0, lambda: scroll(self.list_view, mode="bottom", delay=100))
        return row
   
    def record_presence_event(self, login: str, event_type: str):
        open_row = self.model.get_open_presence_log_row()
        if open_row is not None:
            current = self.model.get_message_at(open_row)
            entries = add_presence_entry(list(current.presence_entries or []), login, event_type)
            self.model.update_presence_entries(open_row, entries, presence_entries_to_text(entries))
            sb = self.list_view.verticalScrollBar()
            if (sb.maximum() - sb.value()) <= 100:
                QTimer.singleShot(0, lambda: scroll(self.list_view, mode="bottom", delay=50))
            return

        entries = add_presence_entry([], login, event_type)
        self.add_message(SimpleNamespace(
            timestamp=datetime.now(),
            login=None,
            body=presence_entries_to_text(entries),
            is_presence_log=True,
            presence_entries=entries,
        ))

    def clear_presence_messages(self):
        self.model.clear_presence_messages()
        self.search.filter_backup(lambda m: getattr(m, 'is_presence_log', False))

    def _on_presence_log_clicked(self, row: int):
        self.clear_presence_messages()

    def clear_private_messages(self):
        """Clear all private messages"""
        self.model.clear_private_messages()
        self.search.filter_backup(lambda m: getattr(m, 'is_private', False))

    def clear_competition_messages(self, game_id=None):
        """Clear rating competition system messages (all or one game_id)."""
        self.model.clear_competition_messages(game_id)
        if game_id is None:
            self.search.filter_backup(lambda m: getattr(m, 'is_competition', False))
        else:
            self.search.filter_backup(
                lambda m: getattr(m, 'is_competition', False)
                and getattr(m, 'competition_game_id', None) == game_id
            )

    def update_competition_message(self, game_id: int, body: str, players=None) -> bool:
        """Update a competition message's header and player chips in place."""
        row = self.model.update_message_by_game_id(game_id, body, players)
        if row is None:
            return False
        self.delegate.row_needs_refresh.emit(row)
        return True

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
        if hasattr(self, 'scroll_buttons'):
            self.scroll_buttons.cleanup()
        if hasattr(self, 'auto_scroller'):
            self.auto_scroller.cleanup()
   
    def clear(self):
        self.model.clear()
        self.search.reset()
   
    @property
    def scroll_area(self):
        """Compatibility property for scroll helpers"""
        return self.list_view

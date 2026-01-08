"""Chatlog viewer widget with virtual scrolling and search"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListView, QCalendarWidget, QLineEdit
from PyQt6.QtCore import Qt, QDate, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from datetime import datetime, timedelta
import threading
from pathlib import Path

from core.chatlogs import ChatlogsParser, ChatlogNotFoundError
from helpers.create import create_icon_button
from helpers.emoticons import EmoticonManager
from helpers.scroll import scroll
from ui.message_model import MessageListModel, MessageData
from ui.message_delegate import MessageDelegate


class ChatlogWidget(QWidget):
    """Chatlog viewer with virtual scrolling and search"""
    back_requested = pyqtSignal()
    messages_loaded = pyqtSignal(list)
    filter_changed = pyqtSignal(set)  # Emit set of filtered usernames
    _error_occurred = pyqtSignal(str)  # Internal signal for error messages

    def __init__(self, config, icons_path: Path):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.parser = ChatlogsParser()
        self.current_date = datetime.now().date()
        self.color_cache = {}
        self.filtered_usernames = set()  # Set of usernames to show (empty = show all)
        self.search_text = ""  # Current search text
        self.all_messages = []  # Store all messages for filtering
        
        # Load search visibility from config
        self.search_visible = config.get("ui", "chatlog_search_visible")
        if self.search_visible is None:
            self.search_visible = False
        
        emoticons_path = Path(__file__).resolve().parent.parent / "emoticons"
        self.emoticon_manager = EmoticonManager(emoticons_path)
        
        self.model = MessageListModel(max_messages=50000)
        self.delegate = MessageDelegate(config, self.emoticon_manager, self.color_cache)
        
        self._setup_ui()

    def _setup_ui(self):
        margin = self.config.get("ui", "margins", "widget") or 5
        spacing = self.config.get("ui", "spacing", "widget_elements") or 6
        
        layout = QVBoxLayout()
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)
        self.setLayout(layout)

        # Navigation bar (buttons only)
        self.nav_bar = QHBoxLayout()
        self.nav_bar.setSpacing(self.config.get("ui", "buttons", "spacing") or 8)
        layout.addLayout(self.nav_bar)

        self.back_btn = create_icon_button(self.icons_path, "go-back.svg", "Back to chat", 
                                          size_type="large", config=self.config)
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.nav_bar.addWidget(self.back_btn)

        self.prev_btn = create_icon_button(self.icons_path, "arrow-left.svg", "Previous day",
                                          size_type="large", config=self.config)
        self.prev_btn.clicked.connect(self._go_previous_day)
        self.nav_bar.addWidget(self.prev_btn)

        # Date label - can be in nav_bar or separate row
        self.date_label = QLabel()
        font = QFont(self.config.get("ui", "font_family"), self.config.get("ui", "font_size") + 2)
        font.setBold(True)
        self.date_label.setFont(font)
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nav_bar.addWidget(self.date_label, stretch=1)

        self.next_btn = create_icon_button(self.icons_path, "arrow-right.svg", "Next day",
                                          size_type="large", config=self.config)
        self.next_btn.clicked.connect(self._go_next_day)
        self.nav_bar.addWidget(self.next_btn)

        self.calendar_btn = create_icon_button(self.icons_path, "calendar.svg", "Select date",
                                              size_type="large", config=self.config)
        self.calendar_btn.clicked.connect(self._show_calendar)
        self.nav_bar.addWidget(self.calendar_btn)

        self.search_toggle_btn = create_icon_button(self.icons_path, "search.svg", "Toggle search",
                                                   size_type="large", config=self.config)
        self.search_toggle_btn.clicked.connect(self._toggle_search)
        self.nav_bar.addWidget(self.search_toggle_btn)

        # Separate date label container for narrow mode
        self.date_container = QWidget()
        date_container_layout = QVBoxLayout()
        date_container_layout.setContentsMargins(0, 0, 0, 0)
        date_container_layout.setSpacing(0)
        self.date_container.setLayout(date_container_layout)
        self.date_container.setVisible(False)
        layout.addWidget(self.date_container)

        # Info label
        self.info_label = QLabel("Loading...")
        self.info_label.setStyleSheet("color: #666666;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)
        
        # Track current layout mode
        self.compact_layout = False

        # Search bar (initially hidden)
        self.search_container = QWidget()
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(self.config.get("ui", "buttons", "spacing") or 8)
        self.search_container.setLayout(search_layout)
        
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search: 'text' or 'U:Bob' or 'U:Bob,Alice' or 'M:hello' or 'U:Bob M:hello'")
        self.search_field.setFont(QFont(self.config.get("ui", "font_family"), self.config.get("ui", "font_size")))
        self.search_field.setFixedHeight(48)
        self.search_field.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_field, stretch=1)
        
        self.clear_search_btn = create_icon_button(self.icons_path, "trash.svg", "Clear search",
                                                  size_type="large", config=self.config)
        self.clear_search_btn.clicked.connect(self._clear_search)
        search_layout.addWidget(self.clear_search_btn)
        
        self.search_container.setVisible(False)
        layout.addWidget(self.search_container)
        
        # Apply saved visibility state
        if self.search_visible:
            self.search_container.setVisible(True)

        # List view
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.delegate.set_list_view(self.list_view)
        
        self.list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.list_view.setUniformItemSizes(False)
        self.list_view.setSpacing(0)
        
        self.list_view.setFrameShape(QListView.Shape.NoFrame)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_view.setMouseTracking(True)
        self.list_view.viewport().setMouseTracking(True)
        
        layout.addWidget(self.list_view)

        self._update_date_display()
        
        # Connect error signal
        self._error_occurred.connect(self._handle_error)
    
    def _handle_error(self, error_msg: str):
        """Handle error on main thread"""
        self.info_label.setText(error_msg)
    
    def _toggle_search(self):
        """Toggle search bar visibility"""
        self.search_visible = not self.search_visible
        self.search_container.setVisible(self.search_visible)
        
        # Save to config
        self.config.set("ui", "chatlog_search_visible", value=self.search_visible)
        
        if self.search_visible:
            self.search_field.setFocus()
        else:
            self.search_field.clear()

    def _on_search_changed(self, text: str):
        """Handle search text change with prefix support
        
        Syntax:
        - "hello" - search in both usernames and messages
        - "U:Bob" - filter by user Bob
        - "U:Bob,Alice" - filter by users Bob and Alice
        - "M:hello" - search only in messages
        - "U:Bob M:hello" - filter by user Bob AND search "hello" in messages
        """
        self.search_text = text.strip()
        self._apply_filter()
    
    def _parse_search_text(self):
        """Parse search text for U: and M: prefixes
        
        Returns:
            tuple: (user_filter_set, message_search_term, is_prefix_mode)
        """
        if not self.search_text:
            return set(), "", False
        
        import re
        
        user_filter = set()
        message_filter = ""
        
        # Check if text contains U: or M: prefixes
        text = self.search_text.strip()
        has_u_prefix = re.search(r'[Uu]:', text)
        has_m_prefix = re.search(r'[Mm]:', text)
        has_prefix = has_u_prefix or has_m_prefix
        
        if not has_prefix:
            return set(), "", False
        
        # Extract U: part - capture until M: or end of string
        if has_u_prefix:
            u_pattern = r'[Uu]:\s*(.+?)(?:\s+[Mm]:|$)'
            match = re.search(u_pattern, text)
            if match:
                users_str = match.group(1).strip()
                # Split by comma and strip whitespace from each username
                users = [u.strip() for u in users_str.split(',') if u.strip()]
                user_filter.update(users)
        
        # Extract M: part - get everything after M: until end or next prefix
        if has_m_prefix:
            m_pattern = r'[Mm]:\s*(.+?)(?:\s+[Uu]:|$)'
            match = re.search(m_pattern, text)
            if match:
                message_filter = match.group(1).strip().lower()
        
        return user_filter, message_filter, True

    def _clear_search(self):
        """Clear search field"""
        self.search_field.clear()
        # Reapply userlist filter if any
        self._apply_filter()

    def _update_date_display(self):
        self.date_label.setText(self.current_date.strftime("%Y-%m-%d (%A)"))
        self.next_btn.setEnabled(self.current_date < datetime.now().date())
        self.prev_btn.setEnabled(self.current_date > self.parser.MIN_DATE)
    
    def set_compact_layout(self, compact: bool):
        """Set compact layout mode (called from resize.py via ui_chat.py)"""
        if compact == self.compact_layout:
            return
        
        if compact:
            # Move date label to separate container
            self.nav_bar.removeWidget(self.date_label)
            self.date_container.layout().addWidget(self.date_label)
            self.date_container.setVisible(True)
            self.compact_layout = True
        else:
            # Move date label back to nav bar
            self.date_container.layout().removeWidget(self.date_label)
            self.nav_bar.insertWidget(2, self.date_label, stretch=1)
            self.date_container.setVisible(False)
            self.compact_layout = False
    
    def set_compact_mode(self, compact: bool):
        self.delegate.set_compact_mode(compact)
        self._force_recalculate()
    
    def update_theme(self):
        self.delegate.update_theme()
        self.color_cache.clear()
        self._force_recalculate()
    
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

    def load_date(self, date_str: str):
        try:
            self.current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            self._update_date_display()
            self.load_current_date()
        except Exception as e:
            self.info_label.setText(f"Error: {e}")

    def set_username_filter(self, usernames: set):
        """Set username filter - empty set means show all"""
        self.filtered_usernames = usernames
        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)
    
    def clear_filter(self):
        """Clear username filter"""
        self.filtered_usernames = set()
        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)
    
    def _apply_filter(self):
        """Apply current filter (username + search) to messages"""
        self.model.clear()
        
        if not self.all_messages:
            return
        
        # Parse search text
        search_users, search_message, is_prefix_mode = self._parse_search_text()
        
        messages_to_show = self.all_messages
        
        if is_prefix_mode:
            # Prefix mode: U: and/or M:
            
            # Apply user filter from search (U:) - case insensitive
            if search_users:
                search_users_lower = {u.lower() for u in search_users}
                messages_to_show = [msg for msg in messages_to_show 
                                if msg.username.lower() in search_users_lower]
            
            # Apply message filter from search (M:)
            if search_message:
                messages_to_show = [msg for msg in messages_to_show
                                if search_message in msg.body.lower()]
        else:
            # Normal mode: search in both username and message
            
            # First apply userlist filter (from clicking users)
            if self.filtered_usernames:
                messages_to_show = [msg for msg in messages_to_show 
                                if msg.username in self.filtered_usernames]
            
            # Then apply search text (searches both username and message)
            if self.search_text:
                search_lower = self.search_text.lower()
                messages_to_show = [msg for msg in messages_to_show
                                if search_lower in msg.username.lower() or 
                                    search_lower in msg.body.lower()]
        
        for msg in messages_to_show:
            self.model.add_message(msg)
        
        # Update info label - ALWAYS update it
        total = len(self.all_messages)
        shown = len(messages_to_show)
        
        filters = []
        if is_prefix_mode:
            if search_users:
                filters.append(f"users: {', '.join(sorted(search_users))}")
            if search_message:
                filters.append(f"message: '{search_message}'")
        else:
            if self.filtered_usernames:
                filters.append(f"users: {', '.join(sorted(self.filtered_usernames))}")
            if self.search_text:
                filters.append(f"search: '{self.search_text}'")
        
        if filters:
            filter_text = " | ".join(filters)
            self.info_label.setText(f"Showing {shown}/{total} messages ({filter_text})")
        else:
            # No filters - show total count without filter info
            # Get the file size from the last load
            if hasattr(self, '_pending_data'):
                _, size_text, was_truncated = self._pending_data
                if was_truncated:
                    self.info_label.setText(f"⚠️ Loaded {total} messages (file truncated at {self.parser.MAX_FILE_SIZE_MB}MB limit) · {size_text}")
                else:
                    self.info_label.setText(f"Loaded {total} messages · {size_text}")
            else:
                self.info_label.setText(f"Loaded {total} messages")
        
        QTimer.singleShot(0, lambda: scroll(self.list_view, mode="bottom", delay=100))

    def load_current_date(self):
        self.model.clear()
        self.all_messages = []
        self.info_label.setText("Loading...")
        
        date_str = self.current_date.strftime("%Y-%m-%d")
        
        def _load():
            try:
                messages, was_truncated = self.parser.get_messages(date_str)
                html, _ = self.parser.fetch_log(date_str)
                size_kb = len(html.encode('utf-8')) / 1024
                size_text = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                
                self._pending_data = (messages, size_text, was_truncated)
                QTimer.singleShot(0, self._display_messages)
            except ChatlogNotFoundError:
                self._error_occurred.emit(f"No chatlog found for {date_str}")
            except ValueError as e:
                self._error_occurred.emit(str(e))
            except Exception as e:
                self._error_occurred.emit(f"Error: {e}")
        
        threading.Thread(target=_load, daemon=True).start()

    def _display_messages(self):
        try:
            messages, size_text, was_truncated = getattr(self, '_pending_data', ([], '', False))
            
            self.model.clear()
            self.all_messages = []
            
            if not messages:
                self.info_label.setText(f"No messages · {size_text}")
                self.messages_loaded.emit([])
                return
            
            message_data = []
            for msg in messages:
                try:
                    timestamp = datetime.strptime(msg.timestamp, "%H:%M:%S")
                    msg_data = MessageData(timestamp, msg.username, msg.message, None, msg.username)
                    message_data.append(msg_data)
                except Exception:
                    pass
            
            self.all_messages = message_data
            self._apply_filter()
            
            # Update info label
            if was_truncated:
                self.info_label.setText(f"⚠️ Loaded {len(messages)} messages (file truncated at {self.parser.MAX_FILE_SIZE_MB}MB limit) · {size_text}")
            elif self.filtered_usernames or self.search_text:
                # Already set by _apply_filter
                pass
            else:
                self.info_label.setText(f"Loaded {len(messages)} messages · {size_text}")
            
            self.messages_loaded.emit(message_data)
            
            QTimer.singleShot(0, lambda: scroll(self.list_view, mode="bottom", delay=100))
        except Exception as e:
            self.info_label.setText(f"❌ Display error: {e}")

    def _go_previous_day(self):
        if self.current_date > self.parser.MIN_DATE:
            self.current_date -= timedelta(days=1)
            self._update_date_display()
            self.load_current_date()

    def _go_next_day(self):
        if self.current_date < datetime.now().date():
            self.current_date += timedelta(days=1)
            self._update_date_display()
            self.load_current_date()

    def _show_calendar(self):
        calendar = QCalendarWidget()
        calendar.setWindowFlags(Qt.WindowType.Popup)
        calendar.setGridVisible(True)
        calendar.setMaximumDate(QDate.currentDate())
        
        # Set minimum date
        min_qdate = QDate(self.parser.MIN_DATE.year, self.parser.MIN_DATE.month, self.parser.MIN_DATE.day)
        calendar.setMinimumDate(min_qdate)
        
        qdate = QDate(self.current_date.year, self.current_date.month, self.current_date.day)
        calendar.setSelectedDate(qdate)
        
        def on_date_selected(date: QDate):
            new_date = date.toPyDate()
            if new_date != self.current_date:
                self.current_date = new_date
                self._update_date_display()
                self.load_current_date()
            calendar.close()
        
        calendar.clicked.connect(on_date_selected)
        btn_pos = self.calendar_btn.mapToGlobal(self.calendar_btn.rect().bottomRight())
        x = btn_pos.x() - calendar.sizeHint().width()
        y = btn_pos.y() + (self.config.get("ui", "spacing", "widget_elements") or 6)
        calendar.move(x, y)
        calendar.show()
    
    def cleanup(self):
        """Cleanup delegate to stop animation timer"""
        if self.delegate:
            self.delegate.cleanup()
"""Chatlog viewer widget with virtual scrolling, search, and parser"""
from PyQt6.QtWidgets import(
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListView, QCalendarWidget, QLineEdit,
    QStackedWidget, QFileDialog, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QDate, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from datetime import datetime, timedelta
import threading
from pathlib import Path

from core.chatlogs import ChatlogsParser, ChatlogNotFoundError
from core.chatlogs_parser import ParseConfig, ChatlogsParserEngine
from helpers.create import create_icon_button
from helpers.emoticons import EmoticonManager
from helpers.scroll import scroll
from helpers.data import get_data_dir
from helpers.fonts import get_font, FontType
from helpers.scroll_button import ScrollToBottomButton
from helpers.auto_scroll import AutoScroller
from ui.message_model import MessageListModel, MessageData
from ui.message_delegate import MessageDelegate
from ui.ui_chatlogs_parser import ChatlogsParserConfigWidget, ParserWorker


class ChatlogWidget(QWidget):
    """Chatlog viewer with virtual scrolling, search, and parser"""
    back_requested = pyqtSignal()
    messages_loaded = pyqtSignal(list)
    filter_changed = pyqtSignal(set)
    _error_occurred = pyqtSignal(str)

    def __init__(self, config, icons_path: Path, account=None):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.account = account
        self.parser = ChatlogsParser()
        self.current_date = datetime.now().date()
        self.color_cache = {}
        self.filtered_usernames = set()
        self.search_text = ""
        self.all_messages = []
        self.last_parsed_date = None
        self.temp_parsed_messages = [] # Temporary storage for parsed messages
     
        self.search_visible = config.get("ui", "chatlog_search_visible")
        if self.search_visible is None:
            self.search_visible = False
     
        emoticons_path = Path(__file__).resolve().parent.parent / "emoticons"
        self.emoticon_manager = EmoticonManager(emoticons_path)
     
        self.model = MessageListModel(max_messages=50000)
        self.delegate = MessageDelegate(config, self.emoticon_manager, self.color_cache)
     
        # Parser state
        self.parser_worker = None
        self.parser_visible = False
     
        self._setup_ui()
        
        # Initialize auto-scroller after UI is set up
        self.auto_scroller = AutoScroller(self.list_view)
  
    def set_account(self, account):
        """Update account for parser widget"""
        self.account = account
        if self.parser_widget:
            self.parser_widget.set_account(account)

    def _setup_ui(self):
        margin = self.config.get("ui", "margins", "widget") or 5
        spacing = self.config.get("ui", "spacing", "widget_elements") or 6
     
        layout = QVBoxLayout()
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)
        self.setLayout(layout)

        # Top bar container for responsive layout
        self.top_bar_container = QWidget()
        self.top_bar_layout = QVBoxLayout()
        self.top_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.top_bar_layout.setSpacing(spacing)
        self.top_bar_container.setLayout(self.top_bar_layout)
        layout.addWidget(self.top_bar_container)

        # Main horizontal bar (for wide screens)
        self.main_bar = QHBoxLayout()
        self.main_bar.setSpacing(spacing)
        self.main_bar.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.top_bar_layout.addLayout(self.main_bar)

        # Left side: Info block (date + status)
        self.info_block = QVBoxLayout()
        self.info_block.setSpacing(spacing)
        self.info_block.setAlignment(Qt.AlignmentFlag.AlignTop)
      
        # Date label
        self.date_label = QLabel()
        self.date_label.setFont(get_font(FontType.HEADER))
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_block.addWidget(self.date_label)
      
        # Info label
        self.info_label = QLabel("Loading...")
        self.info_label.setStyleSheet("color: #666666;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_block.addWidget(self.info_label)
      
        self.main_bar.addLayout(self.info_block, stretch=1)

        # Right side: Navigation buttons
        self.nav_buttons_layout = QHBoxLayout()
        self.nav_buttons_layout.setSpacing(self.config.get("ui", "buttons", "spacing") or 8)
        self.nav_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.back_btn = create_icon_button(self.icons_path, "go-back.svg", "Back to chat",
                                          size_type="large", config=self.config)
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.nav_buttons_layout.addWidget(self.back_btn)

        self.prev_btn = create_icon_button(self.icons_path, "arrow-left.svg", "Previous day",
                                          size_type="large", config=self.config)
        self.prev_btn.clicked.connect(self._go_previous_day)
        self.nav_buttons_layout.addWidget(self.prev_btn)

        self.next_btn = create_icon_button(self.icons_path, "arrow-right.svg", "Next day",
                                          size_type="large", config=self.config)
        self.next_btn.clicked.connect(self._go_next_day)
        self.nav_buttons_layout.addWidget(self.next_btn)

        self.calendar_btn = create_icon_button(self.icons_path, "calendar.svg", "Select date",
                                              size_type="large", config=self.config)
        self.calendar_btn.clicked.connect(self._show_calendar)
        self.nav_buttons_layout.addWidget(self.calendar_btn)

        self.search_toggle_btn = create_icon_button(self.icons_path, "search.svg", "Toggle search",
                                                   size_type="large", config=self.config)
        self.search_toggle_btn.clicked.connect(self._toggle_search)
        self.nav_buttons_layout.addWidget(self.search_toggle_btn)

        self.parse_btn = create_icon_button(self.icons_path, "play.svg", "Parse all chatlogs",
                                           size_type="large", config=self.config)
        self.parse_btn.clicked.connect(self._toggle_parser)
        self.nav_buttons_layout.addWidget(self.parse_btn)
      
        self.main_bar.addLayout(self.nav_buttons_layout)
     
        self.compact_layout = False

        # Search bar (initially hidden)
        self.search_container = QWidget()
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(self.config.get("ui", "buttons", "spacing") or 8)
        self.search_container.setLayout(search_layout)
     
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search: 'text' or 'U:Bob' or 'U:Bob,Alice' or 'M:hello' or 'U:Bob M:hello'")
        self.search_field.setFont(get_font(FontType.TEXT))
        self.search_field.setFixedHeight(self.config.get("ui", "input_height") or 48)
        self.search_field.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_field, stretch=1)
     
        self.clear_search_btn = create_icon_button(self.icons_path, "trash.svg", "Clear search",
                                                  size_type="large", config=self.config)
        self.clear_search_btn.clicked.connect(self._clear_search)
        search_layout.addWidget(self.clear_search_btn)
     
        self.search_container.setVisible(False)
        layout.addWidget(self.search_container)
     
        if self.search_visible:
            self.search_container.setVisible(True)

        # Stacked widget: List view OR Parser config
        self.stacked = QStackedWidget()
        layout.addWidget(self.stacked, stretch=1)

        # List view page
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
     
        self.stacked.addWidget(self.list_view)
        
        # Add scroll-to-bottom button
        self.scroll_button = ScrollToBottomButton(self.list_view, parent=self)
        
        # Parser config page
        self.parser_widget = ChatlogsParserConfigWidget(self.config, self.icons_path, self.account)
        self.parser_widget.parse_started.connect(self._on_parse_started)
        self.parser_widget.parse_cancelled.connect(self._on_parse_cancelled)
      
        # Connect copy/save buttons
        self.parser_widget.copy_button.clicked.connect(self._on_copy_results)
        self.parser_widget.save_button.clicked.connect(self._on_save_results)
      
        self.stacked.addWidget(self.parser_widget)

        # Show list view by default
        self.stacked.setCurrentWidget(self.list_view)

        self._update_date_display()
        self._error_occurred.connect(self._handle_error)
 
    def _on_copy_results(self):
        """Copy parsed results to clipboard"""
        if not self.all_messages:
            QMessageBox.information(self, "No Results", "No messages to copy.")
            return
      
        # Build text with separators
        text_lines = []
        current_date = None
        message_count = 0
      
        for msg in self.all_messages:
            if msg.is_separator:
                text_lines.append(f"\n{'='*60}")
                text_lines.append(f" {msg.date_str}")
                text_lines.append(f"{'='*60}\n")
                current_date = msg.date_str
            else:
                timestamp = msg.timestamp.strftime("%H:%M:%S")
                text_lines.append(f"[{timestamp}] {msg.username}: {msg.body}")
                message_count += 1
      
        result = '\n'.join(text_lines)
      
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(result)
      
        QMessageBox.information(self, "Copied", f"Copied {message_count} messages to clipboard.")
  
    def _on_save_results(self):
        """Save parsed results to file"""
        if not self.all_messages:
            QMessageBox.information(self, "No Results", "No messages to save.")
            return
      
        # Get default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_dir = get_data_dir("exports")
        default_filename = default_dir / f"chatlog_export_{timestamp}.txt"
      
        # Show save dialog
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Chat Log",
            str(default_filename),
            "Text Files (*.txt);;All Files (*)"
        )
      
        if not filename:
            return
      
        try:
            # Build text with separators
            text_lines = []
            current_date = None
            message_count = 0
          
            for msg in self.all_messages:
                if msg.is_separator:
                    text_lines.append(f"\n{'='*60}")
                    text_lines.append(f" {msg.date_str}")
                    text_lines.append(f"{'='*60}\n")
                    current_date = msg.date_str
                else:
                    timestamp = msg.timestamp.strftime("%H:%M:%S")
                    text_lines.append(f"[{timestamp}] {msg.username}: {msg.body}")
                    message_count += 1
          
            result = '\n'.join(text_lines)
          
            # Write to file
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(result)
          
            QMessageBox.information(self, "Saved", f"Saved {message_count} messages to:\n{filename}")
      
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")
 
    def _toggle_parser(self):
        """Toggle between normal view and parser config"""
        if self.parser_visible:
            # Hide parser, show list
            self.parser_visible = False
            self.stacked.setCurrentWidget(self.list_view)
            self.parse_btn.setIcon(create_icon_button(self.icons_path, "play.svg", "Parse all chatlogs", config=self.config).icon())
            self.parse_btn.setToolTip("Parse all chatlogs")
        else:
            # Show parser, hide list
            self.parser_visible = True
            self.stacked.setCurrentWidget(self.parser_widget)
            self.parse_btn.setIcon(create_icon_button(self.icons_path, "list.svg", "Back to chat logs", config=self.config).icon())
            self.parse_btn.setToolTip("Back to chat logs")
 
    def _on_parse_started(self, config: ParseConfig):
        """Start parsing with given config"""
        self.model.clear()
        self.all_messages = []
        self.temp_parsed_messages = [] # Clear temp storage
        self.last_parsed_date = None
     
        self.parser_worker = ParserWorker(config)
        self.parser_worker.progress.connect(self.parser_widget.update_progress)
        self.parser_worker.messages_found.connect(self._on_parsed_messages)
        self.parser_worker.finished.connect(self._on_parse_finished)
        self.parser_worker.error.connect(self._on_parse_error)
        self.parser_worker.start()
 
    def _on_parse_cancelled(self):
        """Cancel parsing"""
        if self.parser_worker:
            self.parser_worker.stop()
            self.parser_worker = None
 
    def _on_parsed_messages(self, messages, date: str):
        """Handle incrementally parsed messages - ONLY update counter, not layout"""
        # Only add separator and messages if we actually have messages
        if not messages:
            return # Skip empty dates entirely
       
        if date != self.last_parsed_date:
            if self.last_parsed_date is not None:
                # Add separator to temp storage only
                separator = MessageData(datetime.now(), "", "", is_separator=True, date_str=date)
                self.temp_parsed_messages.append(separator)
            self.last_parsed_date = date

        # Convert and store in temp storage - DO NOT add to model yet
        for msg in messages:
            try:
                timestamp = datetime.strptime(msg.timestamp, "%H:%M:%S")
                msg_data = MessageData(timestamp, msg.username, msg.message, None, msg.username)
                self.temp_parsed_messages.append(msg_data)
            except Exception as e:
                print(f"Error processing message: {e}")
   
        # Only update counter - count only actual messages (not separators)
        message_count = sum(1 for m in self.temp_parsed_messages if not m.is_separator)
        self.info_label.setText(f"Found {message_count} messages so far...")
 
    def _on_parse_finished(self, messages):
        """Handle parse completion - NOW add all messages to layout at once"""
        self.parser_worker = None
        self.parser_widget._reset_ui()
        self.last_parsed_date = None
   
        if self.temp_parsed_messages:
            # Disable updates for batch insertion
            self.list_view.setUpdatesEnabled(False)
           
            # Add ALL messages at once
            self.all_messages = self.temp_parsed_messages.copy()
            for msg_data in self.temp_parsed_messages:
                self.model.add_message(msg_data)
           
            # Clear temp storage
            self.temp_parsed_messages = []
           
            # Re-enable updates
            self.list_view.setUpdatesEnabled(True)
           
            # Emit only non-separator messages for userlist
            non_separator_messages = [m for m in self.all_messages if not m.is_separator]
            self.messages_loaded.emit(non_separator_messages)
       
            # Show copy/save buttons
            self.parser_widget.show_copy_save_buttons()
           
            # Scroll to bottom after everything is loaded
            QTimer.singleShot(100, lambda: scroll(self.list_view, mode="bottom", delay=50))
        else:
            self.info_label.setText("No messages found")
 
    def _on_parse_error(self, error_msg: str):
        """Handle parse error"""
        self.parser_worker = None
        self.parser_widget._reset_ui()
        self.temp_parsed_messages = [] # Clear temp on error
        self.info_label.setText(f"❌ Error: {error_msg}")
 
    def _handle_error(self, error_msg: str):
        self.info_label.setText(error_msg)
 
    def _toggle_search(self):
        self.search_visible = not self.search_visible
        self.search_container.setVisible(self.search_visible)
        self.config.set("ui", "chatlog_search_visible", value=self.search_visible)
     
        if self.search_visible:
            self.search_field.setFocus()
        else:
            self.search_field.clear()

    def _on_search_changed(self, text: str):
        self.search_text = text.strip()
        self._apply_filter()
 
    def _parse_search_text(self):
        if not self.search_text:
            return set(), "", False
     
        import re
     
        user_filter = set()
        message_filter = ""
     
        text = self.search_text.strip()
        has_u_prefix = re.search(r'[Uu]:', text)
        has_m_prefix = re.search(r'[Mm]:', text)
        has_prefix = has_u_prefix or has_m_prefix
     
        if not has_prefix:
            return set(), "", False
     
        if has_u_prefix:
            u_pattern = r'[Uu]:\s*(.+?)(?:\s+[Mm]:|$)'
            match = re.search(u_pattern, text)
            if match:
                users_str = match.group(1).strip()
                users = [u.strip() for u in users_str.split(',') if u.strip()]
                user_filter.update(users)
     
        if has_m_prefix:
            m_pattern = r'[Mm]:\s*(.+?)(?:\s+[Uu]:|$)'
            match = re.search(m_pattern, text)
            if match:
                message_filter = match.group(1).strip().lower()
     
        return user_filter, message_filter, True

    def _clear_search(self):
        self.search_field.clear()
        self._apply_filter()

    def _update_date_display(self):
        self.date_label.setText(self.current_date.strftime("%Y-%m-%d (%A)"))
        self.next_btn.setEnabled(self.current_date < datetime.now().date())
        self.prev_btn.setEnabled(self.current_date > self.parser.MIN_DATE)
 
    def set_compact_layout(self, compact: bool):
        """Handle responsive layout for < 1000px width"""
        if compact == self.compact_layout:
            return
     
        if compact:
            # Remove sub-layouts from main_bar
            self.main_bar.takeAt(1) # nav_buttons_layout item
            self.main_bar.takeAt(0) # info_block item
            # Remove main_bar from top_bar_layout
            self.top_bar_layout.takeAt(0)
            # Add sub-layouts to top_bar_layout
            self.top_bar_layout.addLayout(self.nav_buttons_layout)
            self.top_bar_layout.addLayout(self.info_block)
            self.compact_layout = True
        else:
            # Remove sub-layouts from top_bar_layout
            self.top_bar_layout.takeAt(1) # info_block item
            self.top_bar_layout.takeAt(0) # nav_buttons_layout item
            # Add main_bar back
            self.top_bar_layout.addLayout(self.main_bar)
            # Add sub-layouts to main_bar
            self.main_bar.addLayout(self.info_block, stretch=1)
            self.main_bar.addLayout(self.nav_buttons_layout)

            self.compact_layout = False
 
    def set_compact_mode(self, compact: bool):
        self.delegate.set_compact_mode(compact)
        self._force_recalculate()
 
    def update_theme(self):
        self.delegate.update_theme()
        self.color_cache.clear()
        self._force_recalculate()
 
    def _force_recalculate(self):
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
        self.filtered_usernames = usernames
        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)
 
    def clear_filter(self):
        self.filtered_usernames = set()
        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)
 
    def _apply_filter(self):
        # Batch operations for better performance
        self.list_view.setUpdatesEnabled(False)
       
        self.model.clear()
     
        if not self.all_messages:
            self.list_view.setUpdatesEnabled(True)
            return
     
        search_users, search_message, is_prefix_mode = self._parse_search_text()
        messages_to_show = self.all_messages
     
        if is_prefix_mode:
            if search_users:
                search_users_lower = {u.lower() for u in search_users}
                messages_to_show = [msg for msg in messages_to_show
                                if msg.username.lower() in search_users_lower]
         
            if search_message:
                messages_to_show = [msg for msg in messages_to_show
                                if search_message in msg.body.lower()]
        else:
            if self.filtered_usernames:
                messages_to_show = [msg for msg in messages_to_show
                                if msg.username in self.filtered_usernames]
         
            if self.search_text:
                search_lower = self.search_text.lower()
                messages_to_show = [msg for msg in messages_to_show
                                if search_lower in msg.username.lower() or
                                    search_lower in msg.body.lower()]
     
        # Batch add all filtered messages
        for msg in messages_to_show:
            self.model.add_message(msg)
     
        self.list_view.setUpdatesEnabled(True)
       
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
            if hasattr(self, '_pending_data'):
                _, size_text, was_truncated, from_cache = self._pending_data
                cache_marker = " 📁" if from_cache else ""
                if was_truncated:
                    self.info_label.setText(f"⚠️ Loaded {total} messages (file truncated at {self.parser.MAX_FILE_SIZE_MB}MB limit) · {size_text}{cache_marker}")
                else:
                    self.info_label.setText(f"Loaded {total} messages · {size_text}{cache_marker}")
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
                messages, was_truncated, from_cache = self.parser.get_messages(date_str)
                html, _, _ = self.parser.fetch_log(date_str)
                size_kb = len(html.encode('utf-8')) / 1024
                size_text = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
             
                self._pending_data = (messages, size_text, was_truncated, from_cache)
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
            messages, size_text, was_truncated, from_cache = getattr(self, '_pending_data', ([], '', False, False))
         
            # Batch operations
            self.list_view.setUpdatesEnabled(False)
           
            self.model.clear()
            self.all_messages = []
         
            cache_marker = " 📁" if from_cache else ""
         
            if not messages:
                self.info_label.setText(f"No messages · {size_text}{cache_marker}")
                self.messages_loaded.emit([])
                self.list_view.setUpdatesEnabled(True)
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
         
            self.list_view.setUpdatesEnabled(True)
           
            if was_truncated:
                self.info_label.setText(f"⚠️ Loaded {len(messages)} messages (file truncated at {self.parser.MAX_FILE_SIZE_MB}MB limit) · {size_text}{cache_marker}")
            elif self.filtered_usernames or self.search_text:
                pass
            else:
                self.info_label.setText(f"Loaded {len(messages)} messages · {size_text}{cache_marker}")
         
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
        if self.delegate:
            self.delegate.cleanup()
        if hasattr(self, 'scroll_button'):
            self.scroll_button.cleanup()
        if hasattr(self, 'auto_scroller'):
            self.auto_scroller.cleanup()

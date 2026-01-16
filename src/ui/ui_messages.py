"""Messages display widget"""
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListView
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from helpers.emoticons import EmoticonManager
from helpers.scroll import scroll
from helpers.cache import get_cache
from ui.message_model import MessageListModel, MessageData
from ui.message_delegate import MessageDelegate
from helpers.fonts import get_font, FontType
from helpers.scroll_button import ScrollToBottomButton

class MessagesWidget(QWidget):
    """Widget for displaying chat messages with virtual scrolling"""
    timestamp_clicked = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.input_field = None
        self.cache = get_cache()
       
        emoticons_path = Path(__file__).resolve().parent.parent / "emoticons"
        self.emoticon_manager = EmoticonManager(emoticons_path)
       
        self.model = MessageListModel(max_messages=10000)
        # Pass the cache's color dictionary directly to delegate
        self.delegate = MessageDelegate(config, self.emoticon_manager, self.cache._color_cache)
       
        self.delegate.timestamp_clicked.connect(self.timestamp_clicked.emit)
        self.delegate.username_clicked.connect(self._handle_username_click)
       
        self._setup_ui()

    def set_color_cache(self, cache: dict):
        """Update delegate's color cache reference"""
        self.delegate.color_cache = cache
   
    def set_input_field(self, input_field):
        self.input_field = input_field
        self.delegate.set_input_field(input_field)
   
    def _handle_username_click(self, username: str, is_double_click: bool):
        if not self.input_field:
            return
       
        current = (self.input_field.text() or "").strip()
        existing = [u.strip() for u in current.split(',') if u.strip()]
       
        if is_double_click:
            if len(existing) == 1 and existing[0] == username:
                self.input_field.clear()
            else:
                self.input_field.setText(username + ", ")
        else:
            if username not in existing:
                if existing:
                    self.input_field.setText(", ".join(existing + [username]) + ", ")
                else:
                    self.input_field.setText(username + ", ")
       
        self.input_field.setFocus()
   
    def set_compact_mode(self, compact: bool):
        if self.delegate.compact_mode != compact:
            self.delegate.set_compact_mode(compact)
            self._force_recalculate()
   
    def _setup_ui(self):
        margin = self.config.get("ui", "margins", "list") or 2
        spacing = self.config.get("ui", "spacing", "widget_elements") or 4
       
        layout = QVBoxLayout()
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)
        self.setLayout(layout)
       
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.delegate.set_list_view(self.list_view)
       
        self.list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.list_view.setUniformItemSizes(False)
       
        # Don't set spacing from config - let it be fully dynamic
        self.list_view.setSpacing(0)
       
        self.list_view.setFrameShape(QListView.Shape.NoFrame)
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
        # Update centralized color cache if background color is available
        if msg.login and getattr(msg, 'background', None):
            # Get current theme
            theme = self.config.get("ui", "theme")
            bg_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
            # Calculate optimized color and store it
            optimized_color = self.cache.get_or_calculate_color(msg.login, msg.background, bg_hex, 4.5)
       
        msg_data = MessageData(
            getattr(msg, 'timestamp', None) or datetime.now(),
            msg.login if msg.login else "Unknown",
            msg.body,
            getattr(msg, 'background', None),
            msg.login,
            getattr(msg, 'is_private', False)
        )
        self.model.add_message(msg_data)
        QTimer.singleShot(0, lambda: scroll(self.list_view, mode="bottom", delay=100))
   
    def clear_private_messages(self):
        """Clear all private messages"""
        self.model.clear_private_messages()
   
    def rebuild_messages(self):
        self.delegate.update_theme()
        self.delegate._emoticon_cache.clear()
        self._force_recalculate()
   
    def update_theme(self):
        theme = self.config.get("ui", "theme")
        self.delegate.is_dark_theme = (theme == "dark")
        self.delegate.bg_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
   
    def _force_recalculate(self):
        """Aggressive force recalculation of all item sizes"""
        # Disable updates during recalculation
        self.list_view.setUpdatesEnabled(False)
       
        # Clear the view completely
        self.list_view.reset()
       
        # Clear all internal size caches
        self.list_view.clearSelection()
       
        # Force delegate to recalculate all sizes
        self.list_view.scheduleDelayedItemsLayout()
       
        # Signal model that everything changed
        self.model.layoutChanged.emit()
       
        # Force repaint
        self.list_view.setUpdatesEnabled(True)
        self.list_view.viewport().update()
       
        # Additional force update
        QTimer.singleShot(10, lambda: self.list_view.viewport().update())
   
    def cleanup(self):
        """Cleanup delegate to stop animation timer"""
        if self.delegate:
            self.delegate.cleanup()
        if hasattr(self, 'scroll_button'):
            self.scroll_button.cleanup()
   
    def clear(self):
        self.model.clear()
   
    @property
    def scroll_area(self):
        """Compatibility property for scroll helpers"""
        return self.list_view

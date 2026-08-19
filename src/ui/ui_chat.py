"""Chat window with XMPP integration"""
import threading
import re
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import(
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QApplication, QMenu,
    QStackedWidget, QStatusBar, QLabel, QProgressBar, QPushButton, QMessageBox, QSplitter, QTabWidget, QTabBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QEvent
from PyQt6.QtGui import QAction, QCursor
            

from helpers.config import Config
from helpers.create import create_icon_button, _render_svg_icon, update_all_icons, set_theme, HoverIconButton
from helpers.resize import handle_chat_resize, recalculate_layout
from helpers.color_utils import get_private_message_colors
from helpers.scroll.scroll import scroll
from helpers.cache import get_cache
from helpers.username_color_manager import(
    change_username_color,
    reset_username_color,
    update_from_server
)
from helpers.emoticons import EmoticonManager
from helpers.fonts import get_font, FontType, get_userlist_width
from helpers.font_scaler import FontScaleSlider
from helpers.voice_engine import get_voice_engine, play_sound
from helpers.me_action import format_me_action
from helpers.window_size_manager import WindowSizeManager
from helpers.window_presets_dialog import WindowPresetsDialog
from themes.theme import ThemeManager
from core.xmpp import XMPPClient
from core.messages import Message
from ui.ui_messages import MessagesWidget
from ui.ui_gameroom import GameRoomWidget
from ui.ui_userlist import UserListWidget
from ui.ui_chatlog import ChatlogWidget
from ui.ui_chatlog_userlist import ChatlogUserlistWidget
from ui.ui_profile import ProfileWidget
from ui.ui_emoticon_selector import EmoticonSelectorWidget, PANEL_WIDTH
from ui.ui_pronunciation import PronunciationWidget
from ui.ui_banlist import BanListWidget
from ui.ui_settings import SettingsWidget, get_sound_path
from helpers.duration_dialog import DurationDialog
from helpers.jid_utils import extract_user_data_from_jid
from ui.ui_buttons import ButtonPanel
from helpers.help import HelpPanel
from components.notification import show_notification, popup_manager
from helpers.input_activity import cursor_moved_or_key_pressed
from core.races_listener import RacesListener
from components.messages_separator import NewMessagesSeparator
from components.tag_button import update_all_tag_buttons


class SignalEmitter(QObject):
    message_received = pyqtSignal(object)
    presence_received = pyqtSignal(object)
    bulk_update_complete = pyqtSignal()
    connection_changed = pyqtSignal(str)

class ChatWindow(QWidget):
    _dispatch = pyqtSignal(object)  # thread-safe main-thread callable dispatch
    _HISTORY_SETTLE_MS = 400  # idle gap after the last initial-history message before it's considered fully loaded

    def __init__(
        self,
        account=None,
        app_controller=None,
        pronunciation_manager=None,
        ban_manager=None
        ):
        super().__init__()
        self._dispatch.connect(lambda f: f())
        self.app_controller = app_controller
        self.pronunciation_manager = pronunciation_manager
        self.ban_manager = ban_manager
        self.tray_mode = False
        self.really_close = False
        self.account = account
        self.xmpp_client = None
        self.signal_emitter = SignalEmitter()
        self.cache = get_cache()

        self.races_listener = None
        self._competition_notified = set()  # game_ids already announced this session
        self._competition_log_lines = []
        self._competition_log_status = {}  # game_id -> last logged status (dedupe)
        self._races_status = "disconnected"
        self._pending_competitions = []  # queued while chat history isn't ready yet
        self._chat_ready = False  # True once initial history has settled once
        self._history_settle_timer = QTimer(self)  # fires when history stream goes quiet
        self._history_settle_timer.setSingleShot(True)
        self._history_settle_timer.timeout.connect(self._on_history_settled)

        # Live-updating competition messages: game_id -> {mult, url, begintime, players}
        self._competition_live = {}
        self._competition_alert_timers = {}  # game_id -> pending lead-time alert QTimer
        self._competition_focus_gid = None  # keep this row centered while chips grow after alert
        self._competition_countdown_timer = QTimer(self)
        self._competition_countdown_timer.timeout.connect(self._tick_competition_countdowns)
        self._competition_sound_repeat_timer = QTimer(self)
        self._competition_sound_repeat_timer.timeout.connect(self._on_competition_sound_repeat_tick)
        self._competition_sound_repeat_cursor_pos = None

        self.initial_roster_loading = False
        self.auto_hide_messages_userlist = True
        self.auto_hide_chatlog_userlist = True

        # Track window show/reset state to avoid persisting programmatic geometry
        self._showing_window = False
        self._resetting_geometry = False

        # Simple connection state tracking
        self.is_connecting = False # True when attempting to connect
        self.allow_reconnect = True # Disable when switching accounts
        self.reconnect_count = 0 # Incremented each time a reconnect attempt is made
        self.reconnect_timer = None # Timer for delayed reconnect attempts

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
        # rating competitions tracking
        track = self.config.get("competitions", "enabled")
        if track is None or track:
            # defer start until event loop is running
            QTimer.singleShot(0, lambda: self.set_track_competitions(True))


        # Initialize emoticon manager
        emoticons_path = Path(__file__).parent.parent / "emoticons"
        self.emoticon_manager = EmoticonManager(emoticons_path)
        
        # Initialize window size manager
        self.window_size_manager = WindowSizeManager(
            self.config,
            on_save_callback=self.update_reset_size_button_state
        )
        
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
        self.competition_sound_path = None
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
        self.apply_voice_sound(not current)

    def apply_voice_sound(self, new: bool):
        """Set TTS (Voice Sound) to an explicit state. Shared by the panel button and Settings."""
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

    def on_toggle_effects_sound(self):
        """Toggle effects sound on/off from the panel button."""
        current = self.config.get("sound", "effects_enabled")
        if current is None:
            current = True
        self.apply_effects_sound(not current)

    def apply_effects_sound(self, new: bool):
        """Set effects sound to an explicit state. Shared by the panel button and Settings."""
        # Persist centrally via app controller so tray stays in sync
        config = self.app_controller.config if self.app_controller else self.config
        config.set("sound", "effects_enabled", value=new)
        # Also update local config data to keep in sync
        if self.app_controller:
            self.config.data = self.app_controller.config.data

        # update tray menu state immediately
        if self.app_controller and hasattr(self.app_controller, 'update_sound_menu'):
            self.app_controller.update_sound_menu()

        # Update visual and icon
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'effects_button', None):
            self.button_panel.set_button_state(self.button_panel.effects_button, new)
            self.button_panel.update_effects_button_icon()

    def update_effects_button_state(self):
        """Sync effects button visual to config state."""
        enabled = self.config.get("sound", "effects_enabled")
        if enabled is None:
            enabled = True
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'effects_button', None):
            self.button_panel.set_button_state(self.button_panel.effects_button, enabled)
            self.button_panel.update_effects_button_icon()

    def on_toggle_notification(self):
        """Cycle through notification states: Stack → Replace → Muted → Stack"""
        current_mode = self.config.get("notification", "mode") or "stack"
        current_muted = self.config.get("notification", "muted") or False
        
        # Determine next state in cycle
        if current_muted:
            # Muted → Stack (unmute and reset to stack)
            new_mode = "stack"
            new_muted = False
        elif current_mode == "stack":
            # Stack → Replace
            new_mode = "replace"
            new_muted = False
        else:  # replace
            # Replace → Muted
            new_mode = "replace"  # Keep mode, just mute
            new_muted = True
        
        self.apply_notification_state(new_mode, new_muted)

    def apply_notification_state(self, new_mode: str, new_muted: bool):
        """Set notification mode/muted to explicit values. Shared by the panel button and Settings."""
        # Persist centrally via app controller so tray stays in sync
        config = self.app_controller.config if self.app_controller else self.config
        config.set("notification", "mode", value=new_mode)
        config.set("notification", "muted", value=new_muted)
        
        # Update local config data to keep in sync
        if self.app_controller:
            self.config.data = self.app_controller.config.data
        
        # Update tray menu state immediately
        if self.app_controller and hasattr(self.app_controller, 'update_notification_menu'):
            self.app_controller.update_notification_menu()
        
        # Update popup_manager
        popup_manager.set_notification_mode(new_mode)
        popup_manager.set_muted(new_muted)
        
        # Update button visual
        self.button_panel.update_notification_button_icon()
        
        # Log state change
        state_text = "Muted" if new_muted else f"{new_mode.capitalize()} mode"
        print(f"🔔 Notifications: {state_text}")

    def update_notification_button_state(self):
        """Sync notification button visual to config state"""
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'notification_button', None):
            self.button_panel.update_notification_button_icon()

    def sync_notification_state(self):
        """Sync notification state from config - updates button and popup_manager"""
        # Update config data first
        if self.app_controller:
            self.config.data = self.app_controller.config.data
        
        # Update button icon to match new state
        self.update_notification_button_state()
        
        # Update popup_manager to match config
        mode = self.config.get("notification", "mode") or "stack"
        muted = self.config.get("notification", "muted") or False
        popup_manager.set_notification_mode(mode)
        popup_manager.set_muted(muted)

    def on_toggle_always_on_top(self):
        """Toggle always on top window flag"""
        current = self.config.get("ui", "always_on_top") or False
        self.apply_always_on_top(not current)

    def apply_always_on_top(self, new: bool):
        """Set always-on-top to an explicit state. Shared by the panel button and Settings."""
        # Save to config
        config = self.app_controller.config if self.app_controller else self.config
        config.set("ui", "always_on_top", value=new)
        
        # Update local config data
        if self.app_controller:
            self.config.data = self.app_controller.config.data
        
        # Apply window flag (requires hide/show to take effect properly)
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, new)
        
        # Show window if it was visible before
        if was_visible:
            self.setWindowOpacity(0)
            self.show()
            QTimer.singleShot(50, lambda: self.setWindowOpacity(1))
            self.activateWindow()
            self.raise_()
        
        # Update button icon to reflect new state
        if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'update_pin_button_icon'):
            self.button_panel.update_pin_button_icon()
        
        print(f"📌 Always on top: {'Enabled' if new else 'Disabled'}")

    def update_always_on_top_button_state(self):
        """Sync always on top button visual to config state"""
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'update_pin_button_icon', None):
            self.button_panel.update_pin_button_icon()

    def on_exit_requested(self):
        """Handle exit request from the button panel."""
        # Prefer the application controller's cleanup exit when available
        if self.app_controller and hasattr(self.app_controller, 'exit_application'):
            self.app_controller.exit_application()
        else:
            QApplication.quit()

    def _setup_sounds(self):
        """Setup sound paths using the per-category sound folders."""
        sounds_dir = Path(__file__).parent.parent / "sounds"
        for kind, attr in (
            ("mention", "mention_sound_path"),
            ("ban", "ban_sound_path"),
            ("competition", "competition_sound_path"),
        ):
            path = get_sound_path(sounds_dir, kind, self.config)
            setattr(self, attr, str(path) if path else None)

    def _init_ui(self):
        window_title = f"Chat - {self.account['chat_username']}" if self.account else "Chat"
        self.setWindowTitle(window_title)
        geo = QApplication.primaryScreen().availableGeometry()
      
        # Check for saved window geometry (size + position) first
        saved_width, saved_height, saved_x, saved_y = self.window_size_manager.get_saved_geometry()

        if saved_width and saved_height:
            window_width, window_height = saved_width, saved_height
            window_x = saved_x if saved_x is not None else None
            window_y = saved_y if saved_y is not None else None
        else:
            window_width, window_height, window_x, window_y = self._calculate_default_geometry()

        # Apply window geometry
        self.resize(window_width, window_height)
        if window_x is not None and window_y is not None:
            self.move(window_x, window_y)
        
        # Apply always on top flag from config if enabled
        always_on_top = self.config.get("ui", "always_on_top")
        if always_on_top:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

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
        self.messages_widget = MessagesWidget(self.config, self.emoticon_manager, my_username=my_username)

        # Splitter so a chatlog can be shown alongside the live messages view
        # (RMB on a timestamp), without leaving/replacing the messages view itself
        self.messages_splitter = QSplitter(Qt.Orientation.Vertical)
        self.messages_splitter.addWidget(self.messages_widget)
        self.chatlog_split_widget = None  # the split-pane ChatlogWidget, when open

        self.game_rooms = {}  # game_id -> GameRoomWidget
        self.room_tabs = None  # QTabWidget; General is always tab 0 when present
        self.general_body = None
        self._unread_rooms = set()  # game_ids with a "●" unread marker on their tab
        self._general_unread = False  # "●" on General when messages arrive while on a game tab

        self.stacked_widget.addWidget(self.messages_splitter)
        self.chatlog_widget = None
        self.chatlog_userlist_widget = None
        self.pre_profile_view = None  # 'messages' or 'chatlog' - where to return after profile/pronunciation/ban-list views
        self._restore_room_gid = None  # game_id of room tab to reopen after profile/private...

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
    
        # User list widget (right side, vertical scrollable)
        self.user_list_widget = UserListWidget(self.config, self.input_field, self.ban_manager)
        # Connect signals for user list actions
        self._wire_userlist_signals(self.user_list_widget)
        self.user_list_widget.open_game_requested.connect(self._open_game_room_by_id)

        messages_userlist_visible = self.config.get("ui", "messages_userlist_visible")
        userlist_visible = messages_userlist_visible if messages_userlist_visible is not None else True
        self.user_list_widget.setVisible(userlist_visible)

        # Right column: wrap in QWidget so hiding it collapses the space
        self.userlist_panel = QWidget()
        userlist_panel = QVBoxLayout()
        userlist_panel.setContentsMargins(0, 0, 0, 0)
        userlist_panel.setSpacing(4)
        userlist_panel.addWidget(self.user_list_widget, stretch=1)

        # Font scale slider under userlist — fixed height matches input_container
        # so the slider is vertically centred against the input field row.
        font_scaler = getattr(self.app_controller, 'font_scaler', None)
        if font_scaler is not None:
            self.font_scale_slider = FontScaleSlider(font_scaler)
            self.font_scale_slider.setFixedHeight(self.input_field.minimumHeight())
            userlist_panel.addWidget(self.font_scale_slider)
        else:
            self.font_scale_slider = None

        self.userlist_panel.setLayout(userlist_panel)
        self.userlist_panel.setFixedWidth(get_userlist_width())
        self.userlist_panel.setVisible(userlist_visible)
        if font_scaler is not None:
            font_scaler.font_size_committed.connect(
                lambda: self.userlist_panel.setFixedWidth(get_userlist_width())
            )
        self.content_layout.addWidget(self.userlist_panel)
     
        # Create button panel (right side, vertical scrollable)
        # Add to content_wrapper so it's always on the right
        self.button_panel = ButtonPanel(self.config, self.icons_path, self.theme_manager)

        self.button_panel.toggle_userlist_requested.connect(self.toggle_user_list)
        self.button_panel.switch_account_requested.connect(self._on_switch_account)
        self.button_panel.show_banlist_requested.connect(self.show_ban_list_view)
        self.button_panel.toggle_voice_requested.connect(self.on_toggle_voice_sound)
        self.button_panel.pronunciation_requested.connect(self.show_pronunciation_view)
        self.button_panel.toggle_effects_requested.connect(self.on_toggle_effects_sound)
        self.button_panel.toggle_notification_requested.connect(self.on_toggle_notification)

        # Color management connections (change / reset / update-from-server)
        self.button_panel.change_color_requested.connect(self.on_change_username_color)
        self.button_panel.reset_color_requested.connect(self.on_reset_username_color)
        self.button_panel.update_color_requested.connect(self.on_update_username_color)

        self.button_panel.toggle_theme_requested.connect(self.toggle_theme)
        self.button_panel.reset_window_size_requested.connect(self.reset_window_size)
        self.button_panel.show_window_presets_requested.connect(self.show_window_presets)
        self.button_panel.toggle_always_on_top_requested.connect(self.on_toggle_always_on_top)
        self.button_panel.show_settings_requested.connect(self.show_settings_view)
        self.button_panel.exit_requested.connect(self.on_exit_requested)
        self.button_panel.reconnect_requested.connect(self.manual_reconnect)

        content_wrapper.addWidget(self.button_panel, stretch=0)

        # Initialize voice, mention and notification button states
        self.update_voice_button_state()
        self.update_effects_button_state()
        self.update_notification_button_state()
        
        # Initialize reset window size button state
        self.update_reset_size_button_state()

        # Initialize always on top button state
        self.update_always_on_top_button_state()

        # Enable mouse tracking for hover-reveal
        self.setMouseTracking(True)
        self._hover_reveal = False
     
        # Initialize userlist button state
        messages_userlist_visible = self.config.get("ui", "messages_userlist_visible")
        if messages_userlist_visible is not None:
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, messages_userlist_visible)
        else:
            # Default to visible
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, True)
     
        # Emoticon selector widget (overlay - positioned absolutely)
        # Create AFTER userlist so positioning works correctly
        self.emoticon_selector = EmoticonSelectorWidget(
            self.config,
            self.emoticon_manager,
            self.icons_path
        )
        self.emoticon_selector.attach(self, self._on_emoticon_selected)

        # Register shared instance with popup manager so notifications can borrow it
        popup_manager.emoticon_selector = self.emoticon_selector

        # Help panel (context-aware, shared across all views)
        self.help_panel = HelpPanel(self)
     
        # Install a minimal event filter to detect clicks outside selector
        # (install on window and application with a single line to keep it simple)
        self.installEventFilter(self)
        try:
            app = QApplication.instance()
            if app:
                app.installEventFilter(self)
        except Exception:
            pass

        # Set focus policy to ensure we receive key events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Position will be set in showEvent
        QTimer.singleShot(50, self._position_emoticon_selector)
     
        self.messages_widget.timestamp_left_clicked.connect(self.show_chatlog_view)
        self.messages_widget.timestamp_right_clicked.connect(self.show_chatlog_split_view)
        self.messages_widget.competition_timestamp_right_clicked.connect(
            lambda msg: self.open_game_room_tab(msg, room_label="Competition")
        )
        self._wire_username_signals(self.messages_widget)
        self.messages_widget.chatlog_link_clicked.connect(self.show_chatlog_split_view)
    
        self._update_input_style()

    def _reclaim_emoticon_selector(self):
        """Take back the selector from a popup that borrowed it, cleaning up that popup's layout."""
        self.emoticon_selector.attach(self, self._on_emoticon_selected)

    def _toggle_emoticon_selector(self):
        """Toggle emoticon selector - reclaim from notification if borrowed, then toggle."""
        if not hasattr(self, 'emoticon_selector'):
            return
        if self.emoticon_selector.parent() is not self:
            self._reclaim_emoticon_selector()
        # _position_emoticon_selector resets fixedSize, clearing any height set by a notification
        self.emoticon_selector.toggle_visibility()
        self._position_emoticon_selector()

        # When opening, remove input focus so arrow/hjkl hotkeys work immediately.
        # Explicitly take focus on ChatWindow so the scroll area inside the selector
        # doesn't capture arrow keys before keyPressEvent sees them.
        if self.emoticon_selector.isVisible():
            self._active_input_field().clearFocus()
            self.setFocus()
 
    def _current_game_room(self):
        """GameRoomWidget of the currently selected tab, or None if General."""
        if not self.room_tabs or self.room_tabs.currentIndex() <= 0:
            return None
        w = self.room_tabs.currentWidget()
        return w if isinstance(w, GameRoomWidget) else None

    def _active_input_field(self):
        """Input that should receive typed/emoticon text."""
        gr = self._current_game_room()
        if gr is not None and getattr(gr, 'input_field', None) is not None:
            if gr.input_field.hasFocus() or not self.input_field.hasFocus():
                return gr.input_field
        return self.input_field

    def _active_emoticon_button(self):
        """Emoticon button of the active room (game tab or General)."""
        gr = self._current_game_room()
        if gr is not None and getattr(gr, 'emoticon_button', None) is not None:
            return gr.emoticon_button
        return self.emoticon_button

    def _on_emoticon_selected(self, emoticon_name: str):
        """Insert emoticon into the active input field."""
        field = self._active_input_field()
        cursor_pos = field.cursorPosition()
        current_text = field.text() or ""
        emoticon_code = f":{emoticon_name}: "
        field.setText(current_text[:cursor_pos] + emoticon_code + current_text[cursor_pos:])
        field.setCursorPosition(cursor_pos + len(emoticon_code))
        QTimer.singleShot(0, self._refocus_if_selector_closed)

    def _refocus_if_selector_closed(self):
        if not (hasattr(self, 'emoticon_selector') and self.emoticon_selector.isVisible()):
            self._active_input_field().setFocus()

    def _position_emoticon_selector(self):
        """Place selector aligned to the active room's emoticon button."""
        if not hasattr(self, 'emoticon_selector'):
            return

        # Don't reposition while the selector is borrowed by a notification popup.
        # Calling setFixedSize/move on it while it lives inside a notification's
        # layout corrupts that layout, causing an empty-space artifact.
        if self.emoticon_selector.parent() is not self:
            return

        # Clamp size to available space
        available = max(200, self.height() - self.input_container.height() - 40)
        h = max(250, min(650, available))
        w = PANEL_WIDTH
        self.emoticon_selector.setFixedSize(w, h)

        # Align to the button of the current tab (General or game room).
        # General's button is inside a hidden tab while a game room is active,
        # so its geometry is unreliable until that tab has been shown at least once.
        btn = self._active_emoticon_button()
        btn_top_right = self.mapFromGlobal(btn.mapToGlobal(btn.rect().topRight()))
        x = btn_top_right.x() - w
        y = max(16, btn_top_right.y() - h - 8)
        x = max(8, min(x, self.width() - w - 8))

        self.emoticon_selector.move(x, y)
        self.emoticon_selector.raise_()

    def _calculate_default_geometry(self):
        """Calculate default window size and position"""
        geo = QApplication.primaryScreen().availableGeometry()
        width = geo.width() if geo.width() < 1000 else int(geo.width() * 0.7)
        height = geo.height() - 32
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y()
        return width, height, x, y

    def eventFilter(self, obj, event):
        font_scaler = getattr(self.app_controller, 'font_scaler', None)
        if font_scaler is not None:
            # Ctrl + Scroll → font size
            if event.type() == QEvent.Type.Wheel:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    if event.angleDelta().y() > 0:
                        font_scaler.scale_up()
                    else:
                        font_scaler.scale_down()
                    return True
            # Ctrl + Plus/Minus/Equal → font size
            elif event.type() == QEvent.Type.KeyPress:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                        font_scaler.scale_up()
                        return True
                    elif event.key() == Qt.Key.Key_Minus:
                        font_scaler.scale_down()
                        return True

        # Handle Tab key for view switching (or emoticon group cycling when selector is open)
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            sel = getattr(self, 'emoticon_selector', None)
            if sel and sel.isVisible():
                # Emoticon selector gets priority: Tab/Shift+Tab cycles through groups
                forward = event.key() != Qt.Key.Key_Backtab and not (
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                )
                sel.cycle_tab(forward=forward)
                return True

            if event.key() == Qt.Key.Key_Tab:
                current_view = self.stacked_widget.currentWidget()
                if current_view == self.messages_splitter:
                    # Close the split chatlog pane if open, otherwise switch to full chatlog view
                    if self.chatlog_split_widget:
                        self._close_chatlog_split_view()
                    else:
                        self.show_chatlog_view()
                elif current_view == self.chatlog_widget:
                    # Close the date split pane if open, otherwise leave chatlog for messages
                    if self.chatlog_widget.split_chatlog_widget:
                        self.chatlog_widget._close_split_view()
                    else:
                        # Restore room tab if chatlog was opened from a game tab (Tab / ensure)
                        self._on_stacked_back()
                else:
                    # Profile / settings / ban / pronun → messages, restore room tab if any
                    self._on_stacked_back()
                return True
        
        # Handle mouse button presses/releases for navigation and focus reclaim
        if event.type() == QEvent.Type.MouseButtonPress:
            # Back/Forward mouse buttons navigate chatlog days
            # (works on main stacked chatlog OR split view under cursor)
            cw = self._get_hovered_chatlog_widget()
            if cw:
                direction = {Qt.MouseButton.BackButton: -1, Qt.MouseButton.ForwardButton: 1}.get(event.button())
                if direction is not None:
                    cw._navigate_hold(direction)
                    return True

            # Close emoticon selector if click is outside it and outside the button
            if hasattr(self, 'emoticon_selector') and self.emoticon_selector.isVisible():
                try:
                    gp = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                    w = QApplication.widgetAt(gp)
                    # Walk up parents to see if click landed inside selector or on the button
                    btn = self._active_emoticon_button()
                    inside = False
                    while w:
                        if w == self.emoticon_selector or w == btn:
                            inside = True
                            break
                        w = w.parentWidget()
                    if not inside and self.emoticon_selector.parent() is self:
                        self.emoticon_selector.setVisible(False)
                        self.config.set("ui", "emoticon_selector_visible", value=False)
                except Exception:
                    pass

            # Reclaim focus for ChatWindow after any click that doesn't land on a
            # text input — keeps arrow/hotkeys working regardless of what was clicked.
            # Skip when the click is inside a QMenu (e.g. context menu "Paste"),
            # otherwise focus is stolen from the input field before the action fires.
            try:
                gp = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                clicked = QApplication.widgetAt(gp)
                in_menu = False
                w = clicked
                while w:
                    if isinstance(w, QMenu):
                        in_menu = True
                        break
                    w = w.parentWidget()
                if clicked and not in_menu and not isinstance(clicked, QLineEdit):
                    self.setFocus()
            except Exception:
                pass

        if event.type() == QEvent.Type.MouseButtonRelease:
            cw = self._get_hovered_chatlog_widget()
            if cw and event.button() in (Qt.MouseButton.BackButton, Qt.MouseButton.ForwardButton):
                cw._navigate_hold()
                return True

        return super().eventFilter(obj, event)

    def showEvent(self, event):
        """Handle window show events"""
        super().showEvent(event)

        # Prevent programmatic geometry changes during show from being saved
        self._showing_window = True

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
                delegate = self.messages_widget.delegate
                delegate.set_list_view(self.messages_widget.list_view)
                # Ensure timer is running
                if not delegate.animation_timer.isActive():
                    delegate.animation_timer.start(33)
                # Restart any QMovie instances
                if delegate.message_renderer and hasattr(delegate.message_renderer, '_movie_cache'):
                    for movie in delegate.message_renderer._movie_cache.values():
                        try:
                            movie.start()
                        except Exception:
                            pass
        except Exception as e:
            print(f"ShowEvent resume animations error: {e}")

        # Update notification and always-on-top button state on show
        if hasattr(self, 'button_panel'):
            self.button_panel.update_notification_button_icon()
            # Ensure pin/unpin icon reflects current config
            self.button_panel.update_pin_button_icon()

        # Trigger an initial resize handler so UI elements (userlist, button panel)
        # reflect the current width immediately on first show
        QTimer.singleShot(50, lambda: self._apply_resize(self.width()))

        # Clear the showing flag after a short delay so subsequent user-initiated resize/move
        # events will be persisted normally
        QTimer.singleShot(200, lambda: setattr(self, '_showing_window', False))

    def disable_reconnect(self):
        """Disable auto-reconnect (called when switching accounts)"""
        self.allow_reconnect = False

    def _clear_for_reconnect(self):
        """Clear messages and userlist for fresh reconnection"""
        # Clear all messages to avoid duplicates (server will send last 20 again)
        self.messages_widget.clear()

        # History is being reloaded from scratch - hold competitions back until it settles again
        self._chat_ready = False
        self._history_settle_timer.stop()
    
        # Clear userlist completely (will rebuild from fresh roster)
        if hasattr(self.user_list_widget, 'clear_all'):
            self.user_list_widget.clear_all()
    
        # Exit private mode if active
        if self.private_mode:
            self.exit_private_mode()

        if self.game_rooms:
            for gid in list(self.game_rooms.keys()):
                self._close_game_room_tab(gid)

    def _is_connected(self):
        """Check if XMPP client is connected"""
        return self.xmpp_client and hasattr(self.xmpp_client, 'sid') and self.xmpp_client.sid

    def _ensure_general_tab_visible(self):
        """Switch to General so stacked views/input are visible; remember the room tab."""
        if self.room_tabs is not None and self.room_tabs.currentIndex() != 0:
            w = self.room_tabs.currentWidget()
            if isinstance(w, GameRoomWidget):
                self._restore_room_gid = w.game_id
            self.room_tabs.setCurrentIndex(0)

    def _restore_room_tab(self):
        """Re-select the game-room tab we left when opening a General stacked view."""
        gid = self._restore_room_gid
        self._restore_room_gid = None
        if gid is None or not self.room_tabs:
            return
        w = self.game_rooms.get(gid)
        if w is not None:
            self.room_tabs.setCurrentWidget(w)

    def enter_private_mode(self, jid: str, username: str, user_id: str):
        """Enter private chat mode with a user"""
        self._ensure_general_tab_visible()
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

        # Focus input for immediate typing — deferred so userlist click doesn't steal it back
        QTimer.singleShot(0, self.input_field.setFocus)
    
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
        if self.config.get("ui", "clear_private_messages_on_exit"):
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
        self._restore_room_tab()

    def _clear_private_messages(self):
        """Clear all private messages from the messages widget"""
        self.messages_widget.clear_private_messages()

    def _clear_new_messages_marker(self):
        if self.has_new_messages_marker:
            NewMessagesSeparator.remove_from_model(self.messages_widget.model)
            self.has_new_messages_marker = False

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
            self.input_field.setPlaceholderText(f"Private message to {self.private_chat_username}")
        else:
            # Normal mode - remove custom styling
            self.input_field.setStyleSheet("")
            self.input_field.setPlaceholderText("")

    def show_messages_view(self):
        """Switch back to messages and conditionally destroy chatlog widgets"""
        self._ensure_general_tab_visible()
        # Cleanup and destroy chatlog userlist
        if self.chatlog_userlist_widget:
            try:
                self.chatlog_userlist_widget.filter_requested.disconnect()
                self.chatlog_userlist_widget.clear_cache()
            except:
                pass
            self.userlist_panel.layout().removeWidget(self.chatlog_userlist_widget)
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

        self.stacked_widget.setCurrentWidget(self.messages_splitter)

        # Restore messages userlist based on width
        width = self.width()
        messages_userlist_visible = self.config.get("ui", "messages_userlist_visible")
        if messages_userlist_visible is None:
            messages_userlist_visible = True

        self.user_list_widget.setVisible(messages_userlist_visible)
        if hasattr(self, 'userlist_panel'):
            self.userlist_panel.setVisible(messages_userlist_visible)

        # Sync button state for messages userlist
        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(
                self.button_panel.toggle_userlist_button,
                self.user_list_widget.isVisible()
            )

        self._scroll_to_bottom(self.messages_widget.list_view)
        # If parsing ongoing, show status widget
        if self.chatlog_widget and self.chatlog_widget.parser_widget.is_parsing:
            self.start_parse_status()

    def _configure_chatlog_widget(self, widget):
        """Configure chatlog widget (main + split view) with actions support and shared settings."""
        if not widget:
            return
            
        # Enable Reply and Paste - chatlogs SHOULD include timestamp
        widget.set_input_field(self.input_field, include_timestamp=True)
        
        # Layout / compact mode
        compact = self.width() <= 1000
        widget.set_compact_mode(compact)
        widget.set_compact_layout(compact)
        
        # Username click handlers (reuse same logic as live messages)
        self._wire_username_signals(widget.interactions, right_click_widget=widget)

    def show_chatlog_view(self, timestamp: str = None, reload: bool = True):
        """Open chatlog for today. reload=False just re-shows the existing widget
        as-is (used when returning from the profile view)."""
        self._ensure_general_tab_visible()
        # Hide messages userlist when in chatlog view
        self.user_list_widget.setVisible(False)
      
        if not self.chatlog_widget:
            # Create chatlog widget
            self.chatlog_widget = ChatlogWidget(
                self.config,
                self.emoticon_manager,
                self.icons_path,
                self.account,
                parent_window=self,
                ban_manager=self.ban_manager
            )
            self.chatlog_widget.back_requested.connect(self._on_stacked_back)
            self.chatlog_widget.messages_loaded.connect(self._on_chatlog_messages_loaded)
            self.chatlog_widget.filter_changed.connect(self._on_chatlog_filter_changed)
            self.stacked_widget.addWidget(self.chatlog_widget)
            
            # Configure it (reply, compact mode, username clicks, etc.)
            self._configure_chatlog_widget(self.chatlog_widget)
      
        if not self.chatlog_userlist_widget:
            self.chatlog_userlist_widget = ChatlogUserlistWidget(
                self.config,
                self.icons_path,
                self.ban_manager
            )
            self.chatlog_userlist_widget.filter_requested.connect(self._on_filter_requested)
            self._wire_userlist_signals(self.chatlog_userlist_widget)
            # Insert into userlist_panel before the font slider
            self.userlist_panel.layout().insertWidget(0, self.chatlog_userlist_widget, stretch=1)
      
        # Show chatlog userlist based on config and width
        width = self.width()
        chatlog_userlist_visible = self.config.get("ui", "chatlog_userlist_visible")
        if chatlog_userlist_visible is None:
            chatlog_userlist_visible = True
      
        visible = width > 1000 and chatlog_userlist_visible
        self.chatlog_userlist_widget.setVisible(visible)
        self.userlist_panel.setVisible(visible)

        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(
                self.button_panel.toggle_userlist_button,
                chatlog_userlist_visible
            )
      
        # Sync userlist ban visibility with chatlog parse mode
        if self.chatlog_widget and self.chatlog_userlist_widget:
            self.chatlog_userlist_widget.set_show_banned(self.chatlog_widget.is_parsing)
      
        # If reload is True and the parser is not visible, reset to today's date
        if reload and not self.chatlog_widget.parser_visible:
            self.chatlog_widget.current_date = datetime.now().date()
            self.chatlog_widget._update_date_display()
            self.chatlog_widget.load_current_date()
      
        self.stacked_widget.setCurrentWidget(self.chatlog_widget)

    def show_chatlog_split_view(self, date_str: str, time_str: str = ""):
        """Show that date's chatlog in a split pane below the messages view, keeping the messages
        view open. Used both for RMB on a live-chat timestamp and for clicking a chatlog link in a
        message body (time_str, if given, scrolls to and highlights that specific message)."""
        if self.chatlog_split_widget is None:
            self.chatlog_split_widget = ChatlogWidget(
                self.config,
                self.emoticon_manager,
                self.icons_path,
                self.account,
                parent_window=self,
                ban_manager=self.ban_manager
            )
            self.chatlog_split_widget.back_btn.setToolTip("Close split view")
            self.chatlog_split_widget.back_requested.connect(self._close_chatlog_split_view)
            # Match the live messages view's row layout so the two panes line up
            self._configure_chatlog_widget(self.chatlog_split_widget)
            self.messages_splitter.insertWidget(0, self.chatlog_split_widget)
            self.messages_splitter.setSizes([self.height() // 2, self.height() // 2])
            self.chatlog_split_widget.load_date_and_scroll(date_str, time_str)

            # Shrinking messages_widget's viewport here invalidates its "at bottom"
            # scroll position, breaking future auto-scroll in add_message() unless restored.
            QTimer.singleShot(150, lambda: scroll(self.messages_widget.list_view, mode="bottom", delay=50))
            return

        self.chatlog_split_widget.load_date_and_scroll(date_str, time_str)

    def _close_chatlog_split_view(self):
        """Close the split pane opened via RMB on a live-chat timestamp"""
        if not self.chatlog_split_widget:
            return
        widget = self.chatlog_split_widget
        self.chatlog_split_widget = None
        widget.cleanup()
        widget.setParent(None)
        widget.deleteLater()


    def _open_game_room_by_id(self, game_id):
        class _Fake:
            pass
        fake = _Fake()
        try:
            fake.competition_game_id = int(game_id)
        except (TypeError, ValueError):
            return
        self.open_game_room_tab(fake)

    def open_game_room_tab(self, msg, room_label: str = "Game"):
        """Open or focus a game-room tab.

        room_label: "Game" (default, opened via a live game_id) or
        "Competition" (opened via RMB on a competition announcement timestamp).
        """
        gid = getattr(msg, 'competition_game_id', None)
        if not gid:
            return
        try:
            gid = int(gid)
        except (TypeError, ValueError):
            return

        if self.chatlog_split_widget:
            self._close_chatlog_split_view()

        # Already open → just switch to it
        if gid in self.game_rooms:
            self.room_tabs.setCurrentWidget(self.game_rooms[gid])
            return

        self._ensure_room_tabs()

        widget = GameRoomWidget(
            self.config, self.emoticon_manager, self.icons_path,
            account=self.account, ban_manager=self.ban_manager,
            game_id=gid, room_label=room_label, parent=self,
        )
        widget.send_requested.connect(lambda text, w=widget: self._send_game_room_message(text, w))
        self._wire_userlist_signals(widget)
        widget.open_game_requested.connect(self._open_game_room_by_id)
        widget.emoticon_requested.connect(lambda w=widget: self._on_game_room_emoticon_requested(w))
        self._wire_username_signals(widget, right_click_widget=widget.messages_widget)

        self.game_rooms[gid] = widget
        widget.set_compact_mode(self.width() <= 1000)  # match current window width immediately
        idx = self.room_tabs.addTab(widget, widget.tab_title())
        self.room_tabs.setCurrentIndex(idx)
        self._join_game_room(gid, widget.room_jid, widget)

    @staticmethod
    def _transfer_layout_items(src_layout, dst_layout):
        """Move every item from src_layout to dst_layout, preserving each
        item's stretch factor (e.g. left pane vs userlist width). Shared by
        _ensure_room_tabs and _collapse_room_tabs, which both rewrap the
        general-chat content between content_layout and general_body's own
        layout and previously duplicated this loop."""
        while src_layout.count():
            # Capture the stretch factor before takeAt(0) removes it —
            # otherwise panes reset to equal width.
            stretch = src_layout.stretch(0)
            item = src_layout.takeAt(0)
            if item.widget():
                dst_layout.addWidget(item.widget())
            elif item.layout():
                dst_layout.addLayout(item.layout())
            dst_layout.setStretch(dst_layout.count() - 1, stretch)

    def _wire_userlist_signals(self, userlist):
        """Connect the profile/private-chat/paste actions shared by every
        userlist panel — the main userlist, the chatlog userlist, and each
        game room's own (which just re-emits its internal userlist's
        signals). open_game_requested is wired separately since only the
        main userlist and game-room widgets have it."""
        userlist.profile_requested.connect(self.show_profile_view)
        userlist.private_chat_requested.connect(self.enter_private_mode)
        userlist.paste_requested.connect(self._paste_username_to_input)

    def _wire_username_signals(self, source, right_click_widget=None):
        """Connect username left/ctrl/shift/right click signals to their
        shared handlers. Used for the general messages view, chatlog
        widgets, and each game-room tab, which all wire the same four
        signals to the same handlers.

        right_click_widget: widget passed to _on_username_right_click so
        context-menu actions (ban, remove messages) apply to the right
        message list. None lets it default to self.messages_widget."""
        source.username_left_clicked.connect(self._on_username_left_click)
        source.username_ctrl_clicked.connect(self._on_username_ctrl_click)
        source.username_shift_clicked.connect(self._on_username_shift_click)
        source.username_right_clicked.connect(
            lambda msg, pos, w=right_click_widget: self._on_username_right_click(msg, pos, w)
        )

    def _ensure_room_tabs(self):
        """Create QTabWidget once; wrap existing general content as non-closable tab 0."""
        if self.room_tabs is not None:
            return

        self.general_body = QWidget()
        gen_layout = QHBoxLayout()
        gen_layout.setContentsMargins(0, 0, 0, 0)
        gen_layout.setSpacing(self.config.get("ui", "spacing", "widget_content") or 6)
        self.general_body.setLayout(gen_layout)

        # Freeze repaints for the whole rewrap: moving widgets out of
        # content_layout one at a time briefly leaves it under-populated,
        # and Qt would otherwise paint that intermediate state — visible as
        # messages_widget flashing evenly stretched for a frame. A single
        # repaint after everything is back in place avoids that.
        self.setUpdatesEnabled(False)
        self._transfer_layout_items(self.content_layout, gen_layout)

        self.room_tabs = QTabWidget()
        self.room_tabs.setDocumentMode(True)
        self.room_tabs.setMovable(True)
        self.room_tabs.setTabsClosable(True)
        self.room_tabs.tabCloseRequested.connect(self._on_room_tab_close_requested)
        self.room_tabs.currentChanged.connect(self._on_room_tab_changed)

        self.room_tabs.addTab(self.general_body, "General")
        # General is permanent — hide its close button
        self.room_tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        # Also prevent closing via middle-click etc. by ignoring in handler

        self.content_layout.addWidget(self.room_tabs)
        self.setUpdatesEnabled(True)
        self.messages_widget._force_recalculate()

    def _collapse_room_tabs(self):
        """Reverse of _ensure_room_tabs: once no game-room tabs remain, unwrap
        General back into content_layout directly so the tab bar doesn't sit
        there taking up space for a single permanent tab."""
        if self.room_tabs is None:
            return

        self.setUpdatesEnabled(False)
        gen_layout = self.general_body.layout()
        self._transfer_layout_items(gen_layout, self.content_layout)

        self.content_layout.removeWidget(self.room_tabs)
        self.room_tabs.deleteLater()
        self.room_tabs = None
        self.general_body = None
        self._general_unread = False
        self.setUpdatesEnabled(True)
        self.messages_widget._force_recalculate()

    def _set_room_unread(self, gid, unread: bool):
        """Set/clear "●" on a game-room tab. No-op if the tab isn't open."""
        widget = self.game_rooms.get(gid)
        if not widget or not self.room_tabs:
            return
        idx = self.room_tabs.indexOf(widget)
        if idx < 0:
            return
        self._unread_rooms.add(gid) if unread else self._unread_rooms.discard(gid)
        self.room_tabs.setTabText(idx, ("● " if gid in self._unread_rooms else "") + widget.tab_title())

    def _set_general_unread(self, unread: bool):
        """Set/clear "●" on the General tab."""
        if not self.room_tabs:
            return
        self._general_unread = unread
        self.room_tabs.setTabText(0, ("● " if unread else "") + "General")

    def _on_room_tab_close_requested(self, index: int):
        if index <= 0:
            return  # General never closes
        widget = self.room_tabs.widget(index)
        if not isinstance(widget, GameRoomWidget):
            return
        gid = widget.game_id
        self._close_game_room_tab(gid)

    def _on_room_tab_changed(self, index: int):
        # Optional: focus the input of the newly selected pane
        if index <= 0:
            if hasattr(self, 'input_field') and self.input_field:
                self.input_field.setFocus()
            if self._general_unread:
                self._set_general_unread(False)
        else:
            w = self.room_tabs.widget(index)
            if isinstance(w, GameRoomWidget):
                if w.input_field:
                    w.input_field.setFocus()
                if w.game_id in self._unread_rooms:
                    self._set_room_unread(w.game_id, False)
        # sizeHints go stale while a tab is hidden in QTabWidget
        mw = self._active_messages_widget()
        if mw:
            mw._force_recalculate()
            QTimer.singleShot(0, mw._force_recalculate)

    def _join_game_room(self, game_id, room_jid: str, widget=None):
        client = self.xmpp_client
        target = widget or self.game_rooms.get(game_id)
        if not client or not client.sid:
            if target:
                target.set_status("Not connected")
            return
        try:
            client.join_room(room_jid, game_id=str(game_id))
            if target:
                target.set_status(f"In game #{game_id}")
        except Exception as e:
            print(f"⚠️ Game room join error: {e}")
            if target:
                target.set_status(f"Join error: {e}")

    def _leave_game_room(self, game_id=None, room_jid=None):
        client = self.xmpp_client
        if not client:
            return
        jid = room_jid
        if not jid and game_id is not None:
            gr = self.game_rooms.get(game_id)
            jid = gr.room_jid if gr else XMPPClient.game_room_jid(game_id)
        if not jid:
            return
        try:
            client.leave_room(jid)
        except Exception as e:
            print(f"⚠️ Leave game room: {e}")

    def _close_game_room_tab(self, game_id):
        widget = self.game_rooms.pop(game_id, None)
        if not widget:
            return
        self._unread_rooms.discard(game_id)
        self._leave_game_room(game_id=game_id, room_jid=widget.room_jid)
        idx = self.room_tabs.indexOf(widget) if self.room_tabs else -1
        if idx >= 0:
            self.room_tabs.removeTab(idx)
        widget.cleanup()
        widget.setParent(None)
        widget.deleteLater()

        # Last game room closed → collapse back to plain General view,
        # so a lone permanent tab doesn't waste vertical space.
        if not self.game_rooms:
            self._collapse_room_tabs()

    def _on_game_room_emoticon_requested(self, widget=None):
        gr = widget or self._current_game_room()
        if gr and gr.input_field:
            gr.input_field.setFocus()
        self._toggle_emoticon_selector()

    def _send_game_room_message(self, text: str, widget=None):
        gr = widget or self._current_game_room()
        if not gr or not self.xmpp_client or not gr.room_jid:
            return
        self._dispatch_chat_message(text, 'groupchat', gr.room_jid, gr.add_message)

    def _get_hovered_chatlog_widget(self):
        """Return the ChatlogWidget (main or split) currently under the mouse cursor.
        Returns None if no suitable chatlog widget is hovered."""
        gp = QCursor.pos()
        widget = QApplication.widgetAt(gp)
        if not widget:
            return None

        while widget:
            if isinstance(widget, ChatlogWidget):
                if not getattr(widget, 'parser_visible', False):
                    return widget
            widget = widget.parentWidget()
        return None

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
        show_notification(
            title="Parse Error",
            message=error_msg,
            config=self.config,
            emoticon_manager=self.emoticon_manager,
            account=self.account
        )

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
        """Handle filter change from chatlog widget - sync to userlist"""
        if self.chatlog_userlist_widget:
            self.chatlog_userlist_widget.update_filter_state(usernames)

    def _apply_resize(self, width: int):
        """handle_chat_resize only knows about the main chat's userlist/messages
        (it predates game-room tabs), so sync the same compact-width behaviour
        to any open game rooms here instead of teaching resize.py about tabs."""
        handle_chat_resize(self, width)
        self._sync_game_room_compact_state(width)

    def _sync_game_room_compact_state(self, width: int):
        """Apply the compact-mode / userlist auto-hide threshold to every open
        game-room tab, same 1000px breakpoint as the main chat."""
        if not self.game_rooms:
            return
        is_compact = width <= 1000
        if is_compact != getattr(self, '_game_rooms_were_compact', is_compact):
            # Crossing the threshold re-enables auto-hide, same as the main chat
            for gr in self.game_rooms.values():
                gr.auto_hide_userlist = True
        self._game_rooms_were_compact = is_compact
        for gr in self.game_rooms.values():
            gr.set_compact_mode(is_compact)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_resize(self.width())

        self._update_geometry_on_manual_change()

    def moveEvent(self, event):
        """Track window position changes"""
        super().moveEvent(event)

        self._update_geometry_on_manual_change()

    def mouseMoveEvent(self, event):
        """Hover-reveal button panel when mouse near right edge"""
        if self.width() < 500 and hasattr(self, 'button_panel'):
            near_edge = (self.width() - event.pos().x()) <= 40
            over_panel = self.button_panel.geometry().contains(event.pos())
            
            if near_edge and not self.button_panel.isVisible():
                self.button_panel.setVisible(True)
                self._hover_reveal = True
            elif self._hover_reveal and not near_edge and not over_panel:
                def hide_if_away():
                    cursor_pos = self.mapFromGlobal(self.cursor().pos())
                    if self.width() < 500 and not self.button_panel.geometry().contains(cursor_pos):
                        self.button_panel.setVisible(False)
                
                QTimer.singleShot(300, hide_if_away)
                self._hover_reveal = False
        super().mouseMoveEvent(event)

    def reset_window_size(self):
        """Reset window to default calculated size and position"""
        # Stop any pending saves in WindowSizeManager to prevent race condition
        self.window_size_manager.save_timer.stop()
        
        was_reset = self.window_size_manager.reset_size()
        
        if not was_reset:
            return  # Already at default
        
        # Set flag to prevent resize/move events from saving during reset
        self._resetting_geometry = True
        
        # Apply default geometry
        width, height, x, y = self._calculate_default_geometry()
        self.resize(width, height)
        self.move(x, y)
        
        # Clear flag after events have fired
        QTimer.singleShot(100, lambda: setattr(self, '_resetting_geometry', False))
        
        # Update button state immediately
        self.update_reset_size_button_state()
    
    def show_window_presets(self):
        """Show window presets dialog"""
        dialog = WindowPresetsDialog(self.config, self, parent=self)
        dialog.exec()
    
    def update_reset_size_button_state(self):
        """Update reset size button state based on whether geometry is customized"""
        if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'reset_size_button'):
            has_custom = self.window_size_manager.has_saved_size()
            self.button_panel.set_button_state(self.button_panel.reset_size_button, has_custom)

    def _update_geometry_on_manual_change(self):
        """Update saved geometry when the user has manually changed window size/position."""
        if getattr(self, '_showing_window', False) or getattr(self, '_resetting_geometry', False):
            return
        cur = (self.width(), self.height(), self.x(), self.y())
        if self.window_size_manager.has_saved_size() or cur != self._calculate_default_geometry():
            self.window_size_manager.update_geometry(*cur)

    def _scroll_to_bottom(self, view, delay: int = 50):
        """Scroll a list view to bottom after `delay` ms (lets layout settle first).
        Small shared helper — this exact QTimer+lambda+scroll pattern was repeated
        all over the file for messages/chatlog/competition scroll-to-bottom calls."""
        QTimer.singleShot(delay, lambda: scroll(view, mode="bottom"))

    def _scroll_to_row(self, view, row: int, delay: int = 0):
        """Scroll a list view to a specific row, centered."""
        QTimer.singleShot(delay, lambda: scroll(view, mode="middle", target_row=row))

    def _active_messages_widget(self):
        """MessagesWidget of the current tab (game room or General)."""
        gr = self._current_game_room()
        return gr.messages_widget if gr else self.messages_widget

    def _complete_resize_recalculation(self):
        """Complete resize with aggressive recalculation"""
        current = self.stacked_widget.currentWidget()
        if current == self.messages_splitter:
            mw = self._active_messages_widget()
            mw._force_recalculate()
            self._scroll_to_bottom(mw.list_view)
        elif current == self.chatlog_widget and self.chatlog_widget:
            self.chatlog_widget._force_recalculate()
            self._scroll_to_bottom(self.chatlog_widget.list_view)

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
                        emoticon_manager=self.emoticon_manager,
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
                    emoticon_manager=self.emoticon_manager,
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

    
    def set_track_competitions(self, enabled: bool):
        if enabled:
            if self.races_listener is None:
                self.races_listener = RacesListener()
                self.races_listener.competition_found.connect(
                    self._on_competition_found, Qt.ConnectionType.QueuedConnection
                )
                self.races_listener.players_changed.connect(
                    self._on_competition_players_changed, Qt.ConnectionType.QueuedConnection
                )
                self.races_listener.status_changed.connect(
                    self._on_races_status, Qt.ConnectionType.QueuedConnection
                )
                min_m = self.config.get("competitions", "min_multiplier") or "x1+"
                self.races_listener.set_min_multiplier(min_m)
                self.races_listener.start()
            else:
                min_m = self.config.get("competitions", "min_multiplier") or "x1+"
                self.races_listener.set_min_multiplier(min_m)
            self._on_races_status("connecting")
        else:
            if self.races_listener is not None:
                self.races_listener.stop()
                try:
                    self.races_listener.competition_found.disconnect(self._on_competition_found)
                    self.races_listener.players_changed.disconnect(self._on_competition_players_changed)
                    self.races_listener.status_changed.disconnect(self._on_races_status)
                except TypeError:
                    pass
                self.races_listener = None
            self._history_settle_timer.stop()
            self._competition_notified.clear()
            self._pending_competitions.clear()
            self._competition_log_lines.clear()
            self._competition_log_status.clear()
            self._remove_competition_messages()
            self._reset_competition_live_state()
            self._on_races_status("disconnected")

    def _on_min_multiplier_changed(self, text: str):
        if self.races_listener:
            self.races_listener.set_min_multiplier(text)
        self.prune_competitions_by_filter()

    def prune_competitions_by_filter(self):
        """Drop live competition messages that no longer pass the current min_multiplier."""
        if not self.races_listener:
            return
        to_remove = [
            gid for gid, live in self._competition_live.items()
            if not self.races_listener.passes_filter(live.get("mult") or "?")
        ]
        if not to_remove:
            return
        mw = getattr(self, "messages_widget", None)
        for gid in to_remove:
            if mw and hasattr(mw, "clear_competition_messages"):
                mw.clear_competition_messages(gid)
            self._competition_live.pop(gid, None)
            self._competition_notified.discard(gid)
            if self._competition_focus_gid == gid:
                self._competition_focus_gid = None
            timer = self._competition_alert_timers.pop(gid, None)
            if timer:
                timer.stop()
            popup_manager.close_by_tag(f"competition:{gid}")
        if mw:
            self._scroll_to_bottom(mw.list_view)

    def _reset_competition_live_state(self):
        self._competition_countdown_timer.stop()
        self._competition_sound_repeat_timer.stop()
        self._competition_live.clear()
        self._competition_focus_gid = None
        for timer in self._competition_alert_timers.values():
            timer.stop()
        self._competition_alert_timers.clear()

    def _on_races_status(self, state: str):
        prev = getattr(self, "_races_status", None)
        self._races_status = state
        sw = getattr(self, "settings_widget", None)
        if sw and hasattr(sw, "_update_competitions_status"):
            enabled = self.config.get("competitions", "enabled") is not False
            sw._update_competitions_status(enabled, state)
        # log connection changes (skip duplicate)
        if state != prev:
            label = {
                "connecting": "connecting...",
                "connected": "connected",
                "disconnected": "disconnected / reconnecting...",
            }.get(state, state)
            self._append_competition_log(f"ws {label}")

    def _remove_competition_messages(self):
        mw = getattr(self, "messages_widget", None)
        if mw and hasattr(mw, "clear_competition_messages"):
            mw.clear_competition_messages()

    @staticmethod
    def _competition_fields(info: dict) -> tuple:
        gid = info.get("game_id")
        tag = f"competition:{gid}" if gid else None
        return gid, info.get("multiplier") or "?", info.get("url") or "", tag

    def _on_history_settled(self):
        self._chat_ready = True
        self._flush_pending_competitions()

    def _on_competition_found(self, info: dict):
        gid, mult, url, tag = self._competition_fields(info)
        status = info.get("status") or "?"

        if self._competition_log_status.get(gid) != status:
            self._competition_log_status[gid] = status
            self._append_competition_log(f"{mult} #{gid} {status}")

        if status == "racing":
            if tag:
                popup_manager.close_by_tag(tag)
            mw = getattr(self, "messages_widget", None)
            if mw and hasattr(mw, "clear_competition_messages"):
                mw.clear_competition_messages(gid)
                # Scroll to bottom to show current chat after competition message is removed
                self._scroll_to_bottom(mw.list_view)
            self._competition_live.pop(gid, None)
            if self._competition_focus_gid == gid:
                self._competition_focus_gid = None
            alert_timer = self._competition_alert_timers.pop(gid, None)
            if alert_timer:
                alert_timer.stop()
            self._competition_sound_repeat_timer.stop()
            return

        # chat + notification only for waiting (once)
        if status != "waiting":
            return

        if gid in self._competition_notified:
            return
        self._competition_notified.add(gid)
        if len(self._competition_notified) > 200:
            self._competition_notified = set(list(self._competition_notified)[-100:])

        # queue until history has settled at least once, so it can't land ahead of loaded messages
        if not self._chat_ready or self.initial_roster_loading or self._history_settle_timer.isActive():
            self._pending_competitions.append(info)
            return

        self._announce_competition(info)

    def _format_competition_header(
        self,
        mult: str,
        url: str,
        begintime,
        total: int,
        shown: int | None = None,
        cost=None,
    ) -> str:
        parts = [mult]
        show_cost = self.config.get("competitions", "show_cost")
        if show_cost is not False and cost is not None and cost != "" and cost != 0:
            parts.append(f"💰 {cost}")
        if url:
            parts.append(url)
        if begintime:
            remaining = max(0, round(begintime - datetime.now().timestamp()))
            parts.append(f"⏱️ {remaining // 60:02d}:{remaining % 60:02d}")
        if shown is not None and shown < total:
            parts.append(f"🗿 {shown}/{total}")
        else:
            parts.append(f"🗿 {total}")
        return " ".join(parts)

    def _player_chips(self, players: list) -> list:
        show = self.config.get("competitions", "show_players")
        if show is False:
            return []
        chips = [
            {
                "name": p.get("name") or p.get("login") or "?",
                "level": p.get("level"),
            }
            for p in players
        ]
        if self.config.get("competitions", "sort_players_by_level"):
            chips.sort(key=lambda c: c.get("level") or 0, reverse=True)
        limit = int(self.config.get("competitions", "max_player_chips") or 20)
        if limit > 0 and len(chips) > limit:
            return chips[:limit] + [{"name": "…", "level": None}]
        return chips

    @staticmethod
    def _player_names(players: list) -> list:
        return [p.get("name") or p.get("login") or "?" for p in players]

    def _announce_competition(self, info: dict):
        gid, mult, url, tag = self._competition_fields(info)
        begintime = info.get("begintime")
        cost = info.get("competition_cost")
        players = info.get("players") or []
        self._competition_live[gid] = {
            "mult": mult, "url": url, "begintime": begintime,
            "players": players, "cost": cost,
        }
        chips = self._player_chips(players)
        shown = None if not chips else sum(1 for c in chips if c.get("name") != "…")
        header = self._format_competition_header(
            mult, url, begintime, len(players), shown, cost=cost
        )
        try:
            msg = Message(
                from_jid="", body=header, msg_type="groupchat",
                login="Система", timestamp=datetime.now(),
            )
            msg.is_competition = True
            msg.competition_game_id = gid
            msg.competition_players = chips
            self.add_local_message(msg)
        except Exception as e:
            print(f"[races] local message error: {e}")

        if not self._competition_countdown_timer.isActive():
            self._start_competition_countdown_timer()

        self._schedule_competition_alert(gid, mult, url, tag, begintime)

    def _start_competition_countdown_timer(self):
        """Align ticks to wall-clock second boundaries so the countdown doesn't lag behind real time."""
        self._competition_countdown_timer.setInterval(1000)
        ms_to_next_second = 1000 - (int(datetime.now().timestamp() * 1000) % 1000)

        def _aligned_start():
            self._tick_competition_countdowns()
            self._competition_countdown_timer.start()

        QTimer.singleShot(ms_to_next_second, _aligned_start)


    def refresh_competition_player_display(self):
        for gid in list(self._competition_live.keys()):
            self._refresh_competition_message(gid)

    def _on_competition_players_changed(self, gid: int, players: list):
        live = self._competition_live.get(gid)
        if live is None:
            return
        live["players"] = players
        self._refresh_competition_message(gid)

    def _tick_competition_countdowns(self):
        if not self._competition_live:
            self._competition_countdown_timer.stop()
            return
        for gid in list(self._competition_live.keys()):
            self._refresh_competition_message(gid)

    def _refresh_competition_message(self, gid: int):
        live = self._competition_live.get(gid)
        mw = getattr(self, "messages_widget", None)
        if live is None or not mw:
            return
        players = live.get("players") or []
        chips = self._player_chips(players)
        names = [c["name"] for c in chips if c.get("name") != "…"]
        shown = None if not chips else len(names)
        header = self._format_competition_header(
            live["mult"], live["url"], live.get("begintime"), len(players), shown,
            cost=live.get("cost"),
        )
        sb = mw.list_view.verticalScrollBar()
        at_bottom = (sb.maximum() - sb.value()) <= 100
        mw.update_competition_message(gid, header, chips)
        if self._competition_focus_gid == gid:
            row = mw.model.find_competition_message_row(gid)
            if row is not None:
                self._scroll_to_row(mw.list_view, row)
        elif at_bottom:
            self._scroll_to_bottom(mw.list_view, delay=0)

        popup = popup_manager.find_by_tag(f"competition:{gid}")
        if popup:
            popup.update_message(header, chips)

    def _schedule_competition_alert(self, gid: int, mult: str, url: str, tag: str, begintime):
        """Fire the popup/sound alert immediately, or delayed to `alert_lead_seconds` before start."""
        lead = int(self.config.get("competitions", "alert_lead_seconds") or 0)
        delay = max(0, int(begintime - datetime.now().timestamp()) - lead) if begintime and lead else 0

        def fire():
            self._competition_alert_timers.pop(gid, None)
            self._fire_competition_alert(gid, mult, url, tag)

        if delay <= 0:
            fire()
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(fire)
        timer.start(delay * 1000)
        self._competition_alert_timers[gid] = timer

    def _within_notify_window(self) -> bool:
        if not self.config.get("competitions", "notify_window_enabled"):
            return True
        start = self.config.get("competitions", "notify_window_start")
        end = self.config.get("competitions", "notify_window_end")
        if start is None or end is None or start == end:
            return True
        hour = datetime.now().hour
        return start <= hour < end if start < end else hour >= start or hour < end

    def _fire_competition_alert(self, gid: int, mult: str, url: str, tag: str):
        if not self._within_notify_window():
            return
        live = self._competition_live.get(gid, {})
        players = live.get("players") or []
        chips = self._player_chips(players)
        shown = None if not chips else sum(1 for c in chips if c.get("name") != "…")
        header = self._format_competition_header(
            mult, url, live.get("begintime"), len(players), shown,
            cost=live.get("cost"),
        )

        # Competition sound plays regardless of window focus, like ban sound
        self._play_competition_sound()
        self._start_competition_sound_repeat()

        # Scroll to competition message and keep it centered while chips grow
        self._competition_focus_gid = gid
        mw = getattr(self, "messages_widget", None)
        if mw and hasattr(mw, "list_view") and hasattr(mw, "model"):
            row = mw.model.find_competition_message_row(gid)
            if row is not None:
                QTimer.singleShot(50, lambda r=row: self._scroll_to_row(mw.list_view, r))

        # Same rule as chat messages: notify only when window is not focused
        if not self.isActiveWindow():
            try:
                show_notification(
                    title=f"Competition {mult}",
                    message=header,
                    duration=10000,
                    config=self.config,
                    cache=getattr(self, "cache", None),
                    emoticon_manager=getattr(self, "emoticon_manager", None),
                    account=getattr(self, "account", None),
                    is_system=False,
                    is_competition=True,
                    window_show_callback=self._show_and_focus_window,
                    tag=tag,
                    players=chips,
                )
            except Exception as e:
                print(f"[races] notification error: {e}")

    def _start_competition_sound_repeat(self):
        """Repeat the competition sound until the user moves the mouse or presses a key."""
        self._competition_sound_repeat_timer.stop()
        if not self.config.get("sound", "competition_repeat_enabled"):
            return
        interval = int(self.config.get("sound", "competition_repeat_interval") or 15)
        if interval <= 0:
            return
        self._competition_sound_repeat_cursor_pos = QCursor.pos()
        self._competition_sound_repeat_timer.start(interval * 1000)

    def _on_competition_sound_repeat_tick(self):
        if cursor_moved_or_key_pressed(self._competition_sound_repeat_cursor_pos):
            self._competition_sound_repeat_timer.stop()
            return
        self._play_competition_sound()

    def _flush_pending_competitions(self):
        pending = self._pending_competitions
        self._pending_competitions = []
        for info in pending:
            self._announce_competition(info)

    def _append_competition_log(self, line: str):
        from datetime import datetime as _dt
        entry = f"{_dt.now().strftime('%H:%M:%S')}  {line}"
        self._competition_log_lines.append(entry)
        if len(self._competition_log_lines) > 200:
            self._competition_log_lines = self._competition_log_lines[-200:]
        sw = getattr(self, "settings_widget", None)
        if (
            sw
            and hasattr(sw, "append_competition_log")
            and self.config.get("competitions", "enabled") is not False
        ):
            sw.append_competition_log(entry)

    def clear_competition_log(self):
        self._competition_log_lines.clear()
        self._competition_log_status.clear()

    def _sync_competitions_settings_ui(self):
        """Restore full session log + indicator into settings."""
        sw = getattr(self, "settings_widget", None)
        if not sw:
            return
        enabled = self.config.get("competitions", "enabled") is not False
        status = getattr(self, "_races_status", "disconnected")
        sw._update_competitions_status(enabled, status if enabled else None)
        if not hasattr(sw, "competitions_log"):
            return
        if enabled:
            sw.competitions_log.setEnabled(True)
            if hasattr(sw, "set_competition_log_lines"):
                sw.set_competition_log_lines(list(self._competition_log_lines))


    def add_local_message(self, msg):
        self.messages_widget.add_message(msg)

    def _is_ban_message(self, msg):
        """Detect if a message is a ban message from Клавобот"""
        if not msg.body or not msg.login:
            return False
        return msg.login == 'Клавобот' and all(word in msg.body for word in ['Пользователь', 'заблокирован'])
    
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

    def _is_from_game_room(self, from_jid: str) -> bool:
        if not from_jid:
            return False
        bare = from_jid.split('/')[0]
        return bare.startswith('game') and '@conference.jabber.klavogonki.ru' in bare

    def _game_id_from_jid(self, from_jid: str):
        try:
            bare = from_jid.split('/')[0]
            local = bare.split('@')[0]
            if local.startswith('game'):
                return int(local[4:])
        except Exception:
            pass
        return None

    def on_message(self, msg):
        # Check if initial load
        is_initial = getattr(msg, 'initial', False)

        from_jid = getattr(msg, 'from_jid', '') or ''
        if self.game_rooms and self._is_from_game_room(from_jid):
            gid = self._game_id_from_jid(from_jid)
            gr = self.game_rooms.get(gid) if gid is not None else None
            if gr is not None:
                body = (msg.body or '').strip()
                if 'not anonymous' in body.lower():
                    return
                if msg.login == self.account.get('chat_username') and not is_initial:
                    return
                if msg.login:
                    user_id, _ = extract_user_data_from_jid(from_jid)
                    if self._is_user_banned(user_id, msg.login):
                        return
                    if user_id:
                        self.cache.update_user(user_id, msg.login)
                is_ban = self._is_ban_message(msg)
                msg.is_ban = is_ban
                msg.is_private = False
                display_body, is_system = format_me_action(msg.body, msg.login)
                gr.add_message(msg)
                if not is_initial and self._current_game_room() is not gr:
                    self._set_room_unread(gid, True)
                self._notify_incoming_message(
                    msg, display_body, is_ban, is_system, is_initial,
                    room_jid=gr.room_jid, add_message_fn=gr.add_message,
                    source_label=self._room_source_label(gr),
                    game_id=gid,
                )
                return

        if is_initial:
            self._history_settle_timer.start(self._HISTORY_SETTLE_MS)

        # Skip own messages (server echoes groupchat messages back)
        if msg.login == self.account.get('chat_username') and not is_initial:
            return

        # CHECK IF USER IS BANNED - BLOCK IMMEDIATELY
        if msg.login:
            user_id, _ = extract_user_data_from_jid(getattr(msg, 'from_jid', None))
            if self._is_user_banned(user_id, msg.login):
                return  # Silently drop banned user's messages
            # Persist login → user_id mapping automatically
            if user_id:
                self.cache.update_user(user_id, msg.login)

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

        # Mark General tab unread when the user is currently on a game-room tab
        if not is_initial and self.room_tabs and self.room_tabs.currentIndex() > 0:
            self._set_general_unread(True)

        # Increment unread count if window is hidden and not initial load
        if not is_initial and not self.isVisible() and self.app_controller:
            self.app_controller.increment_unread()

        self._notify_incoming_message(msg, display_body, is_ban, is_system, is_initial)

    @staticmethod
    def _room_source_label(gr) -> str:
        """Source kind for notification accent color: 'game' or 'competition'."""
        return "competition" if gr.room_label == "Competition" else "game"

    def _notify_incoming_message(self, msg, display_body, is_ban, is_system, is_initial, room_jid=None, add_message_fn=None, source_label=None, game_id=None):
        """TTS, effect sounds, and popup — shared by general and game-room messages.

        room_jid/add_message_fn: route a popup reply back to the originating game room.
        source_label: 'game'/'competition' — colors the notification timestamp/title.
        game_id: tab to activate on notification click."""
        if is_initial:
            return

        if msg.login and not self.isActiveWindow():
            tts_enabled = self.config.get("sound", "tts_enabled")
            if tts_enabled:
                # Update voice engine state
                self.voice_engine.set_enabled(True)
                self.voice_engine.speak_message(
                    username=msg.login,
                    message=display_body,
                    my_username=self.account.get('chat_username', ''),
                    is_initial=is_initial,
                    is_private=getattr(msg, 'is_private', False),
                    is_ban=is_ban,
                    is_system=is_system,
                )
            else:
                # Ensure voice engine is disabled
                self.voice_engine.set_enabled(False)

        if is_ban:
            self._play_ban_sound()

        play_mention_sound_always = self.config.get("sound", "play_mention_sound_always") or False
        # Play mention sound if message mentions me and either window not active or config overrides it to always play
        if self._message_mentions_me(msg) and (not self.isActiveWindow() or play_mention_sound_always):
            self._play_mention_sound()

        # Only show notifications when the window is not active
        if not self.isActiveWindow():
            # Check if YouTube URLs need time to cache
            from core.youtube import YOUTUBE_URL_PATTERN, get_cached_info, youtube_signals
            uncached = [
                m.group(0) for m in YOUTUBE_URL_PATTERN.finditer(msg.body or '')
                if not (get_cached_info(m.group(0)) or (None, False))[1]
            ]
            if uncached:
                pending = set(uncached)
                timer = QTimer(self)
                timer.setSingleShot(True)

                def show_now():
                    try:
                        youtube_signals.metadata_cached.disconnect(on_ready)
                    except Exception:
                        pass
                    timer.stop()
                    if not self.isActiveWindow():
                        self._show_notification(msg, display_body, is_ban, is_system, room_jid=room_jid, add_message_fn=add_message_fn, source_label=source_label, game_id=game_id)

                def on_ready(url):
                    pending.discard(url)
                    if not pending:
                        show_now()

                youtube_signals.metadata_cached.connect(on_ready)
                timer.timeout.connect(show_now)
                timer.start(2000)
            else:
                self._show_notification(msg, display_body, is_ban, is_system, room_jid=room_jid, add_message_fn=add_message_fn, source_label=source_label, game_id=game_id)

    def _show_and_focus_window(self, game_id=None):
        """Show/focus the chat window; switch to the originating room tab if any."""
        if not self.isVisible():
            self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.activateWindow()
        self.raise_()
        if self.stacked_widget.currentWidget() is not self.messages_splitter:
            self.show_messages_view()
        if self.room_tabs:
            if game_id is not None and game_id in self.game_rooms:
                self.room_tabs.setCurrentWidget(self.game_rooms[game_id])
            else:
                self.room_tabs.setCurrentIndex(0)

    def _show_notification(self, msg, display_body, is_ban, is_system, room_jid=None, add_message_fn=None, source_label=None, game_id=None):
        """Show notification.

        room_jid: originating game room jid (None = General).
        add_message_fn: local echo target for a typed reply.
        source_label: 'game'/'competition' — accent color for timestamp/title.
        game_id: tab to activate on click (None = General)."""
        try:
            show_notification(
                title=msg.login,
                message=display_body,
                xmpp_client=self.xmpp_client,
                cache=self.cache,
                config=self.config,
                emoticon_manager=self.emoticon_manager,
                local_message_callback=add_message_fn or self.add_local_message,
                account=self.account,
                window_show_callback=lambda g=game_id: self._show_and_focus_window(g),
                is_private=getattr(msg, 'is_private', False),
                recipient_jid=msg.from_jid if getattr(msg, 'is_private', False) else None,
                room_jid=room_jid,
                source_label=source_label,
                is_ban=is_ban,
                is_system=is_system
            )
        except Exception as e:
            print(f"Notification error: {e}")

    def _message_mentions_me(self, msg):
        if not self.account or not msg.body:
            return False
        my_username = self.account.get('chat_username', '').lower()
        if not my_username:
            return False
        pattern = r'\b' + re.escape(my_username) + r'\b'
        return bool(re.search(pattern, msg.body.lower()))

    def _play_notification_sound(self, path: str | None, force: bool = False, fallback_beep: bool = False):
        """Play an effect by path. play_sound() already threads and handles its
        own errors, so no extra wrapping is needed here."""
        if not path:
            if fallback_beep:
                try:
                    QApplication.instance().beep()
                except Exception as e:
                    print(f"System beep error: {e}")
            return
        play_sound(path, config=self.config, force=force)

    def _play_mention_sound(self):
        self._play_notification_sound(self.mention_sound_path, fallback_beep=True)

    def _play_ban_sound(self):
        self._play_notification_sound(self.ban_sound_path)

    def _play_competition_sound(self):
        """Falls back to mention sound if no dedicated file is present.
        Can bypass the effects-sound toggle via sound.competition_sound_force
        in config (set from Settings)."""
        path = self.competition_sound_path or self.mention_sound_path
        force = self.config.get("sound", "competition_sound_force") or False
        self._play_notification_sound(path, force=force)

    def on_presence(self, pres):
        if not self.xmpp_client or self.initial_roster_loading:
            return
    
        # CHECK IF USER IS BANNED - BLOCK PRESENCE UPDATES
        if pres and pres.login:
            if self._is_user_banned(pres.user_id, pres.login):
                return  # Silently drop banned user's presence

        from_jid = getattr(pres, 'from_jid', '') or ''
        is_game = self._is_from_game_room(from_jid)

        if is_game and self.game_rooms:
            gid = self._game_id_from_jid(from_jid)
            gr = self.game_rooms.get(gid) if gid is not None else None
            if gr is not None:
                if pres.presence_type == 'available':
                    if pres.login and pres.user_id:
                        self.cache.update_user(pres.user_id, pres.login, pres.background)
                    if pres.user_id and pres.avatar:
                        self.cache.ensure_avatar(
                            pres.user_id, pres.avatar,
                            gr.user_list_widget.on_avatar_updated
                        )
                    gr.add_users(presence=pres)
                elif pres.presence_type == 'unavailable':
                    gr.remove_users(presence=pres)
                return
    
        if pres and pres.presence_type == 'available':
            if pres.login and pres.user_id:
                self.cache.update_user(pres.user_id, pres.login, pres.background)
            if pres.user_id and pres.avatar:
                self.cache.ensure_avatar(pres.user_id, pres.avatar, self.user_list_widget.on_avatar_updated)
            elif pres.user_id and not pres.avatar:
                self.cache.remove_avatar(pres.user_id)
            self.user_list_widget.add_users(presence=pres)
        elif pres and pres.presence_type == 'unavailable':
            self.user_list_widget.remove_users(presence=pres)

    def on_bulk_update_complete(self):
        self._history_settle_timer.start(self._HISTORY_SETTLE_MS)  # fallback in case no history messages follow
        if not self.xmpp_client:
            return
        users = self.xmpp_client.user_list.get_online()
        self.user_list_widget.add_users(users=users, bulk=True)

    def on_font_size_changed(self):
        """Handle font size changes from font scaler - refresh all text"""
        # Debounce: restart timer on every call so rapid slider moves only
        # trigger one full rebuild 80 ms after the last movement.
        if not hasattr(self, '_font_size_timer'):
            self._font_size_timer = QTimer(self)
            self._font_size_timer.setSingleShot(True)
            self._font_size_timer.timeout.connect(self._apply_font_size_change)
        self._font_size_timer.start(80)

    def _apply_font_size_change(self):
        """Actually apply font size change after debounce"""
        new_font = get_font(FontType.TEXT)
        
        # Update message delegates AND their renderers
        for widget in [self.messages_widget, self.chatlog_widget, self.chatlog_split_widget]:
            if widget:
                widget.delegate.body_font = new_font          # For username + metrics
                widget.delegate.timestamp_font = new_font      # For timestamp
                # Also update MessageRenderer font
                if widget.delegate.message_renderer:
                    widget.delegate.message_renderer.body_font = new_font  # For message body
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
                if user_widget.badge:
                    user_widget.badge.setFont(new_font)
            self.user_list_widget.update()
        
        if self.chatlog_userlist_widget:
            for user_widget in self.chatlog_userlist_widget.user_widgets.values():
                user_widget.username_label.setFont(new_font)
                user_widget.count_label.setFont(new_font)
            self.chatlog_userlist_widget.update()
        
        # Update profile widget
        if hasattr(self, 'profile_widget') and self.profile_widget:
            if self.profile_widget.history_widget:
                [label.setFont(new_font) for label in self.profile_widget.history_widget.findChildren(QLabel)]
                self.profile_widget.history_widget._adjust_height()
            # Rebuild cards so StatCard picks up the new font-scaled min width
            if hasattr(self.profile_widget, '_cards_data'):
                self.profile_widget._rebuild_card_layout(getattr(self.profile_widget, '_last_cols', 3))
            self.profile_widget.update()
        
        # Update pronunciation widget inputs
        if hasattr(self, 'pronunciation_widget') and self.pronunciation_widget:
            for item in self.pronunciation_widget.items:
                item.original_input.setFont(new_font)
                item.pronunciation_input.setFont(new_font)
            self.pronunciation_widget.update()
        
        # Update ban list widget inputs
        if hasattr(self, 'ban_list_widget') and self.ban_list_widget:
            # Iterate over both permanent and temporary ban items
            for item in self.ban_list_widget.perm_items + self.ban_list_widget.temp_items:
                item.username_input.setFont(new_font)
                item.user_id_input.setFont(new_font)
                if hasattr(item, 'duration_button'):
                    item.duration_button.setFont(new_font)
            self.ban_list_widget.update()
        

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

        self._dispatch_chat_message(text, msg_type, recipient_jid, self.messages_widget.add_message)

    def _dispatch_chat_message(self, text: str, msg_type: str, target_jid, add_message_fn):
        """Chunk `text`, echo each chunk locally via add_message_fn immediately,
        then send each chunk to target_jid on a staggered delay. Shared by the
        general chat's send_message and game rooms' _send_game_room_message so
        the two don't duplicate the chunk/echo/send dance."""
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

            add_message_fn(own_msg)

            delay = i * 0.8 # 800ms delay between chunks
            threading.Timer(
                delay,
                self.xmpp_client.send_message,
                args=(chunk, target_jid, msg_type)
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
        
        # Reset on success
        if status == 'online':
            self.reconnect_count = 0
            if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'reconnect_button'):
                self.button_panel.reconnect_button.setVisible(False)
        
        # Only trigger auto-reconnect on offline status, not on connecting (which is set during auto-reconnect attempts)
        elif status == 'offline':
            if getattr(self, 'really_close', False):
                return
            
            # Show manual reconnect button immediately
            if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'reconnect_button'):
                self.button_panel.reconnect_button.setVisible(True)
            
            if self.allow_reconnect and not self.is_connecting and self.account:
                print("🔄 Connection lost - initiating auto-reconnect...")
                QTimer.singleShot(100, self._auto_reconnect)

    def _auto_reconnect(self):
        """Auto-reconnect with exponential backoff (max 10 attempts)"""
        if not self.allow_reconnect or self.is_connecting or self._is_connected() or not self.account:
            return
        
        # Max 10 attempts
        if self.reconnect_count >= 10:
            print(f"❌ Max reconnection attempts (10) reached")
            return  # Button already visible
        
        self.reconnect_count += 1
        delay = min(2 ** (self.reconnect_count - 1), 60)
        
        print(f"🔄 Auto-reconnect attempt {self.reconnect_count}/10 in {delay}s...")
        
        # Store timer so we can cancel it if user manually reconnects or app closes
        self.reconnect_timer = QTimer.singleShot(delay * 1000, lambda: (
            self.set_connection_status('connecting'),
            self.connect_xmpp()
        ) if self.allow_reconnect and not self.is_connecting else None)

    def manual_reconnect(self):
        """Manual reconnect - cancels auto-reconnect and resets counter"""
        # Cancel pending auto-reconnect timer
        if self.reconnect_timer is not None:
            try:
                self.reconnect_timer.stop()
            except:
                pass
            self.reconnect_timer = None
        
        self.reconnect_count = 0

        if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'reconnect_button'):
            self.button_panel.reconnect_button.setVisible(False)
        
        print("🔄 Manual reconnection (auto-reconnect cancelled)...")
        self.set_connection_status('connecting')
        self.connect_xmpp()

    def toggle_user_list(self):
        """Toggle userlist based on current view with proper recalculation"""
    
        current_view = self.stacked_widget.currentWidget()
        is_chatlog_view = (current_view == self.chatlog_widget)
        width = self.width()
    
        if is_chatlog_view and self.chatlog_userlist_widget:
            visible = not self.chatlog_userlist_widget.isVisible()
            self.chatlog_userlist_widget.setVisible(visible)
            self.userlist_panel.setVisible(visible)
            self.config.set("ui", "chatlog_userlist_visible", value=visible)
            self.auto_hide_chatlog_userlist = False
        else:
            visible = not self.user_list_widget.isVisible()
            self.user_list_widget.setVisible(visible)
            if hasattr(self, 'userlist_panel'):
                self.userlist_panel.setVisible(visible)
            self.config.set("ui", "messages_userlist_visible", value=visible)
            self.auto_hide_messages_userlist = False
    
        # Update button visual state
        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, visible)

        # Force resize handler to sync everything
        QTimer.singleShot(10, lambda: self._apply_resize(width))
    
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
        self._ensure_general_tab_visible()

        # Remember whether we're coming from the chatlog so "back" can return there
        # instead of always going to messages (which would destroy chatlog_widget).
        self.pre_profile_view = 'chatlog' if self.stacked_widget.currentWidget() is self.chatlog_widget else 'messages'

        if not hasattr(self, 'profile_widget') or not self.profile_widget:
            self.profile_widget = ProfileWidget(self.config, self.icons_path)
            self.profile_widget.back_requested.connect(self._on_back)
            self.stacked_widget.addWidget(self.profile_widget)

        self.profile_widget.load_profile(int(user_id), username)
        self.stacked_widget.setCurrentWidget(self.profile_widget)

    def _on_back(self):
        """Return to whichever view (chatlog or messages) was open before the profile was shown."""
        if self.pre_profile_view == 'chatlog' and self.chatlog_widget:
            self.show_chatlog_view(reload=False)
        else:
            self._on_stacked_back()

    def _on_stacked_back(self):
        """Leave a stacked view and restore room tab if any."""
        self.show_messages_view()
        self._restore_room_tab()
    
    def show_pronunciation_view(self):
        """Show pronunciation management view"""
        self._ensure_general_tab_visible()
        if not hasattr(self, 'pronunciation_widget') or not self.pronunciation_widget:
            self.pronunciation_widget = PronunciationWidget(
                self.config, 
                self.icons_path,
                self.pronunciation_manager
            )
            self.pronunciation_widget.back_requested.connect(self._on_stacked_back)
            self.stacked_widget.addWidget(self.pronunciation_widget)
        
        self.stacked_widget.setCurrentWidget(self.pronunciation_widget)
    
    def show_ban_list_view(self):
        """Show ban list management view"""
        self._ensure_general_tab_visible()
        if not hasattr(self, 'ban_list_widget') or not self.ban_list_widget:
            self.ban_list_widget = BanListWidget(
                self.config, 
                self.icons_path,
                self.ban_manager
            )
            self.ban_list_widget.back_requested.connect(self._on_stacked_back)
            self.stacked_widget.addWidget(self.ban_list_widget)
        
        self.stacked_widget.setCurrentWidget(self.ban_list_widget)

    def show_settings_view(self):
        """Show the settings view"""
        self._ensure_general_tab_visible()
        if not hasattr(self, 'settings_widget') or not self.settings_widget:
            self.settings_widget = SettingsWidget(self.config, self.icons_path)
            self.settings_widget.back_requested.connect(self._on_stacked_back)
            self.settings_widget.track_competitions_checkbox.toggled.connect(self.set_track_competitions)
            self.settings_widget.min_multiplier_combo.currentTextChanged.connect(
                self._on_min_multiplier_changed
            )
            self.settings_widget.show_cost_checkbox.toggled.connect(
                lambda _=None: self.refresh_competition_player_display()
            )
            self.settings_widget.show_players_checkbox.toggled.connect(
                lambda _=None: self.refresh_competition_player_display()
            )
            self.settings_widget.max_player_chips_spin.valueChanged.connect(
                lambda _=None: self.refresh_competition_player_display()
            )
            self.settings_widget.sort_players_by_level_checkbox.toggled.connect(
                lambda _=None: self.refresh_competition_player_display()
            )
            self.settings_widget.sound_changed.connect(self._setup_sounds)
            self.settings_widget.competition_log_clear_requested.connect(
                self.clear_competition_log
            )
            self.stacked_widget.addWidget(self.settings_widget)
        else:
            # Reflect any state changed elsewhere (tray menu, hotkeys) since it was last shown
            self.settings_widget.refresh()

        self._setup_sounds()
        self._sync_competitions_settings_ui()
        self.stacked_widget.setCurrentWidget(self.settings_widget)
    
    def _on_username_left_click(self, username: str, is_double_click: bool):
        """Handle username left-click - insert into input field"""
        if not hasattr(self, 'input_field') or not self.input_field:
            return
        
        current = (self.input_field.text() or "").strip()
        existing = [u.strip() for u in current.split(',') if u.strip()]
        
        if is_double_click:
            # Double-click: replace all with this username (or clear if already solo)
            if len(existing) == 1 and existing[0] == username:
                self.input_field.clear()
            else:
                self.input_field.setText(username + ", ")
        else:
            # Single-click: add to list if not already there
            if username not in existing:
                if existing:
                    self.input_field.setText(", ".join(existing + [username]) + ", ")
                else:
                    self.input_field.setText(username + ", ")
        
        self.input_field.setFocus()

    def _paste_username_to_input(self, username: str):
        """Paste username into the active input field (game room or general)."""
        field = self._active_input_field() if hasattr(self, '_active_input_field') else self.input_field
        if not field:
            return
        cursor_pos = field.cursorPosition()
        current = field.text() or ""
        if current.strip() and not current.strip().endswith((',', ' ')):
            to_insert = f", {username}"
        else:
            to_insert = f"{username}, "
        field.setText(current[:cursor_pos] + to_insert + current[cursor_pos:])
        field.setCursorPosition(cursor_pos + len(to_insert))
        field.setFocus()

    def _resolve_user_then(self, username: str, callback):
        """Resolve user_id for username: userlist → cache → API fallback (threaded)."""
        # 1. Userlist (instant, has jid too)
        if hasattr(self, 'user_list_widget') and self.user_list_widget:
            for jid, widget in self.user_list_widget.user_widgets.items():
                user = getattr(widget, 'user', None)
                if user and user.login == username:
                    callback(jid, user.login, user.user_id)
                    return
        # 2. Cache (instant, no jid)
        user_id = self.cache.get_user_id(username)
        if user_id:
            callback('', username, user_id)
            return
        # 3. API fallback (threaded)
        import threading
        from core.api_data import get_exact_user_id_by_name
        def _fetch():
            uid = get_exact_user_id_by_name(username)
            if uid:
                self.cache.update_user(str(uid), username)
                self._dispatch.emit(lambda: callback('', username, str(uid)))
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_username_ctrl_click(self, username: str):
        """Ctrl+LMB on message username → enter private chat"""
        self._resolve_user_then(username, lambda jid, login, uid: self.enter_private_mode(jid, login, uid))

    def _on_username_shift_click(self, username: str):
        """Shift+LMB on message username → open profile"""
        self._resolve_user_then(username, lambda jid, login, uid: self.show_profile_view(jid, login, uid))

    def _on_username_right_click(self, msg, global_pos, source_widget=None):
        """Show context menu when username is right-clicked in messages or chatlog"""
        source_widget = source_widget or self.messages_widget
        try:
            def icon(name): return _render_svg_icon(self.icons_path / name, 16)

            menu = QMenu(self)

            # Profile / Private chat
            profile_act = menu.addAction(icon("user.svg"), "Profile")
            private_act = menu.addAction(icon("private-chat.svg"), "Private Chat")

            menu.addSeparator()

            # Copy username
            copy_username_act = menu.addAction(icon("clipboard.svg"), "Copy username")

            # Copy user ID
            copy_id_act = menu.addAction(icon("hashtag.svg"), "Copy ID")

            menu.addSeparator()

            # Permanent ban action
            perm_act = menu.addAction(icon("prohibited.svg"), "Ban permanently")

            # Temporary ban action
            temp_act = menu.addAction(icon("forbidden.svg"), "Ban temporarily")

            # Separator
            menu.addSeparator()

            # Message removal actions
            remove_msg_act  = menu.addAction(icon("delete-back.svg"),     "Remove this message")
            remove_up_act   = menu.addAction(icon("delete-bin-up.svg"),   "Remove from here upward")
            remove_down_act = menu.addAction(icon("delete-bin-down.svg"), "Remove from here downward")
            remove_all_act  = menu.addAction(icon("delete-bin.svg"),      "Remove all messages")
            
            act = menu.exec(global_pos)
            if not act:
                return
            
            if act == profile_act:
                username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
                if username:
                    self._resolve_user_then(username, lambda jid, login, uid: self.show_profile_view(jid, login, uid))
            elif act == private_act:
                username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
                if username:
                    self._resolve_user_then(username, lambda jid, login, uid: self.enter_private_mode(jid, login, uid))
            elif act == copy_username_act:
                username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
                if username:
                    QApplication.clipboard().setText(username)
            elif act == copy_id_act:
                username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
                user_id = self.cache.get_user_id(username) if username else None
                QApplication.clipboard().setText(str(user_id or ""))
            elif act == perm_act:
                # Permanent ban
                self._ban_user_from_msg(msg, permanent=True, widget=source_widget)
            elif act == temp_act:
                # Show duration dialog
                seconds, ok = DurationDialog.get_duration(self, default_seconds=3600)
                if ok:
                    self._ban_user_from_msg(msg, permanent=False, duration=seconds, widget=source_widget)
            elif act == remove_msg_act:
                # Remove single message
                self._remove_message(msg, single=True, widget=source_widget)
            elif act == remove_up_act:
                # Remove messages from start to this message
                self._remove_message(msg, direction="up", widget=source_widget)
            elif act == remove_down_act:
                # Remove messages from this message to end
                self._remove_message(msg, direction="down", widget=source_widget)
            elif act == remove_all_act:
                # Remove all messages from user
                self._remove_message(msg, single=False, widget=source_widget)
        
        except Exception as e:
            print(f"Context menu error: {e}")
    
    def _ban_user_from_msg(self, msg, permanent: bool = True, duration: int = None, widget=None):
        """Perform ban: update BanManager, remove messages, remove userlist entry"""
        widget = widget or self.messages_widget
        # Skip separators
        if getattr(msg, 'is_separator', False) or getattr(msg, 'is_new_messages_marker', False):
            return
        
        username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
        jid = getattr(msg, 'from_jid', None)
        
        # Extract user_id from JID using helper
        user_id, _ = extract_user_data_from_jid(jid)
        
        if not user_id and not username:
            return
        
        # Validate username via API to get correct user_id
        if username and not user_id:
            from ui.ui_banlist import validate_username_and_get_id
            user_id = validate_username_and_get_id(username)
        
        if not user_id:
            QMessageBox.warning(self, "Error", f"Could not find user ID for {username}")
            return
        
        # Add to ban manager
        if permanent:
            self.ban_manager.add_user(user_id, username or user_id)
        else:
            self.ban_manager.add_user(user_id, username or user_id, duration=duration)
        
        # Remove messages by login
        if username:
            try:
                widget.model.remove_messages_by_login(username)
            except Exception:
                pass
        
        # Remove from userlist
        if hasattr(self, 'user_list_widget') and self.user_list_widget:
            try:
                if jid:
                    self.user_list_widget.remove_users(jids=[jid])
                # Fallback: remove by username
                if username:
                    for ujid, uw in list(self.user_list_widget.user_widgets.items()):
                        ulogin = getattr(getattr(uw, 'user', None), 'login', None)
                        if ulogin == username:
                            self.user_list_widget.remove_users(jids=[ujid])
            except Exception:
                pass
        
        # Refresh ban list UI if open
        if hasattr(self, 'ban_list_widget') and self.ban_list_widget:
            try:
                self.ban_list_widget._load_bans()
            except Exception:
                pass
    
    def _remove_message(self, msg, single: bool = True, direction: str = None, widget=None):
        """Remove message(s) without banning user.
        direction='down' → from msg to end; 'up' → from start to msg
        """
        widget = widget or self.messages_widget
        username = getattr(msg, 'login', None) or getattr(msg, 'username', None)
        if not username:
            return
        
        try:
            timestamp = getattr(msg, 'timestamp', None)
            if direction == "down":
                widget.model.remove_messages_by_login(username, from_timestamp=timestamp)
            elif direction == "up":
                widget.model.remove_messages_by_login(username, to_timestamp=timestamp)
            else:
                widget.model.remove_messages_by_login(username, timestamp if single else None)
        except Exception as e:
            print(f"Error removing message(s): {e}")

    # Physical key → action, layout-independent via nativeVirtualKey fallback.
    # Qt key values for Latin letters equal their ASCII codes, as does
    # Windows Virtual Key codes — so nativeVirtualKey() works regardless of layout.
    _KEY_ACTION = {
        Qt.Key.Key_F: 'focus',
        Qt.Key.Key_U: 'userlist',
        Qt.Key.Key_B: 'banlist',
        Qt.Key.Key_P: 'pronun',
        Qt.Key.Key_M: 'mute',
        Qt.Key.Key_T: 'top',
        Qt.Key.Key_V: 'voice',
        Qt.Key.Key_R: 'reset_size',
        Qt.Key.Key_C: 'color',
        Qt.Key.Key_N: 'notification',
        Qt.Key.Key_S: 'search',
        Qt.Key.Key_H: 'nav_backward',
        Qt.Key.Key_L: 'nav_forward',
        Qt.Key.Key_Left:  'nav_backward',
        Qt.Key.Key_Right: 'nav_forward',
        Qt.Key.Key_J: 'scroll_down',
        Qt.Key.Key_K: 'scroll_up',
        Qt.Key.Key_Down: 'scroll_down',
        Qt.Key.Key_Up: 'scroll_up',
        Qt.Key.Key_G: 'scroll_gg',   # gg = top, G (Shift+G) = bottom
        Qt.Key.Key_D: 'calendar',
        Qt.Key.Key_Space: 'page_down',
        Qt.Key.Key_X: 'exit_private',
    }

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers()
        ctrl  = mods == Qt.KeyboardModifier.ControlModifier
        shift = mods == Qt.KeyboardModifier.ShiftModifier

        if mods and not ctrl and not shift:
            return super().keyPressEvent(event)

        focused_widget = QApplication.focusWidget()
        focused = isinstance(focused_widget, (QLineEdit, QTextEdit))

        # Forward Ctrl+C to the text selector overlay if active
        if ctrl and (key == Qt.Key.Key_C or event.nativeVirtualKey() == Qt.Key.Key_C):
            delegate = getattr(self.messages_widget, 'delegate', None)
            if delegate and delegate._text_selector:
                delegate._text_selector.copy()
                return

        # F1 — context-aware help
        if key == Qt.Key.Key_F1:
            sel = getattr(self, 'emoticon_selector', None)
            if sel and sel.isVisible():
                context = 'emoticon'
            elif (self.chatlog_widget and
                  self.stacked_widget.currentWidget() == self.chatlog_widget):
                context = 'parser' if self.chatlog_widget.parser_visible else 'chatlog'
            else:
                context = 'chat'
            self.help_panel.show_for_context(context)
            return

        # Loose input focus on (Esc) — also closes chatlog search if open
        if key == Qt.Key.Key_Escape and focused:
            self.input_field.clearFocus()
            return
        if key == Qt.Key.Key_Escape:
            sel = getattr(self, 'emoticon_selector', None)
            if sel and sel.isVisible():
                sel.toggle_visibility()
                self.input_field.setFocus()
                return
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw and cw.search_visible:
                cw._toggle_search()
                return
        # Ctrl+; toggle emoticon selector (works even when input focused, layout-independent)
        # nativeScanCode 0x27 = physical semicolon key on all standard keyboards
        if ctrl and (key == Qt.Key.Key_Semicolon or event.nativeScanCode() == 0x27):
            self._toggle_emoticon_selector()
            return
        # Ctrl+F toggle search in chatlog (works regardless of input focus)
        if ctrl and (key == Qt.Key.Key_F or event.nativeVirtualKey() == Qt.Key.Key_F):
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw:
                cw._toggle_search()
            return
        # Ctrl+C / Ctrl+S in chatlog parser — copy / save results
        if ctrl and self.chatlog_widget and self.stacked_widget.currentWidget() == self.chatlog_widget:
            cw = self.chatlog_widget
            if cw.parser_visible:
                if key == Qt.Key.Key_C or event.nativeVirtualKey() == Qt.Key.Key_C:
                    cw._on_copy_results()
                    return
                if key == Qt.Key.Key_S or event.nativeVirtualKey() == Qt.Key.Key_S:
                    cw._on_save_results()
                    return
        # Ctrl+P open chatlog and parser from anywhere
        if ctrl and (key == Qt.Key.Key_P or event.nativeVirtualKey() == Qt.Key.Key_P):
            if not self.chatlog_widget or self.stacked_widget.currentWidget() != self.chatlog_widget:
                self.show_chatlog_view()
            if self.chatlog_widget and not self.chatlog_widget.parser_visible:
                self.chatlog_widget._toggle_parser()
            return
        # Ctrl+U switch account
        if ctrl and (key == Qt.Key.Key_U or event.nativeVirtualKey() == Qt.Key.Key_U):
            self._on_switch_account()
            return
        # Ctrl+T toggle theme
        if ctrl and (key == Qt.Key.Key_T or event.nativeVirtualKey() == Qt.Key.Key_T):
            self.toggle_theme()
            return
        # Resolve physical key regardless of layout
        vk = self._KEY_ACTION.get(key) or self._KEY_ACTION.get(event.nativeVirtualKey())

        # ── Emoticon selector keyboard navigation ──────────────────────────────
        sel = getattr(self, 'emoticon_selector', None)
        if sel and sel.isVisible() and not focused:
            nk = event.nativeVirtualKey()
            sc = event.nativeScanCode()
            if not ctrl and not shift:
                if key == Qt.Key.Key_Left  or nk == Qt.Key.Key_H: sel.navigate(-1, 0); return
                if key == Qt.Key.Key_Right or nk == Qt.Key.Key_L: sel.navigate(1, 0); return
                if key == Qt.Key.Key_Down  or nk == Qt.Key.Key_J: sel.navigate(0, 1); return
                if key == Qt.Key.Key_Up    or nk == Qt.Key.Key_K: sel.navigate(0, -1); return
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or nk == Qt.Key.Key_A or sc == 0x27:
                    sel.insert_selected(); return
            if shift and (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or nk == Qt.Key.Key_A or sc == 0x27):
                sel.insert_selected(shift=True); return
        # ───────────────────────────────────────────────────────────────────────

        if not vk or focused:
            return super().keyPressEvent(event)
        def _toggle_view(attr, show_fn):
            w = getattr(self, attr, None)
            self.show_messages_view() if w and self.stacked_widget.currentWidget() == w else show_fn()
        def _active_scrollbar():
            current = self.stacked_widget.currentWidget()
            if current == self.messages_splitter:
                return self.messages_widget.list_view.verticalScrollBar()
            if self.chatlog_widget and current == self.chatlog_widget:
                return self.chatlog_widget.list_view.verticalScrollBar()
            return None
        # Focus input on (F) key if not focused, for quick access
        if vk == 'focus':
            # Focus the active room's own input, not always General's —
            # otherwise F kept stealing focus back to General while sitting
            # in a game/competition tab.
            self._active_input_field().setFocus()
        # User list toggle (U) — Ctrl+U is handled before the focus guard above
        elif vk == 'userlist':
            self.toggle_user_list()
        # Ban list toggle (B)
        elif vk == 'banlist':
            _toggle_view('ban_list_widget', self.show_ban_list_view)
        # Pronunciation toggle (P) / in chatlog: toggle parser (P)
        elif vk == 'pronun':
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw:
                cw._toggle_parser()
            else:
                _toggle_view('pronunciation_widget', self.show_pronunciation_view)
        # Mute effects sound (M) or toggle mention filter in chatlog (M)
        elif vk == 'mute':
            if self.chatlog_widget and self.stacked_widget.currentWidget() == self.chatlog_widget:
                self.chatlog_widget._toggle_mention_filter()
            else:
                self.on_toggle_effects_sound()
        # Toggle search in chatlog (S) / start parsing when parser visible
        elif vk == 'search':
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw:
                if cw.parser_visible and not cw.parser_widget.is_parsing:
                    cw.parser_widget._on_parse_clicked()
                elif not cw.parser_visible and not cw.search_field.hasFocus():
                    cw._toggle_search()
        # Navigate chatlog days — H backward, L forward, supports hold
        elif vk in ('nav_backward', 'nav_forward'):
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw and not event.isAutoRepeat():
                cw._navigate_hold(-1 if vk == 'nav_backward' else 1)
        # Vim-style scroll — J down, K up, works in chat and chatlog
        elif vk in ('scroll_down', 'scroll_up'):
            sb = _active_scrollbar()
            if sb:
                step = sb.singleStep() * 5
                sb.setValue(sb.value() + (step if vk == 'scroll_down' else -step))
        # Vim-style G = bottom, gg = top
        elif vk == 'scroll_gg':
            sb = _active_scrollbar()
            if sb:
                if shift:
                    sb.setValue(sb.maximum())
                else:
                    if not hasattr(self, '_gg_timer'):
                        self._gg_timer = QTimer(self)
                        self._gg_timer.setSingleShot(True)
                    if self._gg_timer.isActive():
                        self._gg_timer.stop()
                        sb.setValue(sb.minimum())
                    else:
                        self._gg_timer.start(300)
        # Space — scroll down one page
        elif vk == 'page_down':
            sb = _active_scrollbar()
            if sb:
                sb.setValue(sb.value() + (-sb.pageStep() if shift else sb.pageStep()))
        # Always on top toggle (T)
        elif vk == 'top':
            self.on_toggle_always_on_top()
        # Voice sound toggle (V)
        elif vk == 'voice':
            self.on_toggle_voice_sound()
        # Reset window size (R)
        elif vk == 'reset_size':
            self.reset_window_size()
        # Change username color (C) / Ctrl+C reset / Shift+C update from server
        # In chatlog when parser visible: C cancels if parsing, Ctrl+C copies
        elif vk == 'color':
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw and cw.parser_visible:
                if ctrl:
                    cw._on_copy_results()
                elif cw.parser_widget.is_parsing:
                    cw.parser_widget._on_parse_clicked()  # Cancel
            elif ctrl:
                self.on_reset_username_color()
            elif shift:
                self.on_update_username_color()
            else:
                self.on_change_username_color()
        # Toggle notifications cycle (N)
        elif vk == 'notification':
            self.on_toggle_notification()
        # Open calendar date picker in chatlog (D)
        elif vk == 'calendar':
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw:
                cw._show_calendar()
        # Exit private mode / clear private messages / clear new messages marker (X)
        elif vk == 'exit_private':
            if self.private_mode:
                self.exit_private_mode()
            else:
                self._clear_private_messages()
            self._clear_new_messages_marker()

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        vk = self._KEY_ACTION.get(key) or self._KEY_ACTION.get(event.nativeVirtualKey())
        if vk in ('nav_backward', 'nav_forward'):
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw:
                cw._navigate_hold()  # Stop hold
                return
        super().keyReleaseEvent(event)

    def toggle_theme(self):
        try:
            self.theme_manager.toggle_theme()
            is_dark = self.theme_manager.is_dark()
            set_theme(is_dark)
         
            # Update theme button icon via button panel
            self.button_panel.update_theme_button_icon()
         
            # Update input styling for theme
            self._update_input_style()
         
            update_all_icons()
            update_all_tag_buttons()
            
            # Update shared emoticon manager theme
            self.emoticon_manager.set_theme(is_dark)
            
            # Update widgets
            self.messages_widget.update_theme()
            self.user_list_widget.update_theme()
            
            if self.chatlog_widget:
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

            if getattr(self, "settings_widget", None):
                self.settings_widget.update_theme()
         
            self.messages_widget.rebuild_messages()
         
            if self.chatlog_widget and self.stacked_widget.currentWidget() == self.chatlog_widget:
                self.chatlog_widget._force_recalculate()

            # Re-theme open game rooms
            for gr in self.game_rooms.values():
                gr.update_theme()

            QApplication.processEvents()
        except Exception as e:
            print(f"Theme toggle error: {e}")

    def closeEvent(self, event):
        # Cleanup emoticon selector
        if hasattr(self, 'emoticon_selector'):
            self.emoticon_selector.cleanup()

        # Remove new messages marker when closing
        self._clear_new_messages_marker()
    
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

        # Cleanup window size manager
        if hasattr(self, 'window_size_manager'):
            self.window_size_manager.cleanup()

        self._reset_competition_live_state()

        # Proceed with full cleanup when actually closing
        if self.messages_widget:
            if hasattr(self.messages_widget, 'auto_scroller'):
                try:
                    self.messages_widget.auto_scroller.cleanup()
                except:
                    pass
            self.messages_widget.cleanup()
        if self.chatlog_split_widget:
            self.chatlog_split_widget.cleanup()
        for gid in list(self.game_rooms.keys()):
            self._close_game_room_tab(gid)
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
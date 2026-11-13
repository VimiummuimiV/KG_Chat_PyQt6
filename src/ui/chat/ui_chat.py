"""Chat window with XMPP integration"""

from PyQt6.QtCore import pyqtSignal, QObject, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from components.button import set_theme
from components.font_scale_slider import FontScaleSlider
from components.help_panel import HelpPanel
from components.input_row import InputRow
from components.toast import Toast
from core.state.mentions_digest import MentionsDigest
from core.state.self_ban import SelfBan
from helpers.cache import get_cache
from helpers.config import Config, get_config_path
from helpers.data import get_resource_dir
from helpers.deferred import call_later
from helpers.fonts.fonts import get_userlist_width
from helpers.system.memory import release_memory_soon
from helpers.text.emoticons import EmoticonManager
from helpers.translate import on_language_changed, tr, TranslatableMixin
from helpers.voice.voice_engine import get_voice_engine
from helpers.window.window_size_manager import WindowSizeManager
from themes.theme import ThemeManager
from ui.chat.chat_balance import ChatBalanceMixin
from ui.chat.chat_competitions import ChatCompetitionsMixin
from ui.chat.chat_connection import ChatConnectionMixin
from ui.chat.chat_controls import ChatControlsMixin
from ui.chat.chat_copy import ChatCopyMixin
from ui.chat.chat_delivery import ChatDeliveryMixin
from ui.chat.chat_emoticons import ChatEmoticonsMixin
from ui.chat.chat_fonts import ChatFontsMixin
from ui.chat.chat_geometry import ChatGeometryMixin
from ui.chat.chat_hotkeys import ChatHotkeysMixin
from ui.chat.chat_incoming import ChatIncomingMixin
from ui.chat.chat_input import ChatInputMixin
from ui.chat.chat_lifecycle import ChatLifecycleMixin
from ui.chat.chat_notifications import ChatNotificationsMixin
from ui.chat.chat_panels import ChatPanelsMixin
from ui.chat.chat_parse_status import ChatParseStatusMixin
from ui.chat.chat_presence_log import ChatPresenceLogMixin
from ui.chat.chat_private_mode import ChatPrivateModeMixin
from ui.chat.chat_room_tabs import ChatRoomTabsMixin
from ui.chat.chat_self_ban import ChatSelfBanMixin
from ui.chat.chat_user_actions import ChatUserActionsMixin
from ui.chat.chat_views import ChatViewsMixin
from ui.chat.ui_buttons import ButtonPanel
from ui.chat.ui_emoticon_selector import EmoticonSelectorWidget
from ui.chat.ui_messages import MessagesWidget
from ui.chat.ui_pets import PetOverlay
from ui.chat.ui_userlist import UserListWidget
from ui.chat.voice_input_attach import install_voice_input
from ui.notification.popup_manager import popup_manager


class _SignalEmitter(QObject):
    message_received = pyqtSignal(object)
    presence_received = pyqtSignal(object)
    bulk_update_complete = pyqtSignal()
    connection_changed = pyqtSignal(str)


class ChatWindow(
    TranslatableMixin,
    ChatBalanceMixin,
    ChatCompetitionsMixin,
    ChatConnectionMixin,
    ChatControlsMixin,
    ChatCopyMixin,
    ChatDeliveryMixin,
    ChatEmoticonsMixin,
    ChatFontsMixin,
    ChatGeometryMixin,
    ChatHotkeysMixin,
    ChatIncomingMixin,
    ChatInputMixin,
    ChatLifecycleMixin,
    ChatNotificationsMixin,
    ChatPanelsMixin,
    ChatParseStatusMixin,
    ChatPresenceLogMixin,
    ChatPrivateModeMixin,
    ChatRoomTabsMixin,
    ChatSelfBanMixin,
    ChatUserActionsMixin,
    ChatViewsMixin,
    QWidget,
):
    dispatch = pyqtSignal(object)  # thread-safe main-thread callable dispatch

    def __init__(
        self,
        account=None,
        app_controller=None,
        pronunciation_manager=None,
        ban_manager=None,
        user_tracker=None
        ):
        super().__init__()
        self.init_translatable()
        self.dispatch.connect(lambda f: f())
        self.app_controller = app_controller
        self.pronunciation_manager = pronunciation_manager
        self.ban_manager = ban_manager
        self.user_tracker = user_tracker
        self.tray_mode = False
        self.really_close = False
        self.account = account
        self.xmpp_client = None
        self.signal_emitter = _SignalEmitter()
        self.cache = get_cache()
        self.mentions_digest = MentionsDigest()
        self.self_ban = SelfBan()
        self.mentions_digest_active = False
        self.mentions_digest_checked = False  # digest runs once per window, not on every reconnect
        self.presence_anchor_timer = QTimer(self)
        self.presence_anchor_timer.timeout.connect(self.touch_presence_anchor)
        self.self_ban_until = None  # epoch seconds while our own chat ban is active
        self.self_ban_total = 0
        self.self_muted = False  # MUC role 'visitor' in the general room (no voice)
        self.self_ban_timer = QTimer(self)
        self.self_ban_timer.timeout.connect(self.update_input_style)

        self.races_listener = None
        self.competition_notified = set()  # game_ids already announced this session
        self.competition_log_lines = []
        self.competition_log_status = {}  # game_id -> last logged status (dedupe)
        self.races_status = "disconnected"
        self.pending_competitions = []  # queued while chat history isn't ready yet
        self.chat_ready = False  # True once initial history has settled once
        self.history_settle_timer = QTimer(self)  # fires when history stream goes quiet
        self.history_settle_timer.setSingleShot(True)
        self.history_settle_timer.timeout.connect(self.on_history_settled)
        self.history_settle_timer.timeout.connect(release_memory_soon)

        # Live-updating competition messages: game_id -> {mult, url, begintime, players}
        self.competition_live = {}
        self.competition_alert_timers = {}  # game_id -> pending lead-time alert QTimer
        self.competition_focus_game_id = None  # keep this row centered while chips grow after alert
        self.competition_countdown_timer = QTimer(self)
        self.competition_countdown_timer.timeout.connect(self.tick_competition_countdowns)
        self.competition_sound_repeat_timer = QTimer(self)
        self.competition_sound_repeat_timer.timeout.connect(self.on_competition_sound_repeat_tick)
        self.competition_sound_repeat_cursor_pos = None
        self.balance_fetch_errors_shown = set()  # error codes already dialoged this session

        self.initial_roster_loading = False
        self.auto_hide_messages_userlist = True
        self.auto_hide_chatlog_userlist = True
        self.auto_hide_tracker_userlist = True

        # Track window show/reset state to avoid persisting programmatic geometry
        self.showing_window = False
        self.resetting_geometry = False

        # Simple connection state tracking
        self.is_connecting = False # True when attempting to connect
        self.allow_reconnect = True # Disable when switching accounts
        self.reconnect_count = 0 # Incremented each time a reconnect attempt is made
        self.reconnect_timer = None # Timer for delayed reconnect attempts
        self.connect_generation = 0 # Bumped per attempt so a stale worker can't clobber a newer one's state
        self.connection_status = 'offline'  # normalized key, kept in sync by set_connection_status

        # Private messaging state
        self.private_mode = False
        self.private_chat_jid = None
        self.private_chat_username = None
        self.private_chat_user_id = None

        # Track new messages marker
        self.has_new_messages_marker = False

        # Initialize paths and config — share Config with app_controller to avoid
        # two instances overwriting config.json (family vs size race).
        self.config_path = get_config_path()
        self.icons_path = get_resource_dir("icons")

        if app_controller is not None and getattr(app_controller, "config", None) is not None:
            self.config = app_controller.config
        else:
            self.config = Config(self.config_path)
        # rating competitions tracking
        track = self.config.get("competitions", "enabled")
        if track is None or track:
            # defer start until event loop is running
            call_later(self, 0, lambda: self.set_track_competitions(True))

        # Initialize emoticon manager
        emoticons_path = get_resource_dir("emoticons")
        self.emoticon_manager = EmoticonManager(emoticons_path)

        # Initialize window size manager
        self.window_size_manager = WindowSizeManager(on_save_callback=self.update_reset_size_button_state)

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
        self.setup_sounds()

        self._init_ui()
        self.restore_self_ban()

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

        on_language_changed(self._retranslate)

    @property
    def my_username(self):
        return (self.account or {}).get('chat_username') or None

    def _init_ui(self):
        window_title = f"{tr("Chat", "Чат")} - {self.my_username}" if self.my_username else tr("Chat", "Чат")
        self.setWindowTitle(window_title)

        # Check for saved window geometry (size + position) first
        saved_width, saved_height, saved_x, saved_y = self.window_size_manager.get_saved_geometry()

        if saved_width and saved_height:
            window_width, window_height = saved_width, saved_height
            window_x = saved_x if saved_x is not None else None
            window_y = saved_y if saved_y is not None else None
        else:
            window_width, window_height, window_x, window_y = self.calculate_default_geometry()

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

        self.messages_widget = MessagesWidget(self.config, self.emoticon_manager, my_username=self.my_username)

        # Vertical pane: presence log (created on demand) above the live messages view
        self.presence_pane_splitter = QSplitter(Qt.Orientation.Vertical)
        self.presence_pane_splitter.addWidget(self.messages_widget)
        self.presence_pane_splitter.splitterMoved.connect(self.on_presence_split_moved)
        self.presence_log_widget = None

        # Splitter so a chatlog can be shown alongside the live messages view
        # (RMB on a timestamp), without leaving/replacing the messages view itself
        self.messages_splitter = QSplitter(Qt.Orientation.Vertical)
        self.messages_splitter.addWidget(self.presence_pane_splitter)
        self.chatlog_split_widget = None  # the split-pane ChatlogWidget, when open

        self.game_rooms = {}  # game_id -> RoomWidget
        self.custom_rooms = {}  # room_name -> RoomWidget
        self.room_tabs = None  # QTabWidget; General is always tab 0 when present
        self.general_body = None
        self.unread_rooms = {}  # game_id|None(General)|"c:name" -> unread message count

        self.stacked_widget.addWidget(self.messages_splitter)
        self.chatlog_widget = None
        self.chatlog_userlist_widget = None
        self.pre_profile_view = None  # 'messages' or 'chatlog' - where to return after profile/pronunciation/ban-list views
        self.restore_room_game_id = None  # game_id of room tab to reopen after profile/private...

        pet_strip = QWidget()  # keeps the pets' line free of messages; empty and hidden while there are no pets
        left_layout.addWidget(pet_strip)

        # Input area
        self.input_container = QWidget()
        input_main_layout = QVBoxLayout()
        input_main_layout.setContentsMargins(0, 0, 0, 0)
        input_main_layout.setSpacing(self.config.get("ui", "spacing", "widget_elements") or 6)
        self.input_container.setLayout(input_main_layout)
        left_layout.addWidget(self.input_container, alignment=Qt.AlignmentFlag.AlignBottom)

        button_spacing = self.config.get("ui", "buttons", "spacing") or 8

        self.input_row = InputRow(self.icons_path, self.config)
        self.input_row.submitted.connect(self.send_message)
        self.input_row.emoticon_requested.connect(self.toggle_emoticon_selector)
        self.input_field = self.input_row.input_field
        self.send_button = self.input_row.send_button
        self.emoticon_button = self.input_row.emoticon_button
        input_main_layout.addWidget(self.input_row)

        self._input_bottom_layout = QHBoxLayout()
        self._input_bottom_layout.setSpacing(button_spacing)
        input_main_layout.addLayout(self._input_bottom_layout)

        self.messages_widget.set_input_field(self.input_field)
        self.setup_delivery()
        install_voice_input(self)

        # Exit private mode button reference (created dynamically when needed)
        self.exit_private_button = None

        # User list widget (right side, vertical scrollable)
        self.user_list_widget = UserListWidget(
            self.config, self.input_field, self.ban_manager, self.user_tracker, my_username=self.my_username
        )
        # Connect signals for user list actions
        self.wire_userlist_signals(self.user_list_widget)
        self.user_list_widget.open_game_requested.connect(self.open_game_room_by_id)

        messages_userlist_visible = self.config.get("ui", "userlist", "messages")
        userlist_visible = messages_userlist_visible if messages_userlist_visible is not None else True
        self.user_list_widget.setVisible(userlist_visible)

        # Right column: wrap in QWidget so hiding it collapses the space
        self.userlist_panel = QWidget()
        userlist_layout = QVBoxLayout()
        userlist_layout.setContentsMargins(0, 0, 0, 0)
        userlist_layout.setSpacing(4)
        userlist_layout.addWidget(self.user_list_widget, stretch=1)

        # Font scale slider under userlist — fixed height matches input_container
        # so the slider is vertically centred against the input field row.
        font_scaler = getattr(self.app_controller, 'font_scaler', None)
        if font_scaler is not None:
            self._font_scale_slider = FontScaleSlider(font_scaler)
            self._font_scale_slider.setFixedHeight(self.input_field.minimumHeight())
            userlist_layout.addWidget(self._font_scale_slider)
        else:
            self._font_scale_slider = None

        self.userlist_panel.setLayout(userlist_layout)
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
        self.button_panel.switch_account_requested.connect(self.on_switch_account)
        self.button_panel.show_banlist_requested.connect(self.toggle_ban_list_view)
        self.button_panel.show_tracker_requested.connect(self.toggle_user_tracker_view)
        self.button_panel.toggle_voice_requested.connect(self.on_toggle_voice_sound)
        self.button_panel.pronunciation_requested.connect(self.toggle_pronunciation_view)
        self.button_panel.toggle_effects_requested.connect(self.on_toggle_effects_sound)
        self.button_panel.toggle_notification_requested.connect(self.on_toggle_notification)

        # Color management connections (change / reset / update-from-server)
        self.button_panel.change_color_requested.connect(self.on_change_username_color)
        self.button_panel.reset_color_requested.connect(self.on_reset_username_color)

        self.button_panel.toggle_theme_requested.connect(self.toggle_theme)
        self.button_panel.reset_window_size_requested.connect(self.reset_window_size)
        self.button_panel.show_window_presets_requested.connect(self.show_window_presets)
        self.button_panel.toggle_always_on_top_requested.connect(self.on_toggle_always_on_top)
        self.button_panel.show_settings_requested.connect(self.toggle_settings_view)
        self.button_panel.exit_requested.connect(self.on_exit_requested)
        self.button_panel.reconnect_requested.connect(self.manual_reconnect)
        self.button_panel.join_room_requested.connect(self.on_join_room_requested)
        self.button_panel.search_requested.connect(self.toggle_search_for_current_view)
        self.button_panel.copy_messages_requested.connect(self.copy_messages_from_current_view)
        self.toast = Toast(self, self.theme_manager.is_dark)

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
        self.hover_reveal = False

        # Initialize userlist button state
        messages_userlist_visible = self.config.get("ui", "userlist", "messages")
        if messages_userlist_visible is not None:
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, messages_userlist_visible)
        else:
            # Default to visible
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, True)

        self.pet_overlay = PetOverlay(self, pet_strip, self.stacked_widget, self.config)

        # Emoticon selector widget (overlay - positioned absolutely)
        # Create AFTER userlist so positioning works correctly
        self.emoticon_selector = EmoticonSelectorWidget(
            self.config,
            self.emoticon_manager,
            self.icons_path
        )
        self.emoticon_selector.attach(self, self.on_emoticon_selected)

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
        QTimer.singleShot(50, self.position_emoticon_selector)

        self.messages_widget.timestamp_left_clicked.connect(self.show_chatlog_view)
        self.messages_widget.timestamp_right_clicked.connect(self.show_chatlog_split_view)
        self.messages_widget.competition_timestamp_left_clicked.connect(
            lambda msg: self.open_game_room_tab(msg, room_label="Competition")
        )
        self.messages_widget.chip_clicked.connect(self.on_username_shift_click)
        self.wire_username_signals(self.messages_widget)
        self.messages_widget.chatlog_link_clicked.connect(self.show_chatlog_split_view)
        self.messages_widget.competition_entered.connect(self.on_competition_entered)

        self.update_input_style()

    def _retranslate(self, _code=None):
        self.retranslate_all()
        self.update_connection_title()

        # Force input style update – updates private chat placeholder
        self.update_input_style()

"""ChatWindow: stacked panels (profile, settings, ban list, tracker, pronunciation)."""

from ui.account.ui_profile import ProfileWidget
from ui.settings.ui_settings import SettingsWidget
from ui.tracker.ui_user_tracker import UserTrackerWidget
from ui.ui_banlist import BanListWidget
from ui.ui_pronunciation import PronunciationWidget


class ChatPanelsMixin:
    """ChatWindow: stacked panels (profile, settings, ban list, tracker, pronunciation)."""

    def on_switch_account(self):
        """Handle switch account request from button panel"""
        if self.app_controller:
            self.app_controller.show_account_switcher()

    def show_profile_view(self, jid: str, username: str, user_id: str):
        """Show profile view for a user"""
        if not user_id:
            return

        uid = int(user_id)

        # Already viewing this profile — toggle closed (same as Back)
        if (hasattr(self, 'profile_widget') and self.profile_widget
                and self.stacked_widget.currentWidget() is self.profile_widget
                and self.profile_widget.current_user_id == uid):
            self._on_back()
            return

        self.ensure_general_tab_visible()

        # Remember whether we're coming from the chatlog so "back" can return there
        # instead of always going to messages (which would destroy chatlog_widget).
        self.pre_profile_view = 'chatlog' if self.stacked_widget.currentWidget() is self.chatlog_widget else 'messages'

        if not hasattr(self, 'profile_widget') or not self.profile_widget:
            self.profile_widget = ProfileWidget(self.config, self.icons_path)
            self.profile_widget.back_requested.connect(self._on_back)
            self.stacked_widget.addWidget(self.profile_widget)

        self.profile_widget.load_profile(uid, username)
        self.stacked_widget.setCurrentWidget(self.profile_widget)

    def _on_back(self):
        """Return to whichever view (chatlog or messages) was open before the profile was shown."""
        if self.pre_profile_view == 'chatlog' and self.chatlog_widget:
            self.show_chatlog_view(reload=False)
        else:
            self.on_stacked_back()

    def on_stacked_back(self):
        """Leave a stacked view and restore room tab if any."""
        self.show_messages_view()
        self.restore_room_tab()

    def _toggle_stacked_view(self, widget_attr: str, show_fn):
        """If the stacked view is already open, close it (same as Back); otherwise open it."""
        widget = getattr(self, widget_attr, None)
        if widget is not None and self.stacked_widget.currentWidget() is widget:
            self.on_stacked_back()
        else:
            show_fn()

    def toggle_ban_list_view(self):
        self._toggle_stacked_view('ban_list_widget', self.show_ban_list_view)

    def toggle_user_tracker_view(self):
        self._toggle_stacked_view('user_tracker_widget', self.show_user_tracker_view)

    def toggle_settings_view(self):
        self._toggle_stacked_view('settings_widget', self._show_settings_view)

    def toggle_pronunciation_view(self):
        self._toggle_stacked_view('pronunciation_widget', self.show_pronunciation_view)

    def show_pronunciation_view(self):
        """Show pronunciation management view"""
        self.ensure_general_tab_visible()
        if not hasattr(self, 'pronunciation_widget') or not self.pronunciation_widget:
            self.pronunciation_widget = PronunciationWidget(
                self.config, 
                self.icons_path,
                self.pronunciation_manager
            )
            self.pronunciation_widget.back_requested.connect(self.on_stacked_back)
            self.stacked_widget.addWidget(self.pronunciation_widget)

        self.stacked_widget.setCurrentWidget(self.pronunciation_widget)

    def show_ban_list_view(self):
        """Show ban list management view"""
        self.ensure_general_tab_visible()
        if not hasattr(self, 'ban_list_widget') or not self.ban_list_widget:
            self.ban_list_widget = BanListWidget(
                self.config, 
                self.icons_path,
                self.ban_manager
            )
            self.ban_list_widget.back_requested.connect(self.on_stacked_back)
            self.stacked_widget.addWidget(self.ban_list_widget)

        self.stacked_widget.setCurrentWidget(self.ban_list_widget)

    def show_user_tracker_view(self):
        self.ensure_general_tab_visible()
        if not hasattr(self, 'user_tracker_widget') or not self.user_tracker_widget:
            self.user_tracker_widget = UserTrackerWidget(
                self.config,
                self.icons_path,
                self.user_tracker,
                font_scaler=getattr(self.app_controller, "font_scaler", None)
            )
            self.user_tracker_widget.back_requested.connect(self.on_stacked_back)
            self.user_tracker_widget.tracked_users_changed.connect(
                lambda: self.refresh_tracked_star()
            )
            self.stacked_widget.addWidget(self.user_tracker_widget)
        else:
            self.user_tracker_widget.refresh()
        self.stacked_widget.setCurrentWidget(self.user_tracker_widget)
        self.button_panel.clear_tracker_unread()

        # The shared messages/chatlog userlist panel doesn't apply to tracker view
        if hasattr(self, 'userlist_panel'):
            self.userlist_panel.setVisible(False)

        # Show tracker userlist based on config, compact width, and auto-hide
        width = self.width()
        tracker_userlist_visible = self.user_tracker_widget.userlist_visible
        show = False if (width <= 1000 and self.auto_hide_tracker_userlist) else tracker_userlist_visible
        self.user_tracker_widget.filter_panel.setVisible(
            show and bool(self.user_tracker_widget.chip_widgets)
        )
        if hasattr(self, 'button_panel'):
            self.button_panel.set_button_state(self.button_panel.toggle_userlist_button, show)

    def _show_settings_view(self):
        """Show the settings view"""
        self.ensure_general_tab_visible()
        if not hasattr(self, 'settings_widget') or not self.settings_widget:
            self.settings_widget = SettingsWidget(
                self.config,
                self.icons_path,
                font_scaler=getattr(self.app_controller, "font_scaler", None),
                emoticon_manager=self.emoticon_manager,
            )
            self.settings_widget.back_requested.connect(self.on_stacked_back)
            self.settings_widget.track_competitions_checkbox.toggled.connect(self.set_track_competitions)
            self.settings_widget.min_multiplier_combo.currentTextChanged.connect(
                self.on_min_multiplier_changed
            )
            self.settings_widget.show_cost_checkbox.toggled.connect(
                lambda _=None: self.refresh_competition_player_display()
            )
            self.settings_widget.show_scores_checkbox.toggled.connect(
                self.on_show_balance_toggled_ui
            )
            self.settings_widget.show_bonuses_checkbox.toggled.connect(
                self.on_show_balance_toggled_ui
            )
            self.settings_widget.show_players_checkbox.toggled.connect(
                lambda _=None: self.refresh_competition_player_display()
            )
            self.settings_widget.max_player_chips_spin.committed.connect(
                lambda _=None: self.refresh_competition_player_display()
            )
            self.settings_widget.sort_players_by_level_checkbox.toggled.connect(
                lambda _=None: self.refresh_competition_player_display()
            )
            self.settings_widget.youtube_checkbox.toggled.connect(
                lambda _=None: self.refresh_youtube_previews()
            )
            self.settings_widget.voice_input_checkbox.toggled.connect(
                self.on_voice_input_enabled_toggled
            )
            self.settings_widget.chatlog_max_messages_spin.committed.connect(
                lambda _=None: self.apply_chatlog_max_messages()
            )
            self.settings_widget.chat_max_messages_spin.committed.connect(
                lambda _=None: self.apply_chat_max_messages()
            )
            self.settings_widget.sound_changed.connect(self.setup_sounds)
            self.settings_widget.tracker_badge_style_changed.connect(
                self.button_panel.refresh_tracker_badge_style
            )
            self.settings_widget.input_style_changed.connect(self.update_input_style)
            self.settings_widget.tracker_presence_log_changed.connect(
                self.set_presence_log_enabled
            )
            self.settings_widget.tracker_presence_log_split_changed.connect(
                lambda _percent=None: self.apply_presence_split_sizes()
            )
            self.settings_widget.tracker_enabled_changed.connect(
                self.on_tracker_enabled_changed
            )
            self.settings_widget.tracker_userlist_star_changed.connect(
                lambda _checked=None: self.refresh_tracked_star()
            )
            self.settings_widget.competition_log_clear_requested.connect(
                self.clear_competition_log
            )
            self.settings_widget.font_family_changed.connect(self.on_font_family_changed)
            self.settings_widget.resource_changed.connect(self.manual_reconnect)
            self.settings_widget.pets_changed.connect(self._reload_all_pets)
            self.stacked_widget.addWidget(self.settings_widget)
        else:
            # Reflect any state changed elsewhere (tray menu, hotkeys) since it was last shown
            self.settings_widget.refresh()

        self.setup_sounds()
        self.sync_competitions_settings_ui()
        self.stacked_widget.setCurrentWidget(self.settings_widget)

    def _reload_all_pets(self):
        """Apply pet settings to the general overlay and every open room overlay."""
        if getattr(self, "pet_overlay", None):
            self.pet_overlay.reload()
        for room in self.all_room_widgets():
            overlay = getattr(room, "pet_overlay", None)
            if overlay:
                overlay.reload()

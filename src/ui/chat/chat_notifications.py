"""ChatWindow: popup notifications and the mentions digest."""

from datetime import datetime

from PyQt6.QtCore import QTimer

from core.chatlogs.fetch import CHATLOG_TIMEZONE
from core.chatlogs.range_parser import ParseConfig
from core.web.youtube import get_cached_info, youtube_signals, YOUTUBE_URL_PATTERN
from helpers.translate import tr
from ui.notification.popup_manager import show_notification


class ChatNotificationsMixin:
    """ChatWindow: popup notifications and the mentions digest."""

    def _mentions_digest_mode(self) -> str:
        mode = self.config.get("ui", "chat", "mentions_digest_mode")
        if mode in ("off", "daily", "custom", "start"):
            return mode
        return "daily"

    def _mentions_digest_interval_hours(self) -> int:
        mode = self._mentions_digest_mode()
        if mode == "daily":
            return 24
        if mode == "start":
            return 0
        raw = self.config.get("ui", "chat", "mentions_digest_interval_hours")
        try:
            hours = int(raw) if raw is not None else 24
        except (TypeError, ValueError):
            hours = 24
        return max(1, min(168, hours))

    def badge_font_size(self) -> int:
        raw = self.config.get("ui", "chat", "badge_font_size")
        try:
            size = int(raw) if raw is not None else 9
        except (TypeError, ValueError):
            size = 9
        return max(8, min(18, size))

    def touch_presence_anchor(self):
        """While connected the user sees everything live, so the anchor follows 'now' (survives crashes/kills)"""
        if self.connection_status == 'online' and self.my_username:
            self.mentions_digest.mark_session_end(self.my_username)

    def start_mentions_digest_check(self):
        """Background Personal Mentions parse since last_session_end (same path as manual parser).
        Frequency: off | start | daily (24h) | custom hours — per account timestamp."""

        if self._mentions_digest_mode() == "off":
            return

        username = self.my_username
        if not username:
            return
        if self.mentions_digest_checked:
            return
        self.mentions_digest_checked = True

        last = self.mentions_digest.get_last_session_end(username)
        self.presence_anchor_timer.start(60_000)  # started only after the anchor was read above
        if last is None:
            self.mentions_digest.mark_session_end(username)
            return

        interval_h = self._mentions_digest_interval_hours()
        if interval_h > 0:
            elapsed = (datetime.now() - last).total_seconds()
            if elapsed < interval_h * 3600:
                return

        self.ensure_chatlog_widget()
        cw = self.chatlog_widget
        if not cw or cw.parser_widget.is_parsing:
            return

        last_logged = last.astimezone(CHATLOG_TIMEZONE)
        config = ParseConfig(
            mode="personalmentions",
            from_date=last_logged.strftime("%Y-%m-%d"),
            from_time=last_logged.strftime("%H:%M:%S"),
            to_date=datetime.now(CHATLOG_TIMEZONE).strftime("%Y-%m-%d"),
            mention_keywords=[username],
        )
        self.mentions_digest_active = True
        cw.on_parse_started(config)
        self.start_parse_status()
        if self.parse_current_label:
            self.parse_current_label.setText(tr("Checking mentions…", "Проверка упоминаний…"))

    def end_mentions_digest(self):
        """Reset digest-active state. Shared by stop/error/finish/close paths
        so they don't each repeat the flag reset."""
        self.mentions_digest_active = False

    @staticmethod
    def room_source_label(room) -> str:
        """Source kind for notification accent color: 'game', 'competition' or 'room'."""
        if getattr(room, 'room_name', None):
            return "room"
        return "competition" if room.room_label == "Competition" else "game"

    def notify_incoming_message(self, msg, display_body, is_ban, is_system, is_initial, room_jid=None, add_message_fn=None, source_label=None, game_id=None):
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
                    my_username=self.my_username or '',
                    is_initial=is_initial,
                    is_private=getattr(msg, 'is_private', False),
                    is_ban=is_ban,
                    is_system=is_system,
                )
            else:
                # Ensure voice engine is disabled
                self.voice_engine.set_enabled(False)

        if is_ban:
            self.play_ban_sound()

        play_mention_sound_always = self.config.get("sound", "play_mention_sound_always") or False
        # Mention sound for @mentions and private messages; same focus rule
        is_important = self.message_mentions_me(msg) or getattr(msg, "is_private", False)
        if is_important and (not self.isActiveWindow() or play_mention_sound_always):
            self.play_mention_sound()

        # Only show notifications when the window is not active
        if not self.isActiveWindow():
            youtube_enabled = self.config.get("ui", "youtube", "enabled")
            youtube_enabled = True if youtube_enabled is None else bool(youtube_enabled)
            uncached = []
            if youtube_enabled:
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

    def open_mentions_from_notification(self):
        """Click handler for the tray mentions-digest popup: show window, then open results."""
        self.show_and_focus_window()
        self.show_parser_view()

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
                window_show_callback=lambda g=game_id: self.show_and_focus_window(g),
                is_private=getattr(msg, 'is_private', False),
                recipient_jid=msg.from_jid if getattr(msg, 'is_private', False) else None,
                room_jid=room_jid,
                source_label=source_label,
                is_ban=is_ban,
                is_system=is_system,
                is_mention=self.message_mentions_me(msg),
                profile_callback=self.on_username_shift_click,
                self_ban_placeholder_callback=self.self_ban_placeholder,
            )
        except Exception as e:
            print(f"Notification error: {e}")

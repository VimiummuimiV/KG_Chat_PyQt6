"""ChatWindow: live competition tracking, chips and alerts."""

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor

from core.web.races_listener import RacesListener
from core.xmpp.messages import Message
from helpers.browser import open_url as open_url_in_browser
from helpers.deferred import call_later
from helpers.system.input_activity import activity_detected
from helpers.translate import tr
from ui.notification.popup_manager import popup_manager, show_notification


class ChatCompetitionsMixin:
    """ChatWindow: live competition tracking, chips and alerts."""

    HISTORY_SETTLE_MS = 400  # idle gap after the last initial-history message before it's considered fully loaded

    def open_latest_competition_in_browser(self):
        """Open the latest live competition race URL (already stored on announce)."""
        if not self.competition_live:
            return
        game_id = self.competition_focus_game_id
        if game_id not in self.competition_live:
            game_id = max(self.competition_live.keys())
        url = (self.competition_live.get(game_id) or {}).get("url")
        if not url:
            return
        try:
            open_url_in_browser(url, self.config.get("browser"))
        except Exception as e:
            print(f"Failed to open competition: {e}")
        self.on_competition_entered(game_id)

    def _forget_live_competition(self, game_id: int):
        """Drop bookkeeping for a competition no longer in play (started racing, or its
        message/notification was manually dismissed) so a reconnect can't restore it."""
        self.competition_live.pop(game_id, None)
        if self.competition_focus_game_id == game_id:
            self.competition_focus_game_id = None
        timer = self.competition_alert_timers.pop(game_id, None)
        if timer:
            timer.stop()
        self.competition_sound_repeat_timer.stop()

    def on_competition_entered(self, game_id: int):
        """competitions.remove_message_on_enter: instantly drop the chat message and close
        the matching notification for a competition just entered (link click or hotkey E).
        Also forgets it as live so a brief reconnect doesn't restore the dismissed message."""
        if not self.config.get("competitions", "remove_message_on_enter"):
            return
        mw = getattr(self, "messages_widget", None)
        if mw and hasattr(mw, "clear_competition_messages"):
            mw.clear_competition_messages(game_id)
        popup_manager.close_by_tag(f"competition:{game_id}")
        self._forget_live_competition(game_id)

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
            self.history_settle_timer.stop()
            self.competition_notified.clear()
            self.pending_competitions.clear()
            self.competition_log_lines.clear()
            self.competition_log_status.clear()
            self._remove_competition_messages()
            self.reset_competition_live_state()
            self._on_races_status("disconnected")

    def on_min_multiplier_changed(self, text: str):
        if self.races_listener:
            self.races_listener.set_min_multiplier(text)
        self._prune_competitions_by_filter()

    def _prune_competitions_by_filter(self):
        """Drop live competition messages that no longer pass the current min_multiplier."""
        if not self.races_listener:
            return
        to_remove = [
            game_id for game_id, live in self.competition_live.items()
            if not self.races_listener.passes_filter(live.get("mult") or "?")
        ]
        if not to_remove:
            return
        mw = getattr(self, "messages_widget", None)
        for game_id in to_remove:
            if mw and hasattr(mw, "clear_competition_messages"):
                mw.clear_competition_messages(game_id)
            self.competition_live.pop(game_id, None)
            self.competition_notified.discard(game_id)
            if self.competition_focus_game_id == game_id:
                self.competition_focus_game_id = None
            timer = self.competition_alert_timers.pop(game_id, None)
            if timer:
                timer.stop()
            popup_manager.close_by_tag(f"competition:{game_id}")
        if mw:
            self.scroll_to_bottom(mw.list_view)

    def reset_competition_live_state(self):
        self.competition_countdown_timer.stop()
        self.competition_sound_repeat_timer.stop()
        self.competition_live.clear()
        self.competition_focus_game_id = None
        for timer in self.competition_alert_timers.values():
            timer.stop()
        self.competition_alert_timers.clear()

    def _on_races_status(self, state: str):
        prev = getattr(self, "races_status", None)
        self.races_status = state
        sw = getattr(self, "settings_widget", None)
        if sw and hasattr(sw, "update_competitions_status"):
            enabled = self.config.get("competitions", "enabled") is not False
            sw.update_competitions_status(enabled, state)
        # log connection changes (skip duplicate)
        if state != prev:
            label = {
                "connecting": "connecting...",
                "connected": "connected",
                "disconnected": "disconnected / reconnecting...",
            }.get(state, state)
            self.append_competition_log(f"ws {label}")

    def _remove_competition_messages(self):
        mw = getattr(self, "messages_widget", None)
        if mw and hasattr(mw, "clear_competition_messages"):
            mw.clear_competition_messages()

    def _restore_competition_messages(self):
        """Restore chat rows for competitions still marked as live after reconnect."""
        mw = getattr(self, "messages_widget", None)
        if not mw or not hasattr(mw, "model"):
            return
        for game_id in list(self.competition_live.keys()):
            if mw.model.find_competition_message_row(game_id) is None:
                self._move_competition_message_to_end(game_id)

    @staticmethod
    def _competition_fields(info: dict) -> tuple:
        game_id = info.get("game_id")
        tag = f"competition:{game_id}" if game_id else None
        return game_id, info.get("multiplier") or "?", info.get("url") or "", tag

    def on_history_settled(self):
        self.chat_ready = True
        self._flush_pending_competitions()
        self._restore_competition_messages()
        self.start_mentions_digest_check()

    def _on_competition_found(self, info: dict):
        game_id, mult, url, tag = self._competition_fields(info)
        status = info.get("status") or "?"

        if self.competition_log_status.get(game_id) != status:
            self.competition_log_status[game_id] = status
            self.append_competition_log(f"{mult} #{game_id} {status}")

        if status == "racing":
            if tag:
                popup_manager.close_by_tag(tag)
            mw = getattr(self, "messages_widget", None)
            if mw and hasattr(mw, "clear_competition_messages"):
                mw.clear_competition_messages(game_id)
                # Scroll to bottom to show current chat after competition message is removed
                self.scroll_to_bottom(mw.list_view)
            self._forget_live_competition(game_id)
            return

        # chat + notification only for waiting (once)
        if status != "waiting":
            return

        if game_id in self.competition_notified:
            return
        self.competition_notified.add(game_id)
        if len(self.competition_notified) > 200:
            self.competition_notified = set(list(self.competition_notified)[-100:])

        # queue until history has settled at least once, so it can't land ahead of loaded messages
        if not self.chat_ready or self.initial_roster_loading or self.history_settle_timer.isActive():
            self.pending_competitions.append(info)
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
        scores=None,
        bonuses=None,
    ) -> str:
        parts = [mult]

        show_cost = self.config.get("competitions", "show_cost")
        if show_cost is not False and cost is not None:
            parts.append(f"💵 [COST]{cost}[/COST]")

        show_scores = self.config.get("competitions", "show_scores")
        if show_scores is not False:
            score_text = scores if scores is not None else "—"
            parts.append(f"💰 [SCORE]{score_text}[/SCORE]")

        show_bonuses = self.config.get("competitions", "show_bonuses")
        if show_bonuses is not False:
            bonus_text = bonuses if bonuses is not None else "—"
            parts.append(f"💎 [BONUS]{bonus_text}[/BONUS]")

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

    def _competition_chips_and_header(self, mult: str, url: str, begintime, players: list, cost=None, scores=None, bonuses=None):
        """Build player chips + formatted header from raw competition fields."""
        chips = self._player_chips(players)
        shown = None if not chips else sum(1 for c in chips if c.get("name") != "…")
        header = self._format_competition_header(
            mult, url, begintime, len(players), shown, cost=cost, scores=scores, bonuses=bonuses
        )
        return chips, header

    def _make_competition_message(self, game_id: int, header: str, chips: list) -> "Message":
        """Build a local system chat message for a competition announcement/update."""
        msg = Message(
            from_jid="", body=header, msg_type="groupchat",
            login="Система", timestamp=datetime.now(),
        )
        msg.is_competition = True
        msg.competition_game_id = game_id
        msg.competition_players = chips
        return msg

    def _announce_competition(self, info: dict):
        game_id, mult, url, tag = self._competition_fields(info)
        begintime = info.get("begintime")
        cost = info.get("competition_cost")
        players = info.get("players") or []
        self.competition_live[game_id] = {
            "mult": mult, "url": url, "begintime": begintime,
            "players": players, "cost": cost,
        }
        chips, header = self._competition_chips_and_header(mult, url, begintime, players, cost=cost)
        try:
            msg = self._make_competition_message(game_id, header, chips)
            self.add_local_message(msg)
        except Exception as e:
            print(f"[races] local message error: {e}")

        if not self.competition_countdown_timer.isActive():
            self._start_competition_countdown_timer()

        self._schedule_competition_alert(game_id, mult, url, tag, begintime)
        self.fetch_own_balance(game_id)

    def _start_competition_countdown_timer(self):
        """Align ticks to wall-clock second boundaries so the countdown doesn't lag behind real time."""
        self.competition_countdown_timer.setInterval(1000)
        ms_to_next_second = 1000 - (int(datetime.now().timestamp() * 1000) % 1000)

        def _aligned_start():
            self.tick_competition_countdowns()
            self.competition_countdown_timer.start()

        call_later(self, ms_to_next_second, _aligned_start)

    def refresh_competition_player_display(self):
        for game_id in list(self.competition_live.keys()):
            self.refresh_competition_message(game_id)

    def on_show_balance_toggled_ui(self):
        for game_id, live in self.competition_live.items():
            need_scores = self.config.get("competitions", "show_scores") is not False and "scores" not in live
            need_bonuses = self.config.get("competitions", "show_bonuses") is not False and "bonuses" not in live
            if need_scores or need_bonuses:
                self.fetch_own_balance(game_id)
        self.refresh_competition_player_display()

    def _on_competition_players_changed(self, game_id: int, players: list):
        live = self.competition_live.get(game_id)
        if live is None:
            return
        live["players"] = players
        self.refresh_competition_message(game_id)

    def tick_competition_countdowns(self):
        if not self.competition_live:
            self.competition_countdown_timer.stop()
            return
        for game_id in list(self.competition_live.keys()):
            self.refresh_competition_message(game_id)

    def _scroll_to_competition_message(self, game_id: int):
        """Scroll to competition message and keep it centered while chips grow (alert action)."""
        self.competition_focus_game_id = game_id
        mw = getattr(self, "messages_widget", None)
        if not mw or not hasattr(mw, "list_view") or not hasattr(mw, "model"):
            return
        row = mw.model.find_competition_message_row(game_id)
        if row is not None:
            self.scroll_to_row(mw.list_view, row, delay=50)

    def _move_competition_message_to_end(self, game_id: int):
        """Remove the competition message and re-append it at the bottom (alert action)."""
        live = self.competition_live.get(game_id)
        mw = getattr(self, "messages_widget", None)
        if live is None or not mw:
            return
        players = live.get("players") or []
        chips, header = self._competition_chips_and_header(
            live["mult"], live["url"], live.get("begintime"), players,
            cost=live.get("cost"), scores=live.get("scores"), bonuses=live.get("bonuses")
        )
        try:
            row = mw.model.find_competition_message_row(game_id)
            if row is not None and row == mw.model.rowCount() - 1:
                mw.update_competition_message(game_id, header, chips)
                return
            mw.clear_competition_messages(game_id)
            msg = self._make_competition_message(game_id, header, chips)
            self.add_local_message(msg)
            self.scroll_to_bottom(mw.list_view)
        except Exception as e:
            print(f"[races] move competition message error: {e}")

    def refresh_competition_message(self, game_id: int):
        live = self.competition_live.get(game_id)
        mw = getattr(self, "messages_widget", None)
        if live is None or not mw:
            return
        players = live.get("players") or []
        chips, header = self._competition_chips_and_header(
            live["mult"], live["url"], live.get("begintime"), players,
            cost=live.get("cost"), scores=live.get("scores"), bonuses=live.get("bonuses")
        )
        scroll_bar = mw.list_view.verticalScrollBar()
        at_bottom = (scroll_bar.maximum() - scroll_bar.value()) <= 100
        mw.update_competition_message(game_id, header, chips)
        if self.competition_focus_game_id == game_id:
            row = mw.model.find_competition_message_row(game_id)
            if row is not None:
                self.scroll_to_row(mw.list_view, row)
        elif at_bottom:
            self.scroll_to_bottom(mw.list_view, delay=0)

        popup = popup_manager.find_by_tag(f"competition:{game_id}")
        if popup:
            popup.update_message(header, chips)

    def _schedule_competition_alert(self, game_id: int, mult: str, url: str, tag: str, begintime):
        """Fire the popup/sound alert immediately, or delayed to `alert_lead_seconds` before start."""
        lead = int(self.config.get("competitions", "alert_lead_seconds") or 0)
        delay = max(0, int(begintime - datetime.now().timestamp()) - lead) if begintime and lead else 0

        def fire():
            self.competition_alert_timers.pop(game_id, None)
            self._fire_competition_alert(game_id, mult, url, tag)

        if delay <= 0:
            fire()
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(fire)
        timer.start(delay * 1000)
        self.competition_alert_timers[game_id] = timer

    def _within_notify_window(self) -> bool:
        if not self.config.get("competitions", "notify_window_enabled"):
            return True
        start = self.config.get("competitions", "notify_window_start")
        end = self.config.get("competitions", "notify_window_end")
        if start is None or end is None or start == end:
            return True
        hour = datetime.now().hour
        return start <= hour < end if start < end else hour >= start or hour < end

    def _fire_competition_alert(self, game_id: int, mult: str, url: str, tag: str):
        if not self._within_notify_window():
            return
        live = self.competition_live.get(game_id, {})
        players = live.get("players") or []
        chips, header = self._competition_chips_and_header(
            mult, url, live.get("begintime"), players, cost=live.get("cost")
        )

        play_competition_sound_always = self.config.get("sound", "play_competition_sound_always")
        if play_competition_sound_always is None:
            play_competition_sound_always = True
        if not self.isActiveWindow() or play_competition_sound_always:
            self.play_competition_sound()
            self._start_competition_sound_repeat()

        # Bring competition message into view (config: scroll | move)
        alert_action = self.config.get("competitions", "alert_chat_action") or "scroll"
        if alert_action == "move":
            self.competition_focus_game_id = None
            self._move_competition_message_to_end(game_id)
        else:
            self._scroll_to_competition_message(game_id)

        # Same rule as chat messages: notify only when window is not focused
        if not self.isActiveWindow():
            try:
                show_notification(
                    title=tr(f"Competition {mult}", f"Соревнование {mult}"),
                    message=header,
                    duration=10000,
                    config=self.config,
                    cache=getattr(self, "cache", None),
                    emoticon_manager=getattr(self, "emoticon_manager", None),
                    account=getattr(self, "account", None),
                    is_system=False,
                    is_competition=True,
                    window_show_callback=self.show_and_focus_window,
                    competition_game_id=game_id,
                    open_room_callback=lambda g: self.open_game_room_by_id(g, room_label="Competition"),
                    profile_callback=self.on_username_shift_click,
                    competition_entered_callback=self.on_competition_entered,
                    tag=tag,
                    players=chips,
                )
            except Exception as e:
                print(f"[races] notification error: {e}")

    def _start_competition_sound_repeat(self):
        """Repeat the competition sound until the user moves the mouse or presses a key."""
        self.competition_sound_repeat_timer.stop()
        if not self.config.get("sound", "competition_repeat_enabled"):
            return
        interval = int(self.config.get("sound", "competition_repeat_interval") or 15)
        if interval <= 0:
            return
        self.competition_sound_repeat_cursor_pos = QCursor.pos()
        self.competition_sound_repeat_timer.start(interval * 1000)

    def on_competition_sound_repeat_tick(self):
        # Always stop on mouse or keyboard — user noticed the alert.
        if activity_detected(self.competition_sound_repeat_cursor_pos, "mouse_keyboard"):
            self.competition_sound_repeat_timer.stop()
            return
        self.play_competition_sound()

    def _flush_pending_competitions(self):
        pending = self.pending_competitions
        self.pending_competitions = []
        for info in pending:
            self._announce_competition(info)

    def append_competition_log(self, line: str):
        entry = f"{datetime.now().strftime('%H:%M:%S')}  {line}"
        self.competition_log_lines.append(entry)
        if len(self.competition_log_lines) > 200:
            self.competition_log_lines = self.competition_log_lines[-200:]
        sw = getattr(self, "settings_widget", None)
        if (
            sw
            and hasattr(sw, "append_competition_log")
            and self.config.get("competitions", "enabled") is not False
        ):
            sw.append_competition_log(entry)

    def clear_competition_log(self):
        self.competition_log_lines.clear()
        self.competition_log_status.clear()

    def sync_competitions_settings_ui(self):
        """Restore full session log + indicator into settings."""
        sw = getattr(self, "settings_widget", None)
        if not sw:
            return
        enabled = self.config.get("competitions", "enabled") is not False
        status = getattr(self, "races_status", "disconnected")
        sw.update_competitions_status(enabled, status if enabled else None)
        if not hasattr(sw, "competitions_log"):
            return
        if enabled:
            sw.competitions_log.setEnabled(True)
            if hasattr(sw, "set_competition_log_lines"):
                sw.set_competition_log_lines(list(self.competition_log_lines))

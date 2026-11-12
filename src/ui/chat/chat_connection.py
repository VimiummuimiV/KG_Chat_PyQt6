"""ChatWindow: XMPP connection, reconnect and system resume."""

import threading

from PyQt6.QtCore import QTimer

from components.toast import show_toast, ToastKind
from core.xmpp.client import XMPPClient
from helpers.translate import tr
from ui.notification.popup_manager import show_notification


class ChatConnectionMixin:
    """ChatWindow: XMPP connection, reconnect and system resume."""

    def disable_reconnect(self):
        """Disable auto-reconnect (called when switching accounts)"""
        self.allow_reconnect = False
        self._cancel_reconnect_timer()

    def _clear_for_reconnect(self):
        """Clear messages and userlist for fresh reconnection"""
        # Clear all messages to avoid duplicates (server will send last 20 again)
        self.messages_widget.clear()
        if self.presence_log_widget:
            self.presence_log_widget.clear()

        # History is being reloaded from scratch - hold competitions back until it settles again
        self.chat_ready = False
        self.history_settle_timer.stop()

        # Clear userlist completely (will rebuild from fresh roster)
        if hasattr(self.user_list_widget, 'clear_all'):
            self.user_list_widget.clear_all()

        # Exit private mode if active
        if self.private_mode:
            self.exit_private_mode()

        if self.game_rooms:
            for game_id in list(self.game_rooms.keys()):
                self.close_game_room_tab(game_id)
        if self.custom_rooms:
            for name in list(self.custom_rooms.keys()):
                self.close_custom_room_tab(name)

    def _is_connected(self):
        """Check if XMPP client is connected"""
        return self.xmpp_client and hasattr(self.xmpp_client, 'sid') and self.xmpp_client.sid

    def connect_xmpp(self):
        self.connect_generation += 1
        my_generation = self.connect_generation

        def _worker():
            self.is_connecting = True
            # Local reference so a stale/superseded worker can't stomp on a newer
            # attempt's self.xmpp_client when it finally unblocks and unwinds late.
            client = XMPPClient(str(self.config_path))

            def is_current():
                return self.connect_generation == my_generation

            try:
                # Clear old state before reconnecting
                QTimer.singleShot(0, self._clear_for_reconnect)

                if not client.connect(self.account):
                    if is_current():
                        self.xmpp_client = client
                        self.dispatch.emit(lambda: show_notification(
                            title=tr("Connection Failed", "Ошибка подключения"),
                            message=tr("Could not connect to XMPP server", "Не удалось подключиться к серверу XMPP"),
                            config=self.config,
                            emoticon_manager=self.emoticon_manager,
                            account=self.account
                        ))
                        self.signal_emitter.connection_changed.emit('offline')
                    return

                client.set_message_callback(self.message_callback)
                client.set_presence_callback(self._presence_callback)

                self.initial_roster_loading = True
                rooms = client.account_manager.get_rooms()
                for room in rooms:
                    if room.get('auto_join'):
                        try:
                            client.join_room(room['jid'])
                        except Exception:
                            pass

                self.initial_roster_loading = False

                if not is_current():
                    # A newer attempt already took over; drop this one quietly.
                    try:
                        client.disconnect()
                    except Exception:
                        pass
                    return

                self.xmpp_client = client
                self.signal_emitter.bulk_update_complete.emit()
                self.signal_emitter.connection_changed.emit('online')

                listen_thread = threading.Thread(target=client.listen, daemon=True)
                listen_thread.start()
                listen_thread.join()

                # Connection ended - clear sid to allow reconnection
                client.sid = None
                client.jid = None

                if is_current():
                    self.signal_emitter.connection_changed.emit('offline')
            except Exception as e:
                error_text = str(e)
                # Clear sid on error too
                client.sid = None
                client.jid = None

                if is_current():
                    self.xmpp_client = client
                    self.dispatch.emit(lambda: show_notification(
                        title=tr("Error", "Ошибка"),
                        message=tr(f"Connection error: {error_text}", f"Ошибка подключения: {error_text}"),
                        config=self.config,
                        emoticon_manager=self.emoticon_manager,
                        account=self.account
                    ))
                    self.signal_emitter.connection_changed.emit('offline')
            finally:
                # A forced abort (e.g. system resume) may have already started a
                # newer attempt; don't clear its in-progress flag when we unwind late.
                if is_current():
                    self.is_connecting = False

        threading.Thread(target=_worker, daemon=True).start()

    def message_callback(self, msg):
        self.signal_emitter.message_received.emit(msg)

    def _presence_callback(self, pres):
        self.signal_emitter.presence_received.emit(pres)

    def update_connection_title(self):
        text = {
            'connecting': tr("Connecting", "Подключение"),
            'online': tr("Online", "В сети"),
        }.get(self.connection_status, tr("Offline", "Не в сети"))
        base = f"{tr('Chat', 'Чат')} - {self.my_username}" if self.my_username else tr('Chat', 'Чат')

        # Preserve private mode in title
        if self.private_mode and self.private_chat_username:
            self.setWindowTitle(f"{base} - {tr('Private with', 'Приватно с')} {self.private_chat_username} - {text}")
        else:
            self.setWindowTitle(f"{base} - {text}")

    def set_connection_status(self, status: str):
        status = (status or '').lower()
        previous_status = getattr(self, 'connection_status', None)
        self.connection_status = status
        self.update_connection_title()

        # Reset on success
        if status == 'online':
            if status != previous_status:
                show_toast(self, tr("Connected", "Подключено"), ToastKind.SUCCESS)
            self.reconnect_count = 0
            if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'reconnect_button'):
                self.button_panel.reconnect_button.setVisible(False)

        # Only trigger auto-reconnect on offline status
        elif status == 'offline':
            if getattr(self, 'really_close', False):
                return

            if previous_status == 'online':  # not on every failed retry
                show_toast(self, tr("Connection lost", "Соединение потеряно"), ToastKind.ERROR)

            # Show manual reconnect button immediately
            if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'reconnect_button'):
                self.button_panel.reconnect_button.setVisible(True)

            if self.allow_reconnect and not self.is_connecting and self.account:
                print("🔄 Connection lost - initiating auto-reconnect...")
                QTimer.singleShot(100, self._auto_reconnect)

    def _cancel_reconnect_timer(self):
        """Stop and drop any pending scheduled reconnect attempt"""
        if self.reconnect_timer is not None:
            try:
                self.reconnect_timer.stop()
            except Exception:
                pass
            self.reconnect_timer = None

    def _schedule_reconnect(self, delay_ms: int):
        self._cancel_reconnect_timer()
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self._run_scheduled_reconnect)
        self.reconnect_timer.start(delay_ms)

    def _run_scheduled_reconnect(self):
        self.reconnect_timer = None
        if self.allow_reconnect and not self.is_connecting and not self._is_connected():
            self.set_connection_status('connecting')
            self.connect_xmpp()

    def _auto_reconnect(self):
        """Auto-reconnect with exponential backoff, capped at 60s but never giving up.

        Network can take much longer than a few minutes to come back after a long
        sleep (Wi-Fi re-association, DHCP renewal, driver reset, etc.), so attempts
        must keep retrying at the max delay instead of stopping after a fixed count.
        """
        if not self.allow_reconnect or self.is_connecting or self._is_connected() or not self.account:
            return

        self.reconnect_count += 1
        delay = min(2 ** (self.reconnect_count - 1), 60)

        print(f"🔄 Auto-reconnect attempt {self.reconnect_count} in {delay}s...")
        self._schedule_reconnect(delay * 1000)

    def manual_reconnect(self):
        """Manual reconnect - cancels auto-reconnect and resets counter"""
        self._cancel_reconnect_timer()
        self.reconnect_count = 0

        if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'reconnect_button'):
            self.button_panel.reconnect_button.setVisible(False)

        print("🔄 Manual reconnection (auto-reconnect cancelled)...")
        show_toast(self, tr("Reconnecting…", "Переподключение…"), ToastKind.INFO)
        self.set_connection_status('connecting')
        self.connect_xmpp()

    def handle_system_resume(self):
        """Called when the OS wakes from sleep: kill stale sockets and reconnect promptly"""
        if not self.allow_reconnect or getattr(self, 'really_close', False) or not self.account:
            return

        print("🔄 System resumed - forcing reconnect...")
        self.reconnect_count = 0

        if self.xmpp_client:
            try:
                self.xmpp_client.abort()
            except Exception:
                pass

        # abort() leaves the old long-poll read blocked up to 70s: bump the generation so the new attempt isn't held up
        self.connect_generation += 1
        self.is_connecting = False

        if self.races_listener:
            try:
                self.races_listener.reconnect()
            except Exception:
                pass

        self.set_connection_status('connecting')
        self._schedule_reconnect(500)

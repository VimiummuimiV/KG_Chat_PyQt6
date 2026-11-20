"""ChatWindow: the draft in the input field and the delivery state of sent messages."""

import threading
import time
from datetime import datetime

from PyQt6.QtCore import QTimer

from components.toast import show_toast, ToastKind
from core.state.input_drafts import InputDrafts
from core.xmpp.delivery import DELIVERED, DeliveryTracker, FAILED, is_marker_enabled, PENDING, QUEUED
from core.xmpp.history_replay import CLOCK_TOLERANCE
from helpers.deferred import call_later
from helpers.translate import tr


CHUNK_SEND_DELAY_SECONDS = 0.8  # between the chunks of one long message, so the server keeps their order
_QUEUE_MAX_AGE_SECONDS = 600  # an older queued message is stale; it goes to the input field for the user to decide
_DRAFT_SAVE_DELAY_MS = 400
_DELIVERY_TIMEOUT_MS = 15000  # a delivered groupchat message is echoed by the server well within this time


class ChatDeliveryMixin:
    """ChatWindow: nothing typed or sent is lost, and own messages show whether the server got them."""

    def setup_delivery(self):
        self.delivery_tracker = DeliveryTracker()
        self.input_drafts = InputDrafts()
        self._given_back_ids = set()  # failed messages returned to the input, in case the server still turns out to have them
        for entry in self.input_drafts.queued(self.my_username):  # the queue outlives the chat window
            self.delivery_tracker.restore_queued(entry["text"], entry["at"])
        self.connection_banner.set_queued(len(self.delivery_tracker.queued()))
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(_DRAFT_SAVE_DELAY_MS)
        self._draft_timer.timeout.connect(self.save_draft)
        self.input_field.textChanged.connect(lambda _text: self._draft_timer.start())
        restored_text = self.input_drafts.restorable_text(self.my_username)
        if restored_text and not self.input_field.text():
            self.input_field.setText(restored_text)
            self.save_draft()  # the text is safe as the draft before the unsent entries are dropped
            self.input_drafts.clear_unsent(self.my_username)

    def save_draft(self):
        self.input_drafts.set_draft(self.my_username, self.input_field.text())

    def message_widgets(self) -> list:
        """The message list of the general chat and of every open room."""
        return [self.messages_widget, *(room.messages_widget for room in self.all_room_widgets())]

    def apply_delivery_marker_setting(self):
        enabled = is_marker_enabled(self.config)
        for widget in self.message_widgets():
            widget.set_show_delivery_marker(enabled)

    def track_outgoing(self, target_jid, body: str, msg_type: str) -> int:
        """Follow a message about to be sent; it stays stored (unsent, or queued) until the server has it."""
        self.input_drafts.add_unsent(self.my_username, body)
        return self.delivery_tracker.register(target_jid, body, msg_type)

    def start_tracked_send(self, delay_seconds: float, body: str, target_jid, msg_type: str, delivery_id: int):
        """Send a tracked chunk from a timer thread after the delay."""
        threading.Timer(delay_seconds, self.send_tracked_chunk, args=(body, target_jid, msg_type, delivery_id)).start()

    def note_replayed(self, timestamp: datetime):
        """The oldest message of the history replayed on connect tells how far back the server's history reaches."""
        if self.replay_oldest is None or timestamp < self.replay_oldest:
            self.replay_oldest = timestamp

    def send_queued(self):
        """Send the queued messages once the connection is back and the server's history has been seen.

        The history comes first on purpose: a message the server did get is echoed in it and is never sent again.
        """
        if self.connection_status != 'online':
            return
        sent = 0
        for delivery_id, target_jid, body, msg_type, queued_at in self.delivery_tracker.queued():
            if not self._is_safe_to_send_again(queued_at):
                self._apply_delivery_changes(self.delivery_tracker.fail_queued(delivery_id))  # back to the input field
                continue
            changes = self.delivery_tracker.restart(delivery_id)
            has_row = self.messages_widget.set_delivery(delivery_id, PENDING)
            self._apply_delivery_changes(changes)
            if not has_row:  # queued before the chat was closed: its row is gone
                self.add_local_echo(body, msg_type, delivery_id, self.messages_widget.add_message)
            self.start_tracked_send(sent * CHUNK_SEND_DELAY_SECONDS, body, target_jid, msg_type, delivery_id)
            sent += 1
        if sent:
            show_toast(self, tr("Queued messages sent", "Сообщения из очереди отправлены"), ToastKind.INFO)

    def _is_safe_to_send_again(self, queued_at: float) -> bool:
        """Not stale, and the replayed history reaches back to when it was queued, so its absence there is proof."""
        if time.time() - queued_at > _QUEUE_MAX_AGE_SECONDS:
            return False
        return self.replay_oldest is None or self.replay_oldest <= datetime.fromtimestamp(queued_at) + CLOCK_TOLERANCE

    def send_tracked_chunk(self, body: str, target_jid, msg_type: str, delivery_id: int):
        """Runs on a timer thread: send, then report the outcome to the main thread."""
        client = self.xmpp_client
        is_accepted = bool(client) and client.send_message(body, target_jid, msg_type)
        self.dispatch.emit(lambda: self._on_request_finished(delivery_id, is_accepted))

    def confirm_own_echo(self, msg):
        """The server echoed one of our messages (live or replayed history)."""
        if msg.login and msg.login == self.my_username:
            self._apply_delivery_changes(self.delivery_tracker.echo_received(msg.from_jid, msg.body))

    def _on_request_finished(self, delivery_id: int, is_accepted: bool):
        self._apply_delivery_changes(self.delivery_tracker.request_finished(delivery_id, is_accepted))
        if is_accepted:
            call_later(
                self, _DELIVERY_TIMEOUT_MS,
                lambda: self._apply_delivery_changes(self.delivery_tracker.timed_out(delivery_id))
            )

    def _apply_delivery_changes(self, changes: list):
        for delivery_id, state in changes:
            body = self.delivery_tracker.body_of(delivery_id)
            for widget in self.message_widgets():
                widget.set_delivery(delivery_id, state)
            if state == DELIVERED:
                self.input_drafts.remove_unsent(self.my_username, body)
                self.input_drafts.remove_queued(self.my_username, body)
                if delivery_id in self._given_back_ids:
                    self._take_back_from_input(delivery_id, body)
            elif state == QUEUED:
                self.input_drafts.remove_unsent(self.my_username, body)
                self.input_drafts.add_queued(self.my_username, body, self.delivery_tracker.queued_at_of(delivery_id))
                call_later(self, _DELIVERY_TIMEOUT_MS, self.send_queued)  # online: no echo by then means it was missed
            elif state == PENDING:  # sent again from the queue: unconfirmed until its echo
                self.input_drafts.remove_queued(self.my_username, body)
                self.input_drafts.add_unsent(self.my_username, body)
            elif state == FAILED:
                self._give_back_to_input(delivery_id, body)
        self.connection_banner.set_queued(len(self.delivery_tracker.queued()))

    def _give_back_to_input(self, delivery_id: int, body: str):
        """Put a message the server did not get back into the input field so it can be sent again."""
        if delivery_id in self._given_back_ids:  # a resend failed again: the text is still in the input field
            return
        self._given_back_ids.add(delivery_id)
        self.input_field.setText(f"{self.input_field.text()} {body}".strip())
        self.input_drafts.remove_unsent(self.my_username, body)  # it is the draft now; keeping both would restore it twice
        self.input_drafts.remove_queued(self.my_username, body)
        self.save_draft()

    def _take_back_from_input(self, delivery_id: int, body: str):
        """A message given back as failed was delivered after all (late echo): remove it from the input field."""
        self._given_back_ids.discard(delivery_id)
        text = self.input_field.text()
        if body in text:
            self.input_field.setText(text.replace(body, "", 1).strip())
            self.save_draft()

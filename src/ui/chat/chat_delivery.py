"""ChatWindow: the draft in the input field, the delivery state of sent messages, and the queue for a lost connection."""

import threading
import time
from datetime import datetime

from PyQt6.QtCore import QTimer

from components.toast import show_toast, ToastKind
from core.state.input_drafts import InputDrafts
from core.state.message_outbox import MessageOutbox
from core.xmpp.delivery import (
    DELIVERED, DELIVERED_MARKER_LIFETIME_MS, DeliveryTracker, FAILED, is_marker_enabled, PENDING, queue_max_age_seconds,
    QUEUED, QueuedMessage, SETTLED,
)
from core.xmpp.history_replay import CLOCK_TOLERANCE
from helpers.dates import now_seconds
from helpers.deferred import call_later
from helpers.translate import tr


SEND_INTERVAL_SECONDS = 1.0  # the least pause between two messages: a server may take faster ones for flooding and drop them
_DRAFT_SAVE_DELAY_MS = 400
_DELIVERY_TIMEOUT_MS = 15000  # a delivered groupchat message is echoed by the server well within this time


class ChatDeliveryMixin:
    """ChatWindow: nothing typed or sent is lost, and own messages show whether the server got them."""

    def setup_delivery(self):
        self.delivery_tracker = DeliveryTracker()
        self.input_drafts = InputDrafts()
        self.message_outbox = MessageOutbox()
        self._next_send_at = 0.0  # when the next message may be sent, on the monotonic clock
        self._given_back_ids = set()  # failed messages returned to the input, in case the server still turns out to have them
        for entry in self.message_outbox.queued(self.my_username):  # the queue outlives the chat window
            self.delivery_tracker.restore_queued(entry["text"], entry["at"], entry["certain"])
        self.connection_banner.set_queued(len(self.delivery_tracker.queued()))
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(_DRAFT_SAVE_DELAY_MS)
        self._draft_timer.timeout.connect(self.save_draft)
        self.input_field.textChanged.connect(lambda _text: self._draft_timer.start())
        restored_text = " ".join(
            [*self.message_outbox.unconfirmed(self.my_username), self.input_drafts.draft(self.my_username)]
        ).strip()
        if restored_text and not self.input_field.text():
            self.input_field.setText(restored_text)
            self.save_draft()  # the text is safe as the draft before the unconfirmed entries are dropped
            self.message_outbox.clear_unconfirmed(self.my_username)

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
        """Follow a message about to be sent; it stays stored (unconfirmed, or queued) until the server has it."""
        self.message_outbox.add_unconfirmed(self.my_username, body)
        return self.delivery_tracker.register(target_jid, body, msg_type)

    def start_tracked_send(self, body: str, target_jid, msg_type: str, delivery_id: int):
        """Send a tracked chunk from a timer thread, at least SEND_INTERVAL_SECONDS after the one sent before it."""
        now = time.monotonic()
        send_at = max(now, self._next_send_at)
        self._next_send_at = send_at + SEND_INTERVAL_SECONDS
        threading.Timer(send_at - now, self.send_tracked_chunk, args=(body, target_jid, msg_type, delivery_id)).start()

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
        for message in self.delivery_tracker.queued():
            if not self._is_safe_to_send_again(message):
                self._apply_delivery_changes(self.delivery_tracker.fail_queued(message.delivery_id))  # back to the input field
                continue
            changes = self.delivery_tracker.restart(message.delivery_id)
            has_row = self.messages_widget.set_delivery(message.delivery_id, PENDING)
            self._apply_delivery_changes(changes)
            if not has_row:  # queued before the chat was closed: its row is gone
                self.add_local_echo(message.body, message.msg_type, message.delivery_id, self.messages_widget.add_message)
            self.start_tracked_send(message.body, message.target_jid, message.msg_type, message.delivery_id)
            sent += 1
        if sent:
            show_toast(self, tr("Queued messages sent", "Сообщения из очереди отправлены"), ToastKind.INFO)

    def _is_safe_to_send_again(self, message: QueuedMessage) -> bool:
        """Within the time limit of the settings, and not possibly a duplicate.

        A message sent while the connection was down cannot be a duplicate. Any other has to be proven missing:
        the replayed history must reach back to when it was queued, and not show it.
        """
        max_age = queue_max_age_seconds(self.config)
        if max_age is not None and now_seconds() - message.queued_at > max_age:
            return False
        if message.is_certain or self.replay_oldest is None:
            return True
        return self.replay_oldest <= datetime.fromtimestamp(message.queued_at) + CLOCK_TOLERANCE

    def send_tracked_chunk(self, body: str, target_jid, msg_type: str, delivery_id: int):
        """Runs on a timer thread: send, then report the outcome to the main thread."""
        client = self.xmpp_client
        is_certain = not client or self.connection_status != 'online'  # then a failed request cannot have reached the server
        is_accepted = bool(client) and client.send_message(body, target_jid, msg_type)
        self.dispatch.emit(lambda: self._on_request_finished(delivery_id, is_accepted, is_certain))

    def confirm_own_echo(self, msg):
        """The server echoed one of our messages (live or replayed history)."""
        if msg.login and msg.login == self.my_username:
            self._apply_delivery_changes(self.delivery_tracker.echo_received(msg.from_jid, msg.body))

    def _on_request_finished(self, delivery_id: int, is_accepted: bool, is_certain: bool):
        self._apply_delivery_changes(self.delivery_tracker.request_finished(delivery_id, is_accepted, is_certain))
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
                call_later(self, DELIVERED_MARKER_LIFETIME_MS, lambda delivery_id=delivery_id: self._settle_marker(delivery_id))
                self.message_outbox.remove_unconfirmed(self.my_username, body)
                self.message_outbox.remove_queued(self.my_username, body)
                if delivery_id in self._given_back_ids:
                    self._take_back_from_input(delivery_id, body)
            elif state == QUEUED:
                queued = self.delivery_tracker.queued_message(delivery_id)
                self.message_outbox.remove_unconfirmed(self.my_username, body)
                self.message_outbox.add_queued(self.my_username, body, queued.queued_at, queued.is_certain)
                call_later(self, _DELIVERY_TIMEOUT_MS, self.send_queued)  # online: no echo by then means it was missed
            elif state == PENDING:  # sent again from the queue: unconfirmed until its echo
                self.message_outbox.remove_queued(self.my_username, body)
                self.message_outbox.add_unconfirmed(self.my_username, body)
            elif state == FAILED:
                self._give_back_to_input(delivery_id, body)
        self.connection_banner.set_queued(len(self.delivery_tracker.queued()))

    def _settle_marker(self, delivery_id: int):
        """The delivered dot has had its time: it goes, and only a repaint of that row is needed."""
        for widget in self.message_widgets():
            widget.set_delivery(delivery_id, SETTLED)

    def _give_back_to_input(self, delivery_id: int, body: str):
        """Put a message the server did not get back into the input field so it can be sent again."""
        if delivery_id in self._given_back_ids:  # a resend failed again: the text is still in the input field
            return
        self._given_back_ids.add(delivery_id)
        self.input_field.setText(f"{self.input_field.text()} {body}".strip())
        self.message_outbox.remove_unconfirmed(self.my_username, body)  # it is the draft now; keeping both would restore it twice
        self.message_outbox.remove_queued(self.my_username, body)
        self.save_draft()

    def _take_back_from_input(self, delivery_id: int, body: str):
        """A message given back as failed was delivered after all (late echo): remove it from the input field."""
        self._given_back_ids.discard(delivery_id)
        text = self.input_field.text()
        if body in text:
            self.input_field.setText(text.replace(body, "", 1).strip())
            self.save_draft()

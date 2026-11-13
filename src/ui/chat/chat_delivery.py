"""ChatWindow: the draft in the input field and the delivery state of sent messages."""

from PyQt6.QtCore import QTimer

from core.state.input_drafts import InputDrafts
from core.xmpp.delivery import DELIVERED, DeliveryTracker, FAILED, is_marker_enabled
from helpers.deferred import call_later


_DRAFT_SAVE_DELAY_MS = 400
_DELIVERY_TIMEOUT_MS = 15000  # a delivered groupchat message is echoed by the server well within this time


class ChatDeliveryMixin:
    """ChatWindow: nothing typed or sent is lost, and own messages show whether the server got them."""

    def setup_delivery(self):
        self.delivery_tracker = DeliveryTracker()
        self.input_drafts = InputDrafts()
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
        """Follow a message about to be sent; it stays stored as unsent until the server has it."""
        self.input_drafts.add_unsent(self.my_username, body)
        return self.delivery_tracker.register(target_jid, body, is_echoed=(msg_type == 'groupchat'))

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
            elif state == FAILED:
                self._give_back_to_input(body)

    def _give_back_to_input(self, body: str):
        """Put a message the server did not get back into the input field so it can be sent again."""
        self.input_field.setText(f"{self.input_field.text()} {body}".strip())
        self.input_drafts.remove_unsent(self.my_username, body)  # it is the draft now; keeping both would restore it twice
        self.save_draft()

"""Follows own messages from sending to the server's echo."""

import time
from typing import Dict, List, Optional

from core.xmpp.jid_utils import bare_room_jid

PENDING = "pending"      # sent, the server has not echoed it yet
DELIVERED = "delivered"  # the server echoed it (private messages: accepted by the server)
FAILED = "failed"        # no echo came in time, or the message cannot be sent again by itself
QUEUED = "queued"        # the request failed: it waits for the connection and is sent again by itself


def is_marker_enabled(config) -> bool:
    """Whether own messages show their delivery marker; on unless switched off."""
    value = config.get("ui", "show_delivery_marker")
    return True if value is None else bool(value)


class _Outgoing:
    def __init__(self, target_jid: Optional[str], body: str, msg_type: str):
        self.target_jid = target_jid
        self.body = body
        self.msg_type = msg_type
        self.is_echoed = msg_type == "groupchat"
        self.state = PENDING
        self.queued_at = time.time()  # since when it waits for the connection; wall time, as the queue is stored on disk

    @property
    def is_queueable(self) -> bool:
        """Only the general chat is sent again by itself: rooms and private chats are left on reconnect."""
        return self.target_jid is None and self.msg_type == "groupchat"


class DeliveryTracker:
    """Delivery state of own messages; every method returns the (delivery_id, state) changes it made."""

    def __init__(self):
        self._outgoing: Dict[int, _Outgoing] = {}
        self._next_id = 1

    def register(self, target_jid: Optional[str], body: str, msg_type: str = "groupchat") -> int:
        """Track a message about to be sent; a private chat message gets no echo from the server."""
        delivery_id = self._next_id
        self._next_id += 1
        self._outgoing[delivery_id] = _Outgoing(target_jid, body.strip(), msg_type)
        return delivery_id

    def restore_queued(self, body: str, queued_at: float) -> int:
        """Track a queued message that was stored before the chat was closed."""
        delivery_id = self.register(None, body)
        self._outgoing[delivery_id].state = QUEUED
        self._outgoing[delivery_id].queued_at = queued_at
        return delivery_id

    def request_finished(self, delivery_id: int, is_accepted: bool) -> List[tuple]:
        """The send request ended: a failure queues or fails the message, an accepted one waits for its echo."""
        outgoing = self._outgoing.get(delivery_id)
        if outgoing is None or outgoing.state != PENDING:
            return []
        if not is_accepted:
            return self._change(delivery_id, QUEUED if outgoing.is_queueable else FAILED)
        if not outgoing.is_echoed:
            return self._change(delivery_id, DELIVERED)
        return []

    def echo_received(self, from_jid: str, body: str) -> List[tuple]:
        """Our own message came back from the server; the oldest waiting message with that text is delivered.

        A pending message wins over a queued or failed one with the same text: that one may be a resent duplicate.
        A queued message that is echoed was received by the server after all, so it is never sent again.
        """
        room_jid = bare_room_jid(from_jid)
        text = (body or "").strip()
        for wanted_state in (PENDING, QUEUED, FAILED):
            for delivery_id, outgoing in self._outgoing.items():
                if outgoing.state != wanted_state or not outgoing.is_echoed or outgoing.body != text:
                    continue
                if outgoing.target_jid is None or bare_room_jid(outgoing.target_jid) == room_jid:
                    return self._change(delivery_id, DELIVERED)
        return []

    def timed_out(self, delivery_id: int) -> List[tuple]:
        """No echo arrived in time."""
        outgoing = self._outgoing.get(delivery_id)
        if outgoing is None or outgoing.state != PENDING:
            return []
        return self._change(delivery_id, FAILED)

    def queued(self) -> List[tuple]:
        """(delivery_id, target_jid, body, msg_type, queued_at) of the messages waiting for the connection, oldest first."""
        return [
            (delivery_id, outgoing.target_jid, outgoing.body, outgoing.msg_type, outgoing.queued_at)
            for delivery_id, outgoing in self._outgoing.items() if outgoing.state == QUEUED
        ]

    def queued_at_of(self, delivery_id: int) -> float:
        return self._outgoing[delivery_id].queued_at

    def fail_queued(self, delivery_id: int) -> List[tuple]:
        """The queued message is not sent again by itself (too old, or the server's history cannot show it was missed)."""
        outgoing = self._outgoing.get(delivery_id)
        if outgoing is None or outgoing.state != QUEUED:
            return []
        return self._change(delivery_id, FAILED)

    def restart(self, delivery_id: int) -> List[tuple]:
        """The queued message is being sent again."""
        outgoing = self._outgoing.get(delivery_id)
        if outgoing is None or outgoing.state != QUEUED:
            return []
        return self._change(delivery_id, PENDING)

    def body_of(self, delivery_id: int) -> Optional[str]:
        outgoing = self._outgoing.get(delivery_id)
        return outgoing.body if outgoing else None

    def _change(self, delivery_id: int, state: str) -> List[tuple]:
        outgoing = self._outgoing[delivery_id]
        outgoing.state = state
        if state == QUEUED:
            outgoing.queued_at = time.time()
        return [(delivery_id, state)]

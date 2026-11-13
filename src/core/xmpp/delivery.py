"""Follows own messages from sending to the server's echo."""

from typing import Dict, List, Optional

from core.xmpp.jid_utils import bare_room_jid

PENDING = "pending"      # sent, the server has not echoed it yet
DELIVERED = "delivered"  # the server echoed it (private messages: accepted by the server)
FAILED = "failed"        # the request failed or no echo came in time


def is_marker_enabled(config) -> bool:
    """Whether own messages show their delivery marker; on unless switched off."""
    value = config.get("ui", "show_delivery_marker")
    return True if value is None else bool(value)


class _Outgoing:
    def __init__(self, target_jid: Optional[str], body: str, is_echoed: bool):
        self.target_jid = target_jid
        self.body = body
        self.is_echoed = is_echoed
        self.state = PENDING


class DeliveryTracker:
    """Delivery state of own messages; every method returns the (delivery_id, state) changes it made."""

    def __init__(self):
        self._outgoing: Dict[int, _Outgoing] = {}
        self._next_id = 1

    def register(self, target_jid: Optional[str], body: str, is_echoed: bool = True) -> int:
        """Track a message about to be sent; is_echoed is False where the server sends no echo (private chat)."""
        delivery_id = self._next_id
        self._next_id += 1
        self._outgoing[delivery_id] = _Outgoing(target_jid, body.strip(), is_echoed)
        return delivery_id

    def request_finished(self, delivery_id: int, is_accepted: bool) -> List[tuple]:
        """The send request ended: a failure fails the message, an accepted one waits for its echo."""
        outgoing = self._outgoing.get(delivery_id)
        if outgoing is None or outgoing.state != PENDING:
            return []
        if not is_accepted:
            return self._change(delivery_id, FAILED)
        if not outgoing.is_echoed:
            return self._change(delivery_id, DELIVERED)
        return []

    def echo_received(self, from_jid: str, body: str) -> List[tuple]:
        """Our own message came back from the server; the oldest waiting message with that text is delivered.

        A pending message wins over a failed one with the same text: the failed one may be a resent duplicate.
        """
        room_jid = bare_room_jid(from_jid)
        text = (body or "").strip()
        for wanted_state in (PENDING, FAILED):
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

    def body_of(self, delivery_id: int) -> Optional[str]:
        outgoing = self._outgoing.get(delivery_id)
        return outgoing.body if outgoing else None

    def _change(self, delivery_id: int, state: str) -> List[tuple]:
        self._outgoing[delivery_id].state = state
        return [(delivery_id, state)]

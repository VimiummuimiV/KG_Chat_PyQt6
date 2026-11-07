"""ChatWindow: composing and sending messages."""

import re
import threading
from datetime import datetime

from core.xmpp.messages import Message


class ChatInputMixin:
    """ChatWindow: composing and sending messages."""

    def send_message(self, text: str):
        if not self.xmpp_client:
            self.input_field.setText(text)  # keep what was typed while disconnected
            return

        # Determine message type and recipient
        if self.private_mode and self.private_chat_jid:
            msg_type = 'chat'
            recipient_jid = self.private_chat_jid
        else:
            msg_type = 'groupchat'
            recipient_jid = None

        self._dispatch_chat_message(text, msg_type, recipient_jid, self.messages_widget.add_message)

    def _own_message_mode(self) -> str:
        return self.config.get("ui", "own_message_mode") or "local"

    def _should_skip_own_echo(self, msg, is_initial: bool) -> bool:
        return (
            msg.login == self.my_username
            and not is_initial
            and self._own_message_mode() == "local"
        )

    def _dispatch_chat_message(self, text: str, msg_type: str, target_jid, add_message_fn):
        """Chunk `text`, optionally echo each chunk locally via add_message_fn,
        then send each chunk to target_jid on a staggered delay. Shared by the
        general chat's send_message and room tabs' _send_room_message so
        the two don't duplicate the chunk/echo/send dance."""
        # Get own user data
        own_user = None
        for user in self.xmpp_client.user_list.get_all():
            if (self.my_username and self.my_username in user.jid) or user.login == self.my_username:
                own_user = user
                break

        # Chunk message if over 300 characters
        chunks = self._chunk_message(text, 300)
        local_echo = self._own_message_mode() == "local"

        # Send each chunk
        for i, chunk in enumerate(chunks):
            if local_echo:
                own_msg = Message(
                    from_jid=self.xmpp_client.jid,
                    body=chunk,
                    msg_type=msg_type,
                    login=self.my_username,
                    avatar=None,
                    background=own_user.background if own_user else None,
                    timestamp=datetime.now(),
                    initial=False
                )
                own_msg.is_private = (msg_type == 'chat')
                add_message_fn(own_msg)

            delay = i * 0.8 # 800ms delay between chunks
            threading.Timer(
                delay,
                self.xmpp_client.send_message,
                args=(chunk, target_jid, msg_type)
            ).start()

    def _chunk_message(self, text: str, max_len: int) -> list:
        """Break message into chunks, keeping URLs intact"""
        if len(text) <= max_len:
            return [text]

        chunks = []
        url_pattern = re.compile(r'https?://[^\s]+')

        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break

            # Find a good break point
            chunk = text[:max_len]

            # Check if we're breaking a URL
            urls_in_chunk = list(url_pattern.finditer(chunk))
            if urls_in_chunk:
                last_url = urls_in_chunk[-1]
                # If URL extends beyond chunk, break before it
                if last_url.end() >= max_len - 10: # Give some buffer
                    # Check if there's content before the URL
                    if last_url.start() > 0:
                        chunk = text[:last_url.start()].rstrip()
                    else:
                        # URL at start, must include it even if long
                        chunk = text[:max_len]
            else:
                # Try to break at last space
                last_space = chunk.rfind(' ')
                if last_space > max_len * 0.7: # At least 70% filled
                    chunk = text[:last_space]

            chunks.append(chunk)
            text = text[len(chunk):].lstrip()

        return chunks

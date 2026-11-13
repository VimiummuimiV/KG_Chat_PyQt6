"""XMPP message and presence parsing"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from core.xmpp.jid_utils import extract_user_data_from_jid


@dataclass
class Message:
    """Parsed message"""
    from_jid: str
    body: str
    msg_type: str
    login: Optional[str] = None
    avatar: Optional[str] = None
    background: Optional[str] = None
    timestamp: Optional[datetime] = None
    initial: bool = False
    delivery_id: Optional[int] = None  # set on own messages followed by DeliveryTracker
    delivery: Optional[str] = None

@dataclass
class _Presence:
    """Parsed presence"""
    from_jid: str
    presence_type: str
    login: Optional[str] = None
    user_id: Optional[str] = None
    avatar: Optional[str] = None
    background: Optional[str] = None
    game_id: Optional[str] = None
    affiliation: str = 'none'
    role: str = 'participant'
    moderator: bool = False

class MessageParser:
    """Parse XMPP messages and presence"""

    @staticmethod
    def parse(xml_text: str) -> Tuple[List[Message], List[_Presence]]:
        """Parse XML response"""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return [], []

        messages = MessageParser._parse_messages(root)
        presence = MessageParser._parse_presence(root)

        return messages, presence

    @staticmethod
    def _parse_messages(root: ET.Element) -> List[Message]:
        """Parse messages"""
        messages = []
        ns = '{klavogonki:userdata}'  # FIX: Define namespace for child elements

        for msg in root.findall('.//{jabber:client}message'):
            from_jid = msg.get('from', '')
            msg_type = msg.get('type', 'chat')

            body_element = msg.find('{jabber:client}body')
            if body_element is None or not body_element.text:
                continue

            body = body_element.text
            login = None
            avatar = None
            background = None

            # Try to get user data from klavogonki:userdata
            userdata = msg.find('.//' + ns + 'user')
            if userdata is not None:
                login_element = userdata.find(ns + 'login')  # FIX: Use namespace
                if login_element is not None and login_element.text:
                    login = login_element.text

                avatar_element = userdata.find(ns + 'avatar')  # FIX: Use namespace
                if avatar_element is not None and avatar_element.text:
                    avatar = avatar_element.text

                background_element = userdata.find(ns + 'background')  # FIX: Use namespace
                if background_element is not None and background_element.text:
                    background = background_element.text

            # If login still not found, extract from JID using helper
            if not login and from_jid:
                _, jid_login = extract_user_data_from_jid(from_jid)
                if jid_login:
                    login = jid_login

            # Parse timestamp with timezone conversion
            timestamp = None
            delay_element = msg.find('.//{urn:xmpp:delay}delay')
            if delay_element is not None:
                stamp = delay_element.get('stamp')
                if stamp:
                    try:
                        # Parse UTC timestamp and convert to local timezone
                        timestamp = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                        timestamp = timestamp.astimezone()  # Convert to local time
                        timestamp = timestamp.replace(tzinfo=None)  # Remove timezone info
                    except Exception:
                        pass

            if not timestamp:
                timestamp = datetime.now()

            messages.append(Message(
                from_jid=from_jid,
                body=body,
                msg_type=msg_type,
                login=login,
                avatar=avatar,
                background=background,
                timestamp=timestamp
            ))

        return messages

    @staticmethod
    def _parse_presence(root: ET.Element) -> List[_Presence]:
        """Parse presence"""
        presence_list = []
        ns = '{klavogonki:userdata}'  # FIX: Define namespace for child elements

        for pres in root.findall('.//{jabber:client}presence'):
            from_jid = pres.get('from', '')
            ptype = pres.get('type', 'available')

            login = None
            user_id = None
            avatar = None
            background = None
            game_id = None
            moderator = False

            userdata = pres.find('.//' + ns + 'user')
            if userdata is not None:
                login_element = userdata.find(ns + 'login')
                if login_element is not None:
                    login = login_element.text

                avatar_element = userdata.find(ns + 'avatar')
                if avatar_element is not None:
                    avatar = avatar_element.text

                background_element = userdata.find(ns + 'background')
                if background_element is not None:
                    background = background_element.text

                # Parse moderator tag
                moderator_element = userdata.find(ns + 'moderator')
                if moderator_element is not None:
                    moderator = moderator_element.text == '1'

            game_element = pres.find('.//' + ns + 'game_id')
            if game_element is not None:
                game_id = game_element.text

            affiliation = 'none'
            role = 'participant'

            muc_item = pres.find('.//{http://jabber.org/protocol/muc#user}item')
            if muc_item is not None:
                affiliation = muc_item.get('affiliation', 'none')
                role = muc_item.get('role', 'participant')

            # Extract user_id and login from JID using helper
            if not user_id:
                user_id, _ = extract_user_data_from_jid(from_jid)

            if not login and from_jid:
                _, jid_login = extract_user_data_from_jid(from_jid)
                if jid_login:
                    login = jid_login

            presence_list.append(_Presence(
                from_jid=from_jid,
                presence_type=ptype,
                login=login,
                user_id=user_id,
                avatar=avatar,
                background=background,
                game_id=game_id,
                affiliation=affiliation,
                role=role,
                moderator=moderator
            ))

        return presence_list

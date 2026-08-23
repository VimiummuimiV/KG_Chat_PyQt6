"""JID helper utilities"""
from typing import Optional, Tuple

MUC_DOMAIN = "conference.jabber.klavogonki.ru"


def extract_user_data_from_jid(jid: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract (user_id, login) from a JID resource.

    Returns a tuple (user_id, login) where either element may be None
    if not present in the provided JID.

    Expected resource examples:
      - room@domain/user_id#login  -> (user_id, login)
      - room@domain/login          -> (None, login)
      - None or unexpected format  -> (None, None)
    """
    if not jid:
        return None, None

    try:
        resource = jid.split('/')[-1]
        if '#' in resource:
            parts = resource.split('#')
            if len(parts) >= 2:
                return parts[0], parts[1].split('/')[0]
        # Fallback: resource may be login only
        if resource:
            return None, resource.split('/')[0]
    except Exception:
        pass

    return None, None


def bare_room_jid(from_jid: Optional[str]) -> str:
    """The room part of a stanza's from_jid, with any /resource stripped."""
    return (from_jid or "").split('/')[0]


def is_from_game_room(from_jid: Optional[str]) -> bool:
    """True if from_jid belongs to a gameXXXX@conference room."""
    bare = bare_room_jid(from_jid)
    return bare.startswith('game') and MUC_DOMAIN in bare


def game_id_from_jid(from_jid: Optional[str]) -> Optional[int]:
    """The numeric game_id from a gameXXXX@conference room's jid, or None
    if from_jid isn't a game room."""
    try:
        local = bare_room_jid(from_jid).split('@')[0]
        if local.startswith('game'):
            return int(local[4:])
    except Exception:
        pass
    return None


def custom_room_name_from_jid(from_jid: Optional[str]) -> Optional[str]:
    """The room name from a custom (non-game, non-general) MUC room's jid,
    or None if from_jid isn't a custom room."""
    bare = bare_room_jid(from_jid)
    if MUC_DOMAIN not in bare:
        return None
    local = bare.split('@')[0]
    if local.startswith('game') or local == 'general':
        return None
    return local
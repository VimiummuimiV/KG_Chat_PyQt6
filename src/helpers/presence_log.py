"""Helpers for the rolling JOIN/LEFT/GAME chat summary."""
from typing import List
from components.presence_badge import presence_badge_style, EVENT_TYPES


def add_presence_entry(entries: List[dict], login: str, event_type: str) -> List[dict]:
    if not login or event_type not in EVENT_TYPES:
        return entries
    for entry in entries:
        if entry['login'] == login:
            entry['counts'][event_type] = entry['counts'].get(event_type, 0) + 1
            entry['last'] = event_type
            return entries
    entries.append({
        'login': login,
        'counts': {event_type: 1},
        'last': event_type,
    })
    return entries


def presence_entries_to_text(entries: List[dict]) -> str:
    parts = []
    for entry in entries:
        last = entry.get('last')
        badges = ' '.join(
            (
                f"[{presence_badge_style(et)[0]}{'●' if et == last else ''}]"
                if entry['counts'][et] == 1
                else f"[{presence_badge_style(et)[0]} {entry['counts'][et]}{'●' if et == last else ''}]"
            )
            for et in EVENT_TYPES if entry['counts'].get(et)
        )
        parts.append(f"{entry['login']} {badges}".strip())
    return ' · '.join(parts)
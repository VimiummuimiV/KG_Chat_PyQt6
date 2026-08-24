"""Helpers for the rolling JOIN/LEFT/GAME chat summary."""
from typing import List
from components.presence_badge import presence_badge_style, EVENT_TYPES


def add_presence_entry(entries: List[dict], login: str, event_type: str) -> List[dict]:
    for entry in entries:
        if entry['login'] == login:
            entry['counts'][event_type] = entry['counts'].get(event_type, 0) + 1
            return entries
    entries.append({'login': login, 'counts': {event_type: 1}})
    return entries


def presence_entries_to_text(entries: List[dict]) -> str:
    parts = []
    for entry in entries:
        badges = ' '.join(
            (
                f"[{presence_badge_style(et)[0]}]"
                if entry['counts'][et] == 1
                else f"[{presence_badge_style(et)[0]} {entry['counts'][et]}]"
            )
            for et in EVENT_TYPES if entry['counts'].get(et)
        )
        parts.append(f"{entry['login']} {badges}".strip())
    return ' · '.join(parts)

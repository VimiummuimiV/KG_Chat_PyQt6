import re
from typing import Iterable, List, Optional, Pattern, Tuple


MENTION_NICK = "nick"
MENTION_LOCAL = "local"
MENTION_GLOBAL = "global"
# Marks a matched alias in the text; the settings use the same icons for the alias sections
MENTION_ICONS = {MENTION_LOCAL: "🏷️", MENTION_GLOBAL: "🌐"}


def _keyword_pattern(keyword: str) -> str:
    """Escaped keyword where е and ё match each other."""
    return re.sub("[еёЕЁ]", "[её]", re.escape(keyword))


def compile_mention_pattern(username: str, local_aliases: Iterable[str], global_aliases: Iterable[str]) -> Optional[Pattern]:
    """Case-insensitive whole-word pattern; the matched group name tells the nick, a local and a global alias apart."""
    groups = []
    for kind, keywords in ((MENTION_NICK, [username]), (MENTION_LOCAL, local_aliases), (MENTION_GLOBAL, global_aliases)):
        patterns = [_keyword_pattern(keyword) for keyword in keywords if keyword]
        if patterns:
            groups.append(f"(?P<{kind}>" + "|".join(patterns) + ")")
    if not groups:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(groups) + r")(?!\w)", re.IGNORECASE)


def parse_mentions(text: str, pattern: Optional[Pattern]) -> List[Tuple[Optional[str], str]]:
    """Split text into (kind, text) segments; kind is a MENTION_* constant, or None for plain text."""
    if not pattern or not text:
        return [(None, text)]

    segments = []
    last_end = 0
    for match in pattern.finditer(text):
        if match.start() > last_end:
            segments.append((None, text[last_end:match.start()]))
        segments.append((match.lastgroup, match.group()))
        last_end = match.end()
    if last_end < len(text):
        segments.append((None, text[last_end:]))
    return segments or [(None, text)]

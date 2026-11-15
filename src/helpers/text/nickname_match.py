"""Fuzzy nickname matching: a query matches a nick that contains its letters in the same order."""

import re
from typing import Optional, Pattern, Tuple

from helpers.text.mention_parser import fold_nickname, keyword_pattern


FUZZY_MIN_QUERY = 2  # a shorter query matches only the start of a nick


def fuzzy_pattern(folded_query: str) -> Pattern:
    """Pattern selecting every line of a newline-joined nick list that contains the query letters in order."""
    letters = ".*?".join(keyword_pattern(letter) for letter in folded_query)
    return re.compile(f"^.*?{letters}.*$", re.IGNORECASE | re.MULTILINE)


def _is_word_start(nick: str, index: int) -> bool:
    return index == 0 or not nick[index - 1].isalnum() or (nick[index].isupper() and nick[index - 1].islower())


def match_key(nick: str, folded_query: str) -> Optional[Tuple]:
    """Sort key of a nick for the query (smaller is better), or None when the letters are not in order.

    Order: prefix matches (alphabetical), then more matched letters on word starts (T W in TolikWorkaholic),
    then letters closer together, then shorter nicks.
    """
    folded = fold_nickname(nick)
    if folded.startswith(folded_query):
        return 0, folded
    positions = []
    start = 0
    for letter in folded_query:
        index = folded.find(letter, start)
        if index < 0:
            return None
        positions.append(index)
        start = index + 1
    word_starts = sum(_is_word_start(nick, index) for index in positions if index < len(nick))
    return 1, -word_starts, positions[-1] - positions[0], len(nick), folded

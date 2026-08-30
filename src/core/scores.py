"""Fetch the logged-in account's scores and bonuses."""

import re
from typing import Optional

import requests


_URL = "https://klavogonki.ru/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_SCORES_RE = re.compile(r'id\s*=\s*userpanel-scores[^>]*>\s*(\d+)\s*<')
_BONUSES_RE = re.compile(r'id\s*=\s*userpanel-bonuses[^>]*>\s*(\d+)\s*<')


def fetch_scores_bonuses(
    cookies: list[dict], timeout: int = 5
) -> Optional[tuple[int, int]]:
    if not cookies:
        return None

    cookies = {
        c["name"]: c["value"]
        for c in cookies
        if c.get("name") and c.get("value")
    }
    if not cookies:
        return None

    try:
        response = requests.get(
            _URL, cookies=cookies, headers=_HEADERS, timeout=timeout
        )
    except requests.RequestException:
        return None

    if not response.ok or "/login" in response.url:
        return None

    scores = _SCORES_RE.search(response.text)
    bonuses = _BONUSES_RE.search(response.text)
    if not scores or not bonuses:
        return None

    return int(scores.group(1)), int(bonuses.group(1))
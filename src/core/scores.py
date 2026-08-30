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
) -> Optional[tuple[int, int, Optional[list[dict]]]]:
    """Returns (scores, bonuses, updated_cookies). updated_cookies is a
    refreshed cookie list when the server rotated a value, else None."""
    sent = {c["name"]: c for c in cookies if c.get("name") and c.get("value")}
    if not sent:
        return None

    session = requests.Session()
    for c in sent.values():
        session.cookies.set(
            c["name"], c["value"],
            domain=c.get("domain") or "klavogonki.ru",
            path=c.get("path") or "/",
        )

    try:
        response = session.get(_URL, headers=_HEADERS, timeout=timeout)
    except requests.RequestException:
        return None

    if not response.ok or "/login" in response.url:
        return None

    scores = _SCORES_RE.search(response.text)
    bonuses = _BONUSES_RE.search(response.text)
    if not scores or not bonuses:
        return None

    rotated = {c.name: {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
               for c in session.cookies if c.value != sent.get(c.name, {}).get("value")}
    updated_cookies = {**sent, **rotated}
    updated_cookies = list(updated_cookies.values()) if rotated else None

    return int(scores.group(1)), int(bonuses.group(1)), updated_cookies
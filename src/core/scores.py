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

# Explicit markers that the page was rendered for a guest (not logged in).
# Any of these means session cookies were ignored / expired.
_UNAUTH_MARKERS = (
    re.compile(r'var\s+__user__\s*=\s*null\s*;'),
    re.compile(r"\.constant\(\s*['\"]Me['\"]\s*,\s*null\s*\)"),
    re.compile(r'class\s*=\s*["\']?login-block'),
    re.compile(r'id\s*=\s*["\']?login-form'),
    re.compile(r'id\s*=\s*["\']?login-link'),
)

# error codes returned as the second element on failure
ERR_NO_COOKIES = "no_cookies"
ERR_NETWORK = "network"
ERR_AUTH = "auth"
ERR_PARSE = "parse"


def _is_unauthenticated(html: str) -> bool:
    return any(m.search(html) for m in _UNAUTH_MARKERS)


def fetch_scores_bonuses(
    cookies: list[dict], timeout: int = 5
) -> tuple[Optional[tuple[int, int, Optional[list[dict]]]], Optional[str], Optional[str]]:
    """Returns ((scores, bonuses, updated_cookies), None, None) on success.
    On failure: (None, error_code, debug_html), where debug_html is the raw
    response body for ERR_AUTH/ERR_PARSE, or None if no response was received."""
    sent = {c["name"]: c for c in cookies if c.get("name") and c.get("value")}
    if not sent:
        return None, ERR_NO_COOKIES, None

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
        return None, ERR_NETWORK, None

    if not response.ok or "/login" in response.url:
        return None, ERR_AUTH, response.text

    if _is_unauthenticated(response.text):
        return None, ERR_AUTH, response.text

    scores = _SCORES_RE.search(response.text)
    bonuses = _BONUSES_RE.search(response.text)
    if not scores or not bonuses:
        return None, ERR_PARSE, response.text

    rotated = {c.name: {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
               for c in session.cookies if c.value != sent.get(c.name, {}).get("value")}
    updated_cookies = {**sent, **rotated}
    updated_cookies = list(updated_cookies.values()) if rotated else None

    return (int(scores.group(1)), int(bonuses.group(1)), updated_cookies), None, None
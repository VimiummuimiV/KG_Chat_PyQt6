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

# Strong guest markers only (__user__/Me)
_UNAUTH_MARKERS = (
    re.compile(r"var\s+__user__\s*=\s*null\s*;"),
    re.compile(r"\.constant\(\s*['\"]Me['\"]\s*,\s*null\s*\)"),
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
        print("⚖️ scores: no cookies provided")
        return None, ERR_NO_COOKIES, None

    names = sorted(sent)
    print(
        f"⚖️ scores: sending {len(sent)} cookies: {names}; "
        f"PHPSESSID={'yes' if 'PHPSESSID' in sent else 'NO'}"
    )

    session = requests.Session()
    for c in sent.values():
        session.cookies.set(
            c["name"], c["value"],
            domain=c.get("domain") or "klavogonki.ru",
            path=c.get("path") or "/",
        )

    try:
        response = session.get(_URL, headers=_HEADERS, timeout=timeout)
    except requests.RequestException as e:
        print(f"⚖️ scores: network error: {e}")
        return None, ERR_NETWORK, None

    print(f"⚖️ scores: HTTP {response.status_code} url={response.url!r}")
    if not response.ok or "/login" in response.url:
        print("⚖️ scores: ERR_AUTH (bad status or redirected to login)")
        return None, ERR_AUTH, response.text

    if _is_unauthenticated(response.text):
        print("⚖️ scores: ERR_AUTH (guest markers: __user__/Me null)")
        return None, ERR_AUTH, response.text

    scores = _SCORES_RE.search(response.text)
    bonuses = _BONUSES_RE.search(response.text)
    if not scores or not bonuses:
        print(
            f"⚖️ scores: ERR_PARSE "
            f"scores={'hit' if scores else 'miss'} bonuses={'hit' if bonuses else 'miss'}"
        )
        return None, ERR_PARSE, response.text

    print(f"⚖️ scores: ok scores={scores.group(1)} bonuses={bonuses.group(1)}")

    rotated = {c.name: {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
               for c in session.cookies if c.value != sent.get(c.name, {}).get("value")}
    updated_cookies = {**sent, **rotated}
    updated_cookies = list(updated_cookies.values()) if rotated else None

    return (int(scores.group(1)), int(bonuses.group(1)), updated_cookies), None, None

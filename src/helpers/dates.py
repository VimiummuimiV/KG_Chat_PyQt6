"""Shared date parsing helpers"""
from datetime import datetime, timedelta


def parse_short_date(date_str: str) -> str:
    """Convert shorthand date entries (YYMMDD, YYYYMMDD, today, yesterday, -N) to YYYY-MM-DD.
    Returns the input unchanged if it doesn't match any shorthand format."""
    text = date_str.strip().lower()

    if text == 'today':
        return datetime.now().strftime('%Y-%m-%d')
    if text == 'yesterday':
        return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    if text.startswith('-') and text[1:].isdigit():
        return (datetime.now() - timedelta(days=int(text[1:]))).strftime('%Y-%m-%d')

    clean = date_str.replace('-', '').replace('/', '').replace('.', '').strip()
    if clean.isdigit() and len(clean) in (6, 8):
        try:
            if len(clean) == 6:
                yy, mm, dd = int(clean[0:2]), int(clean[2:4]), int(clean[4:6])
                return datetime(2000 + yy, mm, dd).strftime('%Y-%m-%d')
            yyyy, mm, dd = int(clean[0:4]), int(clean[4:6]), int(clean[6:8])
            return datetime(yyyy, mm, dd).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return date_str
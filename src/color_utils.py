"""Small utilities to ensure foreground colors meet contrast against a background.

Compact, dependency-free helpers used to slightly boost user-provided colors
so they remain legible on dark (or light) themes.
"""
from __future__ import annotations
import colorsys
import re

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    m = HEX_RE.match(h.strip())
    if not m:
        raise ValueError("invalid hex")
    s = m.group(1)
    return int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hexstr: str) -> float:
    r, g, b = hex_to_rgb(hexstr)
    return 0.2126 * _srgb_to_linear(r) + 0.7152 * _srgb_to_linear(g) + 0.0722 * _srgb_to_linear(b)


def contrast_ratio(a: str, b: str) -> float:
    la = relative_luminance(a)
    lb = relative_luminance(b)
    L1, L2 = max(la, lb), min(la, lb)
    return (L1 + 0.05) / (L2 + 0.05)


def _adjust_lightness(hexstr: str, delta: float) -> str:
    r, g, b = hex_to_rgb(hexstr)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0.0, min(1.0, l + delta))
    nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex((nr, ng, nb))


def ensure_contrast(fg: str | None, bg: str, min_ratio: float = 4.5) -> str:
    """Return a foreground hex color (lowercase) that meets min_ratio against bg.

    Strategy:
      - If current fg meets threshold, return it.
      - Try white/black.
      - Try stepping lightness up/down until reaching threshold.
      - Return the best candidate found.
    """
    if not fg:
        fg = '#ffffff'
    fg = fg.strip()
    bg = (bg or '#000000').strip()
    try:
        cur = contrast_ratio(fg, bg)
    except Exception:
        return '#ffffff'
    if cur >= min_ratio:
        return fg.lower()

    # Try small adjustments first (prefer minimal perceptual change)
    best, best_ratio, best_delta = fg, cur, 0.0
    steps = (0.04, 0.08, 0.16, 0.28)
    for step in steps:
        lighter = _adjust_lightness(fg, step)
        try:
            r = contrast_ratio(lighter, bg)
        except Exception:
            r = -1
        delta = step
        if r >= min_ratio:
            # Prefer the smallest delta that reaches target
            if best_ratio < min_ratio or delta < best_delta or best_ratio < r:
                return lighter.lower()
        if r > best_ratio:
            best, best_ratio, best_delta = lighter, r, delta
    for step in steps:
        darker = _adjust_lightness(fg, -step)
        try:
            r = contrast_ratio(darker, bg)
        except Exception:
            r = -1
        delta = step
        if r >= min_ratio:
            if best_ratio < min_ratio or delta < best_delta or best_ratio < r:
                return darker.lower()
        if r > best_ratio:
            best, best_ratio, best_delta = darker, r, delta

    # If adjustments failed to reach threshold, consider white/black only when
    # they meet the threshold and they are substantially better than current
    try:
        w = contrast_ratio('#ffffff', bg)
        b = contrast_ratio('#000000', bg)
    except Exception:
        w = b = 0

    if w >= min_ratio and (w - best_ratio) >= 0.15:
        return '#ffffff'
    if b >= min_ratio and (b - best_ratio) >= 0.15:
        return '#000000'

    # Otherwise return the best adjusted candidate (may still be < min_ratio)
    return best.lower()
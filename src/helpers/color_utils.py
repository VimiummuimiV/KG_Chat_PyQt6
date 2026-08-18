"""Color utilities — conversions, blending, and app palette helpers."""
import colorsys


def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def rgb_to_hsl(rgb: tuple) -> tuple:
    """RGB (0-255) → HSL (h 0-360, s 0-1, l 0-1)."""
    r, g, b = [x / 255.0 for x in rgb]
    max_val, min_val = max(r, g, b), min(r, g, b)
    diff = max_val - min_val
    l = (max_val + min_val) / 2.0

    if diff == 0:
        return (0, 0, l)

    s = diff / (2.0 - max_val - min_val) if l > 0.5 else diff / (max_val + min_val)

    if max_val == r:
        h = ((g - b) / diff + (6 if g < b else 0)) / 6.0
    elif max_val == g:
        h = ((b - r) / diff + 2) / 6.0
    else:
        h = ((r - g) / diff + 4) / 6.0

    return (h * 360, s, l)


def hsl_to_rgb(hsl: tuple) -> tuple:
    """HSL (h 0-360, s 0-1, l 0-1) → RGB (0-255)."""
    h, s, l = hsl
    h = h / 360.0

    if s == 0:
        v = int(l * 255)
        return (v, v, v)

    def hue_to_rgb(p, q, t):
        t = t + 1 if t < 0 else t - 1 if t > 1 else t
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    return (
        round(hue_to_rgb(p, q, h + 1 / 3) * 255),
        round(hue_to_rgb(p, q, h) * 255),
        round(hue_to_rgb(p, q, h - 1 / 3) * 255),
    )


def hsl_to_hex(h: float, s: float, l: float) -> str:
    """HSL (h 0-360, s 0-100, l 0-100) → hex."""
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def blend_hex_colors(base_hex: str, accent_hex: str, ratio: float = 0.15) -> str:
    """Blend two hex colors by ratio toward accent."""
    br, bg, bb = hex_to_rgb(base_hex)
    ar, ag, ab = hex_to_rgb(accent_hex)
    return rgb_to_hex((
        round(br + (ar - br) * ratio),
        round(bg + (ag - bg) * ratio),
        round(bb + (ab - bb) * ratio),
    ))


def _themed_hsl_colors(config, section, default_hue, default_sat, is_dark_theme,
                        dark_values, light_values) -> dict:
    """Shared lookup for the get_*_message_colors helpers below."""
    hue = config.get("ui", section, "hue") or default_hue
    saturation = config.get("ui", section, "saturation") or default_sat
    lightness_values = dark_values if is_dark_theme else light_values
    return {key: hsl_to_hex(hue, saturation, lightness) for key, lightness in lightness_values.items()}


def get_private_message_colors(config, is_dark_theme: bool) -> dict:
    return _themed_hsl_colors(
        config, "private_message_color", 0, 75, is_dark_theme,
        {"text": 75, "input_bg": 15, "input_border": 35},
        {"text": 35, "input_bg": 85, "input_border": 55},
    )


def get_ban_message_colors(config, is_dark_theme: bool) -> dict:
    return _themed_hsl_colors(config, "ban_message_color", 170, 75, is_dark_theme,
                               {"text": 75}, {"text": 35})


def get_system_message_colors(config, is_dark_theme: bool) -> dict:
    return _themed_hsl_colors(config, "system_message_color", 240, 0, is_dark_theme,
                               {"text": 60}, {"text": 50})


def get_mention_color(is_dark_theme: bool) -> str:
    return "#00FF00" if is_dark_theme else "#008000"


def get_competition_message_colors(config, is_dark_theme: bool) -> dict:
    return _themed_hsl_colors(config, "competition_message_color", 45, 80, is_dark_theme,
                               {"text": 75}, {"text": 40})


# level (1-9) → rank base color
RANK_LEVEL_COLORS = {
    1: "#AFAFAF",  # Новичок
    2: "#61B5B3",  # Любитель
    3: "#2DAB4F",  # Таксист
    4: "#C1AA00",  # Профи
    5: "#FF8C00",  # Гонщик
    6: "#DA0543",  # Маньяк
    7: "#B543F5",  # Супермен
    8: "#5681FF",  # Кибергонщик
    9: "#06B4E9",  # Экстракибер
}


# dark/light knobs for get_rank_chip_colors: canvas color, bg/border blend
# ratios (+ cool-hue boost), saturation multiplier, and lightness formula
_RANK_CHIP_THEME = {
    True: dict(canvas="#141414", bg_a=0.22, bg_cool=0.5, bd_a=0.40, bd_cool=1.0,
               s_mul=0.95, l=lambda l, cool: min(0.78, max(l, 0.55) + cool)),
    False: dict(canvas="#F5F5F5", bg_a=0.18, bg_cool=0.3, bd_a=0.35, bd_cool=0.5,
                s_mul=0.90, l=lambda l, cool: max(0.22, min(l, 0.40) - cool * 0.5)),
}


def get_rank_chip_colors(level, is_dark: bool) -> tuple:
    """Return (bg_hex, fg_hex, border_hex) for a player chip.

    Dark theme: muted tinted fill, full-intensity rank text, mid border.
    Blue/violet hues get a small lightness boost (harder for the eye).
    """
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = None
    base = RANK_LEVEL_COLORS.get(level, "#888888")
    h, s, l = rgb_to_hsl(hex_to_rgb(base))
    # blue → violet: ~210–300° — weak perceived brightness
    cool = 0.08 if 200 <= h <= 300 else 0.0

    t = _RANK_CHIP_THEME[is_dark]
    bg = blend_hex_colors(t["canvas"], base, t["bg_a"] + cool * t["bg_cool"])
    border = blend_hex_colors(t["canvas"], base, t["bd_a"] + cool * t["bd_cool"])
    fg = rgb_to_hex(hsl_to_rgb((h, min(1.0, s * t["s_mul"]), t["l"](l, cool))))
    return bg, fg, border
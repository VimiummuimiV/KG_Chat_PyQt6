"""WCAG contrast optimization for usernames on themed backgrounds."""
from helpers.color_utils import hex_to_rgb, rgb_to_hex, rgb_to_hsl, hsl_to_rgb


def relative_luminance(rgb: tuple) -> float:
    """Calculate relative luminance (WCAG formula)."""
    def adjust(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * adjust(rgb[0]) + 0.7152 * adjust(rgb[1]) + 0.0722 * adjust(rgb[2])


def contrast_ratio(c1: tuple, c2: tuple) -> float:
    """Calculate contrast ratio between two colors."""
    l1, l2 = relative_luminance(c1), relative_luminance(c2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def optimize_color_contrast(fg_hex: str, bg_hex: str = "#1E1E1E",
                            target_ratio: float = 4.5) -> str:
    """Adjust foreground lightness so contrast vs background meets target_ratio."""
    if not fg_hex:
        return "#FFFFFF"

    fg_rgb = hex_to_rgb(fg_hex)
    bg_rgb = hex_to_rgb(bg_hex)

    if contrast_ratio(fg_rgb, bg_rgb) >= target_ratio:
        return fg_hex

    h, s, l = rgb_to_hsl(fg_rgb)
    bg_lum = relative_luminance(bg_rgb)

    # Dark background → lighten text; light background → darken text
    min_l, max_l = (l, 1.0) if bg_lum < 0.5 else (0.0, l)
    best_l = max_l if bg_lum < 0.5 else min_l

    for _ in range(20):
        test_l = (min_l + max_l) / 2
        test_rgb = hsl_to_rgb((h, s, test_l))
        test_ratio = contrast_ratio(test_rgb, bg_rgb)

        if test_ratio >= target_ratio:
            best_l = test_l
            if bg_lum < 0.5:
                max_l = test_l
            else:
                min_l = test_l
        else:
            if bg_lum < 0.5:
                min_l = test_l
            else:
                max_l = test_l

    return rgb_to_hex(hsl_to_rgb((h, s, best_l)))

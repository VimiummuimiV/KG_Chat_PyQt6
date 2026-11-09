"""WCAG contrast optimization for usernames on themed backgrounds."""

from helpers.colors.color_utils import hex_to_rgb, hsl_to_rgb, rgb_to_hex, rgb_to_hsl


def _relative_luminance(rgb: tuple) -> float:
    """Calculate relative luminance (WCAG formula)."""
    def adjust(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * adjust(rgb[0]) + 0.7152 * adjust(rgb[1]) + 0.0722 * adjust(rgb[2])


def _contrast_ratio(first_color: tuple, second_color: tuple) -> float:
    """Calculate contrast ratio between two colors."""
    first_luminance, second_luminance = _relative_luminance(first_color), _relative_luminance(second_color)
    return (max(first_luminance, second_luminance) + 0.05) / (min(first_luminance, second_luminance) + 0.05)


def optimize_color_contrast(foreground_hex: str, background_hex: str = "#1E1E1E",
                            target_ratio: float = 4.5) -> str:
    """Adjust foreground lightness so contrast vs background meets target_ratio."""
    if not foreground_hex:
        return "#FFFFFF"

    foreground_rgb = hex_to_rgb(foreground_hex)
    background_rgb = hex_to_rgb(background_hex)

    if _contrast_ratio(foreground_rgb, background_rgb) >= target_ratio:
        return foreground_hex

    h, s, l = rgb_to_hsl(foreground_rgb)
    background_lum = _relative_luminance(background_rgb)

    # Dark background → lighten text; light background → darken text
    min_l, max_l = (l, 1.0) if background_lum < 0.5 else (0.0, l)
    best_l = max_l if background_lum < 0.5 else min_l

    for _ in range(20):
        test_l = (min_l + max_l) / 2
        test_rgb = hsl_to_rgb((h, s, test_l))
        test_ratio = _contrast_ratio(test_rgb, background_rgb)

        if test_ratio >= target_ratio:
            best_l = test_l
            if background_lum < 0.5:
                max_l = test_l
            else:
                min_l = test_l
        else:
            if background_lum < 0.5:
                min_l = test_l
            else:
                max_l = test_l

    return rgb_to_hex(hsl_to_rgb((h, s, best_l)))

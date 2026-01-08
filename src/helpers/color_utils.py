"""Color utilities for HSL manipulation"""
import colorsys


def hsl_to_hex(h: float, s: float, l: float) -> str:
    """Convert HSL to hex color
    
    Args:
        h: Hue (0-360)
        s: Saturation (0-100)
        l: Lightness (0-100)
    
    Returns:
        Hex color string like '#FF0000'
    """
    # Normalize to 0-1 range
    h_norm = h / 360.0
    s_norm = s / 100.0
    l_norm = l / 100.0
    
    # Convert to RGB
    r, g, b = colorsys.hls_to_rgb(h_norm, l_norm, s_norm)
    
    # Convert to 0-255 range and format as hex
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def get_private_message_colors(config, is_dark_theme: bool) -> dict:
    """Generate all private message colors from config
    
    The config should have this structure:
    {
      "hue": 0,
      "dark_theme": {
        "saturation": 80,
        "lightness": 65,
        "input_bg_lightness": 18,
        "input_text_lightness": 70,
        "input_border_lightness": 35
      },
      "light_theme": { ... }
    }
    
    All colors use the same hue and saturation, only lightness varies.
    
    Args:
        config: Config object or dict with private_message_color settings
        is_dark_theme: Whether using dark theme
    
    Returns:
        Dict with all color values for private messages
    """
    # Get base hue
    if hasattr(config, 'get'):
        base_hue = config.get("ui", "private_message_color", "hue") or 0
        theme_key = "dark_theme" if is_dark_theme else "light_theme"
        
        # Get base saturation and lightness (text color)
        saturation = config.get("ui", "private_message_color", theme_key, "saturation") or 80
        text_lightness = config.get("ui", "private_message_color", theme_key, "lightness") or 65
        
        # Get lightness values for other elements
        input_bg_lightness = config.get("ui", "private_message_color", theme_key, "input_bg_lightness") or 18
        input_text_lightness = config.get("ui", "private_message_color", theme_key, "input_text_lightness") or 70
        input_border_lightness = config.get("ui", "private_message_color", theme_key, "input_border_lightness") or 35
    else:
        # Fallback for dict access
        base_hue = config.get("hue", 0)
        theme_key = "dark_theme" if is_dark_theme else "light_theme"
        theme_config = config.get(theme_key, {})
        
        saturation = theme_config.get("saturation", 80)
        text_lightness = theme_config.get("lightness", 65)
        input_bg_lightness = theme_config.get("input_bg_lightness", 18)
        input_text_lightness = theme_config.get("input_text_lightness", 70)
        input_border_lightness = theme_config.get("input_border_lightness", 35)
    
    # Generate all colors using same hue and saturation, different lightness
    return {
        "text": hsl_to_hex(base_hue, saturation, text_lightness),
        "input_bg": hsl_to_hex(base_hue, saturation, input_bg_lightness),
        "input_text": hsl_to_hex(base_hue, saturation, input_text_lightness),
        "input_border": hsl_to_hex(base_hue, saturation, input_border_lightness),
    }
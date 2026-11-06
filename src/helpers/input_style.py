"""Style of a message input: private conversation > own ban > regular."""

from helpers.colors.color_utils import (
    get_input_colors,
    get_input_stylesheet,
    get_private_message_colors,
    get_self_ban_colors,
)
from helpers.translate import tr


def resolve_input_style(config, is_dark: bool, private_username: str | None = None,
                        self_ban_placeholder: str | None = None) -> tuple[str, str]:
    """(stylesheet, placeholder) of an input; a private recipient wins over an active own ban."""
    if private_username:
        colors = get_private_message_colors(config, is_dark)
        placeholder = tr(f"Private message to {private_username}", f"Приватное сообщение для {private_username}")
    elif self_ban_placeholder is not None:
        colors, placeholder = get_self_ban_colors(config, is_dark), self_ban_placeholder
    else:
        colors, placeholder = get_input_colors(config, is_dark), ""
    return get_input_stylesheet(colors), placeholder

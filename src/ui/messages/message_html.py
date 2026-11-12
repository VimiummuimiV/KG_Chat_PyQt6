"""Colored HTML of a message line, in the colors the message has in the list."""

from html import escape

from components.image_viewer.gallery import URL_PATTERN
from ui.messages.message_renderer import MessageRenderer


def _span(color: str, text: str) -> str:
    return f'<span style="color:{color}">{escape(text)}</span>' if text else ""


def message_line_html(
    renderer: MessageRenderer,
    parts: tuple,
    username_color: str,
    is_private: bool,
    is_ban: bool,
    is_system: bool,
    is_competition: bool = False,
    is_parser: bool = False,
) -> str:
    """One paragraph for the ("[time] ", "username: ", body) parts: time, username, text and links each in their own color."""
    time_text, username_text, body = parts
    text_color = renderer.get_text_color(is_ban, is_private, is_system, is_competition, is_parser)
    time_color = renderer.get_timestamp_color(is_ban, is_private, is_system, is_competition, is_parser)

    body_html = []
    position = 0
    for match in URL_PATTERN.finditer(body):
        body_html.append(_span(text_color, body[position:match.start()]))
        body_html.append(_span(renderer.get_link_color(match.group(0)), match.group(0)))
        position = match.end()
    body_html.append(_span(text_color, body[position:]))

    return (
        '<p style="margin:0; white-space:pre-wrap">'
        f"{_span(time_color, time_text)}{_span(username_color, username_text)}{''.join(body_html)}</p>"
    )

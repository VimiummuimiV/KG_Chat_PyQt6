"""Messages display UI for the chat."""
import flet as ft
from flet import Column, ListView, Text, Row, TextField, Button, Image


def build_messages_ui():
    """Build and return the messages view and send handler.
    
    Returns:
        (messages_container, input_field, send_button, messages_view)
    """
    messages_view = ListView(expand=True, spacing=4)
    
    input_field = TextField(
        label="Type a message...",
        multiline=True,
        min_lines=1,
        max_lines=3,
        expand=True
    )
    
    send_button = Button("Send", width=80)
    
    input_row = Row(
        [input_field, send_button],
        expand=True,
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.END,
        tight=True
    )
    
    # Container for messages + input
    messages_container = Column(
        [messages_view, input_row],
        expand=True,
        spacing=8
    )
    
    return messages_container, input_field, send_button, messages_view


def add_message_to_view(messages_view, login: str, text: str, avatar_url: str = None):
    """Add a message to the messages view.
    
    Args:
        messages_view: ListView for messages
        login: username
        text: message body
        avatar_url: optional avatar URL
    """
    # Message row: avatar + username + text
    msg_widgets = []
    
    if avatar_url:
        try:
            avatar = Image(
                src=avatar_url,
                width=24,
                height=24,
                fit=ft.ImageFit.COVER,
                border_radius=ft.border_radius.all(4)
            )
            msg_widgets.append(avatar)
        except:
            # Avatar failed to load
            pass
    
    # Username and message
    username_text = Text(f"[{login}]", weight="bold", size=11)
    message_text = Text(text, size=11)
    
    text_col = Column(
        [username_text, message_text],
        spacing=2,
        expand=True
    )
    
    msg_widgets.append(text_col)
    
    msg_row = Row(msg_widgets, spacing=8, expand=True)
    messages_view.controls.append(msg_row)

"""User list display UI for the chat."""
import flet as ft
from flet import Column, ListView, Text, Row, Image


def build_userlist_ui():
    """Build and return the user list view.
    
    Returns:
        (users_container, users_view)
    """
    users_view = ListView(expand=True, spacing=6)
    
    users_container = Column(
        [users_view],
        expand=True,
        width=260,
        spacing=0
    )
    
    return users_container, users_view


def add_user_to_view(users_view, login: str, avatar_url: str = None, game_id: str = None):
    """Add or update a user in the user list view.
    
    Args:
        users_view: ListView for users
        login: username
        avatar_url: optional avatar URL
        game_id: optional game ID (shows game status)
    """
    # User row: avatar + username + game status
    user_widgets = []
    
    if avatar_url:
        try:
            avatar = Image(
                src=avatar_url,
                width=28,
                height=28,
                fit=ft.ImageFit.COVER,
                border_radius=ft.border_radius.all(4)
            )
            user_widgets.append(avatar)
        except:
            # Avatar failed to load
            pass
    
    # Username
    username_text = Text(login, size=11)
    
    # Game status
    status_text = ""
    if game_id:
        status_text = f"🎮 #{game_id}"
        username_text = Text(f"{login} {status_text}", size=10, italic=True)
    
    user_widgets.append(username_text)
    
    user_row = Row(user_widgets, spacing=8)
    users_view.controls.append(user_row)


def remove_user_from_view(users_view, login: str):
    """Remove a user from the user list view.
    
    Args:
        users_view: ListView for users
        login: username to remove
    """
    # Find and remove user by checking text in controls
    for ctrl in users_view.controls[:]:
        if hasattr(ctrl, 'controls'):  # Row
            for child in ctrl.controls:
                if isinstance(child, Text) and login in child.value:
                    users_view.controls.remove(ctrl)
                    return


def clear_userlist(users_view):
    """Clear all users from the list."""
    users_view.controls.clear()


def rebuild_userlist(users_view, users_list):
    """Rebuild the entire user list from a ChatUser list.
    
    Args:
        users_view: ListView for users
        users_list: list of core.userlist.ChatUser objects
    """
    users_view.controls.clear()
    for user in users_list:
        add_user_to_view(
            users_view,
            login=user.login,
            avatar_url=user.get_avatar_url() if hasattr(user, 'get_avatar_url') else None,
            game_id=user.game_id
        )

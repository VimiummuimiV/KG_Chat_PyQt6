"""KG Chat - Main entry point."""
from pathlib import Path
import threading
import flet as ft
from ui.accounts_manager import build_welcome
from ui.ui_messages import build_messages_ui, add_message_to_view
from ui.ui_userlist import build_userlist_ui, rebuild_userlist
from settings.ui_scale import build_scale_controls, load_scale
from core.xmpp import XMPPClient


def main(page: ft.Page):
    page.title = "KG Chat"
    xmpp_client = None
    
    def on_connect(login, account):
        """Called when user clicks Connect in welcome screen."""
        nonlocal xmpp_client
        
        try:
            # Initialize XMPP client
            cfg_path = str(Path(__file__).parent / "config.json")
            xmpp_client = XMPPClient(cfg_path)
            
            # Connect
            if not xmpp_client.connect(account):
                ft.SnackBar(ft.Text("Failed to connect"), open=True)
                return
            
            # Initialize scale in page.data
            if page.data is None:
                page.data = {}
            page.data['scale'] = load_scale()
            
            # Build chat interface
            messages_container, input_field, send_button, messages_view = build_messages_ui()
            users_container, users_view = build_userlist_ui()
            
            # Build scale controls
            scale_slider, scale_label, initial_scale = build_scale_controls()
            
            # Create toggle button for userlist
            userlist_visible = True
            def on_toggle_userlist(e):
                nonlocal userlist_visible
                userlist_visible = not userlist_visible
                users_container.visible = userlist_visible
                page.update()
            
            toggle_users_btn = ft.IconButton(
                ft.icons.PEOPLE,
                on_click=on_toggle_userlist,
                tooltip="Toggle user list"
            )
            
            # Header with controls
            header = ft.Row(
                [toggle_users_btn, ft.Divider(height=1), scale_slider, scale_label],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True
            )
            
            # Set up callbacks for messages and presence
            def on_message(msg):
                messages_view.controls.append(
                    ft.Row([
                        ft.Text(f"[{msg.login or 'Unknown'}]: {msg.body}", size=11)
                    ], expand=True)
                )
                page.update()
            
            def on_presence(pres):
                # Rebuild user list when presence changes
                rebuild_userlist(users_view, xmpp_client.user_list.get_all())
                page.update()
            
            xmpp_client.set_message_callback(on_message)
            xmpp_client.set_presence_callback(on_presence)
            
            # Join auto-join rooms
            rooms = xmpp_client.account_manager.get_rooms()
            for room in rooms:
                if room.get('auto_join'):
                    xmpp_client.join_room(room['jid'])
            
            # Initial user list
            rebuild_userlist(users_view, xmpp_client.user_list.get_all())
            
            # Wire send button
            def on_send(e):
                text = input_field.value.strip()
                if text and xmpp_client:
                    xmpp_client.send_message(text)
                    input_field.value = ""
                    page.update()
            
            send_button.on_click = on_send
            
            # Build main chat layout with userlist on the right
            main_content = ft.Row(
                [messages_container, users_container],
                expand=True,
                spacing=8
            )
            
            # Clear and show chat UI with header
            page.controls.clear()
            page.add(header)
            page.add(main_content)
            page.update()
            
            # Start XMPP listener in background thread
            def listen_thread():
                xmpp_client.listen()
            
            threading.Thread(target=listen_thread, daemon=True).start()
        
        except Exception as ex:
            ft.SnackBar(ft.Text(f"Error: {ex}"), open=True)
    
    # Start with welcome screen
    build_welcome(page, on_connect_callback=on_connect)


if __name__ == "__main__":
    ft.app(target=main)


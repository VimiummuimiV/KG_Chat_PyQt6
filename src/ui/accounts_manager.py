"""Welcome screen UI for account selection and management."""
from pathlib import Path
from typing import List

import flet as ft
from flet import Page, Text, Row, Column, Dropdown, TextField, ElevatedButton, SnackBar

from core.accounts import AccountManager


def build_welcome(page: Page, on_connect_callback=None):
    """Build and display the welcome/account management screen."""
    page.title = "KG Chat - Welcome"
    page.vertical_alignment = ft.MainAxisAlignment.START

    cfg_path = str(Path(__file__).parent.parent / "config.json")
    acct_mgr = AccountManager(cfg_path)

    # Helper: show a SnackBar notification
    def notify(msg: str, duration: int = 2000):
        page.snack_bar = SnackBar(Text(msg), open=True, duration=duration)
        page.update()

    # Build dropdown options from accounts
    def make_options() -> List[ft.dropdown.Option]:
        opts = []
        for acc in acct_mgr.list_accounts():
            label = f"{acc['login']}{' (active)' if acc.get('active') else ''}"
            opts.append(ft.dropdown.Option(key=acc['login'], text=label))
        return opts

    account_dd = Dropdown(options=make_options(), value=None, width=320)

    connect_btn = ElevatedButton("Connect")
    remove_btn = ElevatedButton("Remove")

    userid_field = TextField(label="User ID", width=140)
    login_field = TextField(label="Username", width=180)
    password_field = TextField(label="Password", password=True, width=180)
    add_btn = ElevatedButton("Add")

    # Refresh dropdown and default selection
    def refresh_dd():
        opts = make_options()
        account_dd.options = opts
        active = next((a for a in acct_mgr.list_accounts() if a.get('active')), None)
        if active:
            account_dd.value = active['login']
        else:
            account_dd.value = opts[0].key if opts else None
        page.update()

    refresh_dd()

    def on_add(e):
        userid = (userid_field.value or "").strip()
        login = (login_field.value or "").strip()
        pwd = (password_field.value or "").strip()
        if not login or not pwd:
            notify("Provide username and password")
            return
        if not userid:
            userid = login
        ok = acct_mgr.add_account(user_id=userid, login=login, password=pwd)
        notify("Added" if ok else "Already exists")
        if ok:
            userid_field.value = ""
            login_field.value = ""
            password_field.value = ""
        refresh_dd()

    def on_remove(e):
        val = account_dd.value
        if not val:
            notify("No account selected")
            return
        ok = acct_mgr.remove_account(val)
        notify("Removed" if ok else "Not found")
        refresh_dd()

    def on_connect(e):
        val = account_dd.value
        if not val:
            notify("Select an account to connect")
            return
        account = acct_mgr.get_account_by_login(val)
        if not account:
            notify("Account not found")
            return
        notify(f"Connecting as {val}...", duration=1000)
        if on_connect_callback:
            on_connect_callback(val, account)

    add_btn.on_click = on_add
    remove_btn.on_click = on_remove
    connect_btn.on_click = on_connect

    header = Text("Welcome to KG Chat", size=24)

    controls = Column(
        [
            header,
            Row([account_dd, Row([connect_btn, remove_btn], spacing=12)], alignment=ft.MainAxisAlignment.START),
            Row([userid_field, login_field, password_field, add_btn], spacing=12),
        ],
        tight=True,
        expand=False,
    )

    page.controls.clear()
    page.add(controls)
    page.update()

"""Unified username color management for username"""
import sqlite3
from typing import Tuple, Dict, Optional

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QMessageBox

from core.accounts import AccountManager


def get_effective_background(account: Dict) -> str:
    """Get the effective background color (custom if set, else server)."""
    return account.get('custom_background') or account.get('background') or '#808080'


def set_color(account_manager: AccountManager, chat_username: str, color: Optional[str] = None,
              mode: str = 'custom') -> Tuple[bool, str]:
    account = account_manager.get_account_by_chat_username(chat_username)
    if not account:
        return False, "Account not found"

    try:
        conn = sqlite3.connect(account_manager.db_path)
        cursor = conn.cursor()

        if mode == 'custom':
            if not color:
                return False, "Color is required for custom mode"
            cursor.execute(
                'UPDATE accounts SET custom_background = ? WHERE chat_username = ?',
                (color, chat_username)
            )
            msg = f"Custom color set to {color}"

        elif mode == 'reset':
            cursor.execute(
                'UPDATE accounts SET custom_background = NULL WHERE chat_username = ?',
                (chat_username,)
            )
            msg = "Reset to original server color"

        else:
            return False, f"Invalid mode: {mode}"

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated, msg if updated else "No changes made"

    except Exception as e:
        return False, f"Operation failed: {str(e)}"


def _refresh_cache(account_manager: AccountManager, account: Dict, cache) -> None:
    updated_account = account_manager.get_account_by_chat_username(account['chat_username'])
    if updated_account:
        account.update(updated_account)
    if cache:
        effective_bg = get_effective_background(account)
        cache.update_user(account['user_id'], account['chat_username'], effective_bg)


def change_username_color(parent, account_manager: AccountManager, account: Dict, cache) -> bool:
    if not account or not account.get('chat_username'):
        QMessageBox.warning(parent, "No Account", "No account selected.")
        return False

    current_color = get_effective_background(account)
    color = QColorDialog.getColor(QColor(current_color), parent, "Choose Username Color")

    if not color.isValid():
        return False

    hex_color = color.name()
    success, message = set_color(account_manager, account['chat_username'], hex_color, 'custom')

    if success:
        _refresh_cache(account_manager, account, cache)
        QMessageBox.information(parent, "Success", message)
        return True
    else:
        QMessageBox.critical(parent, "Error", message)
        return False


def reset_username_color(parent, account_manager: AccountManager, account: Dict, cache) -> bool:
    if not account or not account.get('chat_username'):
        QMessageBox.warning(parent, "No Account", "No account selected.")
        return False

    if not account.get('custom_background'):
        QMessageBox.information(parent, "Info", "Nothing to reset - using original color.")
        return True

    success, message = set_color(account_manager, account['chat_username'], None, 'reset')

    if success:
        _refresh_cache(account_manager, account, cache)
        QMessageBox.information(parent, "Success", message)
        return True
    else:
        QMessageBox.critical(parent, "Error", message)
        return False

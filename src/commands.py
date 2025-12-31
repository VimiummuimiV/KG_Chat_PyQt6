"""Account management commands"""

from accounts import AccountManager
from typing import Optional


class AccountCommands:
    """Handle account-related commands"""
    
    def __init__(self, account_manager: AccountManager):
        self.manager = account_manager
    
    def list_accounts(self) -> str:
        """Return formatted list of accounts"""
        accounts = self.manager.list_accounts()
        if not accounts:
            return "⚠️ No accounts found"
        
        result = "📋 Accounts:\n" + "=" * 50 + "\n"
        for idx, acc in enumerate(accounts):
            status = "✅" if acc.get('active') else "⭕"
            result += f"{idx}. {status} {acc['login']} (ID: {acc['user_id']})\n"
        result += "=" * 50
        return result
    
    def add_account(self, user_id: str, login: str, password: str) -> str:
        """Add account"""
        if self.manager.add_account(user_id, login, password):
            return f"✅ Account '{login}' added"
        return f"❌ Account '{login}' already exists"
    
    def remove_account(self, login: str) -> str:
        """Remove account"""
        if self.manager.remove_account(login):
            return f"✅ Account '{login}' removed"
        return f"❌ Account '{login}' not found"
    
    def switch_account(self, login: str) -> str:
        """Switch active account"""
        if self.manager.switch_account(login):
            return f"✅ Switched to: {login}"
        return f"❌ Account '{login}' not found"
    
    def get_active(self) -> str:
        """Get active account info"""
        account = self.manager.get_active_account()
        if not account:
            return "❌ No active account"
        
        return f"✅ Active: {account['login']} (ID: {account['user_id']})"
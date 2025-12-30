import sqlite3
import json
import os
import platform
from pathlib import Path
from typing import Optional, Dict, List

class AccountManager:
    """Manage multiple XMPP accounts using local SQLite database"""
    
    def __init__(self, config_path: str = 'config.json'):
        self.config_path = config_path
        self.db_path = self._get_db_path()
        self.config = self._load_config()
        self._init_database()
        print(f"💾 Database location: {self.db_path}")
        
        # If no accounts exist, prompt user to create one
        if not self.list_accounts():
            print("\n⚠️  No accounts found in database.")
            self._create_first_account()
    
    def _get_db_path(self) -> str:
        """Detect OS and return appropriate database path"""
        system = platform.system()
        
        if system == "Windows":
            # Windows: Desktop folder
            desktop = Path.home() / "Desktop" / "xmpp_accounts"
        elif system == "Darwin":
            # macOS: Desktop folder
            desktop = Path.home() / "Desktop" / "xmpp_accounts"
        elif system == "Linux":
            # Check if it's Android (Termux)
            if os.path.exists("/data/data/com.termux"):
                # Android/Termux: storage folder
                desktop = Path.home() / "storage" / "shared" / "xmpp_accounts"
            else:
                # Regular Linux: Desktop folder
                desktop = Path.home() / "Desktop" / "xmpp_accounts"
        else:
            # Fallback to home directory
            desktop = Path.home() / ".xmpp_accounts"
        
        # Create directory if it doesn't exist
        desktop.mkdir(parents=True, exist_ok=True)
        
        return str(desktop / "accounts.db")
    
    def _init_database(self):
        """Initialize SQLite database for accounts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                login TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                active INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()
    
    def _create_first_account(self):
        """Interactively create the first account"""
        print("\n📝 Let's create your first account!")
        print("-" * 40)
        
        try:
            user_id = input("User ID: ").strip()
            if not user_id:
                print("❌ Skipped account creation")
                return
            
            login = input("Login: ").strip()
            if not login:
                print("❌ Skipped account creation")
                return
            
            password = input("Password: ").strip()
            if not password:
                print("❌ Skipped account creation")
                return
            
            self.add_account(user_id, login, password, set_active=True)
            print("\n✅ Account created successfully!")
        except (KeyboardInterrupt, EOFError):
            print("\n❌ Account creation cancelled")
    
    def _load_config(self) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Config file not found: {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in config: {e}")
            return {}
    
    def add_account(self, user_id: str, login: str, password: str, set_active: bool = False) -> bool:
        """Add new account to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Deactivate all if setting this as active
            if set_active:
                cursor.execute('UPDATE accounts SET active = 0')
            
            cursor.execute('''
                INSERT INTO accounts (user_id, login, password, active)
                VALUES (?, ?, ?, ?)
            ''', (user_id, login, password, 1 if set_active else 0))
            
            conn.commit()
            conn.close()
            print(f"✅ Account '{login}' added successfully")
            return True
        except sqlite3.IntegrityError:
            print(f"❌ Account '{login}' already exists")
            return False
        except Exception as e:
            print(f"❌ Failed to add account: {e}")
            return False
    
    def remove_account(self, login: str) -> bool:
        """Remove account by login"""
        account = self.get_account_by_login(login)
        if not account:
            print(f"❌ Account '{login}' not found")
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM accounts WHERE login = ?', (login,))
            conn.commit()
            conn.close()
            print(f"✅ Account '{login}' removed")
            return True
        except Exception as e:
            print(f"❌ Failed to remove account: {e}")
            return False
    
    def get_active_account(self) -> Optional[Dict]:
        """Get the currently active account"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM accounts WHERE active = 1 LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_dict(row)
        
        # If no active account, return first one
        return self.get_account_by_index(0)
    
    def get_account_by_login(self, login: str) -> Optional[Dict]:
        """Get account by login"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM accounts WHERE login = ?', (login,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None
    
    def get_account_by_index(self, index: int) -> Optional[Dict]:
        """Get account by index"""
        accounts = self.list_accounts()
        if 0 <= index < len(accounts):
            return accounts[index]
        return None
    
    def list_accounts(self) -> List[Dict]:
        """List all available accounts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM accounts ORDER BY id')
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]
    
    def switch_account(self, login: str) -> bool:
        """
        Switch active account by login
        Returns True if successful
        """
        account = self.get_account_by_login(login)
        if not account:
            print(f"❌ Account '{login}' not found")
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE accounts SET active = 0')
            cursor.execute('UPDATE accounts SET active = 1 WHERE login = ?', (login,))
            conn.commit()
            conn.close()
            print(f"✅ Switched to account: {login}")
            return True
        except Exception as e:
            print(f"❌ Failed to switch account: {e}")
            return False
    
    def _row_to_dict(self, row) -> Dict:
        """Convert database row to dictionary"""
        if not row:
            return None
        return {
            'id': row[0],
            'user_id': row[1],
            'login': row[2],
            'password': row[3],
            'active': bool(row[4])
        }
    
    def get_server_config(self) -> Dict:
        """Get server configuration"""
        return self.config.get('server', {})
    
    def get_rooms(self) -> List[Dict]:
        """Get room list"""
        return self.config.get('rooms', [])
    
    def get_connection_config(self) -> Dict:
        """Get connection parameters"""
        return self.config.get('connection', {})
    
    def display_accounts(self):
        """Display all accounts with their status"""
        accounts = self.list_accounts()
        if not accounts:
            print("\n⚠️  No accounts found.")
            return
        
        print("\n📋 Available Accounts:")
        print("=" * 60)
        for idx, account in enumerate(accounts):
            status = "✅ ACTIVE" if account.get('active', False) else "⭕ Inactive"
            print(f"{idx}. [{status}] {account.get('login')} (ID: {account.get('user_id')})")
        print("=" * 60)
    
    def interactive_menu(self):
        """Display interactive account selection menu"""
        accounts = self.list_accounts()
        
        if not accounts:
            print("❌ No accounts available")
            return None
        
        print("\n" + "=" * 60)
        print("📋 Select Account:")
        print("=" * 60)
        for idx, account in enumerate(accounts):
            print(f"{idx + 1}. 👤 {account['login']} (ID: {account['user_id']})")
        print(f"{len(accounts) + 1}. ➕ Add new account")
        print(f"{len(accounts) + 2}. ❌ Remove account")
        print(f"{len(accounts) + 3}. 🚪 Exit")
        print("=" * 60)
        
        try:
            choice = input("\nSelect option: ").strip()
            choice_num = int(choice)
            
            if choice_num == len(accounts) + 1:
                # Add new account
                self._add_account_interactive()
                return None
            
            elif choice_num == len(accounts) + 2:
                # Remove account
                self._remove_account_interactive()
                return None
            
            elif choice_num == len(accounts) + 3:
                print("\n👋 Goodbye!")
                return "exit"
            
            elif 1 <= choice_num <= len(accounts):
                # Return selected account
                selected = accounts[choice_num - 1]
                self.switch_account(selected['login'])
                return selected
            else:
                print("❌ Invalid option")
                return None
        
        except (ValueError, KeyboardInterrupt, EOFError):
            print("\n❌ Cancelled")
            return None
    
    def _add_account_interactive(self):
        """Interactively add a new account"""
        print("\n➕ Add New Account")
        print("-" * 40)
        
        try:
            user_id = input("User ID: ").strip()
            if not user_id:
                print("❌ Cancelled")
                return
            
            login = input("Login: ").strip()
            if not login:
                print("❌ Cancelled")
                return
            
            password = input("Password: ").strip()
            if not password:
                print("❌ Cancelled")
                return
            
            self.add_account(user_id, login, password, set_active=False)
        except (KeyboardInterrupt, EOFError):
            print("\n❌ Cancelled")
    
    def _remove_account_interactive(self):
        """Interactively remove an account"""
        accounts = self.list_accounts()
        
        print("\n❌ Remove Account")
        print("-" * 40)
        for idx, account in enumerate(accounts):
            print(f"{idx + 1}. {account['login']} (ID: {account['user_id']})")
        
        try:
            remove_choice = input("\nSelect account to remove: ").strip()
            remove_num = int(remove_choice)
            
            if 1 <= remove_num <= len(accounts):
                selected = accounts[remove_num - 1]
                confirm = input(f"Remove '{selected['login']}'? (y/n): ").strip().lower()
                if confirm == 'y':
                    self.remove_account(selected['login'])
            else:
                print("❌ Invalid option")
        except (ValueError, KeyboardInterrupt, EOFError):
            print("\n❌ Cancelled")
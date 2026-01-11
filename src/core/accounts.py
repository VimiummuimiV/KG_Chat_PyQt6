import sqlite3
import json
import os
import platform
import time
from pathlib import Path
from typing import Optional, Dict, List

from helpers.data import get_data_dir

class AccountManager:
    """Manage multiple XMPP accounts using local SQLite database"""
   
    def __init__(self, config_path: str = 'settings/config.json'):
        self.config_path = config_path
        data_dir = get_data_dir("accounts")
        self.db_path = str(data_dir / "accounts.db")
        self.config = self._load_config()
        self._init_database()
   
    def _init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                login TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                avatar TEXT,
                background TEXT,
                active INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()
   
    def _load_config(self) -> dict:
        for i in range(3):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content: return json.loads(content)
                time.sleep(0.1)
            except:
                if i == 2: return {}
                time.sleep(0.1)
        return {}
   
    def add_account(self, user_id: str, login: str, password: str, 
                    avatar: str = None, background: str = None, 
                    set_active: bool = False) -> bool:
        """Add new account"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
           
            if set_active:
                cursor.execute('UPDATE accounts SET active = 0')
           
            cursor.execute('''
                INSERT INTO accounts (user_id, login, password, avatar, background, active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, login, password, avatar, background, 1 if set_active else 0))
           
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
   
    def remove_account(self, login: str) -> bool:
        """Remove account by login"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM accounts WHERE login = ?', (login,))
            deleted = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return deleted
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
   
    def get_active_account(self) -> Optional[Dict]:
        """Get active account"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM accounts WHERE active = 1 LIMIT 1')
        row = cursor.fetchone()
        conn.close()
       
        if row:
            return self._row_to_dict(row)
       
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
        """List all accounts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM accounts ORDER BY id')
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(row) for row in rows]
   
    def switch_account(self, login: str) -> bool:
        """Switch active account"""
        account = self.get_account_by_login(login)
        if not account:
            return False
       
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE accounts SET active = 0')
            cursor.execute('UPDATE accounts SET active = 1 WHERE login = ?', (login,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def update_account_color(self, login: str, background: str) -> bool:
        """Update account background color"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE accounts SET background = ? WHERE login = ?', (background, login))
            updated = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return updated
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
   
    def _row_to_dict(self, row) -> Dict:
        """Convert row to dict"""
        if not row:
            return None
        return {
            'id': row[0],
            'user_id': row[1],
            'login': row[2],
            'password': row[3],
            'avatar': row[4],
            'background': row[5],
            'active': bool(row[6])
        }
   
    def get_server_config(self) -> Dict:
        return self.config.get('server', {})
   
    def get_rooms(self) -> List[Dict]:
        return self.config.get('rooms', [])
   
    def get_connection_config(self) -> Dict:
        return self.config.get('connection', {})
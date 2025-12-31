"""User list management"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChatUser:
    """Chat user"""
    user_id: str
    login: str
    jid: str
    avatar: Optional[str] = None
    background: Optional[str] = None
    game_id: Optional[str] = None
    affiliation: str = 'none'
    role: str = 'participant'
    status: str = 'available'
    last_seen: datetime = None
    
    def __post_init__(self):
        if self.last_seen is None:
            self.last_seen = datetime.now()
    
    def get_avatar_url(self) -> str:
        """Get full avatar URL"""
        if self.avatar:
            return f"https://klavogonki.ru{self.avatar}"
        return None


class UserList:
    """Manage chat users"""
    
    def __init__(self):
        self.users: Dict[str, ChatUser] = {}
    
    def add_or_update(self, jid: str, login: str, user_id: str = None, 
                      avatar: str = None, background: str = None,
                      game_id: str = None, affiliation: str = 'none',
                      role: str = 'participant') -> ChatUser:
        """Add or update user"""
        
        if not user_id and '#' in jid:
            user_id = jid.split('#')[0].split('/')[-1]
        
        if jid in self.users:
            user = self.users[jid]
            user.login = login
            if user_id:
                user.user_id = user_id
            if avatar:
                user.avatar = avatar
            if background:
                user.background = background
            if game_id:
                user.game_id = game_id
            user.affiliation = affiliation
            user.role = role
            user.status = 'available'
            user.last_seen = datetime.now()
        else:
            user = ChatUser(
                user_id=user_id or '',
                login=login,
                jid=jid,
                avatar=avatar,
                background=background,
                game_id=game_id,
                affiliation=affiliation,
                role=role
            )
            self.users[jid] = user
        
        return user
    
    def remove(self, jid: str) -> bool:
        """Remove user"""
        if jid in self.users:
            self.users[jid].status = 'unavailable'
            return True
        return False
    
    def get(self, jid: str) -> Optional[ChatUser]:
        """Get user by JID"""
        return self.users.get(jid)
    
    def get_all(self) -> List[ChatUser]:
        """Get all users"""
        return list(self.users.values())
    
    def get_online(self) -> List[ChatUser]:
        """Get online users"""
        return [u for u in self.users.values() if u.status == 'available']
    
    def format_list(self, online_only: bool = False) -> str:
        """Format user list"""
        users = self.get_online() if online_only else self.get_all()
        
        if not users:
            return "👥 No users"
        
        result = f"👥 Users ({len(users)}):\n" + "═" * 40 + "\n"
        for user in sorted(users, key=lambda u: u.login.lower()):
            emoji = "🟢" if user.status == 'available' else "⚫"
            avatar = " 🖼️" if user.avatar else ""
            game = f"\n   └─ 🎮 Game #{user.game_id}" if user.game_id else ""
            bg = f" [{user.background}]" if user.background else ""
            result += f"{emoji} {user.login}{avatar}{bg}{game}\n"
        result += "═" * 40
        return result
    
    def clear(self):
        """Clear all users"""
        self.users.clear()
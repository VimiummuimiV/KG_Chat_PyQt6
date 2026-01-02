import requests
from typing import Optional
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QByteArray


def load_avatar_by_id(user_id: str, timeout: int = 3) -> Optional[QPixmap]:
    if not user_id or not str(user_id).strip():
        return None
    
    try:
        url = f"https://klavogonki.ru/storage/avatars/{user_id}_big.png"
        response = requests.get(url, timeout=timeout)
        
        if response.status_code != 200:
            return None
        
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(response.content))
        
        return pixmap if not pixmap.isNull() else None
    except:
        return None
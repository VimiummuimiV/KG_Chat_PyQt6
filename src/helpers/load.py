import requests
from typing import Optional
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath
from PyQt6.QtCore import QByteArray, Qt, QRectF

# Load big user avatar from Klavogonki by user ID
def load_avatar_by_id(user_id: str, timeout: int = 3) -> Optional[QPixmap]:
    # Load user avatar from Klavogonki by user ID
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


def make_rounded_pixmap(pixmap: QPixmap, size: int, radius: int = 10) -> QPixmap:
    # Create rounded rectangle pixmap with smooth scaling
    scaled = pixmap.scaled(
        size, size, 
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )
    
    output = QPixmap(size, size)
    output.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    # Rounded rectangle clipping path
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)
    
    # Center and draw
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    
    return output

# Load username car color by user ID used for username color display
def load_color_by_id(user_id):
    url = f"https://klavogonki.ru/api/profile/get-summary?id={user_id}"
    return requests.get(url).json()['car']['color']

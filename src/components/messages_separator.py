"""Message Separator Components"""
from PyQt6.QtGui import QPainter, QColor, QFontMetrics, QPen
from PyQt6.QtCore import Qt, QRect, QModelIndex
from datetime import datetime


class NewMessagesSeparator:
    """Component for rendering and managing 'New Messages' separator"""
    
    @staticmethod
    def create_marker():
        """Create a new messages marker MessageData instance"""
        from ui.message_model import MessageData
        return MessageData(
            timestamp=datetime.now(),
            is_new_messages_marker=True
        )
    
    @staticmethod
    def render(painter: QPainter, rect: QRect, font, is_dark_theme: bool):
        """
        Render the new messages separator
        
        Args:
            painter: QPainter instance
            rect: QRect for the rendering area
            font: QFont for the text
            is_dark_theme: bool indicating if dark theme is active
        """
        painter.save()
        
        # Theme-adaptive colors with emphasis
        if is_dark_theme:
            line_color = QColor("#FF6B6B")  # Red accent
            bg_color = QColor("#3A2A2A")    # Dark red tint
            text_color = QColor("#FFB4B4")  # Light red
        else:
            line_color = QColor("#FF4444")
            bg_color = QColor("#FFE8E8")
            text_color = QColor("#CC0000")
        
        mid_y = rect.y() + rect.height() // 2
        
        # Draw horizontal line (slightly thicker than date separator)
        pen = QPen(line_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(rect.x() + 20, mid_y, rect.x() + rect.width() - 80, mid_y)
        
        # Prepare text with fire emoji
        marker_text = "🔥 NEW"
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(marker_text) + 24
        text_height = fm.height() + 8
        
        # Calculate position (right side)
        text_x = rect.x() + rect.width() - text_width - 20
        text_y = mid_y - text_height // 2
        
        # Draw rounded background box
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawRoundedRect(text_x, text_y, text_width, text_height, 6, 6)
        
        # Draw border around box (adjusted inward to prevent clipping)
        border_width = 2
        painter.setPen(QPen(line_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Adjust rectangle inward by half the border width to prevent clipping
        adjusted_rect = QRect(
            text_x + border_width // 2,
            text_y + border_width // 2,
            text_width - border_width,
            text_height - border_width
        )
        painter.drawRoundedRect(adjusted_rect, 6, 6)
        
        # Draw text
        painter.setPen(text_color)
        text_rect = QRect(text_x, text_y, text_width, text_height)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, marker_text)
        
        painter.restore()
    
    @staticmethod
    def get_height() -> int:
        """Get the recommended height for the separator"""
        return 35
    
    @staticmethod
    def remove_from_model(model):
        """
        Remove all new messages markers from a message model
        
        Args:
            model: MessageListModel instance
        """
        if not hasattr(model, '_messages') or not model._messages:
            return
        
        # Find and remove new messages marker
        marker_indices = [i for i, msg in enumerate(model._messages) 
                         if getattr(msg, 'is_new_messages_marker', False)]
        
        for index in reversed(marker_indices):
            model.beginRemoveRows(QModelIndex(), index, index)
            model._messages.pop(index)
            model.endRemoveRows()


class ChatlogDateSeparator:
    """Component for rendering chatlog date separators"""
    
    @staticmethod
    def render(painter: QPainter, rect: QRect, date_str: str, font, is_dark_theme: bool):
        """
        Render a chatlog date separator
        
        Args:
            painter: QPainter instance
            rect: QRect for the rendering area
            date_str: Date string to display
            font: QFont for the text
            is_dark_theme: bool indicating if dark theme is active
        """
        painter.save()
        
        # Theme-adaptive colors
        if is_dark_theme:
            line_color = QColor("#444444")
            bg_color = QColor("#2A2A2A")
            text_color = QColor("#AAAAAA")
        else:
            line_color = QColor("#BBBBBB")
            bg_color = QColor("#E8E8E8")
            text_color = QColor("#444444")
        
        mid_y = rect.y() + rect.height() // 2
        
        # Draw horizontal line
        painter.setPen(line_color)
        painter.drawLine(rect.x() + 20, mid_y, rect.x() + rect.width() - 20, mid_y)
        
        # Prepare date text
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(date_str) + 24
        text_height = fm.height() + 8
        
        # Calculate text box position (centered)
        text_x = rect.x() + (rect.width() - text_width) // 2
        text_y = mid_y - text_height // 2
        
        # Draw rounded background box
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawRoundedRect(text_x, text_y, text_width, text_height, 4, 4)
        
        # Draw date text
        painter.setPen(text_color)
        text_rect = QRect(text_x, text_y, text_width, text_height)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, date_str)
        
        painter.restore()
    
    @staticmethod
    def get_height() -> int:
        """Get the recommended height for the separator"""
        return 30

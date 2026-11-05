"""Rich message body widget shown inside a popup."""

from typing import List, Optional, Tuple

from PyQt6.QtCore import pyqtSignal, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QCursor, QPainter
from PyQt6.QtWidgets import QWidget

from ui.messages.message_renderer import MessageRenderer


class MessageBodyWidget(QWidget):
    """Custom widget that uses MessageRenderer for painting message body"""

    content_resized = pyqtSignal()

    def __init__(self, message_renderer: MessageRenderer, text: str, 
                 is_private: bool = False, is_ban: bool = False, is_system: bool = False,
                 is_competition: bool = False, is_parser: bool = False,
                 players: Optional[list] = None):
        super().__init__()
        self.message_renderer = message_renderer
        self.text = MessageRenderer.emoji_prefix(text, is_private, is_ban, is_system, is_competition, is_parser)
        self.is_private = is_private
        self.is_ban = is_ban
        self.is_system = is_system
        self.is_competition = is_competition
        self.is_parser = is_parser
        self.players = players or []
        self.link_rects: List[Tuple[QRect, str, bool]] = []
        self.chip_rects: List[Tuple[QRect, str]] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        # Initial height estimate
        self.setFixedHeight(50)

        # Repaint when copy highlight clears
        self.message_renderer.refresh_view.connect(self.update)

        # Animation timer for animated emoticons (GIFs)
        self.animation_timer = None
        if self.message_renderer.has_animated_emoticons(text):
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self.update)  # Trigger repaint
            self.animation_timer.start(33)  # ~30 FPS

    def _calculate_height(self, width: int) -> int:
        height = self.message_renderer.calculate_content_height(self.text, width)
        if self.players:
            height += 6 + self.message_renderer.calculate_chips_height(self.players, width)
        return height

    def update_content(self, text: str, players: Optional[list] = None):
        """Update text and player chips in place, without recreating the notification."""
        self.text = MessageRenderer.emoji_prefix(text, self.is_private, self.is_ban, self.is_system,
                                                  self.is_competition, self.is_parser)
        if players is not None:
            self.players = players
        new_height = self._calculate_height(self.width() if self.width() > 0 else 400)
        if new_height != self.height():
            self.setFixedHeight(new_height)
            self.content_resized.emit()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Paint content and get link rectangles
        self.link_rects = self.message_renderer.paint_content(
            painter,
            0, 0,
            self.width(),
            self.text,
            None,  # row
            self.is_private,
            self.is_ban,
            self.is_system,
            self.is_competition,
            self.is_parser,
        )

        if self.players:
            content_height = self.message_renderer.calculate_content_height(self.text, self.width())
            _, self.chip_rects = self.message_renderer.paint_chips(
                painter, 0, content_height + 6, self.width(), self.players, self.message_renderer.is_dark_theme
            )
        else:
            self.chip_rects = []

        # Update height if needed
        calculated_height = self._calculate_height(self.width())
        if self.height() != calculated_height:
            self.setFixedHeight(calculated_height)

    def sizeHint(self):
        width = self.width() if self.width() > 0 else 400
        return QSize(width, self._calculate_height(width))

    def mouseMoveEvent(self, event):
        is_over_link = MessageRenderer.is_over_link(self.link_rects, event.pos())
        is_over_chip = any(r.contains(event.pos()) for r, name in self.chip_rects if name and name != "…")
        self.setCursor(QCursor(
            Qt.CursorShape.PointingHandCursor if (is_over_link or is_over_chip)
            else Qt.CursorShape.ArrowCursor
        ))
        super().mouseMoveEvent(event)

    def get_link_at_pos(self, pos) -> Optional[Tuple[str, bool]]:
        return MessageRenderer.get_link_at_pos(self.link_rects, pos)

    def get_chip_at_pos(self, pos) -> Optional[str]:
        for rect, name in self.chip_rects:
            if rect.contains(pos) and name and name != "…":
                return name
        return None

    def cleanup(self):
        """Cleanup animation timer"""
        if self.animation_timer:
            self.animation_timer.stop()
            self.animation_timer = None

"""Rich message body widget shown inside a popup."""

from typing import List, Optional, Tuple

from PyQt6.QtCore import pyqtSignal, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QCursor, QPainter
from PyQt6.QtWidgets import QWidget

from ui.messages.message_layout import TextLayout
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
        self._layout: Optional[TextLayout] = None
        self._layout_key = None
        self._link_rects: List[Tuple[QRect, str, bool]] = []
        self._chip_rects: List[Tuple[QRect, str]] = []
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

    def _body_layout(self, width: int) -> TextLayout:
        """The wrapped text; rebuilt only when the text, the width or the font changed."""
        key = (self.text, width, self.message_renderer.layout_revision, self.message_renderer.mention_pattern())
        if key != self._layout_key:
            has_mentions = not (self.is_system or self.is_private or self.is_ban or self.is_parser)
            self._layout = self.message_renderer.layout_body(self.text, width, has_mentions)
            self._layout_key = key
        return self._layout

    def _calculate_height(self, width: int) -> int:
        height = self._body_layout(width).height
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
        body = self._body_layout(self.width())
        self._link_rects = self.message_renderer.paint_layout(
            painter,
            body,
            0, 0,
            self.is_private,
            self.is_ban,
            self.is_system,
            self.is_competition,
            self.is_parser,
        )

        if self.players:
            _, self._chip_rects = self.message_renderer.paint_chips(
                painter, 0, body.height + 6, self.width(), self.players, self.message_renderer.is_dark_theme
            )
        else:
            self._chip_rects = []

        # Update height if needed
        calculated_height = self._calculate_height(self.width())
        if self.height() != calculated_height:
            self.setFixedHeight(calculated_height)

    def sizeHint(self):
        width = self.width() if self.width() > 0 else 400
        return QSize(width, self._calculate_height(width))

    def mouseMoveEvent(self, event):
        is_over_link = MessageRenderer.is_over_link(self._link_rects, event.pos())
        is_over_chip = any(r.contains(event.pos()) for r, name in self._chip_rects if name and name != "…")
        self.setCursor(QCursor(
            Qt.CursorShape.PointingHandCursor if (is_over_link or is_over_chip)
            else Qt.CursorShape.ArrowCursor
        ))
        super().mouseMoveEvent(event)

    def get_link_at_pos(self, pos) -> Optional[Tuple[str, bool]]:
        return MessageRenderer.get_link_at_pos(self._link_rects, pos)

    def get_chip_at_pos(self, pos) -> Optional[str]:
        for rect, name in self._chip_rects:
            if rect.contains(pos) and name and name != "…":
                return name
        return None

    def cleanup(self):
        """Cleanup animation timer"""
        if self.animation_timer:
            self.animation_timer.stop()
            self.animation_timer = None

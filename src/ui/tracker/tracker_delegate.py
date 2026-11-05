"""Tracker history row painting and clicks."""

from datetime import datetime
from typing import Dict

from PyQt6.QtCore import pyqtSignal, QEvent, QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QCursor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from components.flash_highlight import FlashFade, highlight_color, paint_flash, RowFlashMixin
from components.presence_badge import presence_badge_style
from helpers.cache import get_cache
from helpers.fonts.fonts import FontType, get_font
from ui.messages.messages_separator import DateSeparator


class TrackerEventDelegate(RowFlashMixin, QStyledItemDelegate):
    """Renders tracker events (time, type badge, username, game id) with virtual scrolling"""

    filter_clicked = pyqtSignal(str, bool)       # login, ctrl_pressed
    type_filter_clicked = pyqtSignal(str, bool)  # event_type, ctrl_pressed
    date_filter_clicked = pyqtSignal(str, bool)  # date_str, ctrl_pressed

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        theme = config.get("ui", "theme") or "dark"
        self.is_dark_theme = (theme == "dark")

        self.padding = 8
        self.spacing = config.get("ui", "spacing", "widget_elements") or 6

        self.click_rects: Dict[int, Dict] = {}
        self.list_view = None

        self.row_flashes: dict[int, FlashFade] = {}

        self._reload_fonts()

    def _reload_fonts(self):
        self.time_font = get_font(FontType.TEXT)
        self.badge_font = get_font(FontType.TEXT)
        self.name_font = get_font(FontType.TEXT)
        self.gid_font = get_font(FontType.TEXT)

    def set_list_view(self, list_view):
        self.list_view = list_view

    def cleanup(self):
        for flash in self.row_flashes.values():
            flash.timer.stop()
        self.row_flashes.clear()
        self.list_view = None
        self.click_rects.clear()

    def clear_click_rects(self):
        self.click_rects.clear()

    def update_theme(self):
        theme = self.config.get("ui", "theme") or "dark"
        self.is_dark_theme = (theme == "dark")
        self._reload_fonts()

    def update_fonts(self):
        """Call after text font size change so row heights and paint use the new size."""
        self._reload_fonts()
        self.click_rects.clear()
        if self.list_view is not None:
            try:
                self.list_view.scheduleDelayedItemsLayout()
                self.list_view.viewport().update()
            except RuntimeError:
                pass

    def _row_height(self) -> int:
        name_h = QFontMetrics(self.name_font).height()
        badge_h = QFontMetrics(self.badge_font).height() + 6
        return max(name_h, badge_h) + 4

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        width = option.rect.width()
        if width <= 0 and self.list_view is not None:
            try:
                width = self.list_view.viewport().width()
            except RuntimeError:
                width = 0
        if width <= 0:
            width = 800
        event = index.data(Qt.ItemDataRole.DisplayRole) or {}
        if event.get('is_separator'):
            return QSize(width, DateSeparator.get_height())
        return QSize(width, self._row_height())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        event = index.data(Qt.ItemDataRole.DisplayRole)
        if not event:
            return

        row = index.row()
        self.click_rects[row] = {'username': QRect(), 'badge': QRect(), 'separator': QRect()}

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        row_flash = self.row_flashes.get(row)
        if row_flash is not None and row_flash.opacity > 0:
            paint_flash(painter, option.rect, highlight_color(self.is_dark_theme), row_flash.opacity)

        if event.get('is_separator'):
            DateSeparator.render(
                painter,
                option.rect,
                event.get('date_str') or '',
                self.time_font,
                self.is_dark_theme,
            )
            self.click_rects[row]['separator'] = QRect(option.rect)
            painter.restore()
            return

        x = option.rect.x() + self.padding
        y = option.rect.y()
        h = option.rect.height()

        ts = event.get('timestamp', 0)
        try:
            time_text = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        except Exception:
            time_text = "—"
        painter.setFont(self.time_font)
        painter.setPen(QColor("#888888"))
        ts_fm = QFontMetrics(self.time_font)
        ts_width = ts_fm.horizontalAdvance(time_text)
        painter.drawText(
            QRect(x, y, ts_width, h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            time_text,
        )
        x += ts_width + self.spacing

        event_type = event.get('type', '') or ''
        badge_text, badge_bg, badge_fg, badge_border = presence_badge_style(
            event_type, self.is_dark_theme
        )
        painter.setFont(self.badge_font)
        badge_fm = QFontMetrics(self.badge_font)
        badge_width = badge_fm.horizontalAdvance(badge_text) + 12
        badge_height = badge_fm.height() + 6
        badge_rect = QRect(x, y + (h - badge_height) // 2, badge_width, badge_height)
        border_width = 2
        inset = border_width // 2
        pen = QPen(QColor(badge_border))
        pen.setWidth(border_width)
        painter.setPen(pen)
        painter.setBrush(QColor(badge_bg))
        painter.drawRoundedRect(
            badge_rect.adjusted(inset, inset, -inset, -inset), 4, 4
        )
        painter.setPen(QColor(badge_fg))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        self.click_rects[row]['badge'] = badge_rect
        x += badge_width + self.spacing

        login = event.get('login', '') or ''
        painter.setFont(self.name_font)
        name_fm = QFontMetrics(self.name_font)
        name_color = get_cache().get_username_color(login, self.is_dark_theme)
        painter.setPen(QColor(name_color))
        name_width = name_fm.horizontalAdvance(login)
        name_rect = QRect(x, y, name_width, h)
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            login,
        )
        self.click_rects[row]['username'] = name_rect
        x += name_width + self.spacing

        game_id = event.get('game_id')
        if game_id and event_type == 'game':
            gid_text = f"#{game_id}"
            painter.setFont(self.gid_font)
            painter.setPen(QColor("#888888"))
            gid_width = QFontMetrics(self.gid_font).horizontalAdvance(gid_text)
            painter.drawText(
                QRect(x, y, gid_width, h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                gid_text,
            )

        painter.restore()

    def editorEvent(self, event: QEvent, model, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        row = index.row()
        rects = self.click_rects.get(row)

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton or not rects:
                return super().editorEvent(event, model, option, index)
            data = index.data(Qt.ItemDataRole.DisplayRole) or {}
            ctrl_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            pos = event.pos()
            if data.get('is_separator') and rects.get('separator') and rects['separator'].contains(pos):
                date_str = data.get('date_str') or ''
                if date_str:
                    self.date_filter_clicked.emit(date_str, ctrl_pressed)
                return True
            if rects['username'].contains(pos) and data.get('login'):
                self.filter_clicked.emit(data['login'], ctrl_pressed)
                return True
            if rects['badge'].contains(pos) and data.get('type'):
                self.type_filter_clicked.emit(data['type'], ctrl_pressed)
                return True

        elif event.type() == QEvent.Type.MouseMove:
            if rects and self.list_view:
                pos = event.pos()
                is_over_clickable = (
                    rects['username'].contains(pos)
                    or rects['badge'].contains(pos)
                    or (rects.get('separator') and rects['separator'].contains(pos))
                )
                cursor = Qt.CursorShape.PointingHandCursor if is_over_clickable else Qt.CursorShape.ArrowCursor
                self.list_view.setCursor(QCursor(cursor))

        return super().editorEvent(event, model, option, index)

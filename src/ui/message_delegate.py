"""Message delegate for rendering with virtual scrolling"""
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QApplication, QTextEdit, QMenu
from PyQt6.QtCore import Qt, QSize, QRect, QModelIndex, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QPainter, QFontMetrics, QColor, QCursor, QMouseEvent, QKeySequence

from components.messages_separator import NewMessagesSeparator, DateSeparator
from helpers.flash_highlight import paint_flash, highlight_color, FlashFade
from helpers.emoticons import EmoticonManager
from helpers.fonts import get_font, FontType
from helpers.me_action import format_me_action
from helpers.cache import get_cache
from ui.message_renderer import MessageRenderer
from helpers.create import _render_svg_icon
from helpers.translate import tr


_DARK  = dict(bg="#0A0A0A", fg="#D4D4D4", sel_bg="#2E7D32", sel_fg="#E8F5E9")
_LIGHT = dict(bg="#C8C8C8", fg="#1A1A1A", sel_bg="#388E3C", sel_fg="#FFFFFF")


class _TextSelectorOverlay(QTextEdit):
    """Self-sizing, self-closing read-only text overlay for copy/select."""

    def __init__(self, text: str, font, row_rect: QRect, is_dark: bool, viewport,
                 reply_callback=None, paste_callback=None,
                 username: str = "", timestamp=None):
        super().__init__(viewport)
        self._reply_callback = reply_callback
        self._paste_callback = paste_callback
        self._username = username
        self._timestamp = timestamp
        self.setReadOnly(True)
        self.setPlainText(text)
        self.setFont(font)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        c = _DARK if is_dark else _LIGHT
        self.setStyleSheet(f"""
            QTextEdit {{
                background   : {c['bg']};
                color        : {c['fg']};
                border       : none;
                border-radius: 3px;
                padding      : 0px;
                selection-background-color: {c['sel_bg']};
                selection-color           : {c['sel_fg']};
            }}
        """)
        self.document().setDocumentMargin(0)

        self.setGeometry(row_rect)
        self.show()
        self.setFocus()

        QApplication.instance().installEventFilter(self)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.textCursor().hasSelection():
            self._show_context_menu(event.globalPosition().toPoint())

    def contextMenuEvent(self, event):
        self._show_context_menu(event.globalPos())

    def _copy_text(self):
        selected = self.textCursor().selectedText().strip()
        QApplication.clipboard().setText(selected or self.toPlainText())
        self.close()

    def _paste_text(self):
        selected = self.textCursor().selectedText().strip()
        text = selected or self.toPlainText()
        self._paste_callback(text)
        self.close()

    def _reply(self):
        selected = self.textCursor().selectedText().strip()
        self._reply_callback(self._username, selected or self.toPlainText(), self._timestamp)
        self.close()

    def _show_context_menu(self, global_pos):
        icons_path = Path(__file__).parent.parent / "icons"
        def icon(name): return _render_svg_icon(icons_path / name, 16)
        menu = QMenu(self)
        if self._reply_callback is not None:
            reply_act = menu.addAction(icon("reply.svg"), tr("Reply", "Ответить"))
            reply_act.setShortcut(QKeySequence("R"))
            reply_act.triggered.connect(self._reply)
            menu.addSeparator()
        copy_act = menu.addAction(icon("clipboard.svg"), tr("Copy", "Копировать"))
        copy_act.setShortcut(QKeySequence("C"))
        copy_act.triggered.connect(self._copy_text)
        if self._paste_callback is not None:
            paste_act = menu.addAction(icon("add-circle.svg"), tr("Paste", "Вставить"))
            paste_act.setShortcut(QKeySequence("V"))
            paste_act.triggered.connect(self._paste_text)
        menu.exec(global_pos)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if QApplication.activePopupWidget() is not None:
                return False
            click_pos = event.globalPosition().toPoint()
            overlay_rect = QRect(self.mapToGlobal(self.rect().topLeft()), self.size())
            if not overlay_rect.contains(click_pos):
                self.close()
        elif event.type() == QEvent.Type.KeyPress and not event.modifiers():
            # Physical key → action, layout-independent via nativeVirtualKey fallback.
            # Qt key values for Latin letters equal their ASCII codes, as does
            # Windows Virtual Key codes — so nativeVirtualKey() works regardless of layout.
            actions = {
                Qt.Key.Key_Escape: self.close,
                Qt.Key.Key_C: self._copy_text,
                **(({Qt.Key.Key_R: self._reply}) if self._reply_callback is not None else {}),
                **(({Qt.Key.Key_V: self._paste_text}) if self._paste_callback is not None else {}),
            }
            action = actions.get(event.key()) or actions.get(event.nativeVirtualKey())
            if action:
                action()
                return True
        return False

    def close(self):
        QApplication.instance().removeEventFilter(self)
        self.deleteLater()


class MessageDelegate(QStyledItemDelegate):
    """Delegate for rendering messages with virtual scrolling"""
 
    row_needs_refresh = pyqtSignal(int)
    message_clicked = pyqtSignal(int)
    separator_clicked = pyqtSignal(str)  # date_str of clicked chatlog date separator
    timestamp_clicked = pyqtSignal(str)  # full chatlog URL for the clicked message
    chatlog_link_clicked = pyqtSignal(str, str)  # date_str, time_str ("" if none) - chatlog URL clicked in a message body
    presence_log_clicked = pyqtSignal(int)
    competition_entered = pyqtSignal(int)  # game_id - competition link opened in browser from a message
 
    def __init__(
        self,
        config,
        emoticon_manager: EmoticonManager,
        parent=None
        ):
        super().__init__(parent)
        self.config = config
        self.emoticon_manager = emoticon_manager
     
        theme = config.get("ui", "theme") or "dark"
        self.is_dark_theme = (theme == "dark")
        self.bg_hex = "#1E1E1E" if self.is_dark_theme else "#FFFFFF"

        self.body_font = get_font(FontType.TEXT)
        self.timestamp_font = get_font(FontType.TEXT)
     
        self.compact_mode = False
        self.padding = config.get("ui", "message", "padding") or 2
        self.spacing = config.get("ui", "message", "element_spacing") or 4
     
        self.click_rects: Dict[int, Dict] = {}
        self.reply_callback = None
        self.paste_callback = None
        self.reply_includes_timestamp = False  # Chatlog sets True; realtime messages omit timestamp
        self.my_username = None # Store username for mention highlighting
        self.highlight_text = "" # Active search term to highlight in message bodies

        # Animation support for GIF emoticons
        self.list_view = None
        self.animated_rows = set()
        self.animation_frames = {}
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animations)
        self.animation_timer.start(33) # 30 FPS

        # Text selector overlay
        self._text_selector = None

        # Highlight support for clicked messages - independent fade per row so a
        # new click doesn't cut off an older row's animation still playing out
        self.row_flashes: dict[int, FlashFade] = {}

        # Connect signal for refreshing rows when async metadata (like link previews) is loaded
        self.row_needs_refresh.connect(self._do_refresh_row)
        
        # Create message renderer
        self.message_renderer = None
 
    def set_my_username(self, username: str):
        """Set the current user's username for mention highlighting"""
        self.my_username = username
        if self.message_renderer:
            self.message_renderer.set_my_username(username)

    def set_highlight_text(self, text: str):
        """Set the active search term to highlight in message bodies."""
        text = text or ""
        if self.highlight_text != text:
            self.highlight_text = text
            if self.list_view:
                self.list_view.viewport().update()

    def set_input_field(self, input_field, include_timestamp: bool = False):
        """Configure reply and paste callbacks for the text selector overlay."""
        if not input_field:
            self.reply_callback = None
            self.paste_callback = None
            return

        def _reply(username: str, text: str, timestamp=None):
            reply_text = MessageDelegate.format_reply_text(username, text, timestamp)
            input_field.setText(reply_text)
            input_field.setCursorPosition(len(reply_text))
            input_field.setFocus()

        def _paste(text: str):
            cursor_pos = input_field.cursorPosition()
            current = input_field.text() or ""
            input_field.setText(current[:cursor_pos] + text + current[cursor_pos:])
            input_field.setCursorPosition(cursor_pos + len(text))
            input_field.setFocus()

        self.reply_callback = _reply
        self.paste_callback = _paste
        self.reply_includes_timestamp = include_timestamp
 
    def set_list_view(self, list_view):
        self.list_view = list_view
        
        # Initialize message renderer with parent for viewers
        if list_view and not self.message_renderer:
            self.message_renderer = MessageRenderer(
                self.config,
                self.emoticon_manager,
                self.is_dark_theme,
                parent_widget=list_view.window()
            )
            # Set username for mention highlighting
            if self.my_username:
                self.message_renderer.set_my_username(self.my_username)
            # Connect refresh signals
            self.message_renderer.refresh_row.connect(self._refresh_row)
            self.message_renderer.refresh_view.connect(lambda: self.list_view.viewport().update())
            self.message_renderer.chatlog_link_clicked.connect(self.chatlog_link_clicked.emit)
 
    def cleanup(self):
        self.list_view = None
        for flash in self.row_flashes.values():
            flash.timer.stop()
        self.row_flashes.clear()
        if self.message_renderer:
            self.message_renderer.cleanup()
 
    def update_theme(self):
        theme = self.config.get("ui", "theme") or "dark"
        self.is_dark_theme = (theme == "dark")
        self.bg_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
        if self.message_renderer:
            self.message_renderer.update_theme(self.is_dark_theme)
 
    def set_compact_mode(self, compact: bool):
        if self.compact_mode != compact:
            self.compact_mode = compact

    @staticmethod
    def _get_display_body(msg) -> tuple:
        """Return (display_body, is_system) with /me formatting and type emoji prefix applied."""
        body, is_me = format_me_action(msg.body, msg.username)
        is_competition = bool(getattr(msg, 'is_competition', False))
        is_parser = bool(getattr(msg, 'is_parser', False))
        is_system = is_me or bool(getattr(msg, 'is_system', False))
        body = MessageRenderer._emoji_prefix(
            body, msg.is_private, msg.is_ban, is_system, is_competition, is_parser
        )
        # layout treats competition like system (no username column)
        return body, is_system or is_competition

    @staticmethod
    def format_reply_text(username: str, text: str, timestamp=None) -> str:
        time_prefix = ""
        if timestamp:
            date_str = timestamp.strftime("%Y-%m-%d")
            time_str = timestamp.strftime("%H:%M:%S")
            url = f"https://klavogonki.ru/chatlogs/{date_str}.html#{time_str}"
            time_prefix = f"{url} "
        username_prefix = f"{username}: " if username else ""
        return f"{time_prefix}{username_prefix}{text} ↩ "

    @staticmethod
    def _chatlog_url(msg) -> str:
        date_str = getattr(msg, 'date', None) or msg.timestamp.strftime("%Y-%m-%d")
        return f"https://klavogonki.ru/chatlogs/{date_str}.html#{msg.get_time_str()}"

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        msg = index.data(Qt.ItemDataRole.DisplayRole)
        if not msg:
            return QSize(200, 50)
     
        # Chatlog date separator
        if getattr(msg, 'is_separator', False):
            return QSize(option.rect.width(), DateSeparator.get_height())

        # New messages marker
        if getattr(msg, 'is_new_messages_marker', False):
            return QSize(option.rect.width(), NewMessagesSeparator.get_height())

        width = option.rect.width()
        if width <= 0 and self.list_view is not None:
            try:
                width = self.list_view.viewport().width()
            except RuntimeError:
                width = 0
        if width <= 0:
            width = 800
        row = index.row()
        if getattr(msg, 'is_presence_log', False):
            height = self._presence_log_height(msg, width)
        else:
            height = self._calculate_compact_height(msg, width, row) if self.compact_mode else self._calculate_normal_height(msg, width, row)
        return QSize(width, height)

    def _presence_log_height(self, msg, width: int) -> int:
        if not self.message_renderer:
            return 50
        fm = QFontMetrics(self.body_font)
        ts_fm = QFontMetrics(self.timestamp_font)
        line_h = max(fm.height(), ts_fm.height())
        entries = getattr(msg, 'presence_entries', None) or []
        ts_w = ts_fm.horizontalAdvance(msg.get_time_str()) + self.spacing
        content_w = max(width - 2 * self.padding - (0 if self.compact_mode else ts_w), 50)
        content_h = self.message_renderer.calculate_presence_entries_height(entries, content_w)
        if self.compact_mode:
            return min(self.padding + line_h + 2 + content_h + self.padding, 500)
        return min(max(line_h, content_h) + 2 * self.padding, 500)
 
    def _calculate_compact_height(self, msg, width: int, row: Optional[int] = None) -> int:
        if not self.message_renderer:
            return 50
        
        fm = QFontMetrics(self.body_font)
        header_height = max(fm.height(), QFontMetrics(self.timestamp_font).height())
        display_body, _ = self._get_display_body(msg)
        content_height = self.message_renderer.calculate_content_height(display_body, width - 2 * self.padding, row)
        chips_height = self._chips_height(msg, width - 2 * self.padding)
        return min(self.padding + header_height + 2 + content_height + chips_height + self.padding, 500)
 
    def _calculate_normal_height(self, msg, width: int, row: Optional[int] = None) -> int:
        if not self.message_renderer:
            return 50
        
        fm = QFontMetrics(self.body_font)
        fm_ts = QFontMetrics(self.timestamp_font)
     
        time_str = msg.get_time_str()
        timestamp_width = fm_ts.horizontalAdvance(time_str) + self.spacing
        username_width = fm.horizontalAdvance(msg.username) + self.spacing
     
        content_width = max(width - timestamp_width - username_width - 2 * self.padding, 200)
     
        display_body, _ = self._get_display_body(msg)
        content_height = self.message_renderer.calculate_content_height(display_body, content_width, row)
        chips_height = self._chips_height(msg, width - 2 * self.padding)
        label_height = max(fm.height(), fm_ts.height())
        return min(max(label_height, content_height) + chips_height + 2 * self.padding, 500)

    def _chips_height(self, msg, width: int) -> int:
        players = getattr(msg, 'competition_players', None)
        if not players or not self.message_renderer:
            return 0
        return self.spacing + self.message_renderer.calculate_chips_height(players, width)
 
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        msg = index.data(Qt.ItemDataRole.DisplayRole)
        if not msg:
            return
  
        # Handle chatlog date separator
        if getattr(msg, 'is_separator', False):
            DateSeparator.render(
                painter,
                option.rect,
                msg.date_str,
                self.timestamp_font,
                self.is_dark_theme
            )
            return

        # Handle new messages marker
        if getattr(msg, 'is_new_messages_marker', False):
            NewMessagesSeparator.render(
                painter,
                option.rect,
                self.timestamp_font,
                self.is_dark_theme
            )
            return

        row = index.row()

        if self.message_renderer and self.message_renderer.has_animated_emoticons(msg.body):
            self.animated_rows.add(row)
        else:
            self.animated_rows.discard(row)
  
        self.click_rects[row] = {'timestamp': QRect(), 'username': QRect(), 'links': [], 'chips': [], 'presence_users': []}
  
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw highlight overlay if this row is highlighted
        row_flash = self.row_flashes.get(row)
        if row_flash is not None and row_flash.opacity > 0:
            paint_flash(painter, option.rect, highlight_color(self.is_dark_theme), row_flash.opacity)
  
        if getattr(msg, 'is_presence_log', False):
            self._paint_presence_log(painter, option.rect, msg, row, self.compact_mode)
        else:
            self._paint_message(painter, option.rect, msg, row, self.compact_mode)
  
        painter.restore()

    def _paint_presence_log(self, painter: QPainter, rect: QRect, msg, row: int, compact: bool):
        if not self.message_renderer:
            return

        x, y = rect.x() + self.padding, rect.y() + self.padding
        width = rect.width() - 2 * self.padding
        ts_fm = QFontMetrics(self.timestamp_font)
        line_h = max(QFontMetrics(self.body_font).height(), ts_fm.height())
        time_str = msg.get_time_str()
        ts_w = ts_fm.horizontalAdvance(time_str)

        painter.setFont(self.timestamp_font)
        painter.setPen(QColor(self.message_renderer.system_colors["text"]))
        ts_rect = QRect(x, y, ts_w, line_h)
        painter.drawText(ts_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, time_str)
        self.click_rects[row]['timestamp'] = ts_rect
        self.click_rects[row]['username'] = QRect()
        self.click_rects[row]['links'] = []

        if compact:
            cx, cy, cw = x, y + line_h + 2, width
        else:
            cx = x + ts_w + self.spacing
            cy, cw = y, rect.width() - (cx - rect.x()) - self.padding

        _, user_rects = self.message_renderer.paint_presence_entries(
            painter, cx, cy, cw,
            getattr(msg, 'presence_entries', None) or [],
            lambda login: self._get_username_color(login, None),
            line_height=line_h,
        )
        self.click_rects[row]['presence_users'] = user_rects

    def _paint_message(self, painter: QPainter, rect: QRect, msg, row: int, compact: bool):
        """Paint message in either compact or normal mode"""
        if not self.message_renderer:
            return
        
        x, y = rect.x() + self.padding, rect.y() + self.padding
        width = rect.width() - 2 * self.padding
        time_str = msg.get_time_str()
      
        body_fm = QFontMetrics(self.body_font)
        ts_fm = QFontMetrics(self.timestamp_font)
      
        # Resolve display body and message type once - used for both timestamp color and content
        display_body, is_system = self._get_display_body(msg)
        is_competition = bool(getattr(msg, 'is_competition', False))
        is_parser = bool(getattr(msg, 'is_parser', False))
      
        # Paint timestamp - color matches text color for special message types
        painter.setFont(self.timestamp_font)
        ts_color = self.message_renderer.get_timestamp_color(
            msg.is_ban, msg.is_private, is_system, is_competition, is_parser
        )
        ts_width = ts_fm.horizontalAdvance(time_str)
        ts_rect = QRect(x, y, ts_width, ts_fm.height())

        if self.message_renderer.is_copied(self._chatlog_url(msg)):
            self.message_renderer.draw_copy_highlight(painter, ts_rect, ts_color)

        painter.setPen(QColor(ts_color))
        painter.drawText(
            ts_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            time_str
        )
        self.click_rects[row]['timestamp'] = ts_rect
      
        # Determine content position based on mode and message type
        if not is_system:
            # Normal message - paint username
            username_x = x + ts_width + self.spacing
            color = self._get_username_color(msg.username, msg.background_color)
          
            painter.setFont(self.body_font)
            painter.setPen(QColor(color))
          
            un_width = body_fm.horizontalAdvance(msg.username)
            un_rect = QRect(username_x, y, un_width, body_fm.height())
            painter.drawText(
                un_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                msg.username
            )
            self.click_rects[row]['username'] = un_rect
          
            # Content position after username
            content_x = username_x + un_width + self.spacing
        else:
            # System message - skip username, create empty click rect
            self.click_rects[row]['username'] = QRect()
            # Content position right after timestamp
            content_x = x + ts_width + self.spacing
      
        # Calculate content position and dimensions based on mode
        if compact:
            # Compact mode: content below header
            content_y = y + max(body_fm.height(), ts_fm.height()) + 2
            content_width = width
            link_rects = self.message_renderer.paint_content(
                painter, x, content_y, content_width, display_body, row,
                msg.is_private, msg.is_ban, is_system, is_competition,
                is_parser, self.highlight_text
            )
            chips_base_y = content_y
        else:
            # Normal mode: content on same line after username/timestamp
            content_width = rect.width() - (content_x - rect.x()) - self.padding
            link_rects = self.message_renderer.paint_content(
                painter, content_x, y, content_width, display_body, row,
                msg.is_private, msg.is_ban, is_system, is_competition,
                is_parser, self.highlight_text
            )
            chips_base_y = y
        
        self.click_rects[row]['links'] = link_rects

        players = getattr(msg, 'competition_players', None)
        if players:
            content_height = self.message_renderer.calculate_content_height(display_body, content_width, row)
            _, chip_rects = self.message_renderer.paint_chips(
                painter, x, chips_base_y + content_height + self.spacing, width, players, self.is_dark_theme
            )
            self.click_rects[row]['chips'] = chip_rects
 
    def _refresh_row(self, row: int):
        """Request refresh from background thread - emit signal to main thread"""
        self.row_needs_refresh.emit(row)
  
    def _do_refresh_row(self, row: int):
        """Refresh row when async metadata arrives"""
        if not self.list_view or not self.list_view.model() or not (0 <= row < self.list_view.model().rowCount()):
            return
        try:
            model = self.list_view.model()
            idx = model.index(row, 0)
            try:
                model.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])
            except Exception:
                pass
            for attr in ('updateGeometries', 'doItemsLayout'):
                try:
                    getattr(self.list_view, attr, lambda: None)()
                except Exception:
                    pass
            self.list_view.viewport().update()
        except RuntimeError:
            pass

    def editorEvent(self, event: QEvent, model, option: QStyleOptionViewItem,
                    index: QModelIndex) -> bool:
        msg = index.data(Qt.ItemDataRole.DisplayRole)
      
        # Handle clicking on new messages marker to remove it
        if getattr(msg, 'is_new_messages_marker', False):
            if event.type() == QEvent.Type.MouseButtonRelease:
                NewMessagesSeparator.remove_from_model(model)
                return True
            return False
      
        # Clicking a date separator opens the full chatlog for that date
        if getattr(msg, 'is_separator', False):
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self.separator_clicked.emit(msg.date_str)
                return True
            if event.type() == QEvent.Type.MouseMove and self.list_view:
                self.list_view.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                return True
            return False

        if event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event: QMouseEvent = event
            button = mouse_event.button()
            pos = mouse_event.pos()
            row = index.row()
         
            if row not in self.click_rects:
                # Click outside specific elements - treat as message click
                if button == Qt.MouseButton.LeftButton:
                    self.message_clicked.emit(row)
                return super().editorEvent(event, model, option, index)
         
            rects = self.click_rects[row]
         
            # Timestamp/username clicks are handled by the VIEW (ui_messages.py)
            if rects['timestamp'].contains(pos):
                if button == Qt.MouseButton.LeftButton:
                    url = self._chatlog_url(msg)
                    self.timestamp_clicked.emit(url)
                    if self.message_renderer:
                        self.message_renderer.copy_and_highlight(url)
                return True

            # Presence log: LMB outside a username dismisses the whole summary row
            if getattr(msg, 'is_presence_log', False):
                if button == Qt.MouseButton.LeftButton:
                    over_user = any(r.contains(pos) for r, _ in rects.get('presence_users') or [])
                    if not over_user:
                        self.presence_log_clicked.emit(row)
                return True

            if rects['username'].contains(pos) and button == Qt.MouseButton.LeftButton:
                return True

            if rects['username'].contains(pos) and button == Qt.MouseButton.RightButton:
                return True
         
            # Link clicks
            if self.message_renderer:
                is_ctrl = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
                is_shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
                link_data = MessageRenderer.get_link_at_pos(rects['links'], pos)
                if link_data:
                    url, is_media = link_data
                    if button == Qt.MouseButton.LeftButton:
                        global_pos = self.list_view.viewport().mapToGlobal(pos)
                        self.message_renderer.handle_link_lmb(url, is_media, global_pos, is_ctrl, is_shift)
                        gid = getattr(msg, 'competition_game_id', None)
                        if getattr(msg, 'is_competition', False) and gid is not None:
                            self.competition_entered.emit(gid)
                    elif button == Qt.MouseButton.RightButton:
                        self.message_renderer.handle_link_rmb(url)
                    return True
            
            # RMB on body - show selectable text overlay
            if button == Qt.MouseButton.RightButton:
                self._show_text_selector(msg, option.rect)
                return True

            # Click on message content area (not on specific clickable elements)
            if button == Qt.MouseButton.LeftButton:
                self.message_clicked.emit(row)
                return True
     
        elif event.type() == QEvent.Type.MouseButtonDblClick:
            pos = event.pos()
            row = index.row()
         
            if row not in self.click_rects:
                return super().editorEvent(event, model, option, index)
         
            rects = self.click_rects[row]
         
            # Double-click on username handled by view (ui_messages.py)
            if rects['username'].contains(pos):
                return True
     
        elif event.type() == QEvent.Type.MouseMove:
            pos = event.pos()
            row = index.row()
          
            if row in self.click_rects:
                rects = self.click_rects[row]
                is_over_chip = any(r.contains(pos) for r, _ in rects.get('chips') or [])
                is_over_presence_user = any(r.contains(pos) for r, _ in rects.get('presence_users') or [])
                msg = index.data(Qt.ItemDataRole.DisplayRole)
                is_over_clickable = (
                    rects['timestamp'].contains(pos) or
                    rects['username'].contains(pos) or
                    is_over_chip or
                    is_over_presence_user or
                    bool(getattr(msg, 'is_presence_log', False)) or
                    (self.message_renderer and MessageRenderer.is_over_link(rects['links'], pos))
                )
              
                if self.list_view:
                    cursor = (Qt.CursorShape.PointingHandCursor
                             if is_over_clickable
                             else Qt.CursorShape.ArrowCursor)
                    self.list_view.setCursor(QCursor(cursor))
     
        return super().editorEvent(event, model, option, index)
 
    def _show_text_selector(self, msg, rect: QRect):
        if self._text_selector:
            self._text_selector.close()
        self._text_selector = _TextSelectorOverlay(
            msg.body, self.body_font, rect, self.is_dark_theme,
            self.list_view.viewport(),
            reply_callback=self.reply_callback,
            paste_callback=self.paste_callback,
            username=getattr(msg, 'username', '') or getattr(msg, 'login', '') or '',
            timestamp=getattr(msg, 'timestamp', None) if self.reply_includes_timestamp else None,
        )
        self._text_selector.destroyed.connect(lambda: setattr(self, '_text_selector', None))

    def _get_username_color(self, username: str, background: Optional[str]) -> str:
        cache = get_cache()
        # Background is stored by ui_userlist/ui_messages which have user_id context.
        # Delegate only reads the precomputed color.
        return cache.get_username_color(username, self.is_dark_theme)
 
    def _update_animations(self):
        if not self.animated_rows or not self.message_renderer:
            return

        # Poll frames for all movies
        has_changes = False
        for key, movie in list(self.message_renderer._movie_cache.items()):
            try:
                current_frame = movie.currentFrameNumber()
            except Exception:
                continue
            if self.animation_frames.get(key, -1) != current_frame:
                self.animation_frames[key] = current_frame
                has_changes = True

        if not has_changes:
            return

        try:
            viewport_visible = bool(self.list_view and self.list_view.isVisible())
        except RuntimeError:
            viewport_visible = False

        if not viewport_visible or not self.list_view or not self.list_view.model():
            return

        visible_rows = self._get_visible_rows()
        if not visible_rows:
            return

        rows_to_update = self.animated_rows & visible_rows
        if not rows_to_update:
            return

        model = self.list_view.model()
        for row in rows_to_update:
            if row < model.rowCount():
                index = model.index(row, 0)
                rect = self.list_view.visualRect(index)
                if rect.isValid():
                    self.list_view.viewport().update(rect)
 
    def _get_visible_rows(self) -> set:
        if not self.list_view:
            return set()
     
        try:
            viewport_rect = self.list_view.viewport().rect()
            first_index = self.list_view.indexAt(viewport_rect.topLeft())
            last_index = self.list_view.indexAt(viewport_rect.bottomLeft())
        except RuntimeError:
            return set()
     
        if not first_index.isValid():
            return set()
     
        start_row = max(0, first_index.row() - 3)
        end_row_base = last_index.row() if last_index.isValid() else start_row + 20
        end_row = end_row_base + 3
     
        return set(range(start_row, end_row + 1))

    def highlight_row(self, row: int):
        """Highlight a row with fade-out effect, independent of any other row's fade"""
        flash = self.row_flashes.get(row)
        if flash is None:
            flash = FlashFade(lambda r=row: self._on_row_highlight_tick(r), parent=self, config=self.config)
            self.row_flashes[row] = flash
        flash.start()

    def _on_row_highlight_tick(self, row: int):
        flash = self.row_flashes.get(row)
        if flash is not None and flash.opacity <= 0:
            del self.row_flashes[row]
        if self.list_view and self.list_view.model():
            index = self.list_view.model().index(row, 0)
            self.list_view.viewport().update(self.list_view.visualRect(index))
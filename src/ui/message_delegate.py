"""Message delegate for rendering with virtual scrolling"""
from typing import Dict, Optional, List
from pathlib import Path
import re
import webbrowser
import threading

from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QApplication
from PyQt6.QtCore import Qt, QSize, QRect, QModelIndex, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QPainter, QFontMetrics, QColor, QPixmap, QMovie, QCursor

from helpers.color_contrast import optimize_color_contrast
from helpers.color_utils import(
    get_private_message_colors,
    get_ban_message_colors,
    get_system_message_colors,
    get_mention_color
)
from components.messages_separator import NewMessagesSeparator, ChatlogDateSeparator
from helpers.emoticons import EmoticonManager
from helpers.fonts import get_font, FontType
from helpers.me_action import format_me_action
from helpers.mention_parser import parse_mentions
from core.youtube import is_youtube_url, get_cached_info, fetch_async
from helpers.image_viewer import ImageHoverView

class MessageDelegate(QStyledItemDelegate):
    """Delegate for rendering messages with virtual scrolling"""
  
    timestamp_clicked = pyqtSignal(str)
    username_clicked = pyqtSignal(str, bool)
    row_needs_refresh = pyqtSignal(int)
  
    def __init__(
        self,
        config,
        emoticon_manager: EmoticonManager,
        color_cache: Dict[str, str],
        parent=None
        ):
        super().__init__(parent)
        self.config = config
        self.emoticon_manager = emoticon_manager
        self.color_cache = color_cache
      
        theme = config.get("ui", "theme") or "dark"
        self.is_dark_theme = (theme == "dark")
        self.bg_hex = "#1E1E1E" if self.is_dark_theme else "#FFFFFF"
       
        # Track own username for mention highlighting
        self.my_username = None
        self.mention_color = get_mention_color(self.is_dark_theme)
      
        # Load private message colors from config
        self.private_colors = get_private_message_colors(config, self.is_dark_theme)

        # Load ban message colors from config
        self.ban_colors = get_ban_message_colors(config, self.is_dark_theme)

        # Load system message colors from config
        self.system_colors = get_system_message_colors(config, self.is_dark_theme)

        self.body_font = get_font(FontType.TEXT)
        self.timestamp_font = get_font(FontType.TEXT)
      
        self.compact_mode = False
        self.padding = config.get("ui", "message", "padding") or 2
        self.spacing = config.get("ui", "message", "element_spacing") or 4
        self.emoticon_max_size = int(config.get("ui", "emoticon_max_size") or 140)
      
        self._emoticon_cache: Dict[str, QPixmap] = {}
        self._movie_cache: Dict[str, QMovie] = {}
        self.click_rects: Dict[int, Dict] = {}
        self.input_field = None
      
        # Animation support
        self.list_view = None
        self.animated_rows = set()
        self.animation_frames = {}
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animations)
        self.animation_timer.start(33) # 30 FPS
       
        # YouTube support
        self.youtube_enabled = config.get("ui", "youtube", "enabled") or True
       
        # Connect the refresh signal
        self.row_needs_refresh.connect(self._do_refresh_row)

        # Image hover view with delay
        self.image_view = None
        self.hover_timer = QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(lambda: self.image_view and self.image_view.show_preview(*self.hover_timer.property('data')))
        self.hover_delay_ms = 500
  
    def set_my_username(self, username: str):
        """Set the current user's username for mention highlighting"""
        self.my_username = username.lower() if username else None
  
    def set_list_view(self, list_view):
        self.list_view = list_view
       
        # Initialize image view widget
        if list_view and not self.image_view:
            self.image_view = ImageHoverView(parent=list_view.window())
  
    def set_input_field(self, input_field):
        self.input_field = input_field
  
    def cleanup(self):
        self.list_view = None
        self.hover_timer.stop()
       
        # Cleanup image view
        if self.image_view:
            self.image_view.cleanup()
            self.image_view.deleteLater()
            self.image_view = None
  
    def update_theme(self):
        theme = self.config.get("ui", "theme") or "dark"
        self.is_dark_theme = (theme == "dark")
        self.bg_hex = "#1E1E1E" if theme == "dark" else "#FFFFFF"
       
        # Update mention color for new theme
        self.mention_color = get_mention_color(self.is_dark_theme)
      
        # Reload private message colors for new theme
        self.private_colors = get_private_message_colors(self.config, self.is_dark_theme)

        # Reload ban message colors for new theme
        self.ban_colors = get_ban_message_colors(self.config, self.is_dark_theme)

        # Reload system message colors for new theme
        self.system_colors = get_system_message_colors(self.config, self.is_dark_theme)
      
        self._emoticon_cache.clear()
        self.color_cache.clear()
  
    def set_compact_mode(self, compact: bool):
        if self.compact_mode != compact:
            self.compact_mode = compact
  
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        msg = index.data(Qt.ItemDataRole.DisplayRole)
        if not msg:
            return QSize(200, 50)
      
        # Chatlog date separator
        if getattr(msg, 'is_separator', False):
            return QSize(option.rect.width(), ChatlogDateSeparator.get_height())

        # New messages marker
        if getattr(msg, 'is_new_messages_marker', False):
            return QSize(option.rect.width(), NewMessagesSeparator.get_height())

        width = option.rect.width() if option.rect.width() > 0 else 800
        row = index.row()
        height = self._calculate_compact_height(msg, width, row) if self.compact_mode else self._calculate_normal_height(msg, width, row)
        return QSize(width, height)
  
    def _calculate_compact_height(self, msg, width: int, row: Optional[int] = None) -> int:
        fm = QFontMetrics(self.body_font)
        header_height = max(fm.height(), QFontMetrics(self.timestamp_font).height())
        content_height = self._calculate_content_height(msg.body, width - 2 * self.padding, fm, row)
        return min(self.padding + header_height + 2 + content_height + self.padding, 500)
  
    def _calculate_normal_height(self, msg, width: int, row: Optional[int] = None) -> int:
        fm = QFontMetrics(self.body_font)
        fm_ts = QFontMetrics(self.timestamp_font)
      
        time_str = msg.get_time_str()
        timestamp_width = fm_ts.horizontalAdvance(time_str) + self.spacing
        username_width = fm.horizontalAdvance(msg.username) + self.spacing
      
        content_width = max(width - timestamp_width - username_width - 2 * self.padding, 200)
      
        content_height = self._calculate_content_height(msg.body, content_width, fm, row)
        label_height = max(fm.height(), fm_ts.height())
        return min(max(label_height, content_height) + 2 * self.padding, 500)
  
    def _calculate_content_height(self, text: str, width: int, fm: QFontMetrics, row: Optional[int] = None) -> int:
        # Replace newlines with spaces and normalize multiple spaces
        text = ' '.join(text.split())
       
        url_pattern = re.compile(r'https?://[^\s<>"]+')
        def repl(m):
            url = m.group(0)
            cached = get_cached_info(url, use_emojis=True)
            if cached and cached[1]:
                return cached[0] + ' ' # Add space after URL
            if row is not None and cached:
                try:
                    fetch_async(url, lambda _, r=row: self._refresh_row(r))
                except Exception:
                    pass
            return url + ' ' # Add space after URL

        processed_text = url_pattern.sub(repl, text)
        segments = self.emoticon_manager.parse_emoticons(processed_text)
        current_line_height = fm.height()
        total_height = 0
        current_width = 0
      
        for seg_type, content in segments:
            if seg_type == 'text':
                lines = self._wrap_text(content, width - current_width, fm)
                for i, line in enumerate(lines):
                    if i == 0 and current_width > 0:
                        line_width = fm.horizontalAdvance(line)
                        if current_width + line_width <= width:
                            current_width += line_width
                            continue
                  
                    if current_width > 0:
                        total_height += current_line_height
                        current_line_height = fm.height()
                        current_width = 0
                    current_width = fm.horizontalAdvance(line)
            else:
                pixmap = self._get_emoticon_pixmap(content)
                if pixmap:
                    w, h = pixmap.width(), pixmap.height()
                    if current_width + w > width:
                        total_height += current_line_height
                        current_line_height = h
                        current_width = w
                    else:
                        current_width += w
                        current_line_height = max(current_line_height, h)
      
        if current_width > 0:
            total_height += current_line_height
      
        return max(total_height, fm.height())
  
    def _wrap_text(self, text: str, width: int, fm: QFontMetrics) -> List[str]:
        """Wrap text to fit within width, handling long words"""
        if not text or width <= 0:
            return [text] if text else []
      
        lines = []
        for para in text.split('\n'):
            if not para:
                lines.append('')
                continue
          
            current_line, current_width = [], 0
            for word in para.split(' '):
                word_width = fm.horizontalAdvance(word + ' ')
              
                if current_width + word_width <= width:
                    current_line.append(word)
                    current_width += word_width
                elif fm.horizontalAdvance(word) > width:
                    if current_line:
                        lines.append(' '.join(current_line))
                        current_line, current_width = [], 0
                  
                    # Split long word across lines
                    while word:
                        chunk = self._fit(word, width, fm)
                        lines.append(chunk)
                        word = word[len(chunk):]
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
                    current_width = word_width
          
            if current_line:
                lines.append(' '.join(current_line))
      
        return lines

    def _fit(self, text: str, max_pixels: int, fm: QFontMetrics) -> str:
        """Binary search to fit maximum characters within pixel width"""
        if not text or max_pixels <= 0:
            return text[:1] if text else ''
      
        lo, hi, best = 1, len(text), 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if fm.horizontalAdvance(text[:mid]) <= max_pixels:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return text[:best]

    def _get_emoticon_pixmap(self, name: str) -> Optional[QPixmap]:
        path = self.emoticon_manager.get_emoticon_path(name)
        if not path:
            return None
      
        # Animated GIF
        if path.suffix.lower() == '.gif':
            key = str(path)
            if key not in self._movie_cache:
                movie = QMovie(str(path))
                # Parent to application to survive view cleanup and avoid
                # being GC'd/stopped when views are hidden.
                try:
                    movie.setParent(QApplication.instance())
                except Exception:
                    pass
                movie.setCacheMode(QMovie.CacheMode.CacheAll)
                first_frame = movie.currentPixmap()
                if not first_frame.isNull():
                    w, h = first_frame.width(), first_frame.height()
                    if w > self.emoticon_max_size or h > self.emoticon_max_size:
                        scale = self.emoticon_max_size / max(w, h)
                        movie.setScaledSize(QSize(int(w * scale), int(h * scale)))
                movie.setSpeed(100)
                movie.start()
                self._movie_cache[key] = movie
                self.animation_frames[key] = -1
          
            return self._movie_cache[key].currentPixmap()
      
        # Static image
        if name in self._emoticon_cache:
            return self._emoticon_cache[name]
      
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            w, h = pixmap.width(), pixmap.height()
            if w > self.emoticon_max_size or h > self.emoticon_max_size:
                scale = self.emoticon_max_size / max(w, h)
                pixmap = pixmap.scaled(int(w * scale), int(h * scale),
                                      Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
            self._emoticon_cache[name] = pixmap
      
        return pixmap
  
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        msg = index.data(Qt.ItemDataRole.DisplayRole)
        if not msg:
            return
   
        # Handle chatlog date separator
        if getattr(msg, 'is_separator', False):
            ChatlogDateSeparator.render(
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

        if self._has_animated_emoticons(msg.body):
            self.animated_rows.add(row)
        else:
            self.animated_rows.discard(row)
   
        self.click_rects[row] = {'timestamp': QRect(), 'username': QRect(), 'links': []}
   
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
   
        self._paint_message(painter, option.rect, msg, row, self.compact_mode)
   
        painter.restore()
  
    def _paint_message(self, painter: QPainter, rect: QRect, msg, row: int, compact: bool):
        """Paint message in either compact or normal mode"""
        x, y = rect.x() + self.padding, rect.y() + self.padding
        width = rect.width() - 2 * self.padding
        time_str = msg.get_time_str()
       
        body_fm = QFontMetrics(self.body_font)
        ts_fm = QFontMetrics(self.timestamp_font)
       
        # Paint timestamp
        painter.setFont(self.timestamp_font)
        painter.setPen(QColor("#999999"))
        ts_width = ts_fm.horizontalAdvance(time_str)
        ts_rect = QRect(x, y, ts_width, ts_fm.height())
        painter.drawText(
            ts_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            time_str
        )
        self.click_rects[row]['timestamp'] = ts_rect
       
        # Format message body if it's a /me action
        display_body, is_me_action = format_me_action(msg.body, msg.username)
        is_system = is_me_action or getattr(msg, 'is_system', False)
       
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
            self._paint_content(
                painter, x, content_y, content_width, display_body, row,
                getattr(msg, 'is_private', False),
                getattr(msg, 'is_ban', False),
                is_system
            )
        else:
            # Normal mode: content on same line after username/timestamp
            content_width = rect.width() - (content_x - rect.x()) - self.padding
            self._paint_content(
                painter, content_x, y, content_width, display_body, row,
                getattr(msg, 'is_private', False),
                getattr(msg, 'is_ban', False),
                is_system
            )
  
    def _paint_content(self, painter: QPainter, x: int, y: int, width: int,
                       text: str, row: int, is_private: bool = False, is_ban: bool = False, is_system: bool = False):
        """Paint content with text, links, and emoticons"""
        # Replace newlines with spaces and normalize multiple spaces
        text = ' '.join(text.split())
       
        url_pattern = re.compile(r'https?://[^\s<>"]+')
        urls = []
        def replace_url(match):
            url = match.group(0)
            urls.append(url)
            return f"[URL{len(urls)-1}] " # Add space after placeholder
        processed_text = url_pattern.sub(replace_url, text)
        segments = self.emoticon_manager.parse_emoticons(processed_text)
        painter.setFont(self.body_font)
        fm = QFontMetrics(self.body_font)

        current_x, current_y = x, y
        line_height = fm.height()

        # Determine text color based on message type
        if is_system:
            text_color = self.system_colors["text"]
        elif is_private:
            text_color = self.private_colors["text"]
        elif is_ban:
            text_color = self.ban_colors["text"]
        else:
            text_color = "#FFFFFF" if self.is_dark_theme else "#000000"
       
        link_color = "#4DA6FF" if self.is_dark_theme else "#0066CC"

        def new_line():
            nonlocal current_x, current_y, line_height
            current_y += line_height
            current_x = x
            line_height = fm.height()

        def draw_text_chunk(content: str, color: str):
            """Draw text chunk with mention highlighting (ONLY for non-system messages)"""
            nonlocal current_x
           
            # Only apply mention highlighting for normal messages (not system/private/ban)
            if not is_system and not is_private and not is_ban:
                # Split content into mention and non-mention segments
                mention_segments = parse_mentions(content, self.my_username)
            else:
                # For system/private/ban messages, treat entire content as non-mention
                mention_segments = [(False, content)]
           
            for is_mention, segment_text in mention_segments:
                if not segment_text:
                    continue
               
                # Use green color AND bold font for mentions
                if is_mention:
                    draw_color = self.mention_color
                    painter.setFont(get_font(FontType.TEXT)) # Reset to ensure we have the font object
                    bold_font = painter.font()
                    bold_font.setBold(True)
                    painter.setFont(bold_font)
                    fm = QFontMetrics(bold_font) # Update font metrics for bold text
                else:
                    draw_color = color
                    painter.setFont(self.body_font) # Use normal font
                    fm = QFontMetrics(self.body_font) # Update font metrics for normal text
               
                lines = self._wrap_text(segment_text, width - (current_x - x), fm)
                for line in lines:
                    if not line:
                        new_line()
                        continue

                    line_width = fm.horizontalAdvance(line)
                    if current_x > x and current_x + line_width > x + width:
                        new_line()

                    painter.setPen(QColor(draw_color))
                    painter.drawText(current_x, current_y + fm.ascent(), line)
                    current_x += line_width
               
                # Reset to normal font after mention
                if is_mention:
                    painter.setFont(self.body_font)
                    fm = QFontMetrics(self.body_font)

        def draw_link(url: str):
            nonlocal current_x, line_height
            link_text = self._get_link_text(url, row)
            painter.setPen(QColor(link_color))

            remaining = link_text
            while remaining:
                avail = x + width - current_x
                if avail <= 0:
                    new_line()
                    avail = width

                chunk = self._fit(remaining, avail, fm) or remaining[0]
                chunk_width = fm.horizontalAdvance(chunk)

                if current_x > x and current_x + chunk_width > x + width:
                    new_line()
                    continue

                painter.drawText(current_x, current_y + fm.ascent(), chunk)
                link_rect = QRect(current_x, current_y, chunk_width, fm.height())
                self.click_rects[row]['links'].append((link_rect, url))
                current_x += chunk_width
                remaining = remaining[len(chunk):]
       
        placeholder_pattern = re.compile(r'\[URL(\d+)\]')

        for seg_type, content in segments:
            if seg_type == 'text':
                last_pos = 0
                for match in placeholder_pattern.finditer(content):
                    if match.start() > last_pos:
                        draw_text_chunk(content[last_pos:match.start()], text_color)
                    url_index = int(match.group(1))
                    draw_link(urls[url_index])
                    last_pos = match.end()

                if last_pos < len(content):
                    draw_text_chunk(content[last_pos:], text_color)

            else: # emoticon
                pixmap = self._get_emoticon_pixmap(content)
                if pixmap:
                    w, h = pixmap.width(), pixmap.height()
                    if current_x > x and current_x + w > x + width:
                        new_line()
                        line_height = h

                    painter.drawPixmap(current_x, current_y, pixmap)
                    current_x += w
                    line_height = max(line_height, h)
  
    def _get_link_text(self, url: str, row: int) -> str:
        """Get display text for link (process YouTube if applicable)"""
        if not self.youtube_enabled or not is_youtube_url(url):
            return url
       
        cached = get_cached_info(url, use_emojis=True)
        if cached:
            formatted_text, is_cached = cached
            if is_cached:
                return formatted_text
            fetch_async(url, lambda result: self._refresh_row(row))
       
        return url
   
    def _refresh_row(self, row: int):
        """Request refresh from background thread - emit signal to main thread"""
        self.row_needs_refresh.emit(row)
   
    def _do_refresh_row(self, row: int):
        """Refresh row when async metadata arrives - re-evaluate sizeHint"""
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
                from components.messages_separator import NewMessagesSeparator
                NewMessagesSeparator.remove_from_model(model)
                return True
            return False
       
        # Ignore clicks on date separators
        if getattr(msg, 'is_separator', False):
            return False

        if event.type() == QEvent.Type.MouseButtonRelease:
            pos = event.pos()
            row = index.row()
          
            if row not in self.click_rects:
                return super().editorEvent(event, model, option, index)
          
            rects = self.click_rects[row]
          
            # Timestamp click
            if rects['timestamp'].contains(pos):
                msg = index.data(Qt.ItemDataRole.DisplayRole)
                if msg:
                    self.timestamp_clicked.emit(msg.get_time_str())
                return True
          
            # Username single click
            if rects['username'].contains(pos):
                msg = index.data(Qt.ItemDataRole.DisplayRole)
                if msg:
                    self.username_clicked.emit(msg.username, False)
                return True
          
            # Link clicks
            for link_rect, url in rects['links']:
                if link_rect.contains(pos):
                    try:
                        webbrowser.open(url)
                    except Exception as e:
                        print(f"Failed to open URL: {e}")
                    return True
      
        elif event.type() == QEvent.Type.MouseButtonDblClick:
            pos = event.pos()
            row = index.row()
          
            if row not in self.click_rects:
                return super().editorEvent(event, model, option, index)
          
            rects = self.click_rects[row]
          
            if rects['username'].contains(pos):
                msg = index.data(Qt.ItemDataRole.DisplayRole)
                if msg:
                    self.username_clicked.emit(msg.username, True)
                return True
      
        elif event.type() == QEvent.Type.MouseMove:
            pos = event.pos()
            row = index.row()
           
            if row in self.click_rects:
                rects = self.click_rects[row]
                is_over_clickable = (
                    rects['timestamp'].contains(pos) or
                    rects['username'].contains(pos) or
                    any(link_rect.contains(pos) for link_rect, _ in rects['links'])
                )
               
                # Check for image URL hover with delay
                found_image = False
                for link_rect, url in rects['links']:
                    if link_rect.contains(pos) and ImageHoverView.is_image_url(url):
                        found_image = True
                        global_pos = self.list_view.viewport().mapToGlobal(pos)
                        if self.hover_timer.property('data') != (url, global_pos):
                            self.hover_timer.setProperty('data', (url, global_pos))
                            self.hover_timer.start(self.hover_delay_ms)
                        break
                
                if not found_image:
                    self.hover_timer.stop()
                    if self.image_view:
                        self.image_view.hide_preview()
               
                if self.list_view:
                    cursor = (Qt.CursorShape.PointingHandCursor
                             if is_over_clickable
                             else Qt.CursorShape.ArrowCursor)
                    self.list_view.setCursor(QCursor(cursor))
      
        return super().editorEvent(event, model, option, index)
  
    def _get_username_color(self, username: str, background: Optional[str]) -> str:
        if username not in self.color_cache:
            # If no background color (messages/chatlog), use simple theme-dependent color
            if not background:
                self.color_cache[username] = "#CCCCCC" if self.is_dark_theme else "#666666"
            else:
                # Messages view: use optimized contrast
                self.color_cache[username] = optimize_color_contrast(background, self.bg_hex, 4.5)
        return self.color_cache[username]
  
    def _has_animated_emoticons(self, text: str) -> bool:
        for seg_type, content in self.emoticon_manager.parse_emoticons(text):
            if seg_type == 'emoticon':
                path = self.emoticon_manager.get_emoticon_path(content)
                if path and path.suffix.lower() == '.gif':
                    return True
        return False
  
    def _update_animations(self):
        if not self.animated_rows:
            return

        # Poll frames for all movies
        has_changes = False
        for key, movie in list(self._movie_cache.items()):
            try:
                current_frame = movie.currentFrameNumber()
            except Exception:
                # Movie may have been invalidated; skip it
                continue
            if self.animation_frames.get(key, -1) != current_frame:
                self.animation_frames[key] = current_frame
                has_changes = True

        if not has_changes:
            return

        # Only repaint when view is visible
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
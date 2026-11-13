"""Reusable message body renderer for delegates and notifications"""

import math
import re
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import pyqtSignal, QObject, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QMovie, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

from components.badge import badge_style, EVENT_TYPES
from components.flash_highlight import FlashFade, link_colors, paint_flash, timestamp_color
from components.image_viewer.gallery import ImageGallery, is_image_url, URL_PATTERN
from components.image_viewer.viewer import ImageHoverView
from components.video_player import VideoPlayer
from core.state.mention_aliases import mention_aliases
from core.web.youtube import fetch_async, get_cached_info, is_youtube_url
from helpers.browser import open_url as open_url_in_browser
from helpers.colors.color_utils import (
    get_ban_message_colors,
    get_competition_message_colors,
    get_competition_value_colors,
    get_mention_colors,
    get_parser_message_colors,
    get_private_message_colors,
    get_rank_chip_colors,
    get_search_highlight_colors,
    get_system_message_colors,
)
from helpers.data import get_resource_dir
from helpers.fonts.fonts import FontType, get_font
from helpers.text.mention_parser import MENTION_ICONS, parse_mentions
from ui.messages.message_layout import Atom, Fragment, KIND_EMOTICON, KIND_LINK, KIND_TEXT, layout_atoms, TextLayout


_WORD_WIDTH_CACHE_LIMIT = 50000


class MessageRenderer(QObject):
    """Renders message body content with links, emoticons, and mentions"""

    # Signal emitted when content needs refresh (e.g., YouTube metadata loaded)
    link_text_loaded = pyqtSignal(object) # owner of a layout whose link label has just arrived
    refresh_view = pyqtSignal() # general refresh (link rmb highlight)
    chatlog_link_clicked = pyqtSignal(str, str) # date_str, time_str ("" if none) - chatlog URL clicked in a message body

    _CHATLOG_URL_PATTERN = re.compile(r'^https?://klavogonki\.ru/chatlogs/(\d{4}-\d{2}-\d{2})\.html(?:#(\d{2}:\d{2}:\d{2}))?$')
    _GAME_URL_PATTERN = re.compile(r'^https?://klavogonki\.ru/g/\?gmid=(\d+)$')
    _TOKEN_PATTERN = re.compile(r'\[(COST|SCORE|BONUS)\](.*?)\[/\1\]|' + URL_PATTERN.pattern)
    _CHIP_GAP = 6

    def __init__(self, config, emoticon_manager, is_dark_theme: bool, parent_widget=None):
        super().__init__()
        self.config = config
        self.emoticon_manager = emoticon_manager
        self.is_dark_theme = is_dark_theme
        self.background_hex = "#1E1E1E" if is_dark_theme else "#FFFFFF"

        # Track own username for mention highlighting
        self.my_username = None
        self._mention_colors = get_mention_colors(is_dark_theme)
        self._highlight_colors = get_search_highlight_colors(is_dark_theme)
        self._link_colors = link_colors(is_dark_theme)

        # Load message colors from config
        self._private_colors = get_private_message_colors(config, is_dark_theme)
        self._ban_colors = get_ban_message_colors(config, is_dark_theme)
        self.system_colors = get_system_message_colors(config, is_dark_theme)
        self.competition_colors = get_competition_message_colors(config, is_dark_theme)
        self._competition_value_colors = get_competition_value_colors(is_dark_theme)
        self.parser_colors = get_parser_message_colors(config, is_dark_theme)

        # Font setup
        self.layout_revision = 0
        self._word_widths: Dict[Tuple[bool, str], float] = {}
        self.set_body_font(get_font(FontType.TEXT))

        # Emoticon settings
        self._emoticon_max_size = int(config.get("ui", "emoticon_max_size") or 140)

        # Caches
        self.emoticon_cache: Dict[str, QPixmap] = {}
        self.movie_cache: Dict[str, QMovie] = {}

        # Copy highlight state
        self._copied_url: Optional[str] = None
        self._copy_flash = FlashFade(self.refresh_view.emit, parent=self, config=config, duration_kind="copy")
        # None = follow config; False/True = force (e.g. parser bulk load)
        self._youtube_override: Optional[bool] = None

        # Create viewer instances
        self.image_viewer = None
        self._video_player = None
        if parent_widget:
            self._init_viewers(parent_widget)

    @property
    def _youtube_enabled(self) -> bool:
        if self._youtube_override is not None:
            return self._youtube_override
        value = self.config.get("ui", "youtube", "enabled")
        return True if value is None else bool(value)

    def set_youtube_override(self, enabled: Optional[bool]):
        self._youtube_override = enabled
        self.invalidate_layouts()

    def _init_viewers(self, parent_widget):
        """Initialize image and video viewers"""
        self.image_viewer = ImageHoverView(parent=parent_widget, config=self.config)
        icons_path = get_resource_dir("icons")
        self._video_player = VideoPlayer(
            parent=parent_widget,
            icons_path=icons_path,
            config=self.config
        )

    @classmethod
    def _parse_chatlog_url(cls, url: str) -> Optional[Tuple[str, Optional[str]]]:
        """Parse a klavogonki chatlog URL into (date_str, time_str or None), or None if it doesn't match"""
        match = cls._CHATLOG_URL_PATTERN.match(url)
        if not match:
            return None
        return match.group(1), match.group(2)

    def handle_link_lmb(self, url: str, is_media: bool, global_pos, is_ctrl: bool = False, is_shift: bool = False,
                        gallery: Optional[ImageGallery] = None):
        # Chatlog URL opens in split view
        chatlog_match = self._parse_chatlog_url(url)
        if chatlog_match and not is_ctrl:
            date_str, time_str = chatlog_match
            self.chatlog_link_clicked.emit(date_str, time_str or "")
            return
        if is_media and not is_ctrl:
            # Media link without Ctrl: open in viewer
            if VideoPlayer.is_video_url(url) and self._video_player:
                self._video_player.show_video(url, global_pos, force_log=is_shift)
            elif is_image_url(url) and self.image_viewer:
                self.image_viewer.show_preview(url, global_pos, gallery)
        else:
            # Normal link, media link with Ctrl, or chatlog link with Ctrl: open in browser
            browser_key = self.config.get("browser") if self.config else None
            try:
                open_url_in_browser(url, browser_key)
            except Exception as e:
                print(f"Failed to open URL: {e}")

    def handle_link_rmb(self, url: str):
        """Copy URL to clipboard and briefly highlight it"""
        self.copy_and_highlight(url)

    def copy_and_highlight(self, url: str):
        """Copy url to clipboard and fade-flag it as copied (drives the highlight repaint)"""
        QApplication.clipboard().setText(url)
        self._copied_url = url
        self._copy_flash.start()

    def is_copied(self, url: str) -> bool:
        """Whether url is the one just copied (drives the flash highlight)"""
        return self._copied_url == url and self._copy_flash.opacity > 0

    def draw_copy_highlight(self, painter: QPainter, rect: QRect, color: str):
        """Translucent rounded-rect background fading out on a just-copied URL/timestamp"""
        paint_flash(painter, rect.adjusted(-2, 0, 2, 0), color, self._copy_flash.opacity, alpha=0.35)

    @staticmethod
    def get_link_at_pos(link_rects: List[Tuple[QRect, str, bool]], pos) -> Optional[Tuple[str, bool]]:
        """Find link at given position"""
        for rect, url, is_media in link_rects:
            if rect.contains(pos):
                return (url, is_media)
        return None

    @staticmethod
    def is_over_link(link_rects: List[Tuple[QRect, str, bool]], pos) -> bool:
        """Check if position is over any link"""
        return any(rect.contains(pos) for rect, _, _ in link_rects)

    def _message_palette(self, is_ban: bool, is_private: bool, is_system: bool, is_competition: bool, is_parser: bool) -> Optional[Dict[str, str]]:
        """Return the color palette of the message type, or None for a regular message"""
        if is_parser:
            return self.parser_colors
        if is_competition:
            return self.competition_colors
        if is_system:
            return self.system_colors
        if is_private:
            return self._private_colors
        if is_ban:
            return self._ban_colors
        return None

    def get_timestamp_color(self, is_ban: bool, is_private: bool, is_system: bool, is_competition: bool = False, is_parser: bool = False) -> str:
        """Return the appropriate timestamp color for the message type"""
        palette = self._message_palette(is_ban, is_private, is_system, is_competition, is_parser)
        return palette["text"] if palette else timestamp_color(self.is_dark_theme)

    def get_text_color(self, is_ban: bool, is_private: bool, is_system: bool, is_competition: bool = False, is_parser: bool = False) -> str:
        """Return the body text color for the message type"""
        palette = self._message_palette(is_ban, is_private, is_system, is_competition, is_parser)
        if palette:
            return palette["text"]
        return "#FFFFFF" if self.is_dark_theme else "#000000"

    def get_link_color(self, url: str, is_media: Optional[bool] = None) -> str:
        """Return the link color: media, chatlog or normal; pass is_media when it is already known"""
        if is_media is None:
            is_media = self._is_media_url(url)
        if is_media:
            return self._link_colors["media"]
        if self._parse_chatlog_url(url):
            return self._link_colors["chatlog"]
        return self._link_colors["normal"]

    def set_my_username(self, username: str):
        """Set the current user's username for mention highlighting"""
        self.my_username = username or None

    def update_theme(self, is_dark_theme: bool):
        """Update theme and reload colors"""
        self.is_dark_theme = is_dark_theme
        self.background_hex = "#1E1E1E" if is_dark_theme else "#FFFFFF"
        self._mention_colors = get_mention_colors(is_dark_theme)
        self._highlight_colors = get_search_highlight_colors(is_dark_theme)
        self._link_colors = link_colors(is_dark_theme)
        self._private_colors = get_private_message_colors(self.config, is_dark_theme)
        self._ban_colors = get_ban_message_colors(self.config, is_dark_theme)
        self.system_colors = get_system_message_colors(self.config, is_dark_theme)
        self.competition_colors = get_competition_message_colors(self.config, is_dark_theme)
        self._competition_value_colors = get_competition_value_colors(is_dark_theme)
        self.parser_colors = get_parser_message_colors(self.config, is_dark_theme)
        self.emoticon_cache.clear()
        self.invalidate_layouts()
        if self.image_viewer:
            self.image_viewer.update_theme(is_dark_theme)

    @staticmethod
    def emoji_prefix(text: str, is_private: bool, is_ban: bool, is_system: bool, is_competition: bool = False, is_parser: bool = False) -> str:
        """Prepend type emoji for special message types."""
        if is_competition:
            return "🏆 " + text
        if is_ban:
            return "🔹 " + text
        if is_private:
            return "🔸 " + text
        if is_system:
            return "◽️ " + text
        if is_parser:
            return "🔥 " + text
        return text

    def mention_pattern(self):
        """Pattern of the own nick and its aliases; part of every layout cache key, as a mention is drawn bold."""
        return mention_aliases.pattern(self.my_username)

    def invalidate_layouts(self):
        """Make every cached layout stale (fonts, emoticon sizes or link labels changed)."""
        self.layout_revision += 1

    def set_body_font(self, font: QFont):
        """Switch the body font; widths measured with the old one are dropped."""
        self.body_font = font
        self._bold_font = QFont(font)
        self._bold_font.setBold(True)
        self._metrics = QFontMetricsF(font)
        self._bold_metrics = QFontMetricsF(self._bold_font)
        self._line_height = QFontMetrics(font).height()
        self._ascent = QFontMetrics(font).ascent()
        self._word_widths.clear()
        self.invalidate_layouts()

    def _measure(self, text: str, bold: bool) -> float:
        key = (bold, text)
        width = self._word_widths.get(key)
        if width is None:
            width = (self._bold_metrics if bold else self._metrics).horizontalAdvance(text)
            if len(self._word_widths) >= _WORD_WIDTH_CACHE_LIMIT:
                self._word_widths.clear()
            self._word_widths[key] = width
        return width

    def layout_body(self, text: str, width: float, has_mentions: bool = True, owner=None) -> TextLayout:
        """Wrap a message body to the width. owner is passed to link_text_loaded when a link label arrives later."""
        return layout_atoms(self._atoms(text, has_mentions, owner), width, self._line_height, self._measure)

    def _atoms(self, text: str, has_mentions: bool, owner) -> List[Atom]:
        """Split a body into text runs, links, colored competition values and emoticons."""
        text = ' '.join(text.split())
        atoms: List[Atom] = []
        position = 0
        for match in self._TOKEN_PATTERN.finditer(text):
            self._add_plain_atoms(atoms, text[position:match.start()], has_mentions)
            if match.group(1):
                atoms.append(Atom(KIND_TEXT, match.group(2), role=match.group(1).lower()))
            else:
                url = match.group(0)
                atoms.append(Atom(KIND_LINK, self._get_link_text(url, owner), url=url, is_media=self._is_media_url(url)))
            position = match.end()
        self._add_plain_atoms(atoms, text[position:], has_mentions)
        return atoms

    def _add_plain_atoms(self, atoms: List[Atom], text: str, has_mentions: bool):
        """Emoticons and (for regular messages) mentions of a stretch without links."""
        for kind, content in self.emoticon_manager.parse_emoticons(text):
            if kind == KIND_EMOTICON:
                pixmap = self._get_emoticon_pixmap(content)
                if pixmap:
                    atoms.append(Atom(KIND_EMOTICON, content, size=(pixmap.width(), pixmap.height())))
                continue
            segments = parse_mentions(content, self.mention_pattern()) if has_mentions else [(None, content)]
            for mention_kind, segment in segments:
                if not segment:
                    continue
                if mention_kind is None:
                    atoms.append(Atom(KIND_TEXT, segment))
                else:
                    label = f"{MENTION_ICONS[mention_kind]} {segment}" if mention_kind in MENTION_ICONS else segment
                    atoms.append(Atom(KIND_TEXT, label, role=mention_kind, bold=True))

    def paint_layout(
        self,
        painter: QPainter,
        layout: TextLayout,
        x: int,
        y: int,
        is_private: bool = False,
        is_ban: bool = False,
        is_system: bool = False,
        is_competition: bool = False,
        is_parser: bool = False,
        highlight_text: str = "",
    ) -> List[Tuple[QRect, str, bool]]:
        """Paint a laid out body with its top-left at (x, y); returns (QRect, url, is_media) for every link piece."""
        text_color = self.get_text_color(is_ban, is_private, is_system, is_competition, is_parser)
        highlight_pattern = re.compile(re.escape(highlight_text), re.IGNORECASE) if highlight_text else None
        link_rects = []
        for fragment in layout.fragments:
            left, top = round(x + fragment.x), round(y + fragment.y)
            if fragment.kind == KIND_EMOTICON:
                pixmap = self._get_emoticon_pixmap(fragment.text)
                if pixmap:
                    painter.drawPixmap(left, top, pixmap)
            elif fragment.kind == KIND_LINK:
                rect = QRect(left, top, math.ceil(fragment.width), fragment.height)
                color = self.get_link_color(fragment.url, fragment.is_media)
                if self.is_copied(fragment.url):
                    self.draw_copy_highlight(painter, rect, color)
                painter.setFont(self.body_font)
                painter.setPen(QColor(color))
                painter.drawText(left, top + self._ascent, fragment.text)
                link_rects.append((rect, fragment.url, fragment.is_media))
            else:
                self._paint_text(painter, fragment, left, top, self._fragment_color(fragment, text_color), highlight_pattern)
        return link_rects

    def _fragment_color(self, fragment: Fragment, text_color: str) -> str:
        if fragment.role in self._mention_colors:
            return self._mention_colors[fragment.role]
        return self._competition_value_colors.get(fragment.role, text_color)

    def _paint_text(self, painter: QPainter, fragment: Fragment, left: int, top: int, color: str, highlight_pattern):
        """Draw a text fragment; search matches get a rounded background and their own text color."""
        metrics = self._bold_metrics if fragment.bold else self._metrics
        painter.setFont(self._bold_font if fragment.bold else self.body_font)
        baseline = top + self._ascent
        text = fragment.text
        matches = [match.span() for match in highlight_pattern.finditer(text)] if highlight_pattern and not fragment.bold else []
        highlight_background, highlight_foreground = self._highlight_colors
        position = 0
        for start, end in matches:
            self._draw_run(painter, text[position:start], left + metrics.horizontalAdvance(text[:position]), baseline, color)
            match_left = left + metrics.horizontalAdvance(text[:start])
            match_rect = QRect(round(match_left), top, math.ceil(metrics.horizontalAdvance(text[start:end])), self._line_height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(highlight_background))
            painter.drawRoundedRect(match_rect, 4, 4)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            self._draw_run(painter, text[start:end], match_left, baseline, highlight_foreground)
            position = end
        self._draw_run(painter, text[position:], left + metrics.horizontalAdvance(text[:position]), baseline, color)

    @staticmethod
    def _draw_run(painter: QPainter, text: str, left: float, baseline: int, color: str):
        if text:
            painter.setPen(QColor(color))
            painter.drawText(round(left), baseline, text)

    @staticmethod
    def _chip_label(player) -> str:
        if isinstance(player, dict):
            return player.get("name") or "?"
        return str(player)

    def calculate_chips_height(self, players: list, width: int) -> int:
        """Height needed for the wrapping row of user chips."""
        if not players or width <= 0:
            return 0
        font_metrics = QFontMetrics(self.body_font)
        chip_height = font_metrics.height() + 6
        row_width = 0
        rows = 1
        for player in players:
            chip_width = font_metrics.horizontalAdvance(self._chip_label(player)) + 16
            if row_width and row_width + self._CHIP_GAP + chip_width > width:
                rows += 1
                row_width = chip_width
            else:
                row_width += (self._CHIP_GAP if row_width else 0) + chip_width
        return rows * chip_height + (rows - 1) * self._CHIP_GAP

    def paint_chips(self, painter: QPainter, x: int, y: int, width: int, players: list, is_dark: bool):
        """Paint usernames as pill-shaped chips. Returns (block_height, [(QRect, name), ...])."""
        if not players or width <= 0:
            return 0, []
        border = 2
        inset = border // 2
        font_metrics = QFontMetrics(self.body_font)
        painter.setFont(self.body_font)
        chip_height = font_metrics.height() + 6
        current_x, current_y = x, y
        chip_rects = []

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for player in players:
            name = self._chip_label(player)
            level = player.get("level") if isinstance(player, dict) else None
            background_hex, foreground_hex, border_hex = get_rank_chip_colors(level, is_dark)
            chip_width = font_metrics.horizontalAdvance(name) + 16
            if current_x > x and current_x + chip_width > x + width:
                current_y += chip_height + self._CHIP_GAP
                current_x = x
            chip_rect = QRect(current_x, current_y, chip_width, chip_height)

            pen = QPen(QColor(border_hex))
            pen.setWidth(border)
            painter.setPen(pen)
            painter.setBrush(QColor(background_hex))
            r = chip_rect.adjusted(inset, inset, -inset, -inset)
            painter.drawRoundedRect(r, max(0, chip_height // 2 - inset), max(0, chip_height // 2 - inset))

            painter.setPen(QColor(foreground_hex))
            painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, name)
            chip_rects.append((chip_rect, name))
            current_x += chip_width + self._CHIP_GAP

        return current_y + chip_height - y, chip_rects

    _PRESENCE_GROUP_GAP = 12
    _PRESENCE_BADGE_GAP = 4
    _PRESENCE_LINE_GAP = 2
    _PRESENCE_BADGE_PAD_X = 12
    _PRESENCE_NAME_GAP = 8
    _PRESENCE_LAST_DOT = 6

    def _presence_badge(self, event_type: str, count: int, is_last: bool = False):
        label, bg, fg, border = badge_style(event_type, self.is_dark_theme)
        text = label if count == 1 else f"{label} {count}"
        return text, bg, fg, border

    def _presence_line_height(self, font_metrics: QFontMetrics = None) -> int:
        font_metrics = font_metrics or QFontMetrics(self.body_font)
        return font_metrics.height() + 4

    def _presence_entry_width(self, entry: dict, font_metrics: QFontMetrics) -> int:
        w = font_metrics.horizontalAdvance(entry.get('login', '')) + self._PRESENCE_NAME_GAP
        last = entry.get('last')
        dot = max(3, font_metrics.height() // 4)
        for event_type in EVENT_TYPES:
            count = entry.get('counts', {}).get(event_type)
            if not count:
                continue
            text, _, _, _ = self._presence_badge(event_type, count)
            w += font_metrics.horizontalAdvance(text) + self._PRESENCE_BADGE_PAD_X + self._PRESENCE_BADGE_GAP
            if event_type == last:
                w += dot + 4
        return w

    def _presence_line_count(self, entries: list, width: int, font_metrics: QFontMetrics) -> int:
        if width <= 0:
            return 1
        lines, row_width = 1, 0
        for entry in entries:
            ew = self._presence_entry_width(entry, font_metrics)
            if row_width and row_width + self._PRESENCE_GROUP_GAP + ew > width:
                lines += 1
                row_width = ew
            else:
                row_width += (self._PRESENCE_GROUP_GAP if row_width else 0) + ew
        return lines

    def calculate_presence_entries_height(self, entries: list, width: int = 0) -> int:
        if not entries:
            return 0
        font_metrics = QFontMetrics(self.body_font)
        line_height = self._presence_line_height(font_metrics)
        lines = self._presence_line_count(entries, width, font_metrics)
        return lines * line_height + (lines - 1) * self._PRESENCE_LINE_GAP

    def paint_presence_entries(self, painter: QPainter, x: int, y: int, width: int,
                               entries: list, get_username_color, line_height: int = 0):
        """Paint presence groups. Returns (bbox, [(name_rect, login), ...])."""
        if not entries or width <= 0:
            return QRect(x, y, max(width, 0), 0), []

        font_metrics = QFontMetrics(self.body_font)
        painter.setFont(self.body_font)
        line_h = line_height if line_height > 0 else self._presence_line_height(font_metrics)
        badge_height = min(self._presence_line_height(font_metrics), line_h)
        cx, cy = x, y
        user_rects = []

        for entry in entries:
            ew = self._presence_entry_width(entry, font_metrics)
            if cx > x and cx + ew > x + width:
                cx = x
                cy += line_h + self._PRESENCE_LINE_GAP

            login = entry.get('login', '')
            name_width = font_metrics.horizontalAdvance(login)
            name_rect = QRect(cx, cy, name_width, line_h)
            painter.setPen(QColor(get_username_color(login)))
            painter.drawText(cx, cy + (line_h - font_metrics.height()) // 2 + font_metrics.ascent(), login)
            user_rects.append((name_rect, login))
            cx += name_width + self._PRESENCE_NAME_GAP

            last = entry.get('last')
            dot = max(3, font_metrics.height() // 4)
            for event_type in EVENT_TYPES:
                count = entry.get('counts', {}).get(event_type)
                if not count:
                    continue
                text, bg, fg, border = self._presence_badge(event_type, count)
                text_width = font_metrics.horizontalAdvance(text)
                is_last = event_type == last
                bw = text_width + self._PRESENCE_BADGE_PAD_X + (dot + 4 if is_last else 0)
                badge_rect = QRect(cx, cy + (line_h - badge_height) // 2, bw, badge_height)

                border_width = 2
                inset = border_width // 2
                pen = QPen(QColor(border))
                pen.setWidth(border_width)
                painter.setPen(pen)
                painter.setBrush(QColor(bg))
                painter.drawRoundedRect(
                    badge_rect.adjusted(inset, inset, -inset, -inset), 4, 4
                )

                painter.setPen(QColor(fg))
                painter.drawText(
                    QRect(badge_rect.x(), badge_rect.y(),
                          text_width + self._PRESENCE_BADGE_PAD_X, badge_rect.height()),
                    Qt.AlignmentFlag.AlignCenter,
                    text,
                )

                if is_last:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(fg))
                    painter.drawEllipse(
                        badge_rect.right() - dot - 4,
                        badge_rect.y() + (badge_rect.height() - dot) // 2,
                        dot, dot,
                    )

                cx += bw + self._PRESENCE_BADGE_GAP

            cx += self._PRESENCE_GROUP_GAP

        return QRect(x, y, width, (cy - y) + line_h), user_rects

    def has_animated_emoticons(self, text: str) -> bool:
        """Check if text contains animated emoticons"""
        for seg_type, content in self.emoticon_manager.parse_emoticons(text):
            if seg_type == 'emoticon':
                path = self.emoticon_manager.get_emoticon_path(content)
                if path and path.suffix.lower() == '.gif':
                    return True
        return False

    def _is_media_url(self, url: str) -> bool:
        """Check if URL is a media link"""
        return is_image_url(url) or VideoPlayer.is_video_url(url)

    def _get_link_text(self, url: str, owner) -> str:
        """Get display text for link (short label for game links, processed YouTube title, else the URL)"""
        game_match = self._GAME_URL_PATTERN.match(url)
        if game_match:
            return f"🔗 {game_match.group(1)}"

        if not self._youtube_enabled or not is_youtube_url(url):
            return url

        cached = get_cached_info(url, use_emojis=True)
        if cached:
            formatted_text, is_cached = cached
            if is_cached:
                return formatted_text
            if owner is not None:
                fetch_async(url, lambda result: self.link_text_loaded.emit(owner))

        return url

    def _get_emoticon_pixmap(self, name: str) -> Optional[QPixmap]:
        """Get emoticon pixmap (static or animated)"""
        path = self.emoticon_manager.get_emoticon_path(name)
        if not path:
            return None

        # Animated GIF
        if path.suffix.lower() == '.gif':
            key = str(path)
            if key not in self.movie_cache:
                movie = QMovie(str(path))
                try:
                    movie.setParent(QApplication.instance())
                except Exception:
                    pass
                movie.setCacheMode(QMovie.CacheMode.CacheAll)
                first_frame = movie.currentPixmap()
                if not first_frame.isNull():
                    w, h = first_frame.width(), first_frame.height()
                    if w > self._emoticon_max_size or h > self._emoticon_max_size:
                        scale = self._emoticon_max_size / max(w, h)
                        movie.setScaledSize(QSize(int(w * scale), int(h * scale)))
                movie.setSpeed(100)
                movie.start()
                self.movie_cache[key] = movie

            return self.movie_cache[key].currentPixmap()

        # Static image
        if name in self.emoticon_cache:
            return self.emoticon_cache[name]

        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            w, h = pixmap.width(), pixmap.height()
            if w > self._emoticon_max_size or h > self._emoticon_max_size:
                scale = self._emoticon_max_size / max(w, h)
                pixmap = pixmap.scaled(
                    int(w * scale), int(h * scale),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            self.emoticon_cache[name] = pixmap

        return pixmap

    def cleanup(self):
        """Cleanup caches and resources"""
        self.emoticon_cache.clear()
        for movie in self.movie_cache.values():
            try:
                movie.stop()
            except Exception:
                pass
        self.movie_cache.clear()

        if self.image_viewer:
            self.image_viewer.cleanup()
            self.image_viewer.deleteLater()
            self.image_viewer = None
        if self._video_player:
            self._video_player.cleanup()
            self._video_player.deleteLater()
            self._video_player = None
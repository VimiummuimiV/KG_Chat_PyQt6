"""ChatlogWidget: search bar, mention and username filters."""

import re
from bisect import bisect_right
from datetime import datetime

from components.button import set_button_icon
from components.search import SearchQuery
from core.chatlogs.search_index import MessageSearchIndex
from core.state.mention_aliases import mention_aliases
from helpers.dates import parse_short_date
from helpers.translate import tr


class ChatlogSearchMixin:
    """ChatlogWidget: search bar, mention and username filters."""

    def has_active_search_or_filter(self) -> bool:
        return bool(
            self.search_text
            or self.filtered_usernames
            or self.filter_mentions
        )

    @property
    def search_visible(self) -> bool:
        return self.search.visible_state

    def toggle_search(self):
        self.search.toggle()

    def toggle_mention_filter(self):
        """Toggle mention filter on/off"""
        self.filter_mentions = not self.filter_mentions

        # Update icon based on state
        set_button_icon(self.mention_filter_button, "fill/at-fill.svg" if self.filter_mentions else "line/at-line.svg")

        # Reapply filter to show/hide messages
        self.apply_filter()

    def on_search_changed(self, text: str):
        self.search_text = text
        if not self.requires_confirmed_search():
            self.apply_filter()

    def on_search_enter(self):
        """Enter/search button - jump to date for a 'D:<date>' entry, otherwise apply the search."""
        match = re.match(r'^[Dd]:\s*(\S+)', self.search_text)
        if match:
            date_str = parse_short_date(match.group(1))
            try:
                target = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.info_label.setText(tr(f"Invalid date: {match.group(1)}", f"Неверная дата: {match.group(1)}"))
                return

            if not (self.parser.MIN_DATE <= target <= datetime.now().date()):
                self.info_label.setText(tr(f"Date out of range: {date_str}", f"Дата вне диапазона: {date_str}"))
                return

            self._clear_search()
            self.load_date(date_str)
            return

        self.apply_filter()

    def current_search_query(self) -> SearchQuery:
        return SearchQuery(self.search_text)

    def _clear_search(self):
        self.search.clear()
        self.apply_filter()

    def set_username_filter(self, usernames: set):
        self.filtered_usernames = usernames
        self.apply_filter()
        self.filter_changed.emit(self.filtered_usernames)

    def clear_filter(self):
        self.filtered_usernames = set()
        self.apply_filter()
        self.filter_changed.emit(self.filtered_usernames)

    def _message_matches_filters(self, msg, query: SearchQuery) -> bool:
        if self.filter_mentions and self.account and self.account.get('chat_username'):
            if not mention_aliases.is_mentioned(self.account.get('chat_username'), msg.body):
                return False
        if not query.is_prefix_mode and self.filtered_usernames and msg.username not in self.filtered_usernames:
            return False
        return query.matches(msg.username, msg.body)

    def filter_messages(self, messages, query: SearchQuery):
        """Keep matching messages together with the date separator that precedes them.
        The query is parsed once by the caller and shared - never re-parsed here."""
        if not self.has_active_search_or_filter():
            return list(messages)

        if query.needle and messages is self.all_messages:
            if self.search_index is None:
                self.search_index = MessageSearchIndex(messages)
            rows = self.search_index.rows_containing(query.needle)
            if rows is not None:
                return self._filter_rows(messages, rows, query)
        result = []
        pending_separator = None
        previous_shown = None
        hidden_since_previous = False
        for msg in messages:
            if msg.is_separator:
                pending_separator = msg
                previous_shown = None
                continue
            if self._message_matches_filters(msg, query):
                if pending_separator is not None:
                    result.append(pending_separator)
                    pending_separator = None
                msg.joins_previous = (
                    previous_shown is not None
                    and not hidden_since_previous
                    and previous_shown.username == msg.username
                )
                msg.joins_next = False
                if previous_shown is not None:
                    previous_shown.joins_next = msg.joins_previous
                previous_shown = msg
                hidden_since_previous = False
                result.append(msg)
            else:
                hidden_since_previous = True
        return result

    def _filter_rows(self, messages, rows, query: SearchQuery):
        """filter_messages for a text search: checks only the rows that contain the text, the result is the same."""
        separator_rows = self.search_index.separator_rows
        result = []
        previous_row = None
        shown_separator_row = None
        for row in rows:
            msg = messages[row]
            if not self._message_matches_filters(msg, query):
                continue
            separator_index = bisect_right(separator_rows, row) - 1
            if separator_index >= 0 and separator_rows[separator_index] != shown_separator_row:
                shown_separator_row = separator_rows[separator_index]
                result.append(messages[shown_separator_row])
            previous = messages[previous_row] if previous_row is not None else None
            msg.joins_previous = previous_row == row - 1 and previous.username == msg.username
            msg.joins_next = False
            if previous is not None:
                previous.joins_next = msg.joins_previous
            previous_row = row
            result.append(msg)
        return result

    def apply_filter(self):
        self.list_view.setUpdatesEnabled(False)
        self.model.clear()

        if not self.all_messages:
            self.list_view.setUpdatesEnabled(True)
            self.update_copy_save_tooltips()
            return

        query = self.current_search_query()
        self.delegate.set_highlight_text(query.highlight_text)
        self.delegate.set_continuity_rails(self.has_active_search_or_filter())
        self.clear_anchors()
        messages_to_show = self.filter_messages(self.all_messages, query)
        self.model.set_messages(messages_to_show)
        self.list_view.setUpdatesEnabled(True)
        self.update_copy_save_tooltips()

        total = self.message_count()
        shown = self.count_messages(messages_to_show)

        filters = []
        if self.filter_mentions:
            filters.append("mentions only")
        if query.is_prefix_mode:
            if query.users:
                filters.append(f"users: {', '.join(sorted(query.users))}")
            if query.message_text:
                filters.append(f"message: '{query.message_text}'")
        else:
            if self.filtered_usernames:
                filters.append(f"users: {', '.join(sorted(self.filtered_usernames))}")
            if self.search_text:
                filters.append(f"search: '{self.search_text}'")

        if filters:
            self.info_label.setText(tr(
                f"Showing {shown}/{total} messages ({' | '.join(filters)})",
                f"Показано {shown}/{total} сообщений ({' | '.join(filters)})")
            )
        else:
            if hasattr(self, 'pending_data'):
                _, size_text, was_truncated, from_cache = self.pending_data
                cache_marker = " 📁" if from_cache else ""
                if was_truncated:
                    self.info_label.setText(tr(
                        f"⚠️ Loaded {total} messages (file truncated at {self.parser.MAX_FILE_SIZE_MB}MB limit) · {size_text}{cache_marker}",
                        f"⚠️ Загружено {total} сообщений (файл обрезан на {self.parser.MAX_FILE_SIZE_MB}МБ) · {size_text}{cache_marker}")
                    )
                else:
                    self.info_label.setText(tr(
                        f"Loaded {total} messages · {size_text}{cache_marker}",
                        f"Загружено {total} сообщений · {size_text}{cache_marker}")
                    )
            else:
                self.info_label.setText(tr(f"Loaded {total} messages", f"Загружено {total} сообщений"))

        self.scroll_to_bottom()

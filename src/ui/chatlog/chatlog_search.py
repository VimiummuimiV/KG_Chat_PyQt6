"""ChatlogWidget: search bar, mention and username filters."""

import re
from datetime import datetime

from components.button import set_button_icon
from components.search import parse_search_text
from helpers.dates import parse_short_date
from helpers.text.mention_parser import parse_mentions
from helpers.translate import tr


class ChatlogSearchMixin:
    """ChatlogWidget: search bar, mention and username filters."""

    def _has_active_search_or_filter(self) -> bool:
        return bool(
            self.search_text
            or self.filtered_usernames
            or self.filter_mentions
        )

    @property
    def search_visible(self) -> bool:
        return self.search.visible_state

    @property
    def search_field(self):
        return self.search.field

    def toggle_search(self):
        self.search.toggle()

    def toggle_mention_filter(self):
        """Toggle mention filter on/off"""
        self.filter_mentions = not self.filter_mentions

        # Update icon based on state
        set_button_icon(self.mention_filter_btn, "at-fill.svg" if self.filter_mentions else "at-line.svg")

        # Reapply filter to show/hide messages
        self._apply_filter()

    def _on_search_changed(self, text: str):
        self.search_text = text
        if not self._requires_confirmed_search():
            self._apply_filter()

    def _on_search_enter(self):
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

        self._apply_filter()

    def _parse_search_text(self):
        return parse_search_text(self.search_text)

    def _clear_search(self):
        self.search.clear()
        self._apply_filter()

    def set_username_filter(self, usernames: set):
        self.filtered_usernames = usernames
        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)

    def clear_filter(self):
        self.filtered_usernames = set()
        self._apply_filter()
        self.filter_changed.emit(self.filtered_usernames)

    def _message_matches_filters(self, msg, search_users, search_message, is_prefix_mode) -> bool:
        if self.filter_mentions and self.account and self.account.get('chat_username'):
            my_username = self.account.get('chat_username')
            if not any(is_mention for is_mention, _ in parse_mentions(msg.body, my_username)):
                return False

        if is_prefix_mode:
            if search_users and msg.username.lower() not in search_users:
                return False
            if search_message and search_message not in msg.body.lower():
                return False
        else:
            if self.filtered_usernames and msg.username not in self.filtered_usernames:
                return False
            if self.search_text:
                search_lower = self.search_text.lower()
                if search_lower not in msg.username.lower() and search_lower not in msg.body.lower():
                    return False
        return True

    def _filter_messages(self, messages, search_users, search_message, is_prefix_mode):
        """Keep matching messages together with the date separator that precedes them.
        search_users/search_message/is_prefix_mode come from _parse_search_text(),
        parsed once by the caller and shared - never re-parsed here."""
        if not self._has_active_search_or_filter():
            return list(messages)

        search_users_lower = {u.lower() for u in search_users} if search_users else set()
        result = []
        pending_separator = None
        previous_shown = None
        hidden_since_previous = False
        for msg in messages:
            if msg.is_separator:
                pending_separator = msg
                previous_shown = None
                continue
            if self._message_matches_filters(msg, search_users_lower, search_message, is_prefix_mode):
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

    def _apply_filter(self):
        self.list_view.setUpdatesEnabled(False)
        self.model.clear()

        if not self.all_messages:
            self.list_view.setUpdatesEnabled(True)
            self._update_copy_save_tooltips()
            return

        search_users, search_message, is_prefix_mode = self._parse_search_text()
        self.delegate.set_highlight_text(search_message if is_prefix_mode else self.search_text)
        self.delegate.set_continuity_rails(self._has_active_search_or_filter())
        self._clear_anchors()
        messages_to_show = self._filter_messages(self.all_messages, search_users, search_message, is_prefix_mode)
        self.model.set_messages(messages_to_show)
        self.list_view.setUpdatesEnabled(True)
        self._update_copy_save_tooltips()

        total = self._message_count()
        shown = self._count_messages(messages_to_show)

        filters = []
        if self.filter_mentions:
            filters.append("mentions only")
        if is_prefix_mode:
            if search_users:
                filters.append(f"users: {', '.join(sorted(search_users))}")
            if search_message:
                filters.append(f"message: '{search_message}'")
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
            if hasattr(self, '_pending_data'):
                _, size_text, was_truncated, from_cache = self._pending_data
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

        self._scroll_to_bottom()

"""ChatWindow: presence log panel, its splitter and tracker events."""

from PyQt6.QtCore import QTimer

from ui.chat.ui_messages import MessagesWidget
from ui.settings.settings_options import DEFAULTS


class ChatPresenceLogMixin:
    """ChatWindow: presence log panel, its splitter and tracker events."""

    def _presence_log_enabled(self) -> bool:
        val = self.config.get("user_tracker", "presence_log")
        return True if val is None else bool(val)

    def set_presence_log_enabled(self, enabled: bool):
        if not enabled:
            self.teardown_presence_log_widget()

    def _presence_split_percent(self) -> int:
        value = self.config.get("user_tracker", "presence_log_split_percent")
        if value is None:
            value = DEFAULTS["user_tracker"]["presence_log_split_percent"]
        return max(
            DEFAULTS["user_tracker"]["presence_log_split_percent_min"],
            min(DEFAULTS["user_tracker"]["presence_log_split_percent_max"], int(value)),
        )

    def _presence_split_bounds(self):
        """(total, max_top) for the presence pane, or None if not yet measurable."""
        total = self.presence_pane_splitter.height() or self.height()
        if total <= 0:
            return None
        return total, max(40, total * self._presence_split_percent() // 100)

    def _apply_presence_split_sizes(self):
        """Fit presence pane to content height, capped by configured max percent."""
        if not self.presence_log_widget:
            return
        bounds = self._presence_split_bounds()
        if bounds is None:
            return
        total, max_top = bounds
        view, model = self.presence_log_widget.list_view, self.presence_log_widget.model
        content = sum(view.sizeHintForRow(r) for r in range(model.rowCount()))
        if content:
            content += view.frameWidth() * 2
            layout = self.presence_log_widget.layout()
            if layout is not None:
                margins = layout.contentsMargins()
                content += margins.top() + margins.bottom()
            content += 8  # slack: padding/wrap so the scrollbar does not flash on
        top = min(max_top, max(40, content))
        self.presence_pane_splitter.setSizes([top, max(40, total - top)])
        QTimer.singleShot(0, self._presence_split_absorb_scroll)

    def _presence_split_absorb_scroll(self):
        """If a vertical scrollbar still appeared, grow the pane up to the max."""
        if not self.presence_log_widget:
            return
        view = self.presence_log_widget.list_view
        scrollbar = view.verticalScrollBar()
        if scrollbar is None or scrollbar.maximum() <= 0:
            return
        bounds = self._presence_split_bounds()
        if bounds is None:
            return
        total, max_top = bounds
        sizes = self.presence_pane_splitter.sizes()
        if len(sizes) < 2 or sizes[0] >= max_top:
            return
        top = min(max_top, sizes[0] + scrollbar.maximum() + 4)
        if top > sizes[0]:
            self.presence_pane_splitter.setSizes([top, max(40, total - top)])

    def _on_presence_split_moved(self, pos: int, _index: int):
        # Debounce: splitterMoved fires on every drag pixel; only persist after idle.
        if not self.presence_log_widget:
            return
        total = self.presence_pane_splitter.height()
        if total <= 0:
            return
        self._pending_presence_split_percent = round(pos * 100 / total)
        if not hasattr(self, "_presence_split_commit_timer"):
            self._presence_split_commit_timer = QTimer(self)
            self._presence_split_commit_timer.setSingleShot(True)
            self._presence_split_commit_timer.timeout.connect(self._commit_presence_split_percent)
        self._presence_split_commit_timer.start(150)

    def _commit_presence_split_percent(self):
        percent = getattr(self, "_pending_presence_split_percent", None)
        if percent is None:
            return
        self.config.set("user_tracker", "presence_log_split_percent", value=percent)
        spin = getattr(getattr(self, "settings_widget", None), "tracker_presence_log_split_spin", None)
        if spin is not None:
            spin.blockSignals(True)
            spin.setValue(percent)
            spin.blockSignals(False)
            slider = getattr(spin, "linked_slider", None)
            if slider is not None:
                slider.blockSignals(True)
                slider.setValue(percent)
                slider.blockSignals(False)
            update_reset = getattr(spin, "update_reset_state", None)
            if update_reset is not None:
                update_reset(percent)

    def _ensure_presence_log_widget(self):
        """Create the presence log pane above the messages view, reusing MessagesWidget for consistent badge rendering."""
        if self.presence_log_widget is not None:
            return
        self.presence_log_widget = MessagesWidget(
            self.config, self.emoticon_manager, my_username=self.my_username, minimal=True
        )
        self._wire_username_signals(self.presence_log_widget, right_click_widget=self.presence_log_widget)
        # Torn down automatically once emptied — by hotkey (X), by clearing a single
        # entry down to none, or by disabling tracking — same as never having opened it.
        self.presence_log_widget.model.rowsRemoved.connect(self._on_presence_log_rows_changed)
        self.presence_log_widget.model.modelReset.connect(self._on_presence_log_rows_changed)
        self.presence_pane_splitter.insertWidget(0, self.presence_log_widget)
        self._apply_presence_split_sizes()

    def teardown_presence_log_widget(self):
        if self.presence_log_widget is None:
            return
        widget = self.presence_log_widget
        self.presence_log_widget = None
        widget.cleanup()
        widget.setParent(None)
        widget.deleteLater()

    def _on_presence_log_rows_changed(self, *_args):
        if self.presence_log_widget and self.presence_log_widget.model.rowCount() == 0:
            self.teardown_presence_log_widget()

    def _on_tracker_enabled_changed(self, enabled: bool):
        """Hide the presence pane when 'Track users' is disabled; restore it on the next event."""
        if not enabled:
            self.teardown_presence_log_widget()

    def _on_presence_notification_click(self, login: str, event_ts=None):

        action = self.config.get("user_tracker", "click_action") or "history"
        if action == "chat":
            self._show_and_focus_window()
            return
        self._open_tracker_history_event(login, event_ts)

    def _open_tracker_history_event(self, login: str, event_ts=None):
        self._show_and_focus_window()
        self.show_user_tracker_view()
        w = getattr(self, 'user_tracker_widget', None)
        if w is not None:
            w.reveal_event(login, event_ts)

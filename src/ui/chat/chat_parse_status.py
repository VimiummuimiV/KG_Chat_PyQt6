"""ChatWindow: chatlog parser view and its status bar."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from components.badge import apply_counter_style
from components.button import create_icon_button
from helpers.translate import tr
from ui.notification.popup_manager import show_notification


class ChatParseStatusMixin:
    """ChatWindow: chatlog parser view and its status bar."""

    def _set_parse_results_badge(self, n: int):
        badge = getattr(self, "_parse_results_badge", None)
        button = None
        if self.parse_status_widget:
            button = self.parse_status_widget.findChild(QPushButton, "view_parser_btn")
        if not badge or not button:
            return
        n = max(0, int(n))
        if n <= 0:
            badge.hide()
            button.setToolTip(tr("View results", "Показать результаты"))
            return
        badge.setText("99+" if n > 99 else str(n))
        badge.adjustSize()
        badge.move(1, button.height() - badge.height() - 1)
        badge.show()
        badge.raise_()
        button.setToolTip(tr(f"View results — {n} new", f"Показать результаты — {n} новых"))

    def show_parser_view(self):
        """Open chatlog list with current parse results and hide the status bar."""
        self._set_parse_results_badge(0)
        self.stop_parse_status()
        self.show_chatlog_view(reload=False)
        cw = self.chatlog_widget
        if cw and cw.parser_visible:
            cw.toggle_parser()

    def _create_parse_status_widget(self):
        """Create the parse status widget dynamically"""
        parse_status_widget = QWidget()
        parse_status_layout = QHBoxLayout()
        parse_status_widget.setLayout(parse_status_layout)

        parse_progress_bar = QProgressBar()
        parse_status_layout.addWidget(parse_progress_bar, stretch=1)

        parse_current_label = QLabel("")
        parse_status_layout.addWidget(parse_current_label)

        stop_parse_btn = create_icon_button(self.icons_path, "fill/stop-large-fill.svg", "", config=self.config)
        self.tr_set(stop_parse_btn.setToolTip, "Stop Parsing", "Остановить парсинг")
        stop_parse_btn.setObjectName("stop_parse_btn")
        stop_parse_btn.clicked.connect(self._on_parse_status_stop)
        parse_status_layout.addWidget(stop_parse_btn)

        view_parser_btn = create_icon_button(self.icons_path, "fill/file-list-fill.svg", "", config=self.config)
        self.tr_set(view_parser_btn.setToolTip, "View results", "Показать результаты")
        view_parser_btn.setObjectName("view_parser_btn")
        view_parser_btn.clicked.connect(self.show_parser_view)
        parse_status_layout.addWidget(view_parser_btn)

        close_parse_btn = create_icon_button(self.icons_path, "line/close-large-line.svg", "", config=self.config)
        self.tr_set(close_parse_btn.setToolTip, "Close", "Закрыть")
        close_parse_btn.setObjectName("close_parse_btn")
        close_parse_btn.clicked.connect(self.stop_parse_status)
        close_parse_btn.setVisible(False)
        parse_status_layout.addWidget(close_parse_btn)

        self._parse_results_badge = QLabel(view_parser_btn)
        self._parse_results_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._parse_results_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        apply_counter_style(
            self._parse_results_badge, "join",
            font_size=self.badge_font_size(),
            is_dark=self.theme_manager.is_dark(),
        )
        self._parse_results_badge.hide()

        main_layout = self.layout()
        main_layout.addWidget(parse_status_widget)

        return parse_status_widget, parse_progress_bar, parse_current_label

    def start_parse_status(self):
        """Start showing parse status"""
        if self.parse_status_widget is None:
            self.parse_status_widget, self.parse_progress_bar, self.parse_current_label = self._create_parse_status_widget()
        self.parse_status_widget.setVisible(True)
        self.parse_progress_bar.setValue(0)
        self.parse_current_label.setText("")

    def _on_parse_status_stop(self):
        if self.chatlog_widget:
            self.chatlog_widget.on_parse_cancelled()
        elif self.mentions_digest_active:
            self.end_mentions_digest()
            self.stop_parse_status()

    def stop_parse_status(self):
        """Stop showing parse status and destroy widget"""
        if self.parse_status_widget:
            main_layout = self.layout()
            main_layout.removeWidget(self.parse_status_widget)
            self.parse_status_widget.deleteLater()
            self.parse_status_widget = None
            self.parse_progress_bar = None
            self.parse_current_label = None
            self._parse_results_badge = None

    def update_parse_progress(self, start_date: str, current_date: str, percent: int):
        if self.parse_progress_bar:
            self.parse_progress_bar.setValue(percent)
            self.parse_current_label.setText(f"{start_date} - {current_date}")

    def on_parse_finished(self):
        self.handle_parse_finished()

    def handle_parse_finished(self):
        """Keep parse status visible but update to finished state"""
        if self.parse_status_widget:
            # Hide stop button; show Close only after finish
            stop_button = self.parse_status_widget.findChild(QPushButton, "stop_parse_btn")
            if stop_button:
                stop_button.setVisible(False)
            close_button = self.parse_status_widget.findChild(QPushButton, "close_parse_btn")
            if close_button:
                close_button.setVisible(True)
            # Update label
            if self.mentions_digest_active:
                count = 0
                if self.chatlog_widget:
                    count = sum(
                        1 for m in (self.chatlog_widget.all_messages or [])
                        if not getattr(m, "is_separator", False)
                    )
                self.end_mentions_digest()
                if not count:
                    # Silent background check found nothing — auto-close instead
                    # of leaving the bar up waiting for a manual Close click.
                    self.stop_parse_status()
                    return
                self.parse_current_label.setText(tr(f"Mentions: {count} new", f"Упоминания: {count} новых"))
                self._set_parse_results_badge(count)
                if not self.isVisible():
                    show_notification(
                        title=tr("Personal Mentions", "Личные упоминания"),
                        message=tr(f"{count} new mention(s) found", f"Найдено новых упоминаний: {count}"),
                        config=self.config,
                        emoticon_manager=self.emoticon_manager,
                        account=self.account,
                        is_mention=True,
                        is_parser=True,
                        window_show_callback=self.open_mentions_from_notification,
                    )
                    self.play_mention_sound()
            else:
                self.parse_current_label.setText(tr("Parsing finished", "Парсинг завершён"))

    def on_parse_error(self, error_msg: str):
        self.end_mentions_digest()
        self.stop_parse_status()
        show_notification(
            title=tr("Parse Error", "Ошибка парсинга"),
            message=error_msg,
            config=self.config,
            emoticon_manager=self.emoticon_manager,
            account=self.account
        )

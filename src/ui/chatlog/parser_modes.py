"""Parser config: search mode and date-mode switching."""

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from components.button import create_icon_button
from helpers.dates import DATE_PLACEHOLDER
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import tr
from ui.chatlog.parser_modes_data import MENTION_SUB_KEYS, MENTION_SUB_LABELS


class ParserModesMixin:
    """Parser config: search mode and date-mode switching."""

    def _update_mention_label(self):
        """Update the mention label based on current mode and inputs"""
        mode = self.mode_combo.currentData() or self.mode_combo.currentText()

        if mode != "Personal Mentions":
            self.mention_label_widget.setVisible(False)
            return

        self.mention_label_widget.setVisible(True)

        # Get current username
        current_username = self._get_current_username()

        # Get search terms (mentions to search for)
        search_text = self.search_input.text().strip()
        search_terms = [k.strip() for k in search_text.split(',') if k.strip()] if search_text else []

        # Add current username if available and not already in list
        all_mentions = []
        if current_username:
            all_mentions.append(current_username)
        for term in search_terms:
            if not current_username or term.lower() != current_username.lower():
                all_mentions.append(term)

        # Get username filter (which users' messages to search in)
        username_text = self.username_input.text().strip()
        username_filter = [u.strip() for u in username_text.split(',') if u.strip()] if username_text else []

        # Build label text
        if all_mentions and username_filter:
            mentions_str = ', '.join(all_mentions)
            users_str = ', '.join(username_filter)
            self.mention_label_widget.setText(tr(
                f"🔍 Searching mentions of: {mentions_str} in messages from: {users_str}",
                f"🔍 Поиск упоминаний: {mentions_str} в сообщениях от: {users_str}")
            )
        elif all_mentions:
            mentions_str = ', '.join(all_mentions)
            self.mention_label_widget.setText(tr(
                f"🔍 Searching mentions of: {mentions_str} in messages from: all users",
                f"🔍 Поиск упоминаний: {mentions_str} в сообщениях от: всех пользователей")
            )
        elif username_filter:
            users_str = ', '.join(username_filter)
            self.mention_label_widget.setText(tr(
                "⚠️ No mentions specified. Please add keywords in the Mentions field.",
                "⚠️ Упоминания не указаны. Добавьте ключевые слова в поле Упоминания.")
            )
        else:
            self.mention_label_widget.setText(tr(
                "⚠️ No mentions specified. Please log in or add keywords in the Mentions field.",
                "⚠️ Упоминания не указаны. Войдите или добавьте ключевые слова в поле Упоминания.")
            )

    def _on_mode_changed(self, index: int):
        """Update UI based on selected mode"""
        # Clear existing date inputs
        while self.date_layout.count():
            item = self.date_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        mode = self.mode_combo.currentData() or self.mode_combo.currentText()
        self.is_sync_mode = (mode == "Sync Database")
        is_mention_mode = (mode == "Personal Mentions")

        # Update field labels based on mode
        if is_mention_mode:
            self.username_label.setText(tr("From Users:", "От пользователей:"))
            self.username_input.setPlaceholderText(
                tr("comma-separated (leave empty for all users)", "через запятую (пусто = все пользователи)"))
            self.search_label.setText(tr("Mentions:", "Упоминания:"))
            self.search_input.setPlaceholderText(
                tr("keywords or usernames to search for (comma-separated)", "ключевые слова или имена (через запятую)"))

            # Prefill current username in Mentions field
            if not self.search_input.text().strip():
                current_username = self._get_current_username()
                if current_username:
                    self.search_input.setText(current_username)
        else:
            self.username_label.setText(tr("Usernames:", "Имена:"))
            self.username_input.setPlaceholderText(
                tr("comma-separated (leave empty for all users)", "через запятую (пусто = все пользователи)"))
            self.search_label.setText(tr("Search:", "Поиск:"))
            self.search_input.setPlaceholderText(
                tr("comma-separated search terms (leave empty for all messages)", "термины через запятую (пусто = все сообщения)"))

            # Clear search input when switching away from Personal Mentions
            if hasattr(self, '_previous_mode') and self._previous_mode == "Personal Mentions":
                self.search_input.clear()

        self._previous_mode = mode

        # Update mention label
        self._update_mention_label()

        # Hide username and search inputs for sync mode
        self.username_container_widget.setVisible(not self.is_sync_mode)
        self.search_container_widget.setVisible(not self.is_sync_mode)

        if mode == "Single Date":
            self._add_date_input(tr("Date:", "Дата:"), "single_date")

        elif mode == "From Date":
            self._add_date_input(tr("From:", "С:"), "from_date")
            info = QLabel(tr("(to today)", "(до сегодня)"))
            info.setStyleSheet("color: #888;")
            self.date_layout.addWidget(info)

        elif mode == "Date Range":
            self._add_date_input(tr("Range:", "Диапазон:"), "range_dates", f"{DATE_PLACEHOLDER}  {DATE_PLACEHOLDER}")

        elif mode == "From Start":
            info = QLabel(tr("Will parse from 2012-12-02 to today", "Парсинг с 2012-12-02 до сегодня"))
            info.setStyleSheet("color: #888;")
            self.date_layout.addWidget(info)

        elif mode == "From Registered":
            info = QLabel(tr(
                "Will use registration date of entered user(s)",
                "Будет использована дата регистрации указанных пользователей")
            )
            info.setStyleSheet("color: #888;")
            self.date_layout.addWidget(info)

        elif mode == "Sync Database":
            info = QLabel(tr(
                "📁 Sync all missing chatlogs to database",
                "📁 Синхронизировать все недостающие чатлоги в базу")
            )
            info.setStyleSheet("color: #4CAF50; font-weight: bold; padding: 8px;")
            self.date_layout.addWidget(info)

            desc = QLabel(tr(
                "This will fetch all chatlogs from 2012-12-02 to today that are not yet in the database. "
                "No messages will be displayed - only database synchronization.",
                "Загрузит все чатлоги с 2012-12-02 до сегодня, которых ещё нет в базе. "
                "Сообщения не будут показаны — только синхронизация базы."
            ))
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #888; padding: 4px;")
            self.date_layout.addWidget(desc)

        elif mode == "Personal Mentions":
            sub_mode_layout = QHBoxLayout()
            sub_mode_layout.setSpacing(self.spacing)
            sub_mode_label = self._create_label(tr("Date Mode:", "Режим дат:"))
            sub_mode_layout.addWidget(sub_mode_label)

            self.mention_date_combo = QComboBox()
            self.mention_date_combo.setFixedHeight(self.input_height)
            self.mention_date_combo.setFont(get_font(FontType.UI))
            for key in MENTION_SUB_KEYS:
                en, ru = MENTION_SUB_LABELS[key]
                self.mention_date_combo.addItem(tr(en, ru), key)
            self.mention_date_combo.currentIndexChanged.connect(self._on_mention_date_mode_changed)
            sub_mode_layout.addWidget(self.mention_date_combo, stretch=1)

            container = QWidget()
            container.setLayout(sub_mode_layout)
            self.date_layout.addWidget(container)

            # Initialize with first sub-mode
            self._on_mention_date_mode_changed(0)

    def _on_mention_date_mode_changed(self, index: int):
        """Update date inputs for personal mentions sub-mode"""
        # Remove existing inputs (except the sub-mode selector)
        while self.date_layout.count() > 1:
            item = self.date_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        sub_mode = self.mention_date_combo.currentData() or self.mention_date_combo.currentText()

        if sub_mode == "Single Date":
            self._add_date_input(tr("Date:", "Дата:"), "mention_single_date")
        elif sub_mode == "From Date":
            self._add_date_input(tr("From:", "С:"), "mention_from_date")
        elif sub_mode == "Date Range":
            self._add_date_input(tr("Range:", "Диапазон:"), "mention_range_dates", f"{DATE_PLACEHOLDER}  {DATE_PLACEHOLDER}")
        elif sub_mode == "From Start":
            pass # No input needed
        elif sub_mode == "Last N Days":
            days_layout, self.days_input = self._create_input_row(tr("Days:", "Дней:"), "7")
            self.days_input.setText("7")

            container = QWidget()
            container.setLayout(days_layout)
            self.date_layout.addWidget(container)

    def _add_date_input(self, label_text: str, obj_name: str, placeholder: str = None):
        """Add a date input field with calendar picker"""
        layout, line_edit = self._create_input_row(label_text, placeholder or DATE_PLACEHOLDER, obj_name)

        # Add auto-format on blur
        line_edit.editingFinished.connect(lambda: self._auto_format_date(line_edit))

        # Add calendar button
        calendar_btn = create_icon_button(
            self.icons_path, "calendar.svg", "Select date",
            size_type="large", config=self.config
        )
        calendar_btn.clicked.connect(lambda: self._show_date_picker(line_edit, calendar_btn))
        layout.addWidget(calendar_btn)

        container = QWidget()
        container.setLayout(layout)
        self.date_layout.addWidget(container)

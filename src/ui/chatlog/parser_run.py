"""Parser config: building the parse config and running or cancelling a parse."""

from datetime import datetime, timedelta
from typing import List, Optional

from PyQt6.QtWidgets import QLineEdit, QMessageBox

from components.button import set_button_icon
from components.toast import show_toast, ToastKind
from core.chatlogs.range_parser import ParseConfig
from core.web.api_data import get_registration_date
from helpers.translate import tr


class ParserRunMixin:
    """Parser config: building the parse config and running or cancelling a parse."""

    def on_parse_clicked(self):
        """Handle parse button click"""
        if self.is_parsing:
            # Stop parsing
            self._cancel_parsing()
        else:
            # Start parsing
            self._start_parsing()

    def on_copy_clicked(self):
        """Copy results to clipboard"""
        pass

    def on_save_clicked(self):
        """Save results to file"""
        pass

    def _start_parsing(self):
        """Validate any typed usernames (mode-permitting) before actually starting the parse"""
        mode = self.mode_combo.currentData() or self.mode_combo.currentText()
        usernames = [] if mode == "Sync Database" else self.get_usernames()
        if not usernames:
            self._on_parse_usernames_validated([], [])
            return
        self.parse_button.setEnabled(False)
        self.validate_usernames(usernames, self._on_parse_usernames_validated)

    def _on_parse_usernames_validated(self, valid: list, invalid: list):
        """Start parse; confirm if some names are unknown to the API (still present in logs)."""
        self.parse_button.setEnabled(True)
        if invalid and not self.confirm_unknown_usernames(
            invalid, "Continue parsing anyway? Old names may still appear in chatlogs."
        ):
            return

        try:
            config = self._build_parse_config()
            if not config:
                return

            # Update UI for parsing state
            self.is_parsing = True
            set_button_icon(self.parse_button, "fill/stop-large-fill.svg")
            self.parse_button.setToolTip(tr("Stop parsing (C)", "Остановить парсинг (C)"))
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_label.setVisible(True)

            if config.mode == 'syncdatabase':
                self.progress_label.setText(tr("Syncing database...", "Синхронизация базы..."))
            else:
                self.progress_label.setText(f"{config.from_date} - {config.from_date}")

            # Hide copy/save buttons during parsing
            self.copy_button.setVisible(False)
            self.save_button.setVisible(False)

            # Emit signal
            self.parse_started.emit(config)

        except Exception as e:
            print(f"Error starting parse: {e}")
            self.reset_ui()

    def _cancel_parsing(self):
        """Cancel parsing"""
        self.parse_cancelled.emit()
        self.reset_ui()

    def reset_ui(self):
        """Reset UI to non-parsing state"""
        self.is_parsing = False
        set_button_icon(self.parse_button, "fill/play-large-fill.svg")
        self.parse_button.setToolTip(tr("Start parsing (S)", "Начать парсинг (S)"))
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.progress_label.setText("")

    def show_copy_save_buttons(self):
        """Show copy and save buttons after successful parse"""
        self.copy_button.setVisible(True)
        self.save_button.setVisible(True)
        if not self.is_sync_mode:
            self.saved_usernames_bar.add_values(self.get_usernames())

    def update_progress(self, start_date: str, current_date: str, percent: int):
        """Update progress display"""
        self.progress_bar.setValue(percent)
        if self.is_sync_mode:
            self.progress_label.setText(f"Syncing: {current_date} ({percent}%)")
        else:
            self.progress_label.setText(f"{start_date} - {current_date}")

    def _build_parse_config(self) -> Optional[ParseConfig]:
        """Build ParseConfig from UI inputs"""
        mode = self.mode_combo.currentData() or self.mode_combo.currentText()

        # Earliest allowed date
        EARLIEST_ALLOWED_DATE = "2012-12-02"

        # Get dates based on mode
        from_date = None
        to_date = None

        if mode == "Sync Database":
            from_date = EARLIEST_ALLOWED_DATE
            to_date = datetime.now().strftime('%Y-%m-%d')

        elif mode == "Single Date":
            date_input = self.findChild(QLineEdit, "single_date")
            if not date_input or not date_input.text().strip():
                QMessageBox.warning(self, tr("Missing Date", "Нет даты"), tr("Please enter a date", "Введите дату"))
                return None
            from_date = to_date = date_input.text().strip()

        elif mode == "From Date":
            date_input = self.findChild(QLineEdit, "from_date")
            if not date_input or not date_input.text().strip():
                QMessageBox.warning(self, tr("Missing Date", "Нет даты"), tr("Please enter from date", "Введите начальную дату"))
                return None
            from_date = date_input.text().strip()
            to_date = datetime.now().strftime('%Y-%m-%d')

        elif mode == "Date Range":
            range_input = self.findChild(QLineEdit, "range_dates")
            if not range_input or not range_input.text().strip():
                QMessageBox.warning(self,
                    tr("Missing Dates", "Нет дат"),
                    tr("Please enter date range in format YYYY-MM-DD YYYY-MM-DD", "Введите диапазон в формате ГГГГ-ММ-ДД ГГГГ-ММ-ДД"))
                return None
            dates = range_input.text().strip().split()
            if len(dates) != 2:
                QMessageBox.warning(self,
                    tr("Invalid Format", "Неверный формат"),
                    tr("Invalid range format - use YYYY-MM-DD YYYY-MM-DD", "Неверный формат диапазона — используйте ГГГГ-ММ-ДД ГГГГ-ММ-ДД"))
                return None
            from_date, to_date = dates

        elif mode == "From Start":
            from_date = EARLIEST_ALLOWED_DATE
            to_date = datetime.now().strftime('%Y-%m-%d')

        elif mode == "From Registered":
            # Use original typed usernames if fetch history was used, otherwise parse from field
            if self.original_usernames:
                # Use stored original usernames (before fetch history expanded them)
                usernames_to_check = self.original_usernames
            else:
                # Parse directly from field (fetch history was not used)
                original_usernames_text = self.username_input.text().strip()
                if not original_usernames_text:
                    QMessageBox.warning(self,
                        tr("Missing Username", "Нет имени"),
                        tr("Please enter at least one username", "Введите хотя бы одно имя пользователя"))
                    return None
                usernames_to_check = [u.strip() for u in original_usernames_text.split(',') if u.strip()]

            if not usernames_to_check:
                QMessageBox.warning(self,
                    tr("Missing Username", "Нет имени"),
                    tr("Please enter at least one username", "Введите хотя бы одно имя пользователя"))
                return None

            # Fetch registration dates only for originally typed usernames
            reg_dates = []
            for username in usernames_to_check:
                reg_date = get_registration_date(username)
                if reg_date:
                    reg_dates.append(reg_date)

            if not reg_dates:
                QMessageBox.warning(self,
                    tr("Error", "Ошибка"),
                    tr(
                        "Could not get registration date for specified username(s)",
                        "Не удалось получить дату регистрации для указанных имён")
                    )
                return None

            # Get earliest registration date, but clamp to earliest allowed date
            earliest_reg = min(reg_dates)
            from_date = max(earliest_reg, EARLIEST_ALLOWED_DATE)
            to_date = datetime.now().strftime('%Y-%m-%d')

            # Optionally inform user if date was clamped
            if earliest_reg < EARLIEST_ALLOWED_DATE:
                show_toast(
                    self,
                    tr(
                        f"Registration date {earliest_reg} is before the earliest logs, starting from {EARLIEST_ALLOWED_DATE}",
                        f"Дата регистрации {earliest_reg} раньше самых ранних логов, начинаем с {EARLIEST_ALLOWED_DATE}",
                    ),
                    ToastKind.INFO,
                )

        elif mode == "Personal Mentions":
            sub_mode = self.mention_date_combo.currentData() or self.mention_date_combo.currentText()

            if sub_mode == "Single Date":
                date_input = self.findChild(QLineEdit, "mention_single_date")
                if not date_input or not date_input.text().strip():
                    QMessageBox.warning(self,
                        tr("Missing Date", "Нет даты"),
                        tr("Please enter a date", "Введите дату")
                    )
                    return None
                from_date = to_date = date_input.text().strip()

            elif sub_mode == "From Date":
                date_input = self.findChild(QLineEdit, "mention_from_date")
                if not date_input or not date_input.text().strip():
                    QMessageBox.warning(self,
                        tr("Missing Date", "Нет даты"),
                        tr("Please enter from date", "Введите начальную дату")
                    )
                    return None
                from_date = date_input.text().strip()
                to_date = datetime.now().strftime('%Y-%m-%d')

            elif sub_mode == "Date Range":
                range_input = self.findChild(QLineEdit, "mention_range_dates")
                if not range_input or not range_input.text().strip():
                    QMessageBox.warning(self,
                        tr("Missing Dates", "Нет дат"),
                        tr("Please enter date range in format YYYY-MM-DD YYYY-MM-DD", "Введите диапазон в формате ГГГГ-ММ-ДД ГГГГ-ММ-ДД"))
                    return None
                dates = range_input.text().strip().split()
                if len(dates) != 2:
                    QMessageBox.warning(self,
                        tr("Invalid Format", "Неверный формат"),
                        tr("Invalid range format - use YYYY-MM-DD YYYY-MM-DD", "Неверный формат диапазона — используйте ГГГГ-ММ-ДД ГГГГ-ММ-ДД"))
                    return None
                from_date, to_date = dates

            elif sub_mode == "From Start":
                from_date = EARLIEST_ALLOWED_DATE
                to_date = datetime.now().strftime('%Y-%m-%d')

            elif sub_mode == "Last N Days":
                if not hasattr(self, 'days_input') or not self.days_input.text().strip():
                    QMessageBox.warning(self,
                        tr("Missing Days", "Нет дней"),
                        tr("Please enter number of days", "Введите количество дней"))
                    return None
                try:
                    days = int(self.days_input.text().strip())
                    if days <= 0:
                        QMessageBox.warning(self,
                            tr("Invalid Days", "Неверные дни"),
                            tr("Days must be positive", "Число дней должно быть положительным"))
                        return None
                    to_date = datetime.now().date()
                    from_date = to_date - timedelta(days=days-1)
                    from_date = from_date.strftime('%Y-%m-%d')
                    to_date = to_date.strftime('%Y-%m-%d')
                except ValueError:
                    QMessageBox.warning(self,
                        tr("Invalid Days", "Неверные дни"),
                        tr("Invalid number of days", "Некорректное число дней"))
                    return None

        # Get usernames and search terms (skip for sync mode)
        usernames = [] if mode == "Sync Database" else self.get_usernames()
        search_terms = [] if mode == "Sync Database" else self._get_search_terms()
        mention_keywords = []

        # Override for Personal Mentions mode
        if mode == "Personal Mentions":
            # Personal Mentions: usernames filter whose messages are searched, mention_keywords is what to look for
            usernames = self.get_usernames()

            # Build mention keywords from current username + search field
            mention_keywords = []
            current_username = self.get_current_username()
            if current_username:
                mention_keywords.append(current_username)

            # Add search terms (excluding duplicates)
            # These can be usernames OR any keywords the user wants to search for
            search_text = self.search_input.text().strip()
            if search_text:
                additional = [kw.strip() for kw in search_text.split(',') if kw.strip()]
                for kw in additional:
                    if not current_username or kw.lower() != current_username.lower():
                        mention_keywords.append(kw)

            known_keywords = {keyword.lower() for keyword in mention_keywords}
            for _kind, alias in self.selected_aliases():
                if alias.lower() not in known_keywords:
                    mention_keywords.append(alias)
                    known_keywords.add(alias.lower())

            search_terms = [] # In Personal Mentions mode, search_terms are moved to mention_keywords

        # Build config
        config = ParseConfig(
            mode=mode.lower().replace(' ', ''),
            from_date=from_date,
            to_date=to_date,
            usernames=usernames,
            search_terms=search_terms,
            mention_keywords=mention_keywords
        )

        return config

    def get_usernames(self) -> List[str]:
        """Get usernames from field"""
        text = self.username_input.text().strip()
        if not text:
            return []
        return [u.strip() for u in text.split(',') if u.strip()]

    def _get_search_terms(self) -> List[str]:
        """Get search terms"""
        text = self.search_input.text().strip()
        if not text:
            return []
        return [term.strip() for term in text.split(',') if term.strip()]

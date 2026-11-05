"""Parser config: username validation, history fetching and saved usernames."""

import threading
from functools import partial

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLineEdit, QMessageBox

from components.button import render_svg_icon
from core.web.api_data import get_exact_user_id_by_name, get_usernames_history
from helpers.translate import tr


class ParserUsernamesMixin:
    """Parser config: username validation, history fetching and saved usernames."""

    def _set_username_fetch_loading(self, is_loading: bool):
        """Change username fetch button icon to loader or back to normal"""
        icon_name = "loader.svg" if is_loading else "user-received.svg"
        tooltip = tr("Fetching...", "Загрузка...") if is_loading else tr("Fetch username history", "Загрузить историю имён")
        icon_size = self.fetch_history_button.icon_size
        self.fetch_history_button.setIcon(render_svg_icon(self.icons_path / icon_name, icon_size))
        self.fetch_history_button.setToolTip(tooltip)

    def _set_search_fetch_loading(self, is_loading: bool):
        """Change search fetch button icon to loader or back to normal"""
        icon_name = "loader.svg" if is_loading else "user-received.svg"
        tooltip = tr("Fetching...", "Загрузка...") if is_loading else tr("Fetch username history", "Загрузить историю имён")
        icon_size = self.search_fetch_history_button.icon_size
        self.search_fetch_history_button.setIcon(render_svg_icon(self.icons_path / icon_name, icon_size))
        self.search_fetch_history_button.setToolTip(tooltip)

    def _validate_usernames_enabled(self) -> bool:
        value = self.config.get("chatlog_parser", "validate_usernames")
        return True if value is None else bool(value)

    def _validate_usernames(self, usernames: list, on_done):
        """Check which usernames exist via API (background), then on_done(valid, invalid).
        When validation is disabled, every name is treated as valid."""
        if not self._validate_usernames_enabled():
            on_done(list(usernames), [])
            return

        def _check():
            valid = [u for u in usernames if get_exact_user_id_by_name(u)]
            invalid = [u for u in usernames if u not in valid]
            QTimer.singleShot(0, partial(on_done, valid, invalid))

        threading.Thread(target=_check, daemon=True).start()

    def _confirm_unknown_usernames(self, invalid: list, action: str) -> bool:
        """Ask whether to proceed with names the API does not know (renamed accounts, etc.)."""
        reply = QMessageBox.question(
            self,
            tr("Users Not Found", "Пользователи не найдены"),
            tr(
                f"The following users were not found (they may have renamed):\n"
                f"{', '.join(invalid)}\n\n"
                f"{action}",
                f"Следующие пользователи не найдены (возможно, сменили имя):\n"
                f"{', '.join(invalid)}\n\n"
                f"{action}"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _add_usernames_to_saved(self):
        """Optionally validate typed usernames before saving them as chips"""
        usernames = self._get_usernames()
        if not usernames:
            return
        self.add_username_button.setEnabled(False)
        self._validate_usernames(usernames, self._on_add_validated)

    def _on_add_validated(self, valid: list, invalid: list):
        """Save usernames; ask before saving names the API does not know."""
        self._update_buttons_state()
        to_save = list(valid)
        if invalid:
            if self._confirm_unknown_usernames(
                invalid, tr("Save them to the list anyway?", "Всё равно сохранить в список?")
            ):
                to_save.extend(invalid)
        if to_save:
            self.saved_usernames_bar.add_values(to_save)

    def _fetch_username_history(self, input_field: QLineEdit):
        """Generic fetch username history for any input field"""
        text = input_field.text().strip()
        if not text:
            return

        usernames = [u.strip() for u in text.split(',') if u.strip()]
        if not usernames:
            return

        # Store original usernames before expansion
        self.original_usernames = usernames.copy()

        # Set loading state for specific field
        if input_field == self.username_input:
            self.is_fetching_username = True
            self._set_username_fetch_loading(True)
        elif input_field == self.search_input:
            self.is_fetching_search = True
            self._set_search_fetch_loading(True)

        self._update_buttons_state()

        def _fetch():
            expanded = set()
            not_found = []

            try:
                for username in usernames:
                    # Check if user exists first
                    user_id = get_exact_user_id_by_name(username)

                    if not user_id:
                        # User doesn't exist
                        not_found.append(username)
                        continue

                    # User exists, add original username
                    expanded.add(username)

                    # Try to get username history
                    history = get_usernames_history(username)

                    # If we got history, add it
                    if history and isinstance(history, list):
                        expanded.update(history)

                # Convert to sorted list for consistent ordering
                expanded_list = sorted(expanded)

                # Update UI on main thread - using partial to avoid closure issues
                QTimer.singleShot(0, partial(self._on_fetch_complete, input_field, expanded_list, not_found))

            except Exception as e:
                error_msg = str(e)
                QTimer.singleShot(0, partial(self._on_fetch_error, input_field, error_msg))

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_fetch_complete(self, input_field: QLineEdit, usernames: list, not_found: list):
        """Handle fetch completion"""
        # Reset loading state
        if input_field == self.username_input:
            self.is_fetching_username = False
            self._set_username_fetch_loading(False)
        elif input_field == self.search_input:
            self.is_fetching_search = False
            self._set_search_fetch_loading(False)

        self._update_buttons_state()

        # Always update username field with valid usernames (even if empty)
        if usernames:
            input_field.setText(', '.join(usernames))
        else:
            # All users not found - clear the field
            input_field.clear()

        # Show errors if any users weren't found
        if not_found:
            QMessageBox.warning(
                self,
                tr("Users Not Found", "Пользователи не найдены"),
                tr(
                    f"The following users were not found:\n{', '.join(not_found)}",
                    f"Следующие пользователи не найдены:\n{', '.join(not_found)}"
                )
            )
        elif usernames:
            # Only show success message if we found users and had no errors
            QMessageBox.information(
                self,
                tr("History Fetched", "История загружена"),
                tr(
                    f"Retrieved {len(usernames)} usernames including history.",
                    f"Получено {len(usernames)} имён с учётом истории."
                )
            )
        else:
            # No users found at all
            QMessageBox.warning(
                self,
                tr("No Users Found", "Пользователи не найдены"),
                tr("None of the entered usernames were found.", "Ни одно из введённых имён не найдено.")
            )

    def _on_fetch_error(self, input_field: QLineEdit, error: str):
        """Handle fetch error"""
        # Reset loading state
        if input_field == self.username_input:
            self.is_fetching_username = False
            self._set_username_fetch_loading(False)
        elif input_field == self.search_input:
            self.is_fetching_search = False
            self._set_search_fetch_loading(False)

        self._update_buttons_state()

        QMessageBox.critical(
            self,
            tr("Error", "Ошибка"),
            tr(
                f"Failed to fetch username history:\n{error}",
                f"Не удалось загрузить историю ников:\n{error}")
            )

    def _get_current_username(self):
        """Get current username from account - try chat_username first, fall back to login"""
        if not self.account:
            return None
        return self.account.get('chat_username') or self.account.get('login')

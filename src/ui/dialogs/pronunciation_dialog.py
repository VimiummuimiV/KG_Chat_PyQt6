"""Dialog for setting username pronunciation"""

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from helpers.translate import on_language_changed, TranslatableMixin


class PronunciationDialog(TranslatableMixin, QDialog):
    """Simple dialog to set or edit pronunciation for a username"""

    def __init__(self, parent=None, username: str = ""):
        super().__init__(parent)
        self.init_translatable()
        self.username = username or ""
        self.tr_set(self.setWindowTitle, "Username Pronunciation", "Произношение имени")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self._label = QLabel()
        self.tr_set(
            self._label.setText,
            f"Pronunciation for: {self.username}",
            f"Произношение для: {self.username}",
        )
        layout.addWidget(self._label)

        self._input = QLineEdit()
        self.tr_set(self._input.setPlaceholderText, "Pronunciation", "Произношение")
        layout.addWidget(self._input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        on_language_changed(self._retranslate)

    def _retranslate(self, _code=None):
        self.retranslate_all()
        self.tr_set(
            self._label.setText,
            f"Pronunciation for: {self.username}",
            f"Произношение для: {self.username}",
        )

    def get_pronunciation(self) -> str:
        return self._input.text().strip()

    @staticmethod
    def get_pronunciation_for_user(parent=None, username: str = ""):
        """Show dialog and return (pronunciation, accepted).
        Empty pronunciation + accepted means remove mapping."""
        dialog = PronunciationDialog(parent, username)
        ok = dialog.exec() == QDialog.DialogCode.Accepted
        return (dialog.get_pronunciation() if ok else "", ok)

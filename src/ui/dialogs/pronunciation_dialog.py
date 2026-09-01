"""Dialog for setting username pronunciation"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox

from helpers.translate import tr, on_language_changed, TranslatableMixin


class PronunciationDialog(TranslatableMixin, QDialog):
    """Simple dialog to set or edit pronunciation for a username"""

    def __init__(self, parent=None, username: str = ""):
        super().__init__(parent)
        self._init_translatable()
        self.username = username or ""
        self._tr_set(self.setWindowTitle, "Username Pronunciation", "Произношение имени")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self._lbl = QLabel()
        self._tr_set(
            self._lbl.setText,
            f"Pronunciation for: {self.username}",
            f"Произношение для: {self.username}",
        )
        layout.addWidget(self._lbl)

        self.input = QLineEdit()
        self._tr_set(self.input.setPlaceholderText, "Pronunciation", "Произношение")
        layout.addWidget(self.input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        on_language_changed(self._retranslate)

    def _retranslate(self, _code=None):
        self._retranslate_all()
        self._tr_set(
            self._lbl.setText,
            f"Pronunciation for: {self.username}",
            f"Произношение для: {self.username}",
        )

    def get_pronunciation(self) -> str:
        return self.input.text().strip()

    @staticmethod
    def get_pronunciation_for_user(parent=None, username: str = ""):
        """Show dialog and return (pronunciation, accepted).
        Empty pronunciation + accepted means remove mapping."""
        dlg = PronunciationDialog(parent, username)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return (dlg.get_pronunciation() if ok else "", ok)

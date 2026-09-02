"""Warning dialog with optional buttons to copy raw page HTML and run an action.

Used when parsing structured data from page may fail due to
unexpected content or site markup changes. The HTML can be attached to a
bug report for debugging.
"""

from PyQt6.QtWidgets import QMessageBox, QApplication

from helpers.translate import tr


class CopyableWarningBox(QMessageBox):
    """QMessageBox.warning() plus optional ActionRole buttons for copy-HTML
    and a custom action (e.g. re-authorize). Copy does not close the dialog."""

    def __init__(
        self,
        parent,
        title: str,
        text: str,
        html: str = None,
        action_text: str = None,
    ):
        super().__init__(parent)
        self.setIcon(QMessageBox.Icon.Warning)
        self.setWindowTitle(title)
        self.setText(text)

        self._html = html
        self._copy_button = None
        self._action_button = None
        if html:
            self._copy_button = self.addButton(
                tr("Copy HTML", "Скопировать HTML"),
                QMessageBox.ButtonRole.ActionRole,
            )
        if action_text:
            self._action_button = self.addButton(
                action_text,
                QMessageBox.ButtonRole.ActionRole,
            )
        self.addButton(QMessageBox.StandardButton.Ok)

    def done(self, result):
        if self._copy_button is not None and self.clickedButton() is self._copy_button:
            QApplication.clipboard().setText(self._html)
            self._copy_button.setText(tr("Copied", "Скопировано"))
            return
        super().done(result)


def show_warning_with_html(
    parent,
    title: str,
    text: str,
    html: str = None,
    action_text: str = None,
    on_action=None,
) -> None:
    """Drop-in replacement for QMessageBox.warning() with optional
    'Copy page HTML' and a custom action button (on_action runs after close)."""
    box = CopyableWarningBox(parent, title, text, html, action_text)
    box.exec()
    if on_action and box._action_button is not None and box.clickedButton() is box._action_button:
        on_action()

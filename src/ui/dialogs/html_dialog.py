"""Warning dialog with an optional button to copy the raw page HTML.

Used when parsing structured data from page may fail due to
unexpected content or site markup changes. The HTML can be attached to a
bug report for debugging.
"""

from PyQt6.QtWidgets import QMessageBox, QApplication

from helpers.translate import tr


class CopyableWarningBox(QMessageBox):
    """QMessageBox.warning() plus an 'ActionRole' button that copies `html`
    to the clipboard instead of closing the dialog."""

    def __init__(self, parent, title: str, text: str, html: str = None):
        super().__init__(parent)
        self.setIcon(QMessageBox.Icon.Warning)
        self.setWindowTitle(title)
        self.setText(text)

        self._html = html
        self._copy_button = None
        if html:
            self._copy_button = self.addButton(
                tr("Copy HTML", "Скопировать HTML"),
                QMessageBox.ButtonRole.ActionRole,
            )
        self.addButton(QMessageBox.StandardButton.Ok)

    def done(self, result):
        # Copying shouldn't close the dialog - only the Ok button should.
        if self._copy_button is not None and self.clickedButton() is self._copy_button:
            QApplication.clipboard().setText(self._html)
            self._copy_button.setText(tr("Copied", "Скопировано"))
            return
        super().done(result)


def show_warning_with_html(parent, title: str, text: str, html: str = None) -> None:
    """Drop-in replacement for QMessageBox.warning() that also offers a
    'Copy page HTML' button when `html` is provided."""
    CopyableWarningBox(parent, title, text, html).exec()
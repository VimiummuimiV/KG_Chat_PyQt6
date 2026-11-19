"""Update dialog: the release notes (commit messages) of the available update and the choice to install it."""

from html import escape

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout

from core.web.updater import changes_url, installed_commit, short_commit, UpdateInfo
from helpers.browser import open_url
from helpers.translate import tr


_DIALOG_WIDTH = 560
_DIALOG_HEIGHT = 420


def _notes_html(info: UpdateInfo) -> str:
    """Commit messages as paragraphs: the first line in bold, the rest below it."""
    if not info.messages:
        text = tr("The list of changes is not available: the whole app will be downloaded.",
                  "Список изменений недоступен: приложение будет скачано целиком.")
        return f"<p>{escape(text)}</p>"
    paragraphs = []
    for message in info.messages:
        subject, _, body = message.partition("\n")
        paragraph = f"<p><b>{escape(subject)}</b>"
        if body.strip():
            paragraph += "<br>" + escape(body.strip()).replace("\n", "<br>")
        paragraphs.append(paragraph + "</p>")
    if info.outside_paths:
        files = ", ".join(info.outside_paths)
        text = tr(f"Files outside the app folder also changed ({files}): run the install script again.",
                  f"Изменились и файлы вне папки приложения ({files}): запустите скрипт установки заново.")
        paragraphs.append(f"<p>{escape(text)}</p>")
    return "".join(paragraphs)


class UpdateDialog(QDialog):
    """Shows what an update changes; accepted when the user chooses to install it."""

    def __init__(self, parent, config, info: UpdateInfo):
        super().__init__(parent)
        self.setWindowTitle(tr("Update available", "Доступно обновление"))
        self.resize(_DIALOG_WIDTH, _DIALOG_HEIGHT)

        main_layout = QVBoxLayout(self)
        versions = f"{short_commit(installed_commit() or '')} → {short_commit(info.latest_commit)}"
        main_layout.addWidget(QLabel(tr(f"Changes: {versions}", f"Изменения: {versions}")))

        notes = QTextBrowser()
        notes.setHtml(_notes_html(info))
        main_layout.addWidget(notes, stretch=1)

        button_layout = QHBoxLayout()
        github_button = QPushButton(tr("Open on GitHub", "Открыть на GitHub"))
        github_button.setAutoDefault(False)
        github_button.clicked.connect(lambda: open_url(changes_url(info), config.get("browser")))
        button_layout.addWidget(github_button)
        button_layout.addStretch(1)
        later_button = QPushButton(tr("Later", "Позже"))
        later_button.clicked.connect(self.reject)
        button_layout.addWidget(later_button)
        install_button = QPushButton(tr("Update and restart", "Обновить и перезапустить"))
        install_button.setDefault(True)
        install_button.clicked.connect(self.accept)
        button_layout.addWidget(install_button)
        main_layout.addLayout(button_layout)

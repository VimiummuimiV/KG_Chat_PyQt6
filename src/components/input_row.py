"""Message input row: text field with send and emoticon buttons."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from components.button import create_icon_button, HoverIconButton
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import on_language_changed, TranslatableMixin


_DEFAULT_FIELD_HEIGHT = 48
_DEFAULT_SPACING = 8


class InputRow(TranslatableMixin, QWidget):
    """Text field with a send button and, optionally, an emoticon selector button."""

    submitted = pyqtSignal(str)  # the stripped, non-empty text; the field is already cleared
    emoticon_requested = pyqtSignal()

    def __init__(self, icons_path: Path, config=None, with_emoticons: bool = True, parent=None):
        super().__init__(parent)
        self.init_translatable()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing((config.get("ui", "buttons", "spacing") if config else None) or _DEFAULT_SPACING)

        self.input_field = QLineEdit()
        self.input_field.setFont(get_font(FontType.TEXT))
        self.input_field.setFixedHeight(
            (config.get("ui", "buttons", "large_button", "button_size") if config else None) or _DEFAULT_FIELD_HEIGHT
        )
        self.input_field.returnPressed.connect(self._submit)
        layout.addWidget(self.input_field, stretch=1)

        self.send_button = create_icon_button(icons_path, "send.svg", "", size_type="large", config=config)
        self.tr_set(self.send_button.setToolTip, "Send message", "Отправить сообщение")
        self.send_button.clicked.connect(self._submit)
        layout.addWidget(self.send_button)

        self.emoticon_button = None
        if with_emoticons:
            self.emoticon_button = HoverIconButton(icons_path, "emotion-normal.svg", "emotion-happy.svg", "")
            self.tr_set(self.emoticon_button.setToolTip, "Toggle Emoticon Selector", "Селектор эмотиконов")
            self.emoticon_button.clicked.connect(self.emoticon_requested)
            layout.addWidget(self.emoticon_button)
        on_language_changed(self.retranslate_all)

    def insert_emoticon(self, emoticon_name: str):
        """Insert the emoticon code at the cursor and keep typing in the field."""
        self.input_field.insert(f":{emoticon_name}: ")
        self.input_field.setFocus()

    def _submit(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.submitted.emit(text)

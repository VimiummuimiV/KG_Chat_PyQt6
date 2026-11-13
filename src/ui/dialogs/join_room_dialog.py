"""Join / Create Room dialog."""

import random
import re
import string
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QVBoxLayout,
)

from components.button import create_icon_button
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import on_language_changed, tr, TranslatableMixin


class JoinRoomDialog(TranslatableMixin, QDialog):
    """Styled replacement for the plain QInputDialog room prompt, matching
    the emoji-header + icon-button look of the account manager window."""

    _WINDOW_WIDTH = 280
    _LEN_MIN = 5
    _LEN_MAX = 20
    _LEN_DEFAULT = 8

    def __init__(self, config, icons_path: Path, parent=None):
        super().__init__(parent)
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.tr_set(self.setWindowTitle, "Join / Create Room", "Войти / Создать комнату")
        self.setFixedWidth(self._WINDOW_WIDTH)
        self.setFont(get_font(FontType.UI))

        margin = 15
        spacing = 10
        button_spacing = 8
        input_height = 48

        layout = QVBoxLayout()
        layout.setSpacing(spacing)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        self.setLayout(layout)

        self.header = QLabel()
        self.header.setFont(get_font(FontType.HEADER))
        self.tr_set(self.header.setText, "🚪 Join / Create Room", "🚪 Войти / Создать комнату")
        layout.addWidget(self.header)

        self._name_input = QLineEdit()
        self.tr_set(self._name_input.setPlaceholderText, "Room name", "Название комнаты")
        self._name_input.setFixedHeight(input_height)
        self._name_input.setFont(get_font(FontType.UI))
        self._name_input.setObjectName("joinRoomField")
        self._name_input.returnPressed.connect(self.accept)
        layout.addWidget(self._name_input)

        self._saved_combo = QComboBox()
        self._saved_combo.setFont(get_font(FontType.UI))
        self._saved_combo.setFixedHeight(input_height)
        self._saved_combo.setEditable(False)
        self._saved_combo.setObjectName("joinRoomField")
        self.tr_set(self._saved_combo.setPlaceholderText, "Saved rooms", "Сохранённые комнаты")
        self._saved_combo.currentIndexChanged.connect(self._on_saved_picked)
        layout.addWidget(self._saved_combo)

        length_row = QHBoxLayout()
        length_row.setSpacing(button_spacing)
        self._length_label = QLabel(tr("Length", "Длина"))
        self._length_label.setFont(get_font(FontType.UI))
        self.tr_set(self._length_label.setText, "Length", "Длина")
        length_row.addWidget(self._length_label)

        saved_len = self.config.get("join_room", "random_name_length") if self.config else None
        try:
            length = int(saved_len) if saved_len is not None else self._LEN_DEFAULT
        except (TypeError, ValueError):
            length = self._LEN_DEFAULT
        length = max(self._LEN_MIN, min(self._LEN_MAX, length))

        self._length_slider = QSlider(Qt.Orientation.Horizontal)
        self._length_slider.setRange(self._LEN_MIN, self._LEN_MAX)
        self._length_slider.setValue(length)
        self._length_slider.setFixedHeight(24)
        self._length_slider.valueChanged.connect(self._on_length_changed)
        length_row.addWidget(self._length_slider, stretch=1)

        self._length_value = QLabel(str(length))
        self._length_value.setFont(get_font(FontType.UI))
        self._length_value.setFixedWidth(24)
        self._length_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        length_row.addWidget(self._length_value)
        layout.addLayout(length_row)

        remember = self.config.get("join_room", "remember") if self.config else None
        self._remember_checkbox = QCheckBox()
        self.tr_set(self._remember_checkbox.setText, "Remember this name", "Запомнить это имя")
        self._remember_checkbox.setFont(get_font(FontType.UI))
        self._remember_checkbox.setChecked(True if remember is None else bool(remember))
        self._remember_checkbox.toggled.connect(self._on_remember_toggled)
        layout.addWidget(self._remember_checkbox)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(button_spacing)

        cancel_button = create_icon_button(
            self.icons_path, "line/arrow-go-back-line.svg", "", config=self.config
        )
        self.tr_set(cancel_button.setToolTip, "Cancel (Esc)", "Отмена (Esc)")
        cancel_button.clicked.connect(self.reject)
        actions_row.addWidget(cancel_button)

        gen_button = create_icon_button(
            self.icons_path, "fill/dice-3-fill.svg", "", config=self.config
        )
        self.tr_set(gen_button.setToolTip, "Generate random name", "Сгенерировать случайное имя")
        gen_button.clicked.connect(self._generate_name)
        actions_row.addWidget(gen_button)

        self._delete_button = create_icon_button(
            self.icons_path, "fill/delete-bin-fill.svg", "", config=self.config
        )
        self.tr_set(self._delete_button.setToolTip, "Remove from saved", "Удалить из сохранённых")
        self._delete_button.clicked.connect(self._delete_saved)
        actions_row.addWidget(self._delete_button)

        join_button = create_icon_button(
            self.icons_path, "fill/login-box-fill.svg", "", config=self.config
        )
        self.tr_set(join_button.setToolTip, "Join / Create (Enter)", "Войти / Создать (Enter)")
        join_button.clicked.connect(self.accept)
        actions_row.addWidget(join_button)

        layout.addLayout(actions_row)

        self._populate_saved()
        self._name_input.setFocus()
        on_language_changed(self.retranslate_all)

    def _load_saved(self) -> list:
        if not self.config:
            return []
        raw = self.config.get("join_room", "saved") or []
        if not isinstance(raw, list):
            return []
        out = []
        seen = set()
        for item in raw:
            name = str(item).strip().lower()
            if name and name not in seen and re.match(r"^[a-z0-9_-]+$", name):
                seen.add(name)
                out.append(name)
        return out

    def _populate_saved(self):
        """Rebuild the saved-rooms combo and show/hide it and the delete
        button depending on whether any saved names exist. The dialog's
        SetFixedSize constraint takes care of resizing the window."""
        saved = self._load_saved()
        has_saved = bool(saved)

        self._saved_combo.blockSignals(True)
        self._saved_combo.clear()
        for name in saved:
            self._saved_combo.addItem(name, name)
        self._saved_combo.setCurrentIndex(-1)
        self._saved_combo.blockSignals(False)

        self._saved_combo.setVisible(has_saved)
        self._delete_button.setVisible(has_saved)

    def _on_saved_picked(self, index: int):
        name = self._saved_combo.itemData(index)
        if name:
            self._name_input.setText(name)
            self._name_input.setFocus()
            self._name_input.selectAll()

    def _on_length_changed(self, value: int):
        self._length_value.setText(str(value))
        if self.config:
            self.config.set("join_room", "random_name_length", value=int(value))

    def _on_remember_toggled(self, checked: bool):
        if self.config:
            self.config.set("join_room", "remember", value=bool(checked))

    def _generate_name(self):
        alphabet = string.ascii_lowercase + string.digits
        name = "".join(random.choices(alphabet, k=self._length_slider.value()))
        self._name_input.setText(name)
        self._name_input.setFocus()
        self._name_input.selectAll()

    def room_name(self) -> str:
        return self._name_input.text().strip().lower()

    def should_remember(self) -> bool:
        return self._remember_checkbox.isChecked()

    def remember_name(self, name: str):
        if not self.config or not name:
            return
        saved = self._load_saved()
        if name in saved:
            return
        saved.append(name)
        self.config.set("join_room", "saved", value=saved)
        self._populate_saved()

    def _delete_saved(self):
        name = self._saved_combo.currentData() or self.room_name()
        if not name or not self.config:
            return
        saved = [n for n in self._load_saved() if n != name]
        self.config.set("join_room", "saved", value=saved)
        if self.room_name() == name:
            self._name_input.clear()
        self._populate_saved()

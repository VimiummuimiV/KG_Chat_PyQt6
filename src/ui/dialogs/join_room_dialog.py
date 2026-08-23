"""Join / Create Room dialog."""
from pathlib import Path
import random
import re
import string

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QSlider, QComboBox, QCheckBox,
)
from PyQt6.QtCore import Qt

from helpers.create import create_icon_button
from helpers.fonts import get_font, FontType


class JoinRoomDialog(QDialog):
    """Styled replacement for the plain QInputDialog room prompt, matching
    the emoji-header + icon-button look of the account manager window."""

    _WINDOW_WIDTH = 280
    _LEN_MIN = 5
    _LEN_MAX = 20
    _LEN_DEFAULT = 8

    def __init__(self, config, icons_path: Path, parent=None):
        super().__init__(parent)
        self.config = config
        self.icons_path = icons_path
        self.setWindowTitle("Join / Create Room")
        self.setFixedWidth(self._WINDOW_WIDTH)
        self.setFont(get_font(FontType.UI))

        margin = 15
        spacing = 10
        button_spacing = 8
        input_height = 48

        layout = QVBoxLayout()
        layout.setSpacing(spacing)
        layout.setContentsMargins(margin, margin, margin, margin)
        self.setLayout(layout)

        header = QLabel("🚪 Join / Create Room")
        header.setFont(get_font(FontType.HEADER))
        layout.addWidget(header)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Room name")
        self.name_input.setFixedHeight(input_height)
        self.name_input.setFont(get_font(FontType.UI))
        self.name_input.setStyleSheet(
            f"QLineEdit {{ height: {input_height}px; padding: 0px 8px; }}"
        )
        self.name_input.returnPressed.connect(self.accept)
        layout.addWidget(self.name_input)

        self.saved_combo = QComboBox()
        self.saved_combo.setFont(get_font(FontType.UI))
        self.saved_combo.setEditable(False)
        self.saved_combo.addItem("Saved rooms…", None)
        for name in self._load_saved():
            self.saved_combo.addItem(name, name)
        self.saved_combo.currentIndexChanged.connect(self._on_saved_picked)
        layout.addWidget(self.saved_combo)

        length_row = QHBoxLayout()
        length_row.setSpacing(button_spacing)
        length_label = QLabel("Length")
        length_label.setFont(get_font(FontType.UI))
        length_row.addWidget(length_label)

        saved_len = self.config.get("join_room", "random_name_length") if self.config else None
        try:
            length = int(saved_len) if saved_len is not None else self._LEN_DEFAULT
        except (TypeError, ValueError):
            length = self._LEN_DEFAULT
        length = max(self._LEN_MIN, min(self._LEN_MAX, length))

        self.length_slider = QSlider(Qt.Orientation.Horizontal)
        self.length_slider.setRange(self._LEN_MIN, self._LEN_MAX)
        self.length_slider.setValue(length)
        self.length_slider.setFixedHeight(24)
        self.length_slider.valueChanged.connect(self._on_length_changed)
        length_row.addWidget(self.length_slider, stretch=1)

        self.length_value = QLabel(str(length))
        self.length_value.setFont(get_font(FontType.UI))
        self.length_value.setFixedWidth(24)
        self.length_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        length_row.addWidget(self.length_value)
        layout.addLayout(length_row)

        remember = self.config.get("join_room", "remember") if self.config else None
        self.remember_checkbox = QCheckBox("Remember this name")
        self.remember_checkbox.setFont(get_font(FontType.UI))
        self.remember_checkbox.setChecked(True if remember is None else bool(remember))
        self.remember_checkbox.toggled.connect(self._on_remember_toggled)
        layout.addWidget(self.remember_checkbox)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(button_spacing)

        cancel_button = create_icon_button(
            self.icons_path, "go-back.svg", "Cancel (Esc)", config=self.config
        )
        cancel_button.clicked.connect(self.reject)
        actions_row.addWidget(cancel_button)

        gen_button = create_icon_button(
            self.icons_path, "dice-3.svg", "Generate random name", config=self.config
        )
        gen_button.clicked.connect(self._generate_name)
        actions_row.addWidget(gen_button)

        join_button = create_icon_button(
            self.icons_path, "login.svg", "Join / Create (Enter)", config=self.config
        )
        join_button.clicked.connect(self.accept)
        actions_row.addWidget(join_button)

        layout.addLayout(actions_row)
        self.name_input.setFocus()

        label_height = 35
        slider_row = 28
        combo_row = 32
        check_row = 28
        button_padding = 10
        total_height = (
            margin * 2
            + label_height
            + spacing
            + input_height
            + spacing
            + combo_row
            + spacing
            + slider_row
            + spacing
            + check_row
            + spacing
            + input_height
            + button_padding
        )
        self.setFixedHeight(total_height)

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

    def _on_saved_picked(self, index: int):
        name = self.saved_combo.itemData(index)
        if name:
            self.name_input.setText(name)
            self.name_input.setFocus()
            self.name_input.selectAll()

    def _on_length_changed(self, value: int):
        self.length_value.setText(str(value))
        if self.config:
            self.config.set("join_room", "random_name_length", value=int(value))

    def _on_remember_toggled(self, checked: bool):
        if self.config:
            self.config.set("join_room", "remember", value=bool(checked))

    def _generate_name(self):
        alphabet = string.ascii_lowercase + string.digits
        name = "".join(random.choices(alphabet, k=self.length_slider.value()))
        self.name_input.setText(name)
        self.name_input.setFocus()
        self.name_input.selectAll()

    def room_name(self) -> str:
        return self.name_input.text().strip().lower()

    def should_remember(self) -> bool:
        return self.remember_checkbox.isChecked()

    def remember_name(self, name: str):
        if not self.config or not name:
            return
        saved = self._load_saved()
        if name in saved:
            return
        saved.append(name)
        self.config.set("join_room", "saved", value=saved)

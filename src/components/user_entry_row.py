"""Editable user row: avatar, username field, user id, the buttons of the list that owns it and a remove button."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal, QSize
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget

from components.avatar import apply_user_avatar, make_avatar_label, refresh_avatar_placeholder
from components.button import create_icon_button, render_svg_icon
from components.username_autocomplete.autocomplete import UsernameAutocomplete
from core.web.api_data import validate_username_and_get_id
from helpers.fonts.fonts import FontType, get_scaled_width, set_font_role
from helpers.translate import on_language_changed, tr, TranslatableMixin
from themes.stylesheet import set_style_property


_ARROW_SIZE = 26
_ARROW_COLOR = "#888888"
_DEFAULT_INPUT_HEIGHT = 44
_DEFAULT_SPACING = 6
_VALIDATION_TOOLTIPS = {
    "missing": ("Fill username before adding new item", "Заполните имя пользователя перед добавлением новой записи"),
    "invalid": ("User not found", "Пользователь не найден"),
}


class UserEntryRow(TranslatableMixin, QWidget):
    """Avatar, username field, user id and a remove button; a list adds its own buttons with add_action.

    The username is checked against the site when editing finishes; changed fires after each check."""

    AVATAR_SIZE = 36
    SVG_AVATAR_SIZE = 24
    USERNAME_BASE_WIDTH = 220
    USER_ID_BASE_WIDTH = 125

    remove_requested = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, config, icons_path: Path, username: str = "", user_id: str = "", check_on_load: bool = True):
        """check_on_load: whether a username given without its user id is checked against the site right away."""
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.user_id = user_id
        self.username_valid = True
        self._scaled_widgets = []

        self._main_layout = QHBoxLayout()
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(config.get("ui", "spacing", "widget_elements") or _DEFAULT_SPACING)
        self.setLayout(self._main_layout)
        self.input_height = config.get("ui", "input_height") or _DEFAULT_INPUT_HEIGHT

        self.avatar_label = make_avatar_label(self.AVATAR_SIZE)
        self._show_avatar()
        self._main_layout.addWidget(self.avatar_label)

        self.username_input = QLineEdit()
        self.tr_set(self.username_input.setPlaceholderText, "Username", "Имя пользователя")
        self.username_input.setText(username)
        self.username_input.setFixedHeight(self.input_height)
        self.username_input.editingFinished.connect(self._validate)
        UsernameAutocomplete(self.username_input, config, bare=True, is_recorded=False, suffix="")
        self._main_layout.addWidget(self.username_input)

        arrow_label = QLabel()
        arrow_label.setPixmap(render_svg_icon(icons_path / "line/arrow-right-s-line.svg", _ARROW_SIZE, _ARROW_COLOR).pixmap(QSize(_ARROW_SIZE, _ARROW_SIZE)))
        arrow_label.setFixedSize(_ARROW_SIZE, _ARROW_SIZE)
        self._main_layout.addWidget(arrow_label)

        self.user_id_input = QLineEdit()
        self.tr_set(self.user_id_input.setPlaceholderText, "ID", "ID")
        self.user_id_input.setText(user_id)
        self.user_id_input.setFixedHeight(self.input_height)
        self.user_id_input.setReadOnly(True)
        self.user_id_input.setObjectName("readOnlyField")
        self._main_layout.addWidget(self.user_id_input)

        remove_button = create_icon_button(icons_path, "fill/delete-bin-fill.svg", "", size_type="large", config=config)
        self.tr_set(remove_button.setToolTip, "Remove", "Удалить")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self._main_layout.addWidget(remove_button)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.update_font_scale()
        if check_on_load and username and not user_id:
            self._validate()
        on_language_changed(self.retranslate_all)

    def add_action(self, widget: QWidget, base_width: int | None = None):
        """Put a widget of the owning list in front of the remove button; base_width makes it follow the font scale."""
        self._main_layout.insertWidget(self._main_layout.count() - 1, widget)
        if base_width:
            self._scaled_widgets.append((widget, base_width))
            widget.setFixedWidth(get_scaled_width(base_width))
        self.fit_width()

    def fit_width(self):
        """Make the row exactly as wide as its parts, so a grid can count how many rows fit."""
        self.setFixedWidth(self.sizeHint().width())

    def update_font_scale(self):
        """Follow the text font size: the fields keep their share of the row."""
        set_font_role(self.username_input, FontType.TEXT)
        set_font_role(self.user_id_input, FontType.TEXT)
        self.username_input.setFixedWidth(get_scaled_width(self.USERNAME_BASE_WIDTH))
        self.user_id_input.setFixedWidth(get_scaled_width(self.USER_ID_BASE_WIDTH))
        for widget, base_width in self._scaled_widgets:
            widget.setFixedWidth(get_scaled_width(base_width))
        self.fit_width()

    def update_theme(self, is_dark: bool):
        """Recolor the placeholder avatar; a real avatar is left as is."""
        refresh_avatar_placeholder(self.avatar_label, self.user_id or None, self.SVG_AVATAR_SIZE, is_dark, self.icons_path)

    def _show_avatar(self):
        is_dark = self.config.get("ui", "theme") == "dark"
        apply_user_avatar(self.avatar_label, self.user_id or None, self.AVATAR_SIZE, self.SVG_AVATAR_SIZE, is_dark, self.icons_path)

    def _validate(self):
        username = self.username_input.text().strip()
        user_id = validate_username_and_get_id(username) if username else None
        self.username_valid = user_id is not None or not username
        self.user_id = user_id or ""
        self.user_id_input.setText(self.user_id)
        self._show_avatar()
        self.update_input_style()
        self.changed.emit()

    def update_input_style(self, highlight_empty: bool = False):
        """Mark the username field as missing or not found."""
        if highlight_empty and not self.username_input.text().strip():
            state = "missing"
        elif self.username_input.text().strip() and not self.username_valid:
            state = "invalid"
        else:
            state = ""
        set_style_property(self.username_input, "validation", state)
        self._show_validation_tooltip()

    def _show_validation_tooltip(self):
        messages = _VALIDATION_TOOLTIPS.get(self.username_input.property("validation"))
        self.username_input.setToolTip(tr(*messages) if messages else "")

    def retranslate_all(self, _code=None):
        super().retranslate_all(_code)
        self._show_validation_tooltip()

    def is_empty(self) -> bool:
        """Whether no username is typed."""
        return not self.username_input.text().strip()

    def get_data(self) -> tuple:
        """The typed username and its user id."""
        return self.username_input.text().strip(), self.user_id

    def cleanup(self):
        """Stop whatever the row runs; nothing by default."""

"""Tracked user input rows and chips."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget

from components.button import create_icon_button, set_visual_active
from components.user_count_row import UserCountRow
from core.web.api_data import validate_username_and_get_id
from helpers.fonts.fonts import FontType, get_scaled_width, set_font_role
from helpers.translate import on_language_changed, tr, TranslatableMixin
from themes.stylesheet import set_style_property


class TrackedUserItem(TranslatableMixin, QWidget):
    remove_requested = pyqtSignal(object)

    _USERNAME_BASE_WIDTH = 220
    _USER_ID_BASE_WIDTH = 125
    _ARROW_WIDTH = 26
    _BUTTON_WIDTH = 48

    def __init__(self, config, icons_path: Path, username="", user_id=""):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.user_id = user_id
        self.frozen = False
        self.parent_widget = None
        self.username_valid = True

        spacing = config.get("ui", "spacing", "widget_elements") or 6
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        self.setLayout(layout)

        input_height = config.get("ui", "input_height") or 44

        self.username_input = QLineEdit()
        self.tr_set(self.username_input.setPlaceholderText, "Username", "Имя пользователя")
        self.username_input.setText(username)
        set_font_role(self.username_input, FontType.TEXT)
        self.username_input.setFixedHeight(input_height)
        self._username_width = get_scaled_width(self._USERNAME_BASE_WIDTH)
        self.username_input.setFixedWidth(self._username_width)
        self.username_input.editingFinished.connect(self._validate)
        layout.addWidget(self.username_input)

        arrow_label = QLabel()
        arrow_svg = icons_path / "line/arrow-right-s-line.svg"
        if arrow_svg.exists():
            with open(arrow_svg, 'r') as f:
                svg_content = f.read().replace('fill="currentColor"', 'fill="#888888"')
            renderer = QSvgRenderer()
            renderer.load(svg_content.encode('utf-8'))
            pixmap = QPixmap(26, 26)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            arrow_label.setPixmap(pixmap)
            arrow_label.setFixedSize(26, 26)
        layout.addWidget(arrow_label)

        self._user_id_input = QLineEdit()
        self.tr_set(self._user_id_input.setPlaceholderText, "ID", "ID")
        self._user_id_input.setText(user_id)
        set_font_role(self._user_id_input, FontType.TEXT)
        self._user_id_input.setFixedHeight(input_height)
        self._user_id_width = get_scaled_width(self._USER_ID_BASE_WIDTH)
        self._user_id_input.setFixedWidth(self._user_id_width)
        self._user_id_input.setReadOnly(True)
        layout.addWidget(self._user_id_input)

        self._freeze_button = create_icon_button(
            icons_path, "line/snowflake-line.svg", tr("Freeze tracking", "Заморозить отслеживание"),
            size_type="large", config=config
        )
        self._freeze_button.clicked.connect(self._toggle_freeze)
        layout.addWidget(self._freeze_button)

        self._remove_button = create_icon_button(
            icons_path, "fill/delete-bin-fill.svg", "",
            size_type="large", config=config
        )
        self.tr_set(self._remove_button.setToolTip, "Remove", "Удалить")
        self._remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self._remove_button)

        self._spacing = spacing
        self._update_total_width()
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        if username and not user_id:
            self._validate()
        on_language_changed(self.retranslate_all)

    def _update_total_width(self):
        total_width = (
            self._username_width + self._ARROW_WIDTH + self._user_id_width
            + self._BUTTON_WIDTH * 2 + self._spacing * 4
        )
        self.setFixedWidth(total_width)

    def update_font_scale(self):
        self._username_width = get_scaled_width(self._USERNAME_BASE_WIDTH)
        self._user_id_width = get_scaled_width(self._USER_ID_BASE_WIDTH)
        set_font_role(self.username_input, FontType.TEXT)
        set_font_role(self._user_id_input, FontType.TEXT)
        self.username_input.setFixedWidth(self._username_width)
        self._user_id_input.setFixedWidth(self._user_id_width)
        self._update_total_width()

    def _validate(self):
        username = self.username_input.text().strip()
        if not username:
            self.username_valid = True
            self.user_id = ""
            self._user_id_input.clear()
            self.update_input_style()
            if self.parent_widget:
                self.parent_widget.save_selected()
            return

        user_id = validate_username_and_get_id(username)
        self.username_valid = user_id is not None
        if self.username_valid:
            self.user_id = user_id
            self._user_id_input.setText(self.user_id)
        else:
            self.user_id = ""
            self._user_id_input.clear()

        self.update_input_style()
        if self.parent_widget:
            self.parent_widget.save_selected()

    def update_input_style(self, highlight_empty=False):
        if highlight_empty and not self.username_input.text().strip():
            set_style_property(self.username_input, "validation", "missing")
            self.username_input.setToolTip(tr(
                "Fill username before adding new item",
                "Заполните имя пользователя перед добавлением новой записи")
            )
        elif self.username_input.text().strip() and not self.username_valid:
            set_style_property(self.username_input, "validation", "invalid")
            self.username_input.setToolTip(tr("User not found", "Пользователь не найден"))
        else:
            set_style_property(self.username_input, "validation", "")
            self.username_input.setToolTip("")

    def set_frozen(self, frozen: bool):
        self.frozen = bool(frozen)
        set_visual_active(self.username_input, not self.frozen)
        set_visual_active(self._user_id_input, not self.frozen)
        set_visual_active(self._freeze_button, not self.frozen)
        self._freeze_button.setToolTip(
            tr("Unfreeze tracking", "Разморозить отслеживание") if self.frozen
            else tr("Freeze tracking", "Заморозить отслеживание")
        )

    def _toggle_freeze(self):
        if not self.user_id:
            return
        self.set_frozen(not self.frozen)
        if self.parent_widget:
            self.parent_widget.user_tracker.set_frozen(self.user_id, self.frozen)

    def is_empty(self):
        return not self.username_input.text().strip()

    def get_data(self):
        return self.username_input.text().strip(), self.user_id

    def cleanup(self):
        pass


class TrackerUserChip(UserCountRow):
    """History filter chip: avatar + login + event count, orange highlight when filtered"""

    delete_requested = pyqtSignal(str)

    def __init__(self, config, icons_path: Path, login: str, count: int, user_id: str = None):
        super().__init__(
            login, count, config, icons_path, user_id,
        )
        self.login = login
        self._delete_button = create_icon_button(
            icons_path, "fill/delete-bin-fill.svg", tr("Remove history for this user", "Удалить историю этого пользователя"),
            size_type="small", config=config
        )
        self._delete_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._delete_button.clicked.connect(lambda: self.delete_requested.emit(self.login))
        self.layout().addWidget(self._delete_button)

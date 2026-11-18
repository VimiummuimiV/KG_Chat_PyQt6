"""Rows of users (avatar, username > user id, the list's own columns, remove button) painted by one widget.

Only the cell being edited has a real input field; every other cell is drawn with the style of a hidden prototype,
so a row looks exactly as a row of real widgets does."""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import pyqtSignal, QEvent, QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QFontMetrics, QPainter, QPixmap, QRegion
from PyQt6.QtWidgets import (
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QToolTip,
    QWidget,
)

from components.avatar import make_avatar_pixmap, make_rounded_avatar, request_avatar
from components.button import create_icon_button, get_button_sizes, get_user_svg_color, render_svg_icon
from components.user_row.model import (
    ARROW_COLOR,
    ARROW_SIZE,
    AVATAR_SIZE,
    COLUMN_BUTTON,
    COLUMN_FIELD,
    COLUMN_TOGGLE,
    DEFAULT_INPUT_HEIGHT,
    DEFAULT_SPACING,
    ExtraColumn,
    SVG_AVATAR_SIZE,
    USER_ID_BASE_WIDTH,
    USERNAME_BASE_WIDTH,
    UserRow,
    VALIDATION_TOOLTIPS,
)
from components.username_autocomplete.autocomplete import UsernameAutocomplete
from core.web.api_data import validate_username_and_get_id
from helpers.cache import get_cache
from helpers.fonts.fonts import FontType, get_scaled_width, set_font_role
from helpers.translate import on_language_changed, tr, TranslatableMixin
from themes.stylesheet import set_style_property


_DIMMED_OPACITY = 0.5
_BUTTON_TEXT_PADDING = 40
_USERNAME = "username"
_REMOVE = "remove"
_REMOVE_ICON = "fill/delete-bin-fill.svg"
_ARROW_ICON = "line/arrow-right-s-line.svg"


class UserRowView(TranslatableMixin, QWidget):
    """Grid of user rows; a row reports through signals, a list keeps the rows in `rows`."""

    changed = pyqtSignal()  # a username was checked or a row removed
    extra_changed = pyqtSignal(object, str)  # row, column key: a toggle flipped or a field typed in
    extra_clicked = pyqtSignal(object, str)  # row, column key: a button pressed
    editor_shown = pyqtSignal(QWidget)
    row_added = pyqtSignal()  # a row was appended at the end

    def __init__(self, config, icons_path: Path, columns: tuple = ()):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.columns = {column.key: column for column in columns}
        self.rows: list[UserRow] = []
        self._parts: dict[str, QRect] = {}
        self._row_size = QSize()
        self._grid_columns = 1
        self._hover: Optional[tuple[int, str]] = None
        self._pressed: Optional[tuple[int, str]] = None
        self._editing: Optional[tuple[UserRow, str]] = None  # row, "username" or the key of a field column
        self._username_editor: Optional[QLineEdit] = None
        self._field_editor: Optional[QLineEdit] = None
        self._input_height = config.get("ui", "input_height") or DEFAULT_INPUT_HEIGHT
        self._spacing = config.get("ui", "spacing", "widget_elements") or DEFAULT_SPACING
        list_spacing = config.get("ui", "spacing", "list_items") or 2
        self._horizontal_gap = list_spacing * 4
        self._vertical_gap = list_spacing * 2
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._name_prototypes = {state: self._make_field_prototype(validation=state) for state in ("", "missing", "invalid")}
        self._id_prototype = self._make_field_prototype(is_id=True)
        self._remove_prototype = self._make_icon_prototype(_REMOVE_ICON)
        self._prototypes = {}  # column key -> hidden widget the column is drawn with
        for column in columns:
            if column.kind == COLUMN_TOGGLE:
                self._prototypes[column.key] = self._make_icon_prototype(column.icon)
            elif column.kind == COLUMN_BUTTON:
                self._prototypes[column.key] = self._hide_prototype(QPushButton(self))
            else:
                self._prototypes[column.key] = self._make_field_prototype(placeholder=column.placeholder)
        self.update_font_scale()
        on_language_changed(self.retranslate_all)

    # ---- prototypes

    def _make_field_prototype(self, validation: str = "", is_id: bool = False, placeholder: tuple = ("Username", "Имя пользователя")) -> QLineEdit:
        """A hidden field rendered once per painted cell."""
        prototype = QLineEdit(self)
        if is_id:
            self.tr_set(prototype.setPlaceholderText, "ID", "ID")
            prototype.setObjectName("readOnlyField")
            prototype.setReadOnly(True)
        else:
            self.tr_set(prototype.setPlaceholderText, *placeholder)
            if validation:
                prototype.setProperty("validation", validation)
        return self._hide_prototype(prototype)

    def _make_icon_prototype(self, icon_name: str) -> QPushButton:
        return self._hide_prototype(create_icon_button(self.icons_path, icon_name, "", size_type="large", config=self.config))

    def _hide_prototype(self, widget):
        widget.setParent(self)
        widget.setVisible(False)
        widget.ensurePolished()
        return widget

    # ---- data

    def set_rows(self, rows: list[UserRow]):
        """Replace the rows."""
        self._cancel_edit()
        self.rows = rows
        self.refresh()

    def edit_empty_row(self) -> bool:
        """Mark the row that still has no username and edit it; False when every row has one."""
        row = next((row for row in self.rows if not row.username), None)
        if row is None:
            return False
        row.is_missing_marked = True
        self.update(self._row_rect(self.rows.index(row)))
        self._start_edit(row, _USERNAME)
        return True

    def add_row(self, row: Optional[UserRow] = None):
        """Append a row (an empty one by default) and edit its username."""
        row = row or UserRow()
        self.rows.append(row)
        self.refresh()
        self._start_edit(row, _USERNAME)
        self.row_added.emit()

    def remove_row(self, row: UserRow):
        if self._editing and row is self._editing[0]:
            self._cancel_edit()
        self.rows.remove(row)
        self.refresh()
        self.changed.emit()

    def clear(self):
        self.set_rows([])

    def filled_count(self) -> int:
        """How many rows have a username."""
        return sum(1 for row in self.rows if row.username)

    # ---- geometry

    def refresh(self):
        """Measure the columns again (a button text may have changed) and lay the rows out."""
        self._update_metrics()
        self._relayout()

    def _update_metrics(self):
        _, button_size = get_button_sizes("large", self.config)
        sizes = {
            "avatar": (AVATAR_SIZE, AVATAR_SIZE),
            _USERNAME: (get_scaled_width(USERNAME_BASE_WIDTH), self._input_height),
            "arrow": (ARROW_SIZE, ARROW_SIZE),
            "id": (get_scaled_width(USER_ID_BASE_WIDTH), self._input_height),
        }
        for key, column in self.columns.items():
            if column.kind == COLUMN_TOGGLE:
                sizes[key] = (button_size, button_size)
            elif column.kind == COLUMN_BUTTON:
                sizes[key] = (self._button_width(column), self._input_height)
            else:
                sizes[key] = (get_scaled_width(column.base_width), self._input_height)
        sizes[_REMOVE] = (button_size, button_size)

        for prototype in self._name_prototypes.values():
            prototype.setFixedSize(*sizes[_USERNAME])
        self._id_prototype.setFixedSize(*sizes["id"])
        for key, column in self.columns.items():
            if column.kind == COLUMN_FIELD:
                self._prototypes[key].setFixedSize(*sizes[key])

        row_height = max(height for _, height in sizes.values())
        x = 0
        for part, (width, height) in sizes.items():
            self._parts[part] = QRect(x, (row_height - height) // 2, width, height)
            x += width + self._spacing
        self._row_size = QSize(x - self._spacing, row_height)

    def _button_width(self, column: ExtraColumn) -> int:
        """As wide as the longest text of its rows needs, so every row has the same width."""
        metrics = QFontMetrics(self._prototypes[column.key].font())
        longest = max((metrics.horizontalAdvance(column.text_of(row)) for row in self.rows), default=0)
        return max(column.base_width, longest + _BUTTON_TEXT_PADDING)

    def _relayout(self):
        available = max(self.width(), 1)
        self._grid_columns = max(1, (available + self._horizontal_gap) // (self._row_size.width() + self._horizontal_gap))
        grid_rows = -(-len(self.rows) // self._grid_columns)
        self.setFixedHeight(max(0, grid_rows * (self._row_size.height() + self._vertical_gap) - self._vertical_gap))
        self.updateGeometry()
        self._place_editor()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._row_size.width(), self.height())

    def _row_origin(self, index: int) -> QPoint:
        row_number, column = divmod(index, self._grid_columns)
        return QPoint(column * (self._row_size.width() + self._horizontal_gap), row_number * (self._row_size.height() + self._vertical_gap))

    def _row_rect(self, index: int) -> QRect:
        return QRect(self._row_origin(index), self._row_size)

    def _hit_test(self, position: QPoint) -> Optional[tuple[int, str]]:
        """The (row index, part) under the position, or None."""
        step_x = self._row_size.width() + self._horizontal_gap
        step_y = self._row_size.height() + self._vertical_gap
        column, offset_x = divmod(position.x(), step_x)
        row_number, offset_y = divmod(position.y(), step_y)
        index = row_number * self._grid_columns + column
        if position.x() < 0 or position.y() < 0 or column >= self._grid_columns or index >= len(self.rows):
            return None
        point = QPoint(offset_x, offset_y)
        part = next((name for name, rect in self._parts.items() if rect.contains(point)), None)
        return (index, part) if part else None

    def _is_clickable(self, part: str) -> bool:
        return part == _REMOVE or (part in self.columns and self.columns[part].kind != COLUMN_FIELD)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    # ---- painting

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for index, row in enumerate(self.rows):
            origin = self._row_origin(index)
            if QRect(origin, self._row_size).intersects(event.rect()):
                self._paint_row(painter, index, row, origin)

    def _paint_row(self, painter: QPainter, index: int, row: UserRow, origin: QPoint):
        painter.save()
        painter.translate(origin)
        parts = self._parts
        self._paint_avatar(painter, row, parts["avatar"])
        arrow = render_svg_icon(self.icons_path / _ARROW_ICON, ARROW_SIZE, ARROW_COLOR).pixmap(QSize(ARROW_SIZE, ARROW_SIZE))
        painter.drawPixmap(parts["arrow"].topLeft(), arrow)

        is_dimmed = any(column.dims_row and row.extras.get(column.key) for column in self.columns.values())
        painter.setOpacity(_DIMMED_OPACITY if is_dimmed else 1.0)
        if self._editing != (row, _USERNAME):
            self._paint_field(painter, self._name_prototypes[row.validation], parts[_USERNAME], row.username)
        self._paint_field(painter, self._id_prototype, parts["id"], row.user_id)
        for column in self.columns.values():
            self._paint_column(painter, index, row, column, is_dimmed)
        painter.setOpacity(1.0)
        self._paint_button(painter, index, _REMOVE, self._remove_prototype, parts[_REMOVE])
        painter.restore()

    def _paint_column(self, painter: QPainter, index: int, row: UserRow, column: ExtraColumn, is_dimmed: bool):
        prototype = self._prototypes[column.key]
        rect = self._parts[column.key]
        if column.kind == COLUMN_FIELD:
            if self._editing != (row, column.key):
                self._paint_field(painter, prototype, rect, row.extras.get(column.key, ""))
        elif column.kind == COLUMN_BUTTON:
            self._paint_button(painter, index, column.key, prototype, rect, column.text_of(row))
        else:
            painter.setOpacity(_DIMMED_OPACITY if is_dimmed and column.dims_row else 1.0)
            self._paint_button(painter, index, column.key, prototype, rect)

    def _paint_avatar(self, painter: QPainter, row: UserRow, rect: QRect):
        if row.avatar is None:
            self._make_avatar(row)
        size = row.avatar.deviceIndependentSize()
        painter.drawPixmap(rect.x() + int((rect.width() - size.width()) // 2), rect.y() + int((rect.height() - size.height()) // 2), row.avatar)

    def _make_avatar(self, row: UserRow):
        cache = get_cache()
        raw = cache.get_avatar(row.user_id) if row.user_id else None
        is_dark = self.config.get("ui", "theme") == "dark"
        color = get_user_svg_color(cache.has_user(row.user_id), is_dark)
        row.avatar = make_avatar_pixmap(self.icons_path, raw, AVATAR_SIZE, SVG_AVATAR_SIZE, color)
        row.is_avatar_real = bool(raw)
        if row.user_id and not raw and not row.is_avatar_requested:
            row.is_avatar_requested = True
            user_id = row.user_id
            request_avatar(self, user_id, lambda pixmap: self._show_loaded_avatar(row, user_id, pixmap))

    def _show_loaded_avatar(self, row: UserRow, user_id: str, pixmap: QPixmap):
        if row.user_id == user_id:
            row.avatar = make_rounded_avatar(pixmap, AVATAR_SIZE)
            row.is_avatar_real = True
            self.update()

    @staticmethod
    def _paint_field(painter: QPainter, prototype: QLineEdit, rect: QRect, text: str):
        prototype.setText(text)
        prototype.render(painter, rect.topLeft(), QRegion(), QWidget.RenderFlag.DrawChildren)

    def _paint_button(self, painter: QPainter, index: int, part: str, prototype: QPushButton, rect: QRect, text: str = ""):
        """Draw a button through the style, which a prototype that is not under the mouse cannot show hovered or pressed."""
        option = QStyleOptionButton()
        option.initFrom(prototype)
        option.rect = rect
        option.icon = prototype.icon()
        option.iconSize = prototype.iconSize()
        option.text = text
        option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active
        option.state |= QStyle.StateFlag.State_Sunken if self._pressed == (index, part) else QStyle.StateFlag.State_Raised
        if self._hover == (index, part):
            option.state |= QStyle.StateFlag.State_MouseOver
        painter.setFont(prototype.font())
        prototype.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, prototype)

    # ---- mouse

    def mouseMoveEvent(self, event):
        hit = self._hit_test(event.position().toPoint())
        if hit is not None and not self._is_clickable(hit[1]):
            hit = None
        if hit != self._hover:
            for target in (self._hover, hit):
                if target:
                    self.update(self._row_rect(target[0]))
            self._hover = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover:
            self.update(self._row_rect(self._hover[0]))
        self._hover = None
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        hit = self._hit_test(event.position().toPoint()) if event.button() == Qt.MouseButton.LeftButton else None
        if hit and (hit[1] == _USERNAME or (hit[1] in self.columns and self.columns[hit[1]].kind == COLUMN_FIELD)):
            self._start_edit(self.rows[hit[0]], hit[1])
        elif hit and self._is_clickable(hit[1]):
            self._pressed = hit
            self.update(self._row_rect(hit[0]))
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        pressed, self._pressed = self._pressed, None
        if pressed is None:
            super().mouseReleaseEvent(event)
            return
        self.update(self._row_rect(pressed[0]))
        if self._hit_test(event.position().toPoint()) != pressed:
            return
        row = self.rows[pressed[0]]
        if pressed[1] == _REMOVE:
            self.remove_row(row)
        elif self.columns[pressed[1]].kind == COLUMN_TOGGLE:
            self._toggle(row, pressed[1])
        else:
            self.extra_clicked.emit(row, pressed[1])

    def _toggle(self, row: UserRow, key: str):
        if not row.user_id:
            return
        row.extras[key] = not row.extras.get(key)
        self.update(self._row_rect(self.rows.index(row)))
        self.extra_changed.emit(row, key)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            text = self._tooltip_at(event.pos())
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def _tooltip_at(self, position: QPoint) -> str:
        hit = self._hit_test(position)
        if hit is None:
            return ""
        row, part = self.rows[hit[0]], hit[1]
        if part == _USERNAME:
            messages = VALIDATION_TOOLTIPS.get(row.validation)
            return tr(*messages) if messages else ""
        if part == _REMOVE:
            return tr("Remove", "Удалить")
        column = self.columns.get(part)
        if column is not None and column.kind == COLUMN_TOGGLE:
            return tr(*column.tooltips[1 if row.extras.get(part) else 0])
        return ""

    # ---- editing

    def _make_editor(self, is_username: bool) -> QLineEdit:
        editor = QLineEdit(self)
        editor.editingFinished.connect(self._finish_edit)
        if is_username:
            self.tr_set(editor.setPlaceholderText, "Username", "Имя пользователя")
            UsernameAutocomplete(editor, self.config, is_recorded=False, suffix="")
        else:
            editor.textChanged.connect(self._store_field_text)
        return editor

    def _editor(self) -> Optional[QLineEdit]:
        if self._editing is None:
            return None
        return self._username_editor if self._editing[1] == _USERNAME else self._field_editor

    def _start_edit(self, row: UserRow, part: str):
        """Put an input field over the cell; the cell that was edited is finished first."""
        if self._editing == (row, part):
            return
        self._finish_edit()
        is_username = part == _USERNAME
        if is_username and self._username_editor is None:
            self._username_editor = self._make_editor(True)
        elif not is_username and self._field_editor is None:
            self._field_editor = self._make_editor(False)
        self._editing = (row, part)
        editor = self._editor()
        if is_username:
            editor.setText(row.username)
            set_style_property(editor, "validation", row.validation)
        else:
            editor.blockSignals(True)
            editor.setText(row.extras.get(part, ""))
            editor.blockSignals(False)
            editor.setPlaceholderText(tr(*self.columns[part].placeholder))
        set_font_role(editor, FontType.TEXT)
        self._place_editor()
        editor.show()
        editor.setFocus()
        QTimer.singleShot(0, lambda: self.editor_shown.emit(editor))  # after the scroll area has grown
        self.update()

    def _store_field_text(self, text: str):
        row, key = self._editing
        row.extras[key] = text
        self.extra_changed.emit(row, key)

    def _place_editor(self):
        if self._editing is None:
            return
        row, part = self._editing
        self._editor().setGeometry(self._parts[part].translated(self._row_origin(self.rows.index(row))))

    def _cancel_edit(self):
        editor = self._editor()
        self._editing = None
        if editor is not None:
            editor.hide()

    def _finish_edit(self):
        """Finish the edited cell; a username is checked against the site and the result shown in the row."""
        if self._editing is None:
            return
        row, part = self._editing
        editor = self._editor()
        self._editing = None
        editor.hide()
        if part != _USERNAME:
            self.update()
            return
        username = editor.text().strip()
        if username != row.username or (username and not row.user_id):
            user_id = validate_username_and_get_id(username) if username else None
            row.is_valid = user_id is not None or not username
            row.user_id = user_id or ""
            row.avatar = None
            row.is_avatar_requested = False
        row.username = username
        row.is_missing_marked = False
        self.update()
        self.changed.emit()

    # ---- look

    def update_font_scale(self):
        """Follow the text font size."""
        text_columns = [self._prototypes[key] for key, column in self.columns.items() if column.kind != COLUMN_TOGGLE]
        for prototype in (*self._name_prototypes.values(), self._id_prototype, *text_columns):
            set_font_role(prototype, FontType.TEXT)
        for editor in (self._username_editor, self._field_editor):
            if editor is not None:
                set_font_role(editor, FontType.TEXT)
        self.refresh()

    def update_theme(self):
        """Recolor the placeholder avatars; a real avatar is left as is."""
        for row in self.rows:
            if not row.is_avatar_real:
                row.avatar = None
        self.update()

    def retranslate_all(self, _code=None):
        super().retranslate_all(_code)
        self.update()

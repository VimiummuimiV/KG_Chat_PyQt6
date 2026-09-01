"""Reusable scroll buttons panel (top/bottom full + page up/down) for list views"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QListView, QScrollArea, QWidget, QVBoxLayout,
    QGraphicsOpacityEffect, QAbstractItemView, QApplication,
    QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QObject, QTimer, QPropertyAnimation, QEvent, QPoint, pyqtSignal
from helpers.config import Config
from helpers.create import create_icon_button, create_disabled_icon
from helpers.scroll.scroll import scroll, jump_to_date, _is_separator
from helpers.translate import tr

OPACITY_HIDDEN   = 0.0
OPACITY_VISIBLE  = 1.0
FADE_DURATION    = 180
BUTTON_GAP       = 6
REVEAL_PADDING   = 150 

# Top-to-bottom order, matching the on-screen stack: full-up, page-up, page-down, full-down
# tooltips: (en, ru) resolved at button creation
_BUTTONS = (
    # icon_name,              tooltip_en,             tooltip_ru,              action
    ("arrow-up-double.svg",   "Scroll to top",        "В начало",              "top"),
    ("arrow-up.svg",          "Scroll up a page",     "Страница вверх",        "page_up"),
    ("arrow-down.svg",        "Scroll down a page",   "Страница вниз",         "page_down"),
    ("arrow-down-double.svg", "Scroll to bottom",     "В конец",               "bottom"),
)


_DATE_JUMP_ACTIONS = (
    (-1, "calendar-arrow-up.svg",  "Previous day", "Предыдущий день"),
    (1, "calendar-arrow-down.svg", "Next day",     "Следующий день"),
)


class ScrollButtonsPanel(QObject):
    """Floating panel of scroll buttons (top/bottom full + page up/down) for a QListView.

    All four buttons live in a single container widget that is invisible (opacity 0)
    until the cursor comes near it, then fades in as one unit. Individually, a button
    dims further while disabled (already at the top/bottom, so that direction is a
    no-op).
    """
    clicked_scroll = pyqtSignal(str)  # emits the action that was triggered: top/page_up/page_down/bottom

    def __init__(self, list_view, parent=None, extra_actions=None, date_jump=False):
        """extra_actions: optional list of {"icon", "tooltip", "callback"} dicts for
        buttons appended after the standard four. date_jump=True adds prev/next-day
        buttons that scroll to the nearest is_separator row (dict key or attribute)."""
        super().__init__(parent)  # Parent the QObject properly
        self.list_view = list_view  # QListView or QScrollArea

        # Paths
        base_path = Path(__file__).parent.parent.parent
        self.icons_path = base_path / "icons"

        # Load config
        self.config = Config()

        # Parent to list_view so the panel cannot spill over sibling panes (e.g. chatlog split)
        # and steal clicks from their toolbar buttons.
        self.container = QWidget(list_view)
        self.container.setMouseTracking(True)
        self.container.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.container.setAutoFillBackground(False)
        self._layout = QVBoxLayout(self.container)
        # No right margin: that side sits against the scrollbar, so padding there
        # would steal its hover/click events. Left/top/bottom keep the full reveal zone.
        self._layout.setContentsMargins(REVEAL_PADDING, REVEAL_PADDING, 0, REVEAL_PADDING)
        self._layout.setSpacing(BUTTON_GAP)

        self._container_effect = QGraphicsOpacityEffect(self.container)
        self._container_effect.setOpacity(OPACITY_HIDDEN)
        self.container.setGraphicsEffect(self._container_effect)

        self._container_anim = QPropertyAnimation(self._container_effect, b"opacity", self)
        self._container_anim.setDuration(FADE_DURATION)

        self.container.installEventFilter(self)

        self._entries = []
        for icon_name, tooltip_en, tooltip_ru, action in _BUTTONS:
            button = self._create_button(icon_name, tr(tooltip_en, tooltip_ru))
            button.clicked.connect(lambda _checked=False, a=action: self._on_clicked(a))

            icon_normal = button.icon()
            icon_dimmed = create_disabled_icon(self.icons_path, icon_name, icon_size=button._icon_size)

            self._entries.append({
                "button": button,
                "action": action,
                "icon_normal": icon_normal,
                "icon_dimmed": icon_dimmed,
            })

        self._has_extra_actions = bool(extra_actions)
        self._date_spacer = None
        if date_jump or extra_actions:
            self._date_spacer = QSpacerItem(0, BUTTON_GAP * 2, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self._layout.addItem(self._date_spacer)

        self._date_buttons = []
        self._separator_rows = []
        if date_jump:
            for direction, icon, tooltip_en, tooltip_ru in _DATE_JUMP_ACTIONS:
                button = self._create_button(icon, tr(tooltip_en, tooltip_ru))
                button.clicked.connect((lambda d: lambda: jump_to_date(self.list_view, d))(direction))
                self._date_buttons.append({
                    "button": button,
                    "direction": direction,
                    "icon_normal": button.icon(),
                    "icon_dimmed": create_disabled_icon(self.icons_path, icon, icon_size=button._icon_size),
                })

        if extra_actions:
            for extra in extra_actions:
                tip = extra["tooltip"]
                if isinstance(tip, tuple) and len(tip) == 2:
                    tip = tr(tip[0], tip[1])
                button = self._create_button(extra["icon"], tip)
                button.clicked.connect(extra["callback"])

        self.container.adjustSize()

        # Show/reveal only while scrollable, and disable up/down buttons at the respective end
        sb = self.list_view.verticalScrollBar()
        sb.rangeChanged.connect(self._update_buttons)
        sb.valueChanged.connect(self._update_buttons)
        self._update_buttons()

        self._date_jump_model = None
        self._date_update_timer = QTimer(self)
        self._date_update_timer.setSingleShot(True)
        self._date_update_timer.setInterval(0)
        self._date_update_timer.timeout.connect(self._update_date_buttons)
        if date_jump:
            self._date_jump_model = self.list_view.model()
            if self._date_jump_model:
                self._date_jump_model.modelReset.connect(self._schedule_date_update)
                self._date_jump_model.rowsInserted.connect(self._schedule_date_update)
                self._date_jump_model.rowsRemoved.connect(self._schedule_date_update)
            self._update_date_buttons()

        # Position update timer
        self.position_timer = QTimer(self)  # Parent timer to the QObject
        self.position_timer.timeout.connect(self._update_position)
        self.position_timer.start(100)

    def _create_button(self, icon_name, tooltip):
        button = create_icon_button(
            icons_path=self.icons_path,
            icon_name=icon_name,
            tooltip=tooltip,
            size_type="large",
            config=self.config
        )
        self._layout.addWidget(button)
        return button

    def _update_buttons(self, *_args):
        """Hide the container entirely when nothing is scrollable; disable up-buttons
        at the top and down-buttons at the bottom of the range."""
        sb = self.list_view.verticalScrollBar()
        scrollable = sb.maximum() > sb.minimum()
        at_top = sb.value() <= sb.minimum()
        at_bottom = sb.value() >= sb.maximum()
        self.container.setVisible(scrollable)
        for entry in self._entries:
            enabled = not (at_top if entry["action"] in ("top", "page_up") else at_bottom)
            if enabled != entry["button"].isEnabled():
                entry["button"].setEnabled(enabled)
                entry["button"].setIcon(entry["icon_normal"] if enabled else entry["icon_dimmed"])
        if self._date_buttons:
            self._update_date_enabled()

    def _schedule_date_update(self, *_args):
        self._date_update_timer.start()

    def _update_date_buttons(self, *_args):
        model = self._date_jump_model
        self._separator_rows = []
        if model:
            for row in range(model.rowCount()):
                if _is_separator(model.data(model.index(row, 0), Qt.ItemDataRole.DisplayRole)):
                    self._separator_rows.append(row)

        visible = bool(self._separator_rows)
        for entry in self._date_buttons:
            entry["button"].setVisible(visible)
        if self._date_spacer is not None:
            h = BUTTON_GAP * 2 if (visible or self._has_extra_actions) else 0
            self._date_spacer.changeSize(0, h, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self._layout.invalidate()
            self.container.adjustSize()
        self._update_date_enabled()

    def _update_date_enabled(self):
        if not self._date_buttons or not self.list_view:
            return
        top_index = self.list_view.indexAt(self.list_view.viewport().rect().topLeft())
        top_row = top_index.row() if top_index.isValid() else 0
        for entry in self._date_buttons:
            if entry["direction"] < 0:
                enabled = any(r < top_row for r in self._separator_rows)
            else:
                enabled = any(r > top_row for r in self._separator_rows)
            if enabled != entry["button"].isEnabled():
                entry["button"].setEnabled(enabled)
                entry["button"].setIcon(entry["icon_normal"] if enabled else entry["icon_dimmed"])

    def eventFilter(self, obj, event):
        if obj is self.container:
            if event.type() == QEvent.Type.Enter:
                self._animate_container(OPACITY_VISIBLE)
            elif event.type() == QEvent.Type.Leave:
                self._animate_container(OPACITY_HIDDEN)
            elif event.type() == QEvent.Type.Wheel:
                QApplication.sendEvent(self.list_view.viewport(), event)
                return True
        return super().eventFilter(obj, event)

    def _animate_container(self, target: float):
        self._container_anim.stop()
        self._container_anim.setStartValue(self._container_effect.opacity())
        self._container_anim.setEndValue(target)
        self._container_anim.start()

    def _on_clicked(self, action: str):
        if not self.list_view:
            return
        if action == "top":
            scroll(self.list_view, mode="top", delay=0)
        elif action == "bottom":
            scroll(self.list_view, mode="bottom", delay=0)
        elif action == "page_up":
            self._page_scroll(-1)
        elif action == "page_down":
            self._page_scroll(1)
        self.clicked_scroll.emit(action)

    def _page_scroll(self, direction: int):
        """Scroll by one page. For QListView uses whole rows; for QScrollArea uses scrollbar page step."""
        if isinstance(self.list_view, QListView):
            model = self.list_view.model()
            if not model or not model.rowCount():
                return
            viewport = self.list_view.viewport()
            top_index = self.list_view.indexAt(viewport.rect().topLeft())
            if not top_index.isValid():
                return
            bottom_index = self.list_view.indexAt(QPoint(1, viewport.height() - 1))
            bottom_row = bottom_index.row() if bottom_index.isValid() else model.rowCount() - 1
            page_rows = max(1, bottom_row - top_index.row())
            last_row = model.rowCount() - 1
            if direction > 0:
                target_row = min(top_index.row() + page_rows, last_row)
            else:
                target_row = max(top_index.row() - page_rows, 0)
            self.list_view.scrollTo(model.index(target_row, 0), QAbstractItemView.ScrollHint.PositionAtTop)
            return

        # QScrollArea (and similar): pixel page step via scrollbar
        sb = self.list_view.verticalScrollBar()
        if not sb:
            return
        step = sb.pageStep() or max(1, self.list_view.viewport().height() - 20)
        sb.setValue(sb.value() + direction * step)

    def _update_position(self):
        """Right-align the container, centered vertically in the viewport.
        Clamped to list_view bounds so the reveal padding never covers a sibling pane."""
        if not self.list_view:
            return
        try:
            padding = 10
            viewport = self.list_view.viewport()
            container_size = self.container.sizeHint()
            viewport_pos = viewport.mapTo(self.list_view, viewport.rect().topLeft())

            x = viewport_pos.x() + viewport.width() - container_size.width() - padding
            y = viewport_pos.y() + (viewport.height() - container_size.height()) // 2

            max_x = max(0, self.list_view.width() - container_size.width())
            max_y = max(0, self.list_view.height() - container_size.height())
            x = max(0, min(x, max_x))
            y = max(0, min(y, max_y))

            self.container.move(x, y)
        except RuntimeError:
            pass

    def cleanup(self):
        """Stop timers and release the container"""
        if self.position_timer:
            self.position_timer.stop()
        if self._date_update_timer:
            self._date_update_timer.stop()
        if self.list_view:
            try:
                sb = self.list_view.verticalScrollBar()
                sb.rangeChanged.disconnect(self._update_buttons)
                sb.valueChanged.disconnect(self._update_buttons)
            except (RuntimeError, TypeError):
                pass
        if self._date_jump_model:
            try:
                self._date_jump_model.modelReset.disconnect(self._schedule_date_update)
                self._date_jump_model.rowsInserted.disconnect(self._schedule_date_update)
                self._date_jump_model.rowsRemoved.disconnect(self._schedule_date_update)
            except (RuntimeError, TypeError):
                pass
        self.container.hide()
        self.container.setParent(None)

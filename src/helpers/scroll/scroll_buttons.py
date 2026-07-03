"""Reusable scroll buttons panel (top/bottom full + page up/down) for list views"""
from pathlib import Path
from PyQt6.QtWidgets import QListView, QGraphicsOpacityEffect, QAbstractItemView
from PyQt6.QtCore import QObject, QTimer, QPropertyAnimation, QEvent, QPoint, pyqtSignal
from helpers.config import Config
from helpers.create import create_icon_button
from helpers.scroll.scroll import scroll

OPACITY_DEFAULT = 0.35
OPACITY_HOVER   = 1.0
FADE_DURATION   = 180  # ms
BUTTON_GAP      = 6    # px between stacked buttons

# Top-to-bottom order, matching the on-screen stack: full-up, page-up, page-down, full-down
_BUTTONS = (
    # icon_name,              tooltip,              action
    ("arrow-up-double.svg",   "Scroll to top",       "top"),
    ("arrow-up.svg",          "Scroll up a page",    "page_up"),
    ("arrow-down.svg",        "Scroll down a page",  "page_down"),
    ("arrow-down-double.svg", "Scroll to bottom",     "bottom"),
)


class ScrollButtonsPanel(QObject):
    """Floating panel of scroll buttons (top/bottom full + page up/down) for a QListView.

    Shown only while the list is actually scrollable (rangeChanged-driven), and while
    shown stays at OPACITY_DEFAULT, brightening to OPACITY_HOVER per-button on hover.
    """
    clicked_scroll = pyqtSignal(str)  # emits the action that was triggered: top/page_up/page_down/bottom

    def __init__(self, list_view: QListView, parent=None):
        super().__init__(parent)  # Parent the QObject properly
        self.list_view = list_view

        # Paths
        base_path = Path(__file__).parent.parent.parent
        icons_path = base_path / "icons"
        config_path = base_path / "settings" / "config.json"

        # Load config
        self.config = Config(str(config_path))

        # Build the four buttons, each with its own opacity effect/animation so hover
        # only affects the button under the cursor
        self._entries = []
        for icon_name, tooltip, action in _BUTTONS:
            button = create_icon_button(
                icons_path=icons_path,
                icon_name=icon_name,
                tooltip=tooltip,
                size_type="large",
                config=self.config
            )
            button.setParent(parent)

            effect = QGraphicsOpacityEffect(button)
            effect.setOpacity(OPACITY_DEFAULT)
            button.setGraphicsEffect(effect)

            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(FADE_DURATION)

            button.installEventFilter(self)
            button.clicked.connect(lambda _checked=False, a=action: self._on_clicked(a))

            self._entries.append({"button": button, "effect": effect, "anim": anim})

        # Only show buttons when there's actually something to scroll
        self.list_view.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        self._on_range_changed(*self._scrollbar_range())

        # Position update timer
        self.position_timer = QTimer(self)  # Parent timer to the QObject
        self.position_timer.timeout.connect(self._update_positions)
        self.position_timer.start(100)

    def _scrollbar_range(self):
        sb = self.list_view.verticalScrollBar()
        return sb.minimum(), sb.maximum()

    def _on_range_changed(self, minimum: int, maximum: int):
        """Show the panel only while the list actually has a scrollbar (content overflows
        the viewport); hide it entirely when everything already fits on screen."""
        scrollable = maximum > minimum
        for entry in self._entries:
            entry["button"].setVisible(scrollable)

    def _animate_opacity(self, entry: dict, target: float):
        anim = entry["anim"]
        anim.stop()
        anim.setStartValue(entry["effect"].opacity())
        anim.setEndValue(target)
        anim.start()

    def eventFilter(self, obj, event):
        for entry in self._entries:
            if obj is entry["button"]:
                if event.type() == QEvent.Type.Enter:
                    self._animate_opacity(entry, OPACITY_HOVER)
                elif event.type() == QEvent.Type.Leave:
                    self._animate_opacity(entry, OPACITY_DEFAULT)
                break
        return super().eventFilter(obj, event)

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
        """Scroll by one page of whole rows, so the row landing at the viewport edge
        is always fully visible - never cropped like raw pixel-based page stepping would be."""
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

        if direction > 0:  # page down: reveal the next unseen chunk below
            target_row = min(top_index.row() + page_rows, last_row)
        else:  # page up: reveal the previous chunk above
            target_row = max(top_index.row() - page_rows, 0)

        self.list_view.scrollTo(model.index(target_row, 0), QAbstractItemView.ScrollHint.PositionAtTop)

    def _update_positions(self):
        """Stack buttons right-aligned, centered as a group vertically in the viewport"""
        if not self.list_view or not self._entries:
            return
        try:
            padding = 10
            viewport = self.list_view.viewport()
            button = self._entries[0]["button"]
            button_h = button.height()
            total_h = button_h * len(self._entries) + BUTTON_GAP * (len(self._entries) - 1)

            # Right aligned
            x = viewport.width() - button.width() - padding

            # Stack centered as a group vertically in the viewport
            top_y = (viewport.height() - total_h) // 2

            # Map viewport position to list_view coordinates
            viewport_pos = viewport.mapTo(self.list_view, viewport.rect().topLeft())
            final_x = viewport_pos.x() + x

            y = top_y
            for entry in self._entries:
                entry["button"].move(final_x, viewport_pos.y() + y)
                y += button_h + BUTTON_GAP
        except RuntimeError:
            pass

    def cleanup(self):
        """Stop timers and release buttons"""
        if self.position_timer:
            self.position_timer.stop()
        if self.list_view:
            try:
                self.list_view.verticalScrollBar().rangeChanged.disconnect(self._on_range_changed)
            except (RuntimeError, TypeError):
                pass
        for entry in self._entries:
            entry["button"].hide()
            entry["button"].setParent(None)
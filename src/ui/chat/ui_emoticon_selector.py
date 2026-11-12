"""Emoticon selector widget for choosing emoticons"""

from pathlib import Path
from typing import List

from PyQt6.QtCore import pyqtSignal, QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QCursor, QIcon, QMovie
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from helpers.text.emoticons import EmoticonManager
from helpers.translate import on_language_changed, TranslatableMixin
from themes.stylesheet import repolish


# Grid / sizing constants — single source of truth
_COLS           = 7    # columns in the emoticon grid (must match number of groups)
_BUTTON_SIZE       = 60   # emoticon & tab button size (px)
_BUTTON_SPACING    = 6    # gap between buttons (px)
_NAV_ICON_SIZE  = 32   # group icon size in the nav buttons (px)
_MARGIN         = 6    # margin for nav area (px)
_CONTENT_MARGIN = _MARGIN - 3  # margin for content area (px) — compensates for QScrollArea platform chrome
_GRID_WIDTH     = _COLS * _BUTTON_SIZE + (_COLS - 1) * _BUTTON_SPACING
PANEL_WIDTH    = _MARGIN + _GRID_WIDTH + _MARGIN
_NAV_HEIGHT     = _MARGIN + _BUTTON_SIZE + _MARGIN

class _EmoticonButton(QPushButton):
    """Button displaying an animated emoticon"""
    _emoticon_clicked = pyqtSignal(str, bool)

    def __init__(self, emoticon_path: Path, emoticon_name: str):
        super().__init__()
        self.setObjectName("emoticonButton")
        self._emoticon_name = emoticon_name
        self._emoticon_path = emoticon_path
        self.movie = None

        self.setFixedSize(QSize(_BUTTON_SIZE, _BUTTON_SIZE))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(f":{emoticon_name}:")

        self._load_emoticon()

    def set_highlighted(self, active: bool):
        """Keyboard cursor look; the colors come from the stylesheet."""
        self.setProperty("highlighted", active)
        repolish(self)

    def _load_emoticon(self):
        """Load and animate the emoticon GIF"""
        if not self._emoticon_path.exists():
            return

        # Create QMovie and parent to QApplication to prevent garbage collection
        self.movie = QMovie(str(self._emoticon_path))
        try:
            # Parent to QApplication instance to keep alive
            self.movie.setParent(QApplication.instance())
        except Exception:
            # Fallback to button if QApplication not available
            self.movie.setParent(self)

        # Set cache mode first for better performance
        self.movie.setCacheMode(QMovie.CacheMode.CacheAll)

        # Set speed to 100% (default)
        self.movie.setSpeed(100)

        # Get first frame to set icon size
        if self.movie.jumpToFrame(0):
            pixmap = self.movie.currentPixmap()
            if not pixmap.isNull():
                self.setIcon(QIcon(pixmap))
                self.setIconSize(pixmap.size())

        # Connect frame updates
        self.movie.frameChanged.connect(self._on_frame_changed)

        # Start animation
        self.movie.start()

        # Verify it's running
        if self.movie.state() != QMovie.MovieState.Running:
            # Try starting again if it didn't start
            self.movie.jumpToFrame(0)
            self.movie.start()

    def _on_frame_changed(self, frame_number):
        """Update button icon when movie frame changes"""
        if self.movie:
            pixmap = self.movie.currentPixmap()
            if not pixmap.isNull():
                self.setIcon(QIcon(pixmap))

    def mousePressEvent(self, event):
        """Handle click — Shift = insert without closing"""
        if event.button() == Qt.MouseButton.LeftButton:
            shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            self._emoticon_clicked.emit(self._emoticon_name, bool(shift_pressed))
        super().mousePressEvent(event)

    def _resume_animation(self):
        """Resume animation - force restart or recreate if missing"""
        if not self.movie:
            self._load_emoticon()
            return

        self.movie.stop()
        self.movie.jumpToFrame(0)
        self.movie.start()
        if self.movie.state() != QMovie.MovieState.Running:
            self.movie.start()

    def update_theme(self, new_path: Path):
        """Reload the GIF when the theme uses another file"""
        if new_path == self._emoticon_path and self.movie:
            return
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self._emoticon_path = new_path
        self._load_emoticon()

    def cleanup(self):
        """Clean up movie resources"""
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None

class _EmoticonGroup(QWidget):
    """Widget for displaying a group of emoticons"""
    _emoticon_clicked = pyqtSignal(str, bool)

    def __init__(self, group_name: str, emoticons: List[tuple]):
        super().__init__()
        self._group_name = group_name
        self.buttons = []

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("emoticonScroll")
        layout.addWidget(scroll)

        # Container with grid
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        container.setLayout(container_layout)
        scroll.setWidget(container)

        grid = QGridLayout()
        grid.setSpacing(_BUTTON_SPACING)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        container_layout.addLayout(grid)
        container_layout.addStretch()

        self._emoticons = emoticons
        self._grid = grid
        self._is_built = False

    def ensure_built(self):
        """Create the buttons on first use; a never opened group costs no widgets"""
        if self._is_built:
            return
        self._is_built = True
        for index, (name, path) in enumerate(self._emoticons):
            if not self._is_valid(path):
                continue

            row, col = index // _COLS, index % _COLS
            button = _EmoticonButton(path, name)
            button._emoticon_clicked.connect(self._emoticon_clicked.emit)
            self.buttons.append(button)
            self._grid.addWidget(button, row, col, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def _is_valid(self, path: Path) -> bool:
        """Quick validation"""
        try:
            return path.exists() and path.stat().st_size > 100
        except Exception:
            return False

    def resume_animations(self):
        """Resume all button animations"""
        for button in self.buttons:
            button._resume_animation()

    def update_theme(self, manager: EmoticonManager):
        """Update group for new theme"""
        for button in self.buttons:
            button.update_theme(manager.get_emoticon_path(button._emoticon_name))

    def cleanup(self):
        """Clean up all buttons"""
        for button in self.buttons:
            button.cleanup()

class EmoticonSelectorWidget(TranslatableMixin, QWidget):
    """Widget for selecting emoticons with icon-based navigation"""
    _emoticon_selected = pyqtSignal(str)

    def __init__(self, config, emoticon_manager: EmoticonManager, icons_path: Path):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.emoticon_manager = emoticon_manager
        self.icons_path = icons_path

        self._recent_emoticons = config.get("ui", "recent_emoticons") or []
        self._group_indices = {}
        self._nav_buttons = {}
        self._recent_buttons = []
        self._group_widgets = []
        self._nav_btn = None  # currently keyboard-highlighted EmoticonButton
        self._is_theme_stale = False
        self._pos_timer = QTimer(self)
        self._pos_timer.setSingleShot(True)
        self._pos_timer.timeout.connect(self._save_position)

        self._init_ui()
        self.setFixedWidth(PANEL_WIDTH)  # applied after init so nothing can override it
        on_language_changed(self.retranslate_all)

        # Restore visibility and state
        visible = config.get("ui", "emoticon_selector_visible")
        if visible if visible is not None else False:
            self.setVisible(True)
            QTimer.singleShot(50, self._restore_state)
        else:
            self.setVisible(False)

    def _init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.setObjectName("emoticonSelector")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.is_dark_theme = self.config.get("ui", "theme") == "dark"

        # Navigation bar
        self._nav_container = QWidget()
        self._nav_container.setObjectName("emoticonNav")
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        nav_layout.setSpacing(_BUTTON_SPACING)
        self._nav_container.setLayout(nav_layout)
        layout.addWidget(self._nav_container)

        # Install event filter for wheel navigation
        self._nav_container.installEventFilter(self)

        # Create nav buttons
        self._create_nav_button("emoticon_groups/star.svg", "recent", "Recent", "Недавние", nav_layout, active=True)

        group_tooltips = {
            'Army': ("Army", "Армия"),
            'Boys': ("Boys", "Парни"),
            'Christmas': ("Christmas", "Рождество"),
            'Girls': ("Girls", "Девушки"),
            'Halloween': ("Halloween", "Хэллоуин"),
            'Inlove': ("Inlove", "Влюблённые"),
        }
        for group_name, (icon_name, key) in {
            'Army': ('emoticon_groups/military-helmet.svg', 'army'),
            'Boys': ('emoticon_groups/boy.svg', 'boys'),
            'Christmas': ('emoticon_groups/christmas-tree.svg', 'christmas'),
            'Girls': ('emoticon_groups/girl.svg', 'girls'),
            'Halloween': ('emoticon_groups/jack-o-lantern.svg', 'halloween'),
            'Inlove': ('emoticon_groups/red-heart.svg', 'inlove')
        }.items():
            tooltip_en, tooltip_ru = group_tooltips[group_name]
            self._create_nav_button(icon_name, key, tooltip_en, tooltip_ru, nav_layout)

        # Content area
        self._content_container = QWidget()
        self._content_container.setObjectName("emoticonContent")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(_CONTENT_MARGIN, _CONTENT_MARGIN, _CONTENT_MARGIN, _CONTENT_MARGIN)
        content_layout.setSpacing(0)
        self._content_container.setLayout(content_layout)
        layout.addWidget(self._content_container, stretch=1)

        # Stacked widget
        self._stacked_content = QStackedWidget()
        self._stacked_content.setObjectName("emoticonStack")
        content_layout.addWidget(self._stacked_content, stretch=1)

        # Add content
        self._create_recent_content()
        self._create_group_contents()

        # Nav height: button size + margins
        self._nav_container.setFixedHeight(_NAV_HEIGHT)

    def _create_nav_button(self, icon_name: str, key: str, tooltip_en: str, tooltip_ru: str, layout: QHBoxLayout, active: bool = False):
        """Create a navigation button"""
        button = QPushButton()
        button.setIcon(QIcon(str(self.icons_path / icon_name)))
        button.setIconSize(QSize(_NAV_ICON_SIZE, _NAV_ICON_SIZE))
        button.setFixedSize(_BUTTON_SIZE, _BUTTON_SIZE)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.tr_set(button.setToolTip, tooltip_en, tooltip_ru)

        self._update_nav_button_style(button, active)
        button.clicked.connect(lambda: self._switch_to_group(key))
        self._nav_buttons[key] = button
        layout.addWidget(button)

    def _update_nav_button_style(self, button: QPushButton, active: bool):
        button.setProperty("active", active)
        repolish(button)

    def _create_recent_content(self):
        """Create recent emoticons content"""
        self._recent_widget = QWidget()
        recent_layout = QVBoxLayout()
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(0)
        self._recent_widget.setLayout(recent_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("emoticonScroll")
        recent_layout.addWidget(scroll)

        self._recent_container = QWidget()
        self._recent_layout = QVBoxLayout()
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(0)
        self._recent_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._recent_container.setLayout(self._recent_layout)
        scroll.setWidget(self._recent_container)

        self._recent_grid = QGridLayout()
        self._recent_grid.setSpacing(_BUTTON_SPACING)
        self._recent_grid.setContentsMargins(0, 0, 0, 0)
        self._recent_grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._recent_layout.addLayout(self._recent_grid)
        self._recent_layout.addStretch()

        self._populate_recent_emoticons()

        self._group_indices['recent'] = self._stacked_content.count()
        self._stacked_content.addWidget(self._recent_widget)

    def _populate_recent_emoticons(self):
        """Populate recent emoticons grid"""
        # If the keyboard cursor points at a recent button that's about to be
        # deleted, clear it now so _highlight never touches a dead C++ object.
        if self._nav_btn in self._recent_buttons:
            self._nav_btn = None
            self._set_position("recent", 0)

        # Clean up old buttons
        for button in self._recent_buttons:
            button.cleanup()
        self._recent_buttons.clear()

        # Clear existing widgets
        while self._recent_grid.count():
            item = self._recent_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add recent (COLS per row)
        cols = _COLS
        for index, name in enumerate(self._recent_emoticons):
            path = self.emoticon_manager.get_emoticon_path(name)
            if not path:
                continue

            row, col = index // cols, index % cols
            button = _EmoticonButton(path, name)
            button._emoticon_clicked.connect(self._on_emoticon_clicked)
            self._recent_buttons.append(button)
            self._recent_grid.addWidget(button, row, col, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Placeholder if empty
        if not self._recent_emoticons:
            placeholder = QLabel()
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setObjectName("emoticonPlaceholder")
            self.tr_set(placeholder.setText, "No recent emoticons yet", "Пока нет недавних эмотиконов")
            self._recent_grid.addWidget(placeholder, 0, 0, 1, _COLS)

        # If recent is the active tab, restore highlight to index 0
        if self._recent_buttons and self._current_key() == 'recent':
            self._set_nav(self._recent_buttons, 0)

    def _create_group_contents(self):
        """Create content for each emoticon group"""
        groups = self.emoticon_manager.get_groups()

        for group_name in ['Army', 'Boys', 'Christmas', 'Girls', 'Halloween', 'Inlove']:
            if group_name not in groups:
                continue

            group_widget = _EmoticonGroup(group_name, groups[group_name])
            group_widget._emoticon_clicked.connect(self._on_emoticon_clicked)
            self._group_widgets.append(group_widget)

            key = group_name.lower()
            self._group_indices[key] = self._stacked_content.count()
            self._stacked_content.addWidget(group_widget)

        self._stacked_content.currentChanged.connect(self._build_current_group)

    def _build_current_group(self, index: int):
        group_widget = self._stacked_content.widget(index)
        if isinstance(group_widget, _EmoticonGroup):
            group_widget.ensure_built()

    def _current_key(self):
        index = self._stacked_content.currentIndex()
        return next((k for k, v in self._group_indices.items() if v == index), None)

    def _current_buttons(self):
        index = self._stacked_content.currentIndex()
        if index == self._group_indices.get('recent', -1):
            return self._recent_buttons
        for gw in self._group_widgets:
            if self._stacked_content.indexOf(gw) == index:
                return gw.buttons
        return []

    def _highlight(self, button, active):
        if not button:
            return
        try:
            button.set_highlighted(active)
        except RuntimeError:
            pass  # C++ object already deleted — nothing to style

    def _set_nav(self, btns, index):
        """Unhighlight current, highlight btns[idx], scroll into view, schedule save."""
        self._highlight(self._nav_btn, False)
        self._nav_btn = btns[index]
        self._highlight(self._nav_btn, True)
        p = self._nav_btn.parent()
        while p:
            if isinstance(p, QScrollArea):
                p.ensureWidgetVisible(self._nav_btn)
                break
            p = p.parent()
        self._pos_timer.start(600)

    def _get_positions(self) -> dict:
        return self.config.get("ui", "emoticon_nav_positions") or {}

    def _set_position(self, key: str, index: int):
        positions = self._get_positions()
        positions[key] = index
        self.config.set("ui", "emoticon_nav_positions", value=positions)

    def _restore_index(self, btns) -> int:
        """Return saved position index for the current group (default 0)."""
        saved = self._get_positions().get(self._current_key(), 0)
        return min(saved, len(btns) - 1)

    def _save_position(self):
        key = self._current_key()
        if not key:
            return
        btns = self._current_buttons()
        self._set_position(key, btns.index(self._nav_btn) if self._nav_btn in btns else 0)

    def _switch_to_group(self, key: str):
        # Flush position save for the group we're leaving
        if self._pos_timer.isActive():
            self._pos_timer.stop()
            self._save_position()
        self._highlight(self._nav_btn, False)
        self._nav_btn = None

        for k, button in self._nav_buttons.items():
            self._update_nav_button_style(button, k == key)
        if key in self._group_indices:
            self._stacked_content.setCurrentIndex(self._group_indices[key])

        self.config.set("ui", "emoticon_last_group", value=key)

        # Restore saved cursor position for the new group
        btns = self._current_buttons()
        if btns:
            self._set_nav(btns, self._restore_index(btns))

    def navigate(self, dx: int, dy: int):
        """Move keyboard cursor. H/L: flat linear wrap. J/K: column-aware wrap."""
        btns = self._current_buttons()
        if not btns:
            return
        total = len(btns)
        if self._nav_btn not in btns:
            return self._set_nav(btns, self._restore_index(btns))
        cur = btns.index(self._nav_btn)
        if dx:
            new_index = (cur + dx) % total
        else:
            row, col = divmod(cur, _COLS)
            rows = (total - 1) // _COLS + 1
            new_index = min(((row + dy) % rows) * _COLS + col, total - 1)
        self._set_nav(btns, new_index)

    def insert_selected(self, shift=False):
        btns = self._current_buttons()
        if not btns:
            return
        target = self._nav_btn if self._nav_btn in btns else btns[0]
        target._emoticon_clicked.emit(target._emoticon_name, shift)

    def cycle_tab(self, forward: bool = True):
        keys = list(self._group_indices.keys())
        cur  = self._current_key()
        pos  = (keys.index(cur) + (1 if forward else -1)) % len(keys) if cur in keys else 0
        self._switch_to_group(keys[pos])

    def eventFilter(self, obj, event):
        """Handle mouse wheel events on navigation container"""
        if obj == self._nav_container and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            current_index = self._stacked_content.currentIndex()
            total = self._stacked_content.count()

            new_index = (current_index - 1) % total if delta > 0 else (current_index + 1) % total

            for key, index in self._group_indices.items():
                if index == new_index:
                    self._switch_to_group(key)
                    break

            return True

        return super().eventFilter(obj, event)

    def _on_emoticon_clicked(self, emoticon_name: str, shift_pressed: bool):
        """Handle emoticon button click. shift_pressed = keep selector open."""
        self._add_to_recent(emoticon_name)
        self._emoticon_selected.emit(emoticon_name)

        if not shift_pressed:
            lyt = self.parent().layout() if self.parent() else None
            if lyt and lyt.indexOf(self) >= 0:
                release_selector(self)
            else:
                self.setVisible(False)
            self.config.set("ui", "emoticon_selector_visible", value=False)

    def _add_to_recent(self, emoticon_name: str):
        """Add emoticon to recent list"""
        if emoticon_name in self._recent_emoticons:
            self._recent_emoticons.remove(emoticon_name)

        self._recent_emoticons.insert(0, emoticon_name)
        self._recent_emoticons = self._recent_emoticons[:20]

        self.config.set("ui", "recent_emoticons", value=self._recent_emoticons)
        self._populate_recent_emoticons()

    def update_theme(self):
        """Colors come from the application stylesheet; only the theme dependent GIFs are reloaded"""
        self.is_dark_theme = self.config.get("ui", "theme") == "dark"
        self.emoticon_manager.set_theme(self.is_dark_theme)
        self._is_theme_stale = True
        if self.isVisible():
            self._apply_theme_to_buttons()

    def _apply_theme_to_buttons(self):
        """Reload theme-dependent GIFs; deferred while the panel is hidden."""
        if not self._is_theme_stale:
            return
        self._is_theme_stale = False
        for group_widget in self._group_widgets:
            group_widget.update_theme(self.emoticon_manager)

        for button in self._recent_buttons:
            button.update_theme(self.emoticon_manager.get_emoticon_path(button._emoticon_name))

        if 'recent' in self._group_indices:
            self._switch_to_group('recent')

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_theme_to_buttons()

    def toggle_visibility(self):
        """Toggle visibility and save state"""
        new_visible = not self.isVisible()
        self.setVisible(new_visible)
        self.config.set("ui", "emoticon_selector_visible", value=new_visible)

        if new_visible:
            QTimer.singleShot(50, self._restore_state)
        else:
            if self._pos_timer.isActive():
                self._pos_timer.stop()
                self._save_position()
            self._highlight(self._nav_btn, False)
            self._nav_btn = None

    def _restore_state(self):
        """Restore last group + cursor position; called after the widget is shown."""
        last = self.config.get("ui", "emoticon_last_group") or "recent"
        key  = last if last in self._group_indices else "recent"
        # Switch without triggering a config write for the group we're leaving
        for k, button in self._nav_buttons.items():
            self._update_nav_button_style(button, k == key)
        if key in self._group_indices:
            self._stacked_content.setCurrentIndex(self._group_indices[key])
        self.resume_animations()
        btns = self._current_buttons()
        if btns:
            self._set_nav(btns, self._restore_index(btns))

    def resume_animations(self):
        """Resume all emoticon animations in the selector"""
        for button in self._recent_buttons:
            button._resume_animation()
        for group_widget in self._group_widgets:
            group_widget.resume_animations()

    def bind(self, callback):
        """Reconnect emoticon_selected signal to a new callback."""
        try:
            self._emoticon_selected.disconnect()
        except Exception:
            pass
        self._emoticon_selected.connect(callback)

    def attach(self, parent, callback, layout=None, spacing=0):
        """Re-parent the selector and reconnect its signal.

        If *layout* is given the selector is embedded in it (popup mode),
        otherwise it floats as an overlay (chat mode).
        """
        _detach_selector_from_layout(self)
        self.setParent(parent)
        self.bind(callback)
        if layout is not None:
            layout.addWidget(self, stretch=0, alignment=Qt.AlignmentFlag.AlignCenter)
            layout.setSpacing(spacing)
            self.setFixedHeight(350)
            sp = self.sizePolicy()
            sp.setRetainSizeWhenHidden(False)
            self.setSizePolicy(sp)
            self.setFixedWidth(PANEL_WIDTH)  # re-apply after setSizePolicy
            self.setVisible(True)
            QTimer.singleShot(50, self.resume_animations)

    def cleanup(self):
        """Clean up all emoticon buttons"""
        for button in self._recent_buttons:
            button.cleanup()
        for widget in self._group_widgets:
            widget.cleanup()


def _detach_selector_from_layout(sel):
    """Remove *sel* from its current parent's layout and shrink that parent.

    Safe to call when sel is floating (not in any layout) - does nothing in
    that case. Does NOT hide or re-parent sel; callers do that themselves.
    """
    old_parent = sel.parent()
    if old_parent is None:
        return
    old_lyt = old_parent.layout()
    if old_lyt and old_lyt.indexOf(sel) >= 0:
        old_lyt.removeWidget(sel)
        old_lyt.invalidate()
        old_lyt.activate()
        try:
            old_parent.adjustSize()
            if hasattr(old_parent, 'manager'):
                old_parent.manager.position_and_cleanup()
        except Exception:
            pass


def release_selector(sel):
    """Fully release *sel*: detach from layout, hide, and unparent.

    After this call the selector is invisible and owned by no widget.
    The Python reference kept by PopupManager keeps it alive.
    """
    _detach_selector_from_layout(sel)
    sel.setVisible(False)
    sel.setParent(None)

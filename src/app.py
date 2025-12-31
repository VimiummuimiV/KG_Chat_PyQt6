"""
XMPP Chat GUI Application
Desktop chat client with PyQt6 - Klavogonki style
"""
import sys
import threading
import requests
import html
from datetime import datetime
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextBrowser, QLineEdit, QPushButton, QLabel, QSplitter,
    QScrollArea, QDialog, QComboBox, QMessageBox, QMenuBar, QMenu, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QUrl, QByteArray, QRectF
from PyQt6.QtGui import (
    QPixmap, QFont, QTextCursor, QAction, QActionGroup, QDesktopServices,
    QFontMetrics, QKeySequence, QPainter, QPen, QColor
)

from xmpp import XMPPClient
from accounts import AccountManager
from commands import AccountCommands


class ThemeManager:
    """Helpers to discover palettes and render the base QSS template."""

    @staticmethod
    def read_file(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    @staticmethod
    def discover():
        themes_root = os.path.join(os.path.dirname(__file__), "themes")
        dark = []
        light = []
        try:
            if os.path.isdir(themes_root):
                # top-level files
                for entry in os.listdir(themes_root):
                    p = os.path.join(themes_root, entry)
                    if os.path.isfile(p) and entry.lower().endswith(".css"):
                        lowered = entry.lower()
                        if lowered.startswith("dark_"):
                            dark.append(p)
                        elif lowered.startswith("light_"):
                            light.append(p)

                # palettes folder (optional)
                palettes_dir = os.path.join(themes_root, "palettes")
                if os.path.isdir(palettes_dir):
                    for f in os.listdir(palettes_dir):
                        if f.lower().endswith(".css"):
                            pf = os.path.join(palettes_dir, f)
                            lowered = f.lower()
                            if lowered.startswith("dark_"):
                                dark.append(pf)
                            elif lowered.startswith("light_"):
                                light.append(pf)
                            else:
                                dark.append(pf)

                # legacy subfolders
                for sub in ("dark", "light"):
                    subdir = os.path.join(themes_root, sub)
                    if os.path.isdir(subdir):
                        for f in os.listdir(subdir):
                            if f.lower().endswith(".css"):
                                if sub == "dark":
                                    dark.append(os.path.join(subdir, f))
                                else:
                                    light.append(os.path.join(subdir, f))
        except Exception:
            pass
        return dark, light

    @staticmethod
    def parse_palette(path: str) -> dict:
        out = {}
        try:
            text = ThemeManager.read_file(path)
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("/*") or line.startswith("//"):
                    continue
                if line.startswith("--") and ":" in line:
                    try:
                        k, v = line.split(":", 1)
                        k = k.strip().lstrip("-")
                        v = v.strip().rstrip(";")
                        out[k] = v
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    @staticmethod
    def render_qss(template_path: str, palette_path: str) -> str:
        tpl = ThemeManager.read_file(template_path)
        if not tpl:
            return ""
        vars = ThemeManager.parse_palette(palette_path)
        defaults = {
            "bg": "#121212",
            "surface": "#1E1E1E",
            "card": "#232323",
            "primary": "#BB86FC",
            "on_surface": "#E0E0E0",
            "btn_text": "#000000",
            "primary_hover": "#c99bff",
            "overlay": "rgba(0,0,0,0.06)",
            "overlay_light": "rgba(0,0,0,0.04)",
            "border": "rgba(0,0,0,0.06)",
            "scroll_thumb": "rgba(0,0,0,0.06)",
            "slider_groove": "rgba(0,0,0,0.04)",
            "focus_border": "rgba(0,0,0,0.08)",
            "transparent": "transparent",
        }
        for k, v in defaults.items():
            vars.setdefault(k, v)
        qss = tpl
        for k, v in vars.items():
            qss = qss.replace("{{" + k + "}}", v)
        import re
        qss = re.sub(r"\{\{\s*[^}]+\s*\}\}", "", qss)
        return qss

    @staticmethod
    def load_config() -> dict:
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            import json
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def save_config(cfg: dict) -> None:
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            import json
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass


# Theme helpers consolidated into ThemeManager above.
# The ThemeManager class contains file-read, discovery, palette parsing and QSS rendering helpers.
# Use ThemeManager.discover(), ThemeManager.render_qss(), ThemeManager.parse_palette(), ThemeManager.load_config(), ThemeManager.save_config() where needed.


class SignalEmitter(QObject):
    message_received = pyqtSignal(object)
    presence_update = pyqtSignal(object)
    connection_status = pyqtSignal(bool, str)
    avatar_loaded = pyqtSignal(str, QPixmap)  # JID, Pixmap


class ClickableTextBrowser(QTextBrowser):
    """Text browser with clickable usernames without using links"""
    
    username_clicked = pyqtSignal(str)  # Signal when username is clicked
    username_double_clicked = pyqtSignal(str)  # Signal when username is double-clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)  # For actual URLs
        self.setMouseTracking(True)  # Enable mouse tracking for cursor changes
        # Store username positions
        self.username_ranges = []  # List of (start_pos, end_pos, username)
        # Track clicks for double-click detection
        self._last_click_time = 0
        self._last_clicked_username = None
    
    def mouseMoveEvent(self, event):
        """Change cursor when hovering over usernames"""
        cursor = self.cursorForPosition(event.pos())
        position = cursor.position()
        
        # Check if hovering over a username
        over_username = False
        for start_pos, end_pos, username in self.username_ranges:
            if start_pos <= position <= end_pos:
                over_username = True
                break
        
        # Change cursor appearance
        if over_username:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        
        super().mouseMoveEvent(event)
        
    def mousePressEvent(self, event):
        """Handle mouse clicks to detect username clicks and double-clicks"""
        cursor = self.cursorForPosition(event.pos())
        position = cursor.position()
        
        # Check if click is on a username
        for start_pos, end_pos, username in self.username_ranges:
            if start_pos <= position <= end_pos:
                # Check for double-click
                current_time = datetime.now().timestamp()
                time_diff = current_time - self._last_click_time
                
                if time_diff < 0.4 and self._last_clicked_username == username:
                    # Double-click detected
                    self.username_double_clicked.emit(username)
                    self._last_click_time = 0  # Reset to prevent triple-click
                    self._last_clicked_username = None
                else:
                    # Single click
                    self.username_clicked.emit(username)
                    self._last_click_time = current_time
                    self._last_clicked_username = username
                return
        
        # Click was not on a username, reset tracking
        self._last_click_time = 0
        self._last_clicked_username = None
        # Otherwise, handle normally
        super().mousePressEvent(event)
    
    def add_username_range(self, start_pos, end_pos, username):
        """Register a username range for click detection"""
        self.username_ranges.append((start_pos, end_pos, username))
    
    def clear_username_ranges(self):
        """Clear all username ranges"""
        self.username_ranges.clear()


class UserWidget(QWidget):
    def __init__(self, user, signal_emitter, parent=None):
        super().__init__(parent)
        self.user = user
        self.signal_emitter = signal_emitter
        self.zoom_factor = getattr(self.window(), "zoom_level", 100) / 100.0
        self.setup_ui()

        self.signal_emitter.avatar_loaded.connect(self.on_avatar_loaded)

        # Load high-resolution avatar if available
        url = self.user.get_avatar_url()
        if url:
            self.load_avatar(url)

    def setup_ui(self):
        f = self.zoom_factor
        layout = QHBoxLayout()
        layout.setContentsMargins(int(8 * f), int(4 * f), int(8 * f), int(4 * f))

        # Display size = 24×24 px (compact, but sharp thanks to high-res source + scaledContents)
        avatar_display_size = int(24 * f)

        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(avatar_display_size, avatar_display_size)
        self.avatar_label.setScaledContents(True)  # Enables crisp downscaling from 100×100
        self.avatar_label.setObjectName("avatar_label")
        
        # Check if user has avatar
        url = self.user.get_avatar_url()
        if not url:
            # No avatar - display an empty rounded placeholder (SVG-like) instead of an emoji
            pm = QPixmap(avatar_display_size, avatar_display_size)
            pm.fill(QColor(0, 0, 0, 0))  # transparent

            try:
                palette = ThemeManager.parse_palette(self.window().current_theme) if self.window().current_theme else {}
                stroke_color = palette.get('muted') or palette.get('fg') or '#888'
            except Exception:
                stroke_color = '#888'

            # Render compact user SVG into the pixmap using the theme color as stroke
            svg_template = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>'''
            svg = svg_template.format(stroke=stroke_color)

            try:
                from PyQt6.QtSvg import QSvgRenderer
                renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
                pm_svg = QPixmap(avatar_display_size, avatar_display_size)
                pm_svg.fill(QColor(0, 0, 0, 0))
                painter = QPainter(pm_svg)
                renderer.render(painter)
                painter.end()
                self.avatar_label.setPixmap(pm_svg)
            except Exception:
                # Fallback: leave transparent pixmap if SVG rendering isn't available
                self.avatar_label.setPixmap(pm)

            self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.avatar_label.setScaledContents(True)
        
        layout.addWidget(self.avatar_label)

        username_label = QLabel(self.user.login)
        username_label.setFont(QFont("Arial", int(10 * f)))
        color = self.user.background or None
        if color:
            try:
                from color_utils import ensure_contrast
                palette = {}
                try:
                    palette = ThemeManager.parse_palette(self.window().current_theme) if self.window().current_theme else {}
                except Exception:
                    palette = {}
                panel_bg = palette.get('card') or palette.get('surface') or palette.get('bg') or '#000000'
                safe_color = ensure_contrast(color, panel_bg, min_ratio=3.0)
            except Exception:
                safe_color = color
            username_label.setStyleSheet(f"color: {safe_color}; padding-left: {int(5 * f)}px;")
        else:
            username_label.setStyleSheet("padding-left: %dpx;" % int(5 * f))
        layout.addWidget(username_label, 1)

        # Display game counter (semaphore emoji + count) using global font/QSS
        # Lookup using stable key (login preferred)
        key = self.user.login or self.user.user_id or self.user.jid
        game_state = getattr(self.window(), 'user_game_state', {}).get(key, {'count': 0})
        game_count = game_state.get('count', 0)
        if game_count > 0:
            # Use a semaphore/traffic-light emoji (🚦) followed by the per-user count
            game_label = QLabel(f"🚦 {game_count}")
            game_label.setObjectName("game_label")
            # Do not set a font explicitly; QSS/global font will apply (Montserrat primary)
            layout.addWidget(game_label)

        username_label.setObjectName("username_label")
        self.setLayout(layout)
        self.setObjectName("user_widget")

        # Minimum width calculation - always include avatar since we show emoji
        fm = QFontMetrics(username_label.font())
        username_width = fm.horizontalAdvance(self.user.login) + int(5 * f)
        game_width = 0
        # Calculate game width only if we rendered a game counter
        game_label_obj = next((w for w in self.findChildren(QLabel) if w.objectName() == 'game_label'), None)
        if game_label_obj is not None:
            game_fm = QFontMetrics(game_label_obj.font())
            game_width = game_fm.horizontalAdvance(game_label_obj.text()) + int(5 * f)
        
        # Avatar is always visible (either image or emoji)
        min_width = int(8 * f) + avatar_display_size + int(5 * f) + username_width + game_width + int(8 * f)
        self.setMinimumWidth(max(int(180 * f), min_width))

    def load_avatar(self, url):
        if not url:
            return
        full_url = url
        window = self.window()
        if full_url in window.avatar_cache:
            self.apply_avatar(window.avatar_cache[full_url])
            return

        def load_in_thread():
            try:
                response = requests.get(full_url, timeout=5)
                if response.status_code != 200:
                    return
                pixmap = QPixmap()
                if pixmap.loadFromData(QByteArray(response.content)) and not pixmap.isNull():
                    # Cache the full-resolution 100×100 pixmap
                    window.avatar_cache[full_url] = pixmap
                    # Emit – QLabel will downscale it beautifully
                    self.signal_emitter.avatar_loaded.emit(self.user.jid, pixmap)
            except Exception:
                pass  # Silent fail

        threading.Thread(target=load_in_thread, daemon=True).start()

    def apply_avatar(self, pixmap):
        self.avatar_label.setPixmap(pixmap)
        self.avatar_label.show()  # Show avatar when image is loaded

    def on_avatar_loaded(self, jid, pixmap):
        if jid == self.user.jid:
            self.apply_avatar(pixmap)


class AccountDialog(QDialog):
    def __init__(self, account_manager, parent=None):
        super().__init__(parent)
        self.account_manager = account_manager
        self.selected_account = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Select Account")
        self.setMinimumWidth(400)
        layout = QVBoxLayout()
        accounts = self.account_manager.list_accounts()
        if accounts:
            layout.addWidget(QLabel("Select an account:"))
            self.account_combo = QComboBox()
            for acc in accounts:
                self.account_combo.addItem(f"{acc['login']} (ID: {acc['user_id']})", acc)
            layout.addWidget(self.account_combo)
            connect_btn = QPushButton("Connect")
            connect_btn.clicked.connect(self.accept)
            layout.addWidget(connect_btn)
        else:
            layout.addWidget(QLabel("No accounts found."))
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
        self.setLayout(layout)

    def accept(self):
        self.selected_account = self.account_combo.currentData()
        super().accept()


class AddAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_id = None
        self.login = None
        self.password = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Add Account")
        self.setMinimumWidth(400)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("User ID:"))
        self.user_id_field = QLineEdit()
        layout.addWidget(self.user_id_field)
        layout.addWidget(QLabel("Login:"))
        self.login_field = QLineEdit()
        layout.addWidget(self.login_field)
        layout.addWidget(QLabel("Password:"))
        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_field)
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def accept(self):
        self.user_id = self.user_id_field.text().strip()
        self.login = self.login_field.text().strip()
        self.password = self.password_field.text().strip()
        if self.user_id and self.login and self.password:
            super().accept()
        else:
            QMessageBox.warning(self, "Error", "All fields are required!")


class ChatWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.xmpp = XMPPClient()
        self.commands = AccountCommands(self.xmpp.account_manager)
        self.signals = SignalEmitter()
        self.avatar_cache = {}
        self.zoom_level = 100
        self.previous_users = set()
        
        # Track per-user game state: { jid: {'last_game_id': Optional[str], 'count': int} }
        self.user_game_state = {}
        
        # Store message history for theme switching
        self.message_history = []  # List of (sender, text, timestamp, color) tuples

        # Determine preferred font family available on the system
        preferred_list = ["Montserrat", "Roboto", "Tahoma", "Calibri", "Ubuntu", "Helvetica Neue", "Arial"]
        try:
            from PyQt6.QtGui import QFontDatabase
            fams = {f.lower() for f in QFontDatabase().families()}
            chosen = None
            for p in preferred_list:
                if p.lower() in fams:
                    chosen = p
                    break
            self.preferred_font_family = chosen or ""
        except Exception:
            self.preferred_font_family = ""

        # Discover palettes in themes/dark and themes/light
        self.dark_theme_files, self.light_theme_files = ThemeManager.discover()

        # Read saved selection from config.json if present
        cfg = ThemeManager.load_config()
        saved = None
        try:
            saved = cfg.get("ui", {}).get("selected_palette")
        except Exception:
            saved = None

        # Restore userlist visibility if present
        try:
            self.userlist_visible = cfg.get("ui", {}).get("userlist_visible", True)
        except Exception:
            self.userlist_visible = True

        templates_dir = os.path.join(os.path.dirname(__file__), "themes")
        base_tpl = os.path.join(templates_dir, "base_theme.qss")

        chosen_path = None
        if saved:
            candidate = os.path.join(templates_dir, saved)
            if os.path.exists(candidate):
                chosen_path = candidate

        if not chosen_path:
            # fallback to first dark, then first light
            if self.dark_theme_files:
                chosen_path = self.dark_theme_files[0]
            elif self.light_theme_files:
                chosen_path = self.light_theme_files[0]

        self.current_theme = chosen_path

        # Restore saved zoom if present
        try:
            saved_zoom = cfg.get("ui", {}).get("zoom")
            if isinstance(saved_zoom, int) and 50 <= saved_zoom <= 200:
                self.zoom_level = saved_zoom
        except Exception:
            pass

        # Apply chosen palette by rendering the base template
        if self.current_theme and os.path.exists(base_tpl):
            qss = ThemeManager.render_qss(base_tpl, self.current_theme)
            if qss:
                QApplication.instance().setStyleSheet(qss)
            else:
                # fallback: load raw css if parsing failed
                QApplication.instance().setStyleSheet(ThemeManager.read_file(self.current_theme) or "")

        self.signals.message_received.connect(self.on_message)
        self.signals.presence_update.connect(self.on_presence)
        self.signals.connection_status.connect(self.on_connection_status)
        self.xmpp.set_message_callback(self.handle_xmpp_message)
        self.xmpp.set_presence_callback(self.handle_xmpp_presence)

        self.setup_ui()
        # Make sure restored zoom (if any) is applied before loading messages/dialogs
        try:
            self.apply_zoom()
        except Exception:
            pass

        self.show_account_dialog()

    def setup_ui(self):
        self.setWindowTitle("KG Chat")
        self.setGeometry(100, 100, 1400, 800)

        menubar = self.menuBar()
        # Themes menu (dynamically populated)
        self.themes_menu = menubar.addMenu("Themes")
        self.dark_menu = QMenu("Dark", self)
        self.light_menu = QMenu("Light", self)

        def add_theme_actions(menu, files):
            menu.clear()
            files_sorted = sorted(files, key=lambda p: os.path.basename(p).lower())
            if not files_sorted:
                act = QAction("(no themes)", self)
                act.setEnabled(False)
                menu.addAction(act)
                return
            qgroup = QActionGroup(self)
            qgroup.setExclusive(True)
            for p in files_sorted:
                base = os.path.basename(p)
                name = base[:-4]
                # strip leading dark_/light_ if present
                if name.lower().startswith("dark_"):
                    display = name[5:]
                elif name.lower().startswith("light_"):
                    display = name[6:]
                else:
                    display = name
                display = display.replace("_", " ").title()
                act = QAction(display, self)
                act.setCheckable(True)
                # check if this is the current theme
                try:
                    if self.current_theme and os.path.abspath(self.current_theme) == os.path.abspath(p):
                        act.setChecked(True)
                except Exception:
                    pass
                act.triggered.connect(lambda checked=False, path=p: self.apply_theme(path))
                qgroup.addAction(act)
                menu.addAction(act)

        # populate menus
        add_theme_actions(self.dark_menu, self.dark_theme_files)
        add_theme_actions(self.light_menu, self.light_theme_files)

        self.themes_menu.addMenu(self.dark_menu)
        self.themes_menu.addMenu(self.light_menu)

        # helper to refresh theme lists later
        def refresh_theme_menus():
            self.dark_theme_files, self.light_theme_files = ThemeManager.discover()
            add_theme_actions(self.dark_menu, self.dark_theme_files)
            add_theme_actions(self.light_menu, self.light_theme_files)
        self.refresh_theme_menus = refresh_theme_menus
        # Accounts menu
        accounts_menu = menubar.addMenu("Accounts")
        switch_action = QAction("Switch Account", self)
        switch_action.triggered.connect(self.switch_account_dialog)
        accounts_menu.addAction(switch_action)
        add_action = QAction("Add Account", self)
        add_action.triggered.connect(self.add_account_dialog)
        accounts_menu.addAction(add_action)
        remove_action = QAction("Remove Account", self)
        remove_action.triggered.connect(self.remove_account_dialog)
        accounts_menu.addAction(remove_action)
        accounts_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        accounts_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("View")
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcut(QKeySequence(QKeySequence.StandardKey.ZoomIn))
        zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(zoom_in_action)
        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcut(QKeySequence(QKeySequence.StandardKey.ZoomOut))
        zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(zoom_out_action)
        reset_zoom_action = QAction("Reset Zoom", self)
        reset_zoom_action.setShortcut("Ctrl+0")
        reset_zoom_action.triggered.connect(self.reset_zoom)
        view_menu.addAction(reset_zoom_action)

        # Show/hide user list action (persisted)
        self.show_users_action = QAction("Show Users", self)
        self.show_users_action.setCheckable(True)
        self.show_users_action.setChecked(getattr(self, 'userlist_visible', True))
        self.show_users_action.toggled.connect(self.set_userlist_visible)
        view_menu.addAction(self.show_users_action)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - chat
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(0)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.messages_display = ClickableTextBrowser()
        self.messages_display.username_clicked.connect(self.on_username_clicked)
        self.messages_display.username_double_clicked.connect(self.on_username_double_clicked)
        left_layout.addWidget(self.messages_display, 1)

        # Input container for visual separation (styled by QSS)
        input_container = QWidget()
        input_container.setObjectName("input_container")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(8)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type message...")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field, 1)
        
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        
        left_layout.addWidget(input_container)

        # Right panel - users
        self.right_panel = QWidget()
        self.right_panel.setObjectName("right_panel")
        right_layout = QVBoxLayout(self.right_panel)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.user_list_widget = QWidget()
        self.user_list_widget.setObjectName("user_list_widget")
        self.user_list_layout = QVBoxLayout(self.user_list_widget)
        self.user_list_layout.setSpacing(6)
        self.user_list_layout.setContentsMargins(0, 0, 0, 0)

        # Top container: users not currently in a game
        self.top_container = QWidget()
        self.top_container.setObjectName("user_list_top")
        self.top_layout = QVBoxLayout(self.top_container)
        self.top_layout.setSpacing(1)
        self.top_layout.setContentsMargins(0, 0, 0, 0)

        # Bottom container: users currently in a game (game_id present)
        self.bottom_container = QWidget()
        self.bottom_container.setObjectName("user_list_bottom")
        self.bottom_layout = QVBoxLayout(self.bottom_container)
        self.bottom_layout.setSpacing(1)
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.user_list_layout.addWidget(self.top_container)
        # Add small spacing between groups
        self.user_list_layout.addSpacing(10)
        self.user_list_layout.addWidget(self.bottom_container)
        # Add stretch at the end to push everything to the top
        self.user_list_layout.addStretch()

        self.scroll_area.setWidget(self.user_list_widget)
        right_layout.addWidget(self.scroll_area, 1)

        self.splitter.addWidget(left)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        
        # Set minimum width for right panel to ensure it's visible
        self.right_panel.setMinimumWidth(200)
        
        main_layout.addWidget(self.splitter)

        # Status bar: left side shows connection status inside a padded container
        left_status_widget = QWidget()
        left_status_layout = QHBoxLayout(left_status_widget)
        left_status_layout.setContentsMargins(8, 2, 8, 2)
        left_status_layout.setSpacing(6)
        self.status_label = QLabel("Disconnected")
        left_status_layout.addWidget(self.status_label)
        # add the left container with stretch so it occupies the center area professionally
        self.statusBar().addWidget(left_status_widget, 1)

        # Toggle button for user list (checkable) followed by zoom percent and slider at the far right
        self.toggle_users_btn = QPushButton("Users")
        self.toggle_users_btn.setCheckable(True)
        self.toggle_users_btn.setChecked(getattr(self, 'userlist_visible', True))
        self.toggle_users_btn.setMinimumSize(60, 24)
        self.toggle_users_btn.setMaximumHeight(24)
        self.toggle_users_btn.setObjectName("toggle_users_btn")
        self.toggle_users_btn.toggled.connect(self.set_userlist_visible)
        self.statusBar().addPermanentWidget(self.toggle_users_btn)

        self.zoom_percent_label = QLabel(f"{self.zoom_level}%")
        self.zoom_percent_label.setObjectName("zoom_percent_label")
        self.statusBar().addPermanentWidget(self.zoom_percent_label)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(50, 200)
        self.zoom_slider.setValue(self.zoom_level)
        self.zoom_slider.setFixedWidth(140)
        self.zoom_slider.setFixedHeight(18)
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        self.statusBar().addPermanentWidget(self.zoom_slider)

        # ensure status bar has comfortable height for the slider handle
        self.statusBar().setMinimumHeight(30)

        # Apply initial userlist visibility state
        try:
            # Force visible on first load to ensure it's shown
            initial_visible = getattr(self, 'userlist_visible', True)
            if initial_visible:
                self.right_panel.show()
            else:
                self.right_panel.hide()
            # Sync button state
            if hasattr(self, 'toggle_users_btn'):
                self.toggle_users_btn.blockSignals(True)
                self.toggle_users_btn.setChecked(initial_visible)
                self.toggle_users_btn.blockSignals(False)
        except Exception as e:
            print(f"Error setting initial userlist visibility: {e}")
            self.right_panel.show()  # Fallback to visible

    def on_username_clicked(self, username):
        """Handle single username clicks - add username if not present"""
        current = self.input_field.text()
        
        # Extract all existing usernames from comma-separated list
        existing_usernames = []
        if current.strip():
            # Split by comma and extract each username
            parts = current.split(",")
            for part in parts:
                part = part.strip()
                if part:
                    existing_usernames.append(part)
        
        # Check if username already exists
        if username in existing_usernames:
            # Username already present, don't add duplicate
            self.input_field.setFocus()
            return
        
        # Add the new username
        if current.strip() and current.rstrip().endswith(","):
            # Already has username mentions ending with comma, add another
            self.input_field.setText(f"{current.rstrip()} {username}, ")
        elif current.strip():
            # Has text but no proper comma separation yet
            self.input_field.setText(f"{current.rstrip()}, {username}, ")
        else:
            # Empty field
            self.input_field.setText(f"{username}, ")
        
        self.input_field.setFocus()

    def on_username_double_clicked(self, username):
        """Handle double-click on username - replace everything with just this username"""
        self.input_field.setText(f"{username}, ")
        self.input_field.setFocus()

    def show_account_dialog(self):
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            self.connect_xmpp(dialog.selected_account)
        else:
            sys.exit(0)

    def switch_account_dialog(self):
        dialog = AccountDialog(self.xmpp.account_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_account:
            self.disconnect_xmpp()
            self.connect_xmpp(dialog.selected_account)

    def add_account_dialog(self):
        dialog = AddAccountDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            success = self.xmpp.account_manager.add_account(dialog.user_id, dialog.login, dialog.password)
            QMessageBox.information(self, "Success" if success else "Error",
                                    f"Account '{dialog.login}' {'added' if success else 'failed'}!")

    def remove_account_dialog(self):
        accounts = self.xmpp.account_manager.list_accounts()
        if not accounts:
            QMessageBox.information(self, "Info", "No accounts to remove.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Remove Account")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select account to remove:"))
        combo = QComboBox()
        for acc in accounts:
            combo.addItem(acc['login'], acc)
        layout.addWidget(combo)
        btn_layout = QHBoxLayout()
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(remove_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            acc = combo.currentData()
            if self.xmpp.account_manager.remove_account(acc['login']):
                QMessageBox.information(self, "Success", f"Account '{acc['login']}' removed!")

    def connect_xmpp(self, account):
        self.status_label.setText("Connecting...")
        def thread_func():
            try:
                if self.xmpp.connect(account):
                    for room in self.xmpp.account_manager.get_rooms():
                        if room.get('auto_join'):
                            self.xmpp.join_room(room['jid'])
                    self.signals.connection_status.emit(True, f"Connected as {account['login']}")
                    self.xmpp.listen()
                else:
                    self.signals.connection_status.emit(False, "Connection failed")
            except Exception as e:
                self.signals.connection_status.emit(False, str(e))
        threading.Thread(target=thread_func, daemon=True).start()

    def disconnect_xmpp(self):
        # Disconnect XMPP first to stop receiving presence updates
        self.xmpp.disconnect()
        
        # Clear message display and history
        self.messages_display.clear()
        self.messages_display.clear_username_ranges()
        self.message_history.clear()
        
        # Clear user data
        self.xmpp.user_list.clear()
        self.previous_users.clear()
        
        # Clear user list widgets safely
        try:
            # Clear top container
            if hasattr(self, 'top_layout') and self.top_layout:
                while self.top_layout.count() > 0:
                    item = self.top_layout.takeAt(0)
                    if item and item.widget():
                        item.widget().deleteLater()
        except RuntimeError:
            pass
        
        try:
            # Clear bottom container
            if hasattr(self, 'bottom_layout') and self.bottom_layout:
                while self.bottom_layout.count() > 0:
                    item = self.bottom_layout.takeAt(0)
                    if item and item.widget():
                        item.widget().deleteLater()
        except RuntimeError:
            pass
        
        # Update status
        self.status_label.setText("Disconnected")
        self.statusBar().setProperty("class", "status-disconnected")

    def on_connection_status(self, success, msg):
        self.status_label.setText(msg)
        self.statusBar().setProperty("class", "status-connected" if success else "status-disconnected")
        # application stylesheet is applied globally; no per-widget theme required
        if success:
            self.previous_users.clear()
            self.update_user_list()

    def handle_xmpp_message(self, message):
        active = self.xmpp.account_manager.get_active_account()
        if active and message.login == active['login']:
            return
        self.signals.message_received.emit(message)

    def handle_xmpp_presence(self, presence):
        """Update internal game counters and forward presence update"""
        try:
            # Use login as the canonical key when available (more stable than full JID resource)
            key = presence.login or presence.user_id or presence.from_jid
            # Only consider available presences for game counting logic
            if presence.presence_type == 'available':
                if presence.game_id:
                    new_gid = str(presence.game_id).strip()
                    state = self.user_game_state.get(key, {'last_game_id': None, 'count': 0})
                    last_gid = state.get('last_game_id')
                    if last_gid is None:
                        state['last_game_id'] = new_gid
                        state['count'] = 1
                        # Debug information
                        print(f"[game-counter] {key}: initialized to 1 (gid={new_gid})")
                    elif new_gid != last_gid:
                        old = state.get('count', 0)
                        state['last_game_id'] = new_gid
                        state['count'] = old + 1
                        print(f"[game-counter] {key}: {old} -> {state['count']} (gid={new_gid})")
                    # same gid => do nothing
                    self.user_game_state[key] = state
                else:
                    # Presence with no game_id resets the sequence for this user
                    self.user_game_state[key] = {'last_game_id': None, 'count': 0}
            else:
                # Unavailable -> keep game state (do not clear). This allows counting
                # to increment when a user leaves and later re-joins with a game_id.
                # We intentionally do not pop the user's state here.
                pass
        except Exception:
            # Be resilient; on errors, fall back to just forwarding the presence
            pass

        # Forward for normal processing (UI updates happen in on_presence)
        self.signals.presence_update.emit(presence)

    def on_message(self, message):
        sender = message.login or "Unknown"
        ts = message.timestamp.strftime("%H:%M:%S") if message.timestamp else ""
        color = message.background or None
        self.add_message(sender, message.body, ts, color)

    def on_presence(self, presence):
        self.update_user_list()
        QTimer.singleShot(100, self.update_user_list)

    def add_message(self, sender, text, timestamp="", color=None):
        # Store message in history for theme switching (keep last 100 messages)
        self.message_history.append((sender, text, timestamp, color))
        if len(self.message_history) > 100:
            self.message_history.pop(0)
        
        # Save current scroll position
        scrollbar = self.messages_display.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        
        # Add the message
        self._add_message_internal(sender, text, timestamp, color)
        
        # Only scroll if we were at bottom before
        if was_at_bottom:
            self.messages_display.moveCursor(QTextCursor.MoveOperation.End)
            self.messages_display.ensureCursorVisible()


    def update_user_list(self):
        # Safety check: ensure layouts still exist
        try:
            if not hasattr(self, 'top_layout') or not hasattr(self, 'bottom_layout'):
                return
            if self.top_layout is None or self.bottom_layout is None:
                return
        except RuntimeError:
            # Layout has been deleted
            return
        
        current_logins = {u.login for u in self.xmpp.user_list.get_online()}
        self.previous_users = current_logins.copy()

        # Clear top and bottom containers completely
        try:
            while self.top_layout.count() > 0:
                item = self.top_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        except RuntimeError:
            # Layout was deleted while clearing
            return
            
        try:
            while self.bottom_layout.count() > 0:
                item = self.bottom_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        except RuntimeError:
            # Layout was deleted while clearing
            return

        users = sorted(self.xmpp.user_list.get_online(), key=lambda u: u.login.lower())
        max_width = 0
        
        # Ensure initial state for users currently in a game (so counts show on first render)
        for user in users:
            if user.game_id:
                key = user.login or user.user_id or user.jid
                if key not in self.user_game_state:
                    # Initialize unseen in-game users with count=1
                    self.user_game_state[key] = {'last_game_id': str(user.game_id).strip(), 'count': 1}

        try:
            # Add non-game users first (top container), alphabetically
            not_in_game = [u for u in users if not u.game_id]
            for user in not_in_game:
                widget = UserWidget(user, self.signals, self)
                self.top_layout.addWidget(widget)
                max_width = max(max_width, widget.minimumWidth())

            # Add in-game users sorted by descending game counter (bigger counts on top)
            in_game = [u for u in users if u.game_id]
            in_game_sorted = sorted(
                in_game,
                key=lambda u: self.user_game_state.get(u.login or u.user_id or u.jid, {}).get('count', 0),
                reverse=True
            )
            for user in in_game_sorted:
                widget = UserWidget(user, self.signals, self)
                self.bottom_layout.addWidget(widget)
                max_width = max(max_width, widget.minimumWidth())

            self.user_list_widget.setMinimumWidth(max_width + 20)
            self.right_panel.setMinimumWidth(max_width + 40)
        except RuntimeError:
            # Layouts were deleted while adding widgets
            pass


    def set_userlist_visible(self, visible: bool):
        """Show or hide the right-side user list and persist the choice."""
        visible = bool(visible)
        
        # Show or hide the panel
        if not visible:
            # save current splitter sizes so we can restore when showing again
            self._saved_splitter_sizes = self.splitter.sizes()
            self.right_panel.hide()
        else:
            self.right_panel.show()
            # restore previous sizes if available
            if hasattr(self, '_saved_splitter_sizes') and self._saved_splitter_sizes:
                self.splitter.setSizes(self._saved_splitter_sizes)

        # keep UI controls in sync (block signals to prevent recursion)
        if hasattr(self, 'toggle_users_btn'):
            self.toggle_users_btn.blockSignals(True)
            self.toggle_users_btn.setChecked(visible)
            self.toggle_users_btn.blockSignals(False)
            
        if hasattr(self, 'show_users_action'):
            self.show_users_action.blockSignals(True)
            self.show_users_action.setChecked(visible)
            self.show_users_action.blockSignals(False)

        # Persist selection
        try:
            cfg = ThemeManager.load_config()
            ui = cfg.get('ui', {})
            ui['userlist_visible'] = bool(visible)
            cfg['ui'] = ui
            ThemeManager.save_config(cfg)
        except Exception:
            pass

    def zoom_in(self):
        self.zoom_level = min(200, self.zoom_level + 10)
        self.apply_zoom()

    def zoom_out(self):
        self.zoom_level = max(50, self.zoom_level - 10)
        self.apply_zoom()

    def reset_zoom(self):
        self.zoom_level = 100
        self.apply_zoom()

    def on_zoom_slider_changed(self, value):
        self.zoom_level = value
        self.apply_zoom()

    def apply_zoom(self):
        f = self.zoom_level / 100.0
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(self.zoom_level)
        self.zoom_slider.blockSignals(False)
        self.zoom_percent_label.setText(f"{self.zoom_level}%")

        base_size = 13
        scaled_size = int(base_size * f)
        # Make emojis 30% larger than regular text for better visibility
        emoji_size = int(scaled_size * 1.3)

        # Apply preferred font family to chat document so messages use UI font priority and support Cyrillic
        pf = getattr(self, 'preferred_font_family', '')
        if pf:
            doc_font = QFont(pf, scaled_size)
        else:
            doc_font = QFont("", scaled_size)
        self.messages_display.document().setDefaultFont(doc_font)
        
        # Set up font-size with emoji support via CSS
        # Use Noto Color Emoji as fallback for emoji characters
        emoji_css = f"""
            font-size: {scaled_size}px;
            font-family: {pf if pf else 'sans-serif'}, 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI Emoji';
        """
        self.messages_display.setStyleSheet(emoji_css)
        self.input_field.setStyleSheet(f"font-size: {scaled_size}px; font-family: {pf if pf else 'sans-serif'}, 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI Emoji';")

        self.update_user_list()

        # Persist zoom level so it is restored on next launch
        try:
            cfg = ThemeManager.load_config()
            ui = cfg.get("ui", {})
            ui["zoom"] = int(self.zoom_level)
            cfg["ui"] = ui
            ThemeManager.save_config(cfg)
        except Exception:
            pass

    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        if self.xmpp.send_message(text):
            ts = datetime.now().strftime("%H:%M:%S")
            active = self.xmpp.account_manager.get_active_account()
            # outgoing message color from current palette (fallback to a warm pink)
            try:
                palette = ThemeManager.parse_palette(self.current_theme) if self.current_theme else {}
            except Exception:
                palette = {}
            outgoing_color = palette.get("outgoing", palette.get("accent", "#fe3272"))
            self.add_message(active['login'], text, ts, outgoing_color)
            self.input_field.clear()

    def apply_theme(self, path: str):
        """Apply a palette file by path and remember selected palette (saved to config.json).

        The palette file should be a simple file with `--name: value;` lines and lives under `themes/`.
        The base template `themes/base_theme.qss` is rendered with the palette variables.
        """
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Theme error", f"Theme file not found: {path}")
            return

        templates_dir = os.path.join(os.path.dirname(__file__), "themes")
        base_tpl = os.path.join(templates_dir, "base_theme.qss")
        qss = None
        if os.path.exists(base_tpl):
            qss = ThemeManager.render_qss(base_tpl, path)
        if not qss:
            # fallback to raw content
            qss = ThemeManager.read_file(path)

        if not qss:
            QMessageBox.warning(self, "Theme error", f"Failed to load theme: {os.path.basename(path)}")
            return

        app = QApplication.instance()
        if not app:
            QMessageBox.warning(self, "Theme error", "QApplication instance not available")
            return

        # Apply stylesheet globally and reapply UI scale so fonts remain as set by user
        app.setStyleSheet(qss)
        self.current_theme = path
        
        # Reapply zoom so messages and other font sizes don't reset when stylesheet changes
        try:
            self.apply_zoom()
        except Exception:
            pass
        
        # Redraw all messages to recalculate username colors for new theme
        try:
            self.redraw_messages_for_theme()
        except Exception:
            pass

        # Persist selection relative to themes/ directory
        rel = os.path.relpath(path, templates_dir)
        cfg = ThemeManager.load_config()
        ui = cfg.get("ui", {})
        ui["selected_palette"] = rel.replace("\\", "/")
        cfg["ui"] = ui
        ThemeManager.save_config(cfg)

        # Refresh theme menus so checkmarks update
        try:
            if hasattr(self, "refresh_theme_menus"):
                self.refresh_theme_menus()
        except Exception:
            pass

    def redraw_messages_for_theme(self):
        """Redraw all messages to recalculate username colors for the current theme."""
        if not self.message_history:
            return
        
        # Save scroll state
        scrollbar = self.messages_display.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        
        # Clear display
        self.messages_display.clear()
        self.messages_display.clear_username_ranges()
        
        # Redraw all messages with new theme colors
        for sender, text, timestamp, color in self.message_history:
            self._add_message_internal(sender, text, timestamp, color)
        
        # Restore scroll position
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
    
    def _add_message_internal(self, sender, text, timestamp="", color=None):
        """Internal method to add a message without storing in history."""
        # Block signals to prevent any interference
        self.messages_display.blockSignals(True)
        
        # Get cursor and move to end
        cursor = self.messages_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Only add newline if there's already content
        if not self.messages_display.document().isEmpty():
            cursor.insertText("\n")
        
        sender_html = html.escape(sender)
        text_html = html.escape(text)

        # Calculate emoji size (30% larger than base text)
        f = self.zoom_level / 100.0
        base_size = 13
        scaled_size = int(base_size * f)
        emoji_size = int(scaled_size * 1.3)

        # Add timestamp (styled by QSS)
        if timestamp:
            cursor.insertHtml(f'<span class="timestamp">{timestamp}</span> ')
        
        # Add username as clickable styled text
        # Apply user's custom color if provided, with contrast boosting
        username_start = cursor.position()
        if color:
            # Boost color contrast against background for readability
            try:
                from color_utils import ensure_contrast
                # Get current theme background color for contrast calculation
                palette = {}
                try:
                    palette = ThemeManager.parse_palette(self.current_theme) if self.current_theme else {}
                except Exception:
                    palette = {}
                bg_color = palette.get('bg') or '#000000'
                boosted_color = ensure_contrast(color, bg_color, min_ratio=4.5)
                cursor.insertHtml(f'<span class="username" style="color: {boosted_color};">{sender_html}</span> ')
            except Exception:
                # Fallback to original color if boosting fails
                cursor.insertHtml(f'<span class="username" style="color: {color};">{sender_html}</span> ')
        else:
            cursor.insertHtml(f'<span class="username">{sender_html}</span> ')
        username_end = cursor.position()
        
        # Register the username position for click detection
        self.messages_display.add_username_range(username_start, username_end, sender)
        
        # Process message text to make emojis larger
        # Use the preferred UI font for message text and explicitly wrap emoji characters
        # in spans that force the Noto Color Emoji font (so non-avatar emoji use it)
        emoji_display_size = scaled_size * 2  # make emojis three times larger than base text

        # Helper to detect emoji characters using common Unicode ranges
        def is_emoji(ch):
            o = ord(ch)
            ranges = [
                (0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs
                (0x1F600, 0x1F64F),  # Emoticons
                (0x1F680, 0x1F6FF),  # Transport & Map
                (0x2600, 0x26FF),    # Misc symbols
                (0x2700, 0x27BF),    # Dingbats
                (0x1F900, 0x1F9FF),  # Supplemental Symbols and Pictographs
                (0x1FA70, 0x1FAFF),  # Symbols & Pictographs Extended-A
                (0x1F1E6, 0x1F1FF),  # Regional indicator symbols (flags)
            ]
            return any(start <= o <= end for start, end in ranges)

        # Build HTML where emoji characters are wrapped with an explicit Noto Color Emoji span
        parts = []
        for ch in text:
            if is_emoji(ch):
                parts.append(
                    f"<span class=\"emoji\" style=\"font-family: 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI Emoji'; font-size: {emoji_display_size}px; line-height: 1; vertical-align: middle;\">{html.escape(ch)}</span>"
                )
            else:
                parts.append(html.escape(ch))

        pf = (self.preferred_font_family if getattr(self, 'preferred_font_family', '') else 'sans-serif')
        message_html = (
            f'<span class="message-text" style="font-family: {pf}, \'Noto Color Emoji\', \'Apple Color Emoji\', \'Segoe UI Emoji\'; font-size: {scaled_size}px;">'
            + ''.join(parts) + '</span>'
        )
        cursor.insertHtml(message_html)
        
        # Set the cursor back to the document
        self.messages_display.setTextCursor(cursor)
        
        # Restore signals
        self.messages_display.blockSignals(False)



def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = ChatWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
"""Chatlog parser configuration UI"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, QDate, Qt
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from components.button import create_icon_button
from components.tag_button import SavedValuesBar
from helpers.dates import parse_short_date
from helpers.fonts.fonts import FontType, get_font
from helpers.translate import on_language_changed, tr, TranslatableMixin
from ui.chatlog.parser_modes import ParserModesMixin
from ui.chatlog.parser_modes_data import MODE_KEYS, MODE_LABELS
from ui.chatlog.parser_run import ParserRunMixin
from ui.chatlog.parser_usernames import ParserUsernamesMixin


class ChatlogsParserConfigWidget(ParserModesMixin, ParserRunMixin, ParserUsernamesMixin, TranslatableMixin, QWidget):
    """Configuration widget for chatlog parser"""

    parse_started = pyqtSignal(object) # ParseConfig
    parse_cancelled = pyqtSignal()

    def __init__(self, config, icons_path: Path, account=None):
        super().__init__()
        self.init_translatable()
        self.config = config
        self.icons_path = icons_path
        self.account = account
        self.is_parsing = False
        self.is_fetching_username = False
        self.is_fetching_search = False
        self.original_usernames = []
        self.is_sync_mode = False

        self._setup_ui()

    def set_account(self, account):
        """Set account for auto-populating mention usernames"""
        self.account = account
        self.update_mention_label()

    def create_label(self, text: str) -> QLabel:
        """Create a label with consistent height and alignment"""
        label = QLabel(text)
        label.setFixedHeight(self.input_height)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        return label

    def _create_input(self, placeholder: str = "", object_name: str = "") -> QLineEdit:
        """Create an input field with consistent height"""
        input_field = QLineEdit()
        if placeholder:
            input_field.setPlaceholderText(placeholder)
        if object_name:
            input_field.setObjectName(object_name)
        input_field.setFixedHeight(self.input_height)
        input_field.setFont(get_font(FontType.UI))
        return input_field

    def create_input_row(self, label_text: str, placeholder: str = "", object_name: str = "", as_widget: bool = False):
        """Create a complete input row with label and input field"""
        layout = QHBoxLayout()
        layout.setSpacing(self.spacing)

        label = self.create_label(label_text)
        layout.addWidget(label)

        input_field = self._create_input(placeholder, object_name)
        layout.addWidget(input_field, stretch=1)

        if as_widget:
            container = QWidget()
            container.setLayout(layout)
            return container, input_field

        return layout, input_field

    def auto_format_date(self, input_field):
        """Auto-format dates on blur"""
        text = input_field.text().strip()
        if not text:
            return
        parts = [parse_short_date(p) for p in text.split()]
        if parts:
            input_field.setText(' '.join(parts))

    def show_date_picker(self, input_field, calendar_button):
        """Show calendar picker"""
        calendar = QCalendarWidget()
        calendar.setWindowFlags(Qt.WindowType.Popup)
        calendar.setGridVisible(True)
        calendar.setMaximumDate(QDate.currentDate())
        calendar.setMinimumDate(QDate(2012, 12, 2))

        try:
            date_str = input_field.text().split()[0]
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            calendar.setSelectedDate(QDate(date.year, date.month, date.day))
        except Exception:
            calendar.setSelectedDate(QDate.currentDate())

        calendar.clicked.connect(lambda d: (
            input_field.setText(d.toPyDate().strftime('%Y-%m-%d')),
            calendar.close()
        ))

        # Position calendar relative to button
        button_pos = calendar_button.mapToGlobal(calendar_button.rect().bottomRight())
        x = button_pos.x() - calendar.sizeHint().width()
        y = button_pos.y() + (self.config.get("ui", "spacing", "widget_elements") or 6)
        calendar.move(x, y)
        calendar.show()

    def _setup_ui(self):
        margin = self.config.get("ui", "margins", "widget") or 5
        spacing = self.config.get("ui", "spacing", "widget_elements") or 6
        self.spacing = spacing
        self.input_height = self.config.get("ui", "input_height") or 48

        layout = QVBoxLayout()
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(self.spacing)
        self.setLayout(layout)

        # Mode selection
        mode_container = QWidget()
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(self.spacing)
        mode_label = self.create_label(tr("Mode:", "Режим:"))
        self._mode_label = mode_label
        mode_layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.setFixedHeight(self.input_height)
        self.mode_combo.setFont(get_font(FontType.UI))
        for key in MODE_KEYS:
            en, ru = MODE_LABELS[key]
            self.mode_combo.addItem(tr(en, ru), key)
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo, stretch=1)
        mode_container.setLayout(mode_layout)
        layout.addWidget(mode_container)

        # Date inputs (dynamic based on mode)
        self._date_container = QWidget()
        self.date_layout = QVBoxLayout()
        self.date_layout.setContentsMargins(0, 0, 0, 0)
        self.date_layout.setSpacing(self.spacing)
        self._date_container.setLayout(self.date_layout)
        layout.addWidget(self._date_container)

        # Username input with fetch history button (label changes in Personal Mentions mode)
        username_container = QWidget()
        username_layout, self.username_input = self.create_input_row(
            tr("Usernames:", "Имена:"),
            tr("comma-separated (leave empty for all users)", "через запятую (пусто = все пользователи)")
        )

        # Get reference to the label that was created
        self.username_label = username_layout.itemAt(0).widget()

        # Connect to enable/disable fetch button based on input
        self.username_input.textChanged.connect(self.update_buttons_state)
        self.username_input.textChanged.connect(self.update_mention_label)

        # Fetch history button
        self.fetch_history_button = create_icon_button(
            self.icons_path, "fill/user-received-2-fill.svg", "",
            size_type="large", config=self.config
        )
        self.tr_set(self.fetch_history_button.setToolTip, "Fetch username history", "Загрузить историю имён")
        self.fetch_history_button.clicked.connect(lambda: self.fetch_username_history(self.username_input))
        self.fetch_history_button.setEnabled(False)
        username_layout.addWidget(self.fetch_history_button)

        # Add current usernames to the saved chips (not just after a successful parse)
        self.add_username_button = create_icon_button(
            self.icons_path, "line/add-large-line.svg", "",
            size_type="large", config=self.config
        )
        self.tr_set(self.add_username_button.setToolTip, "Add to saved usernames", "Добавить в сохранённые имена")
        self.add_username_button.clicked.connect(self.add_usernames_to_saved)
        self.add_username_button.setEnabled(False)
        username_layout.addWidget(self.add_username_button)

        username_container.setLayout(username_layout)
        self.username_container_widget = username_container
        layout.addWidget(username_container)

        # Saved usernames quick-access chips (loaded from/persisted to config)
        self.saved_usernames_bar = SavedValuesBar(self.config, ("chatlog_parser", "saved_usernames"), self.icons_path)
        self.saved_usernames_bar.value_selected.connect(self._on_saved_username_clicked)
        self.saved_usernames_bar.value_double_clicked.connect(self._on_saved_username_double_clicked)
        layout.addWidget(self.saved_usernames_bar)

        # Search terms input (label changes in Personal Mentions mode)
        search_container = QWidget()
        search_layout, self.search_input = self.create_input_row(
            tr("Search:", "Поиск:"),
            tr("comma-separated search terms (leave empty for all messages)", "термины через запятую (пусто = все сообщения)")
        )

        # Get reference to the label that was created
        self.search_label = search_layout.itemAt(0).widget()

        # Connect to update mention label and fetch button state
        self.search_input.textChanged.connect(self.update_mention_label)
        self.search_input.textChanged.connect(self.update_buttons_state)

        # Fetch history button for search/mentions field
        self.search_fetch_history_button = create_icon_button(
            self.icons_path, "fill/user-received-2-fill.svg", "",
            size_type="large", config=self.config
        )
        self.tr_set(self.search_fetch_history_button.setToolTip, "Fetch username history", "Загрузить историю имён")
        self.search_fetch_history_button.clicked.connect(lambda: self.fetch_username_history(self.search_input))
        self.search_fetch_history_button.setEnabled(False)
        search_layout.addWidget(self.search_fetch_history_button)

        search_container.setLayout(search_layout)
        self.search_container_widget = search_container
        layout.addWidget(search_container)

        # Mention label (only for personal mentions mode)
        self.mention_label_widget = QLabel()
        self.mention_label_widget.setWordWrap(True)
        self.mention_label_widget.setStyleSheet("color: #888; padding: 4px;")
        self.mention_label_widget.setVisible(False)
        layout.addWidget(self.mention_label_widget)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Progress label
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # Buttons row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(self.config.get("ui", "buttons", "spacing") or 8)

        self.parse_button = create_icon_button(
            self.icons_path, "fill/play-large-fill.svg", "",
            size_type="large", config=self.config
        )
        self.tr_set(self.parse_button.setToolTip, "Start parsing (S)", "Начать парсинг (S)")
        self.parse_button.clicked.connect(self.on_parse_clicked)
        button_layout.addWidget(self.parse_button)

        # Copy button (initially hidden)
        self.copy_button = create_icon_button(
            self.icons_path, "fill/clipboard-fill.svg", "",
            size_type="large", config=self.config
        )
        self.tr_set(self.copy_button.setToolTip, "Copy results to clipboard (Ctrl+C)", "Копировать результаты в буфер (Ctrl+C)")
        self.copy_button.clicked.connect(self.on_copy_clicked)
        self.copy_button.setVisible(False)
        button_layout.addWidget(self.copy_button)

        # Save button (initially hidden)
        self.save_button = create_icon_button(
            self.icons_path, "fill/save-2-fill.svg", "",
            size_type="large", config=self.config
        )
        self.tr_set(self.save_button.setToolTip, "Save results to file (Ctrl+S)", "Сохранить результаты в файл (Ctrl+S)")
        self.save_button.clicked.connect(self.on_save_clicked)
        self.save_button.setVisible(False)
        button_layout.addWidget(self.save_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Add stretch to push everything to the top
        layout.addStretch()

        # Initialize with first mode
        self.on_mode_changed(0)
        on_language_changed(self._retranslate)

    def _retranslate(self, _code=None):
        self.retranslate_all()
        # Refresh mode combo labels
        for i, key in enumerate(MODE_KEYS):
            en, ru = MODE_LABELS[key]
            self.mode_combo.setItemText(i, tr(en, ru))
        if hasattr(self, "_mode_label"):
            self._mode_label.setText(tr("Mode:", "Режим:"))
        # Re-apply mode UI to refresh dynamic labels
        self.on_mode_changed(self.mode_combo.currentIndex())

    def update_buttons_state(self):
        """Enable/disable the fetch and add buttons based on inputs"""
        has_username = bool(self.username_input.text().strip())
        has_search = bool(self.search_input.text().strip())
        self.fetch_history_button.setEnabled(has_username and not self.is_fetching_username)
        self.add_username_button.setEnabled(has_username)
        self.search_fetch_history_button.setEnabled(has_search and not self.is_fetching_search)

    def _on_saved_username_clicked(self, username: str):
        """Add a saved username chip into the usernames field"""
        current = self.get_usernames()
        if username not in current:
            current.append(username)
            self.username_input.setText(', '.join(current))

    def _on_saved_username_double_clicked(self, username: str):
        """Replace the usernames field with only the double-clicked chip,
        or clear it if that chip was already the sole entry"""
        current = self.get_usernames()
        self.username_input.setText("" if current == [username] else username)

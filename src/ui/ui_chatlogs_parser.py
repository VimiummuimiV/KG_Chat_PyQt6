"""Chatlog parser configuration UI"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QProgressBar, QTextEdit, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from helpers.create import create_icon_button
from core.api_data import get_exact_user_id_by_name, get_usernames_history, get_registration_date
from core.chatlogs_parser import ParseConfig, ChatlogsParserEngine


class ParserWorker(QThread):
    """Worker thread for parsing"""
    progress = pyqtSignal(str, str, int) # start_date, current_date, percent
    messages_found = pyqtSignal(list, str) # messages, date
    finished = pyqtSignal(list) # all messages
    error = pyqtSignal(str)
    
    def __init__(self, config: ParseConfig):
        super().__init__()
        self.config = config
        self.engine = ChatlogsParserEngine()
    
    def run(self):
        try:
            messages = self.engine.parse(
                self.config,
                progress_callback=self.progress.emit,
                message_callback=self.messages_found.emit
            )
            self.finished.emit(messages)
        except Exception as e:
            self.error.emit(str(e))
    
    def stop(self):
        self.engine.stop()


class ChatlogsParserConfigWidget(QWidget):
    """Configuration widget for chatlog parser"""
    
    parse_started = pyqtSignal(object) # ParseConfig
    parse_cancelled = pyqtSignal()
    
    def __init__(self, config, icons_path: Path):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.is_parsing = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        margin = self.config.get("ui", "margins", "widget") or 5
        spacing = self.config.get("ui", "spacing", "widget_elements") or 6
        self.spacing = spacing
        
        layout = QVBoxLayout()
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(self.spacing)
        self.setLayout(layout)
        
        # Title
        title = QLabel("Parse Chat Logs")
        title_font = QFont(self.config.get("ui", "font_family"), self.config.get("ui", "font_size") + 4)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Mode selection
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(self.spacing)
        mode_label = QLabel("Mode:")
        mode_layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Single Date",
            "From Date",
            "Date Range",
            "From Start",
            "From Registered",
            "Personal Mentions"
        ])
        self.mode_combo.setFixedHeight(self.config.get("ui", "input_height") or 48)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo, stretch=1)
        layout.addLayout(mode_layout)
        
        # Date inputs (dynamic based on mode)
        self.date_container = QWidget()
        self.date_layout = QVBoxLayout()
        self.date_layout.setContentsMargins(0, 0, 0, 0)
        self.date_layout.setSpacing(self.spacing)
        self.date_container.setLayout(self.date_layout)
        layout.addWidget(self.date_container)
        
        # Username input
        username_layout = QHBoxLayout()
        username_layout.setSpacing(self.spacing)
        username_label = QLabel("Usernames:")
        username_layout.addWidget(username_label)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("comma-separated (leave empty for all users)")
        self.username_input.setFixedHeight(self.config.get("ui", "input_height") or 48)
        username_layout.addWidget(self.username_input, stretch=1)
        
        self.fetch_history_checkbox = QCheckBox("Username history")
        self.fetch_history_checkbox.setToolTip("Automatically fetch previous usernames")
        username_layout.addWidget(self.fetch_history_checkbox)
        
        layout.addLayout(username_layout)
        
        # Search terms input
        search_layout = QHBoxLayout()
        search_layout.setSpacing(self.spacing)
        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("comma-separated search terms (leave empty for all messages)")
        self.search_input.setFixedHeight(self.config.get("ui", "input_height") or 48)
        search_layout.addWidget(self.search_input, stretch=1)
        layout.addLayout(search_layout)
        
        # Mention keywords (only for personal mentions mode)
        self.mention_container = QWidget()
        mention_layout = QHBoxLayout()
        mention_layout.setContentsMargins(0, 0, 0, 0)
        mention_layout.setSpacing(self.spacing)
        mention_label = QLabel("Mentions:")
        mention_layout.addWidget(mention_label)
        
        self.mention_input = QLineEdit()
        self.mention_input.setPlaceholderText("comma-separated keywords to search for")
        self.mention_input.setFixedHeight(self.config.get("ui", "input_height") or 48)
        mention_layout.addWidget(self.mention_input, stretch=1)
        self.mention_container.setLayout(mention_layout)
        self.mention_container.setVisible(False)
        layout.addWidget(self.mention_container)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Progress label
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(self.config.get("ui", "buttons", "spacing") or 8)
        
        self.parse_button = create_icon_button(
            self.icons_path, "play.svg", "Start parsing",
            size_type="large", config=self.config
        )
        self.parse_button.clicked.connect(self._on_parse_clicked)
        button_layout.addWidget(self.parse_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Initialize with first mode
        self._on_mode_changed(0)
    
    def _on_mode_changed(self, index: int):
        """Update UI based on selected mode"""
        # Clear existing date inputs
        while self.date_layout.count():
            item = self.date_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        mode = self.mode_combo.currentText()
        
        # Show/hide mention keywords based on mode
        self.mention_container.setVisible(mode == "Personal Mentions")
        
        # Create date inputs based on mode
        if mode == "Single Date":
            self._add_date_input("Date:", "single_date", "YYYY-MM-DD")
        
        elif mode == "From Date":
            self._add_date_input("From:", "from_date", "YYYY-MM-DD")
            info = QLabel("(to today)")
            info.setStyleSheet("color: #888;")
            self.date_layout.addWidget(info)
        
        elif mode == "Date Range":
            self._add_date_input("Range:", "range_dates", "YYYY-MM-DD YYYY-MM-DD")
        
        elif mode == "From Start":
            info = QLabel("Will parse from 2012-02-12 to today")
            info.setStyleSheet("color: #888;")
            self.date_layout.addWidget(info)
        
        elif mode == "From Registered":
            info = QLabel("Will use registration date of entered user(s)")
            info.setStyleSheet("color: #888;")
            self.date_layout.addWidget(info)
        
        elif mode == "Personal Mentions":
            sub_mode_layout = QHBoxLayout()
            sub_mode_layout.setSpacing(self.spacing)
            sub_mode_label = QLabel("Date Mode:")
            sub_mode_layout.addWidget(sub_mode_label)
            
            self.mention_date_combo = QComboBox()
            self.mention_date_combo.addItems([
                "Single Date",
                "From Date",
                "Date Range",
                "From Start",
                "Last N Days"
            ])
            self.mention_date_combo.setFixedHeight(self.config.get("ui", "input_height") or 48)
            self.mention_date_combo.currentIndexChanged.connect(self._on_mention_date_mode_changed)
            sub_mode_layout.addWidget(self.mention_date_combo, stretch=1)
            
            container = QWidget()
            container.setLayout(sub_mode_layout)
            self.date_layout.addWidget(container)
            
            # Initialize with first sub-mode
            self._on_mention_date_mode_changed(0)
    
    def _on_mention_date_mode_changed(self, index: int):
        """Update date inputs for personal mentions sub-mode"""
        # Remove existing inputs (except the sub-mode selector)
        while self.date_layout.count() > 1:
            item = self.date_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        
        sub_mode = self.mention_date_combo.currentText()
        
        if sub_mode == "Single Date":
            self._add_date_input("Date:", "mention_single_date", "YYYY-MM-DD")
        elif sub_mode == "From Date":
            self._add_date_input("From:", "mention_from_date", "YYYY-MM-DD")
        elif sub_mode == "Date Range":
            self._add_date_input("Range:", "mention_range_dates", "YYYY-MM-DD YYYY-MM-DD")
        elif sub_mode == "From Start":
            pass # No input needed
        elif sub_mode == "Last N Days":
            days_layout = QHBoxLayout()
            days_layout.setSpacing(self.spacing)
            days_label = QLabel("Days:")
            days_layout.addWidget(days_label)
            
            self.days_input = QLineEdit()
            self.days_input.setPlaceholderText("7")
            self.days_input.setText("7")
            self.days_input.setFixedHeight(self.config.get("ui", "input_height") or 48)
            days_layout.addWidget(self.days_input, stretch=1)
            
            container = QWidget()
            container.setLayout(days_layout)
            self.date_layout.addWidget(container)
    
    def _add_date_input(self, label_text: str, obj_name: str, placeholder: str = "YYYY-MM-DD"):
        """Add a date input field"""
        layout = QHBoxLayout()
        layout.setSpacing(self.spacing)
        label = QLabel(label_text)
        layout.addWidget(label)
        
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        line_edit.setObjectName(obj_name)
        line_edit.setFixedHeight(self.config.get("ui", "input_height") or 48)
        layout.addWidget(line_edit, stretch=1)
        
        container = QWidget()
        container.setLayout(layout)
        self.date_layout.addWidget(container)
    
    def _on_parse_clicked(self):
        """Handle parse button click"""
        if self.is_parsing:
            # Stop parsing
            self._cancel_parsing()
        else:
            # Start parsing
            self._start_parsing()
    
    def _start_parsing(self):
        """Validate inputs and start parsing"""
        try:
            config = self._build_parse_config()
            if not config:
                return
            
            # Update UI for parsing state
            self.is_parsing = True
            self.parse_button.setIcon(create_icon_button(self.icons_path, "stop.svg", "Stop parsing", config=self.config).icon())
            self.parse_button.setToolTip("Stop parsing")
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_label.setVisible(True)
            self.progress_label.setText(f"{config.from_date} - {config.from_date} | 0%") # Initialize
            
            # Emit signal
            self.parse_started.emit(config)
            
        except Exception as e:
            print(f"Error starting parse: {e}")
            self._reset_ui()
    
    def _cancel_parsing(self):
        """Cancel parsing"""
        self.parse_cancelled.emit()
        self._reset_ui()
    
    def _reset_ui(self):
        """Reset UI to non-parsing state"""
        self.is_parsing = False
        self.parse_button.setIcon(create_icon_button(self.icons_path, "play.svg", "Start parsing", config=self.config).icon())
        self.parse_button.setToolTip("Start parsing")
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.progress_label.setText("")
    
    def update_progress(self, start_date: str, current_date: str, percent: int):
        """Update progress display"""
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"{start_date} - {current_date} | {percent}%")
    
    def _build_parse_config(self) -> Optional[ParseConfig]:
        """Build ParseConfig from UI inputs"""
        mode = self.mode_combo.currentText()
        
        # Get dates based on mode
        from_date = None
        to_date = None
        
        if mode == "Single Date":
            date_input = self.findChild(QLineEdit, "single_date")
            if not date_input or not date_input.text().strip():
                print("Please enter a date")
                return None
            from_date = to_date = date_input.text().strip()
        
        elif mode == "From Date":
            date_input = self.findChild(QLineEdit, "from_date")
            if not date_input or not date_input.text().strip():
                print("Please enter from date")
                return None
            from_date = date_input.text().strip()
            to_date = datetime.now().strftime('%Y-%m-%d')
        
        elif mode == "Date Range":
            range_input = self.findChild(QLineEdit, "range_dates")
            if not range_input or not range_input.text().strip():
                print("Please enter date range in format YYYY-MM-DD YYYY-MM-DD")
                return None
            dates = range_input.text().strip().split()
            if len(dates) != 2:
                print("Invalid range format - use YYYY-MM-DD YYYY-MM-DD")
                return None
            from_date, to_date = dates
        
        elif mode == "From Start":
            from_date = "2012-02-12"
            to_date = datetime.now().strftime('%Y-%m-%d')
        
        elif mode == "From Registered":
            # Get registration date from usernames
            usernames = self._get_usernames()
            if not usernames:
                print("Please enter at least one username")
                return None
            
            # Fetch registration dates (synchronous - might want to make async)
            reg_dates = []
            for username in usernames:
                reg_date = get_registration_date(username)
                if reg_date:
                    reg_dates.append(reg_date)
            
            if not reg_dates:
                print("Could not get registration date")
                return None
            
            from_date = min(reg_dates)
            to_date = datetime.now().strftime('%Y-%m-%d')
        
        elif mode == "Personal Mentions":
            sub_mode = self.mention_date_combo.currentText()
            
            if sub_mode == "Single Date":
                date_input = self.findChild(QLineEdit, "mention_single_date")
                if not date_input or not date_input.text().strip():
                    print("Please enter a date")
                    return None
                from_date = to_date = date_input.text().strip()
            
            elif sub_mode == "From Date":
                date_input = self.findChild(QLineEdit, "mention_from_date")
                if not date_input or not date_input.text().strip():
                    print("Please enter from date")
                    return None
                from_date = date_input.text().strip()
                to_date = datetime.now().strftime('%Y-%m-%d')
            
            elif sub_mode == "Date Range":
                range_input = self.findChild(QLineEdit, "mention_range_dates")
                if not range_input or not range_input.text().strip():
                    print("Please enter date range in format YYYY-MM-DD YYYY-MM-DD")
                    return None
                dates = range_input.text().strip().split()
                if len(dates) != 2:
                    print("Invalid range format - use YYYY-MM-DD YYYY-MM-DD")
                    return None
                from_date, to_date = dates
            
            elif sub_mode == "From Start":
                from_date = "2012-02-12"
                to_date = datetime.now().strftime('%Y-%m-%d')
            
            elif sub_mode == "Last N Days":
                if not hasattr(self, 'days_input') or not self.days_input.text().strip():
                    print("Please enter number of days")
                    return None
                try:
                    days = int(self.days_input.text().strip())
                    if days <= 0:
                        print("Days must be positive")
                        return None
                    to_date = datetime.now().date()
                    from_date = to_date - timedelta(days=days-1)
                    from_date = from_date.strftime('%Y-%m-%d')
                    to_date = to_date.strftime('%Y-%m-%d')
                except ValueError:
                    print("Invalid number of days")
                    return None
        
        # Get usernames and search terms
        usernames = self._get_usernames()
        search_terms = self._get_search_terms()
        
        # Get mention keywords (for personal mentions mode)
        mention_keywords = []
        if mode == "Personal Mentions":
            mention_text = self.mention_input.text().strip()
            if mention_text:
                mention_keywords = [kw.strip() for kw in mention_text.split(',') if kw.strip()]
        
        # Build config
        config = ParseConfig(
            mode=mode.lower().replace(' ', ''),
            from_date=from_date,
            to_date=to_date,
            usernames=usernames,
            search_terms=search_terms,
            mention_keywords=mention_keywords
        )
        
        return config
    
    def _get_usernames(self) -> List[str]:
        """Get and optionally expand usernames with history"""
        text = self.username_input.text().strip()
        if not text:
            return []
        
        usernames = [u.strip() for u in text.split(',') if u.strip()]
        
        if self.fetch_history_checkbox.isChecked() and usernames:
            # Fetch history for all usernames
            expanded = set(usernames)
            for username in usernames:
                history = get_usernames_history(username)
                expanded.update(history)
            return sorted(expanded)
        
        return usernames
    
    def _get_search_terms(self) -> List[str]:
        """Get search terms"""
        text = self.search_input.text().strip()
        if not text:
            return []
        return [term.strip() for term in text.split(',') if term.strip()]
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget
)
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, QSize

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initializeUI()

    def initializeUI(self):
        self.setWindowTitle("KG General Chat")
        self.setGeometry(100, 100, 800, 600)
        app_font = QFont("Montserrat", 16)
        self.setFont(app_font)

        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # Left layout: messages + input
        left_layout = QVBoxLayout()
        main_layout.addLayout(left_layout, stretch=3)

        # Messages (now using QListWidget, same as userlist)
        self.messages_area = QListWidget()
        self.messages_area.setFont(app_font)
        left_layout.addWidget(self.messages_area, stretch=1)

        # Input layout
        input_layout = QHBoxLayout()
        left_layout.addLayout(input_layout)

        self.input_field = QLineEdit()
        self.input_field.setFont(app_font)
        self.input_field.setFixedHeight(48)
        self.input_field.setStyleSheet("padding: 0 10px;")
        input_layout.addWidget(self.input_field, stretch=1)

        # Send button with SVG icon from icons folder
        self.send_button = QPushButton()
        icon_path = Path(__file__).parent / "icons" / "send-message.svg"
        self.send_button.setIcon(QIcon(str(icon_path)))
        self.send_button.setIconSize(QSize(32, 32))
        self.send_button.setFixedSize(48, 48)
        input_layout.addWidget(self.send_button)

        # Right: full height user list (empty)
        self.user_list = QListWidget()
        self.user_list.setFont(app_font)
        main_layout.addWidget(self.user_list, stretch=1)

        # Signals
        self.send_button.clicked.connect(self.send_message)
        self.input_field.returnPressed.connect(self.send_message)

        self.show()

    def send_message(self):
        text = self.input_field.text().strip()
        if text:
            self.messages_area.addItem(f"You: {text}")
            self.input_field.clear()
            self.messages_area.scrollToBottom()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())
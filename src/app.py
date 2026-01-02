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
    
    def create_icon_button(self, icon_name, icon_size=30, button_size=48):
        button = QPushButton()
        icon_path = Path(__file__).parent / "icons" / icon_name
        button.setIcon(QIcon(str(icon_path)))
        button.setIconSize(QSize(icon_size, icon_size))
        button.setFixedSize(button_size, button_size)
        return button

    def initializeUI(self):
        self.setWindowTitle("KG General Chat")
        self.resize(1500, 800)
        app_font = QFont("Montserrat", 16)
        self.setFont(app_font)

        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # Left layout: messages + input
        left_layout = QVBoxLayout()
        main_layout.addLayout(left_layout, stretch=3)

        # Messages
        self.messages_area = QListWidget()
        self.messages_area.setFont(app_font)
        left_layout.addWidget(self.messages_area, stretch=1)

        # Input
        input_layout = QHBoxLayout()
        left_layout.addLayout(input_layout)

        self.input_field = QLineEdit()
        self.input_field.setFont(app_font)
        self.input_field.setFixedHeight(48)
        self.input_field.setStyleSheet("padding: 0 10px;")
        input_layout.addWidget(self.input_field, stretch=1)

        # Send message button
        self.send_button = self.create_icon_button("send.svg")
        input_layout.addWidget(self.send_button)

        # Toggle user list button
        self.toggle_userlist_button = self.create_icon_button("user.svg")
        input_layout.addWidget(self.toggle_userlist_button)

        # Right layout: user list
        self.user_list = QListWidget()
        self.user_list.setFont(app_font)
        main_layout.addWidget(self.user_list, stretch=1)

        # Signals
        self.toggle_userlist_button.clicked.connect(self.toggle_user_list)
        
        self.show()
    
    def toggle_user_list(self):
        self.user_list.setVisible(not self.user_list.isVisible())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())
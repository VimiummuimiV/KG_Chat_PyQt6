from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect
from PyQt6.QtGui import QGuiApplication


class PopupNotification(QWidget):
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("popup_notification")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("popup_title")

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("popup_message")

        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)

        self._position()
        self._animate_in()

        # Auto close
        QTimer.singleShot(4000, self.close)

    def _position(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()

        width = min(int(screen.width() * 0.8), 900)
        height = self.sizeHint().height()

        x = screen.x() + (screen.width() - width) // 2
        y = screen.y() + 20  # top margin

        self.setGeometry(x, y, width, height)

    def _animate_in(self):
        start_rect = self.geometry()
        start_rect.moveTop(start_rect.top() - 20)

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(200)
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(self.geometry())
        self.anim.start()

    def mousePressEvent(self, event):
        self.close()
        if self.parent():
            self.parent().raise_()
            self.parent().activateWindow()
